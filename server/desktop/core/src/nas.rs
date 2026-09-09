use crate::{storage::Profile, Result};
use futures_util::StreamExt;
use reqwest::{Client, Method};
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::Duration,
};
use tokio_util::sync::CancellationToken;
use url::Url;

const MAX_BODY: usize = 16 * 1024 * 1024;

pub fn endpoint(value: &str) -> Result<Url> {
    let url = Url::parse(value.trim()).map_err(|_| "NAS 地址无效".to_string())?;
    if !["http", "https"].contains(&url.scheme())
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
        || url.path() != "/"
    {
        return Err("请输入 http(s)://主机:端口，不含密码、路径或查询参数".into());
    }
    Ok(url)
}
pub fn request_url(base: &Url, path: &str) -> Result<Url> {
    let route = path.split('?').next().unwrap_or_default();
    if path.len() > 8192
        || !route.starts_with("/api/")
        || route.contains('%')
        || route.contains('\\')
        || route.split('/').any(|v| v == "." || v == "..")
        || path.contains('#')
        || route.starts_with("/api/auth/")
        || path.chars().any(|c| c.is_control())
    {
        return Err("不允许的 NAS API 路径".into());
    }
    let url = base.join(path).map_err(|_| "请求路径无效".to_string())?;
    if url.origin() != base.origin() {
        return Err("不允许跨主机请求".into());
    }
    Ok(url)
}
fn client() -> Result<Client> {
    Client::builder()
        .cookie_store(true)
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(5))
        .pool_idle_timeout(Duration::from_secs(30))
        .no_proxy()
        .build()
        .map_err(|e| e.to_string())
}
fn network_error(error: reqwest::Error) -> String {
    let error = error.without_url();
    let mut details = vec![error.to_string()];
    let mut source = std::error::Error::source(&error);
    while let Some(cause) = source {
        details.push(cause.to_string());
        source = cause.source();
    }
    let detail = details.join("；");
    if cfg!(target_os = "macos") && detail.contains("os error 65") {
        return "macOS 无法访问此局域网地址。请检查路由及系统设置 → 隐私与安全 → 本地网络；临时签名测试包可能需要 Apple 开发者签名才能获得授权。（No route to host）".into();
    }
    format!("NAS 连接失败：{detail}")
}
fn credential(id: &str) -> Result<keyring::Entry> {
    keyring::Entry::new("cn.isle.traffic-lens", id).map_err(|_| "系统凭据库不可用".into())
}
pub fn forget_password(id: &str) -> Result<()> {
    match credential(id)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(_) => Err("无法清除系统凭据".into()),
    }
}

#[derive(Clone)]
struct Session {
    base: Url,
    client: Client,
}
#[derive(Default)]
pub struct NasClient {
    sessions: Mutex<HashMap<String, Session>>,
    pending: Mutex<HashMap<String, (String, CancellationToken)>>,
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ApiRequest {
    pub profile_id: String,
    pub request_id: String,
    pub path: String,
    pub method: String,
    pub body: Option<String>,
}
#[derive(Clone, Serialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum Packet {
    Headers { status: u16 },
    Chunk { bytes: Vec<u8> },
    Done,
}
struct PendingGuard<'a> {
    client: &'a NasClient,
    id: String,
}
impl Drop for PendingGuard<'_> {
    fn drop(&mut self) {
        self.client.pending.lock().unwrap().remove(&self.id);
    }
}

impl NasClient {
    async fn authenticate(profile: &Profile, secret: &str) -> Result<Session> {
        let base = endpoint(&profile.url)?;
        let client = client()?;
        let response = client
            .post(base.join("/api/auth/login").unwrap())
            .timeout(Duration::from_secs(15))
            .json(&serde_json::json!({"password":secret}))
            .send()
            .await
            .map_err(network_error)?;
        if !response.status().is_success() {
            return Err(format!("登录失败（HTTP {}）", response.status().as_u16()));
        }
        Ok(Session { base, client })
    }
    pub async fn login(
        &self,
        profile: Profile,
        password: Option<String>,
        remember: bool,
    ) -> Result<()> {
        self.disconnect(&profile.id);
        let secret = match password {
            Some(v) => v,
            None => credential(&profile.id)?
                .get_password()
                .map_err(|_| "未保存密码，请输入访问密码".to_string())?,
        };
        if secret.len() > 4096 {
            return Err("密码过长".into());
        }
        let session = Self::authenticate(&profile, &secret).await?;
        if remember {
            credential(&profile.id)?
                .set_password(&secret)
                .map_err(|_| "密码无法保存到系统凭据库".to_string())?;
        } else {
            forget_password(&profile.id)?;
        }
        self.sessions.lock().unwrap().insert(profile.id, session);
        Ok(())
    }
    pub fn disconnect(&self, id: &str) {
        self.sessions.lock().unwrap().remove(id);
        self.pause(id);
    }
    pub fn connected(&self) -> Vec<String> {
        self.sessions.lock().unwrap().keys().cloned().collect()
    }
    pub fn pause(&self, id: &str) {
        for (profile, token) in self.pending.lock().unwrap().values() {
            if profile == id {
                token.cancel();
            }
        }
    }
    pub async fn logout(&self, id: &str) -> Result<()> {
        let session = self.sessions.lock().unwrap().get(id).cloned();
        self.disconnect(id);
        if let Some(s) = session {
            s.client
                .post(s.base.join("/api/auth/logout").unwrap())
                .timeout(Duration::from_secs(5))
                .send()
                .await
                .map_err(|_| "远端退出失败，本机会话已清除".to_string())?;
        }
        Ok(())
    }
    pub fn cancel(&self, id: &str) {
        if let Some((_, t)) = self.pending.lock().unwrap().get(id) {
            t.cancel();
        }
    }
    pub async fn request<F>(&self, request: ApiRequest, send: F) -> Result<()>
    where
        F: Fn(Packet) -> Result<()> + Send,
    {
        let session = self
            .sessions
            .lock()
            .unwrap()
            .get(&request.profile_id)
            .cloned()
            .ok_or("请先登录此 NAS")?;
        let url = request_url(&session.base, &request.path)?;
        let method = match request.method.as_str() {
            "GET" => Method::GET,
            "POST" => Method::POST,
            "PUT" => Method::PUT,
            "DELETE" => Method::DELETE,
            "PATCH" => Method::PATCH,
            _ => return Err("不支持的请求方法".into()),
        };
        if request.body.as_ref().is_some_and(|b| b.len() > MAX_BODY) {
            return Err("请求超过 16 MiB 限制".into());
        }
        let token = CancellationToken::new();
        {
            let mut pending = self.pending.lock().unwrap();
            if pending.len() >= 24
                || request.request_id.len() > 64
                || pending.contains_key(&request.request_id)
            {
                return Err("请求过多或请求标识无效".into());
            }
            pending.insert(
                request.request_id.clone(),
                (request.profile_id.clone(), token.clone()),
            );
        }
        let _guard = PendingGuard {
            client: self,
            id: request.request_id,
        };
        let work = async {
            let mut builder = session.client.request(method, url);
            if let Some(body) = request.body {
                builder = builder
                    .header("Content-Type", "application/json")
                    .body(body);
            }
            let response = builder
                .send()
                .await
                .map_err(|_| "NAS 请求失败，请检查网络".to_string())?;
            if response.status().is_redirection() {
                return Err("NAS 返回了重定向，请使用最终服务地址".into());
            }
            if response
                .content_length()
                .is_some_and(|n| n > MAX_BODY as u64)
            {
                return Err("响应超过 16 MiB 限制".into());
            }
            send(Packet::Headers {
                status: response.status().as_u16(),
            })?;
            let mut stream = response.bytes_stream();
            let mut count = 0;
            while let Some(chunk) = tokio::time::timeout(Duration::from_secs(90), stream.next())
                .await
                .map_err(|_| "NAS 响应超时".to_string())?
            {
                let chunk = chunk.map_err(|_| "NAS 响应中断".to_string())?;
                count += chunk.len();
                if count > MAX_BODY {
                    return Err("响应超过 16 MiB 限制".into());
                }
                for bytes in chunk.chunks(32 * 1024) {
                    send(Packet::Chunk {
                        bytes: bytes.to_vec(),
                    })?;
                }
            }
            send(Packet::Done)
        };
        let timeout = if request.path.starts_with("/api/ai/") {
            600
        } else {
            20
        };
        tokio::select! {
            _=token.cancelled()=>Err("请求已取消".into()),
            result=tokio::time::timeout(Duration::from_secs(timeout),work)=>result.map_err(|_|"NAS 请求超时".to_string())?,
        }
    }
}

pub type SharedNas = Arc<NasClient>;

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::{
        io::{AsyncReadExt, AsyncWriteExt},
        net::TcpListener,
    };
    async fn server(responses: Vec<String>) -> (Profile, tokio::task::JoinHandle<Vec<String>>) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let profile = Profile {
            id: uuid::Uuid::new_v4().to_string(),
            name: "Mock".into(),
            url: format!("http://{}", listener.local_addr().unwrap()),
        };
        let task = tokio::spawn(async move {
            let mut requests = Vec::new();
            for response in responses {
                let (mut socket, _) = listener.accept().await.unwrap();
                let mut buffer = vec![0; 16384];
                let n = socket.read(&mut buffer).await.unwrap();
                requests.push(String::from_utf8_lossy(&buffer[..n]).to_string());
                socket.write_all(response.as_bytes()).await.unwrap();
            }
            requests
        });
        (profile, task)
    }
    fn reply(headers: &str, body: &str) -> String {
        format!(
            "HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: {}\r\n{headers}\r\n{body}",
            body.len()
        )
    }
    fn request(id: &str) -> ApiRequest {
        ApiRequest {
            profile_id: id.into(),
            request_id: uuid::Uuid::new_v4().to_string(),
            path: "/api/overview".into(),
            method: "GET".into(),
            body: None,
        }
    }
    #[tokio::test]
    async fn cookies_stay_in_their_profile_session() {
        let (a, ta) = server(vec![
            reply("Set-Cookie: session=only-a; Path=/; HttpOnly\r\n", "{}"),
            reply("", "{}"),
        ])
        .await;
        let (b, tb) = server(vec![reply("", "{}"), reply("", "{}")]).await;
        let client = NasClient::default();
        for p in [&a, &b] {
            let s = NasClient::authenticate(p, "synthetic-test").await.unwrap();
            client.sessions.lock().unwrap().insert(p.id.clone(), s);
        }
        for p in [&a, &b] {
            client.request(request(&p.id), |_| Ok(())).await.unwrap();
            client.pause(&p.id);
            assert!(client.connected().contains(&p.id));
        }
        let ar = ta.await.unwrap();
        let br = tb.await.unwrap();
        assert!(ar[1].to_lowercase().contains("cookie: session=only-a"));
        assert!(!br[1].to_lowercase().contains("cookie:"));
        assert!(client.pending.lock().unwrap().is_empty());
        client.disconnect(&a.id);
        assert_eq!(client.connected(), vec![b.id]);
    }
    #[tokio::test]
    async fn auth_failures_redirects_and_oversized_responses_are_rejected() {
        let (p, t) = server(vec![
            "HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n".into(),
        ])
        .await;
        assert!(NasClient::authenticate(&p, "synthetic-test").await.is_err());
        t.await.unwrap();
        for response in [
            "HTTP/1.1 302 Found\r\nLocation: http://example.invalid/\r\nContent-Length: 0\r\n\r\n"
                .into(),
            format!(
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n",
                MAX_BODY + 1
            ),
        ] {
            let (p, t) = server(vec![reply("", "{}"), response]).await;
            let c = NasClient::default();
            let s = NasClient::authenticate(&p, "").await.unwrap();
            c.sessions.lock().unwrap().insert(p.id.clone(), s);
            assert!(c.request(request(&p.id), |_| Ok(())).await.is_err());
            assert!(c.pending.lock().unwrap().is_empty());
            t.await.unwrap();
        }
    }
    #[tokio::test]
    async fn cancellation_removes_inflight_requests_and_disconnected_sessions() {
        let (p, t) = server(vec![
            reply("", "{}"),
            "HTTP/1.1 200 OK\r\nContent-Length: 99\r\n\r\n".into(),
        ])
        .await;
        let c = Arc::new(NasClient::default());
        let s = NasClient::authenticate(&p, "").await.unwrap();
        c.sessions.lock().unwrap().insert(p.id.clone(), s);
        let c2 = c.clone();
        let id = p.id.clone();
        let result = c
            .request(request(&p.id), move |packet| {
                if matches!(packet, Packet::Headers { .. }) {
                    c2.disconnect(&id);
                }
                Ok(())
            })
            .await;
        assert!(result.is_err());
        assert!(c.pending.lock().unwrap().is_empty());
        assert!(c.request(request(&p.id), |_| Ok(())).await.is_err());
        t.await.unwrap();
    }
}
