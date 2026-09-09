use serde_json::json;
use std::sync::Arc;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};
use traffic_lens_core::{
    ai::{AiPacket, AiService, AiSettings, AnalysisScope, ChatRequest},
    monitor::Monitor,
};

async fn provider(body: &'static str) -> (String, tokio::task::JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let task = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let mut data = Vec::new();
        let mut buffer = [0; 8192];
        loop {
            let n = socket.read(&mut buffer).await.unwrap();
            if n == 0 {
                break;
            }
            data.extend_from_slice(&buffer[..n]);
            if let Some(pos) = data.windows(4).position(|w| w == b"\r\n\r\n") {
                let headers = String::from_utf8_lossy(&data[..pos]).to_lowercase();
                let length = headers
                    .lines()
                    .find_map(|line| {
                        line.strip_prefix("content-length:")
                            .and_then(|v| v.trim().parse::<usize>().ok())
                    })
                    .unwrap_or(0);
                if data.len() >= pos + 4 + length {
                    break;
                }
            }
        }
        let response=format!("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nContent-Length: {}\r\n\r\n{}",body.len(),body);
        socket.write_all(response.as_bytes()).await.unwrap();
        String::from_utf8(data).unwrap()
    });
    (url, task)
}
fn request() -> ChatRequest {
    ChatRequest {
        request_id: uuid::Uuid::new_v4().to_string(),
        chat_id: None,
        prompt: "分析上传".into(),
        scope: AnalysisScope {
            interface: "test-interface".into(),
            start: 60,
            end: 3600,
            processes: false,
        },
        configure: false,
    }
}
fn setup(url: String) -> (tempfile::TempDir, Arc<Monitor>, Arc<AiService>) {
    let dir = tempfile::tempdir().unwrap();
    let monitor = Monitor::start(&dir.path().join("test.db")).unwrap();
    monitor
        .store
        .lock()
        .unwrap()
        .set_setting(
            "localAi",
            &json!(AiSettings {
                enabled: true,
                base_url: url,
                ..AiSettings::default()
            }),
        )
        .unwrap();
    let ai = Arc::new(AiService::new(monitor.clone()));
    (dir, monitor, ai)
}
#[tokio::test]
async fn chat_sends_bounded_real_context_and_persists_complete_response() {
    let (url, server) = provider(
        "data: {\"choices\":[{\"delta\":{\"content\":\"## 分析\\n正常\"}}]}\n\ndata: [DONE]\n\n",
    )
    .await;
    let (_dir, monitor, ai) = setup(url);
    monitor
        .store
        .lock()
        .unwrap()
        .add_traffic(120, "test-interface", 50, 100)
        .unwrap();
    let id = ai.chat(request(), |_| Ok(())).await.unwrap();
    let sent = server.await.unwrap();
    assert!(sent.starts_with("POST /chat/completions"));
    assert!(sent.contains("test-interface"));
    assert!(sent.contains("rx_bytes"));
    assert!(!sent.to_lowercase().contains("authorization:"));
    let page = monitor
        .store
        .lock()
        .unwrap()
        .chat_messages(&id, None)
        .unwrap();
    assert_eq!(page.messages[1].content, "## 分析\n正常");
    assert_eq!(page.messages[1].status, "complete");
    monitor.stop();
}
#[tokio::test]
async fn cancellation_and_eof_save_partial_text_and_release_request_slot() {
    for cancel in [false, true] {
        let (url, server) =
            provider("data: {\"choices\":[{\"delta\":{\"content\":\"部分\"}}]}\n\n").await;
        let (_dir, monitor, ai) = setup(url);
        let req = request();
        let id = req.request_id.clone();
        let copy = ai.clone();
        let result = ai
            .chat(req, move |packet| {
                if cancel && matches!(packet, AiPacket::Delta { .. }) {
                    copy.cancel(&id);
                }
                Ok(())
            })
            .await;
        assert!(result.is_err());
        server.await.unwrap();
        {
            let mut db = monitor.store.lock().unwrap();
            let chat = db.chats().unwrap().remove(0);
            let page = db.chat_messages(&chat.id, None).unwrap();
            assert_eq!(page.messages[1].content, "部分");
            assert_eq!(page.messages[1].status, "interrupted");
            db.set_setting("localAi", &json!(AiSettings::default()))
                .unwrap();
        }
        assert!(ai
            .chat(request(), |_| Ok(()))
            .await
            .unwrap_err()
            .contains("启用"));
        monitor.stop();
    }
}
