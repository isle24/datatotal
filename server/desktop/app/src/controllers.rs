use crate::AppState;
use serde_json::{json, Value};
use tauri::{ipc::Channel, Manager, State};
use tauri_plugin_opener::OpenerExt;
use traffic_lens_core::{
    metrics::Snapshot,
    nas::{ApiRequest, Packet},
    storage::{History, Profile},
    Result,
};

#[tauri::command]
pub fn local_snapshot(state: State<AppState>, processes: bool) -> Snapshot {
    state.monitor.snapshot(processes)
}
#[tauri::command]
pub async fn local_history(
    state: State<'_, AppState>,
    start: i64,
    end: i64,
    interface: String,
    bucket: i64,
) -> Result<History> {
    let monitor = state.monitor.clone();
    tauri::async_runtime::spawn_blocking(move || {
        monitor
            .store
            .lock()
            .unwrap()
            .history(start, end, &interface, bucket)
    })
    .await
    .map_err(|e| e.to_string())?
}
#[tauri::command]
pub fn desktop_config(state: State<AppState>) -> Result<Value> {
    let db = state.monitor.store.lock().unwrap();
    Ok(
        json!({"version":env!("CARGO_PKG_VERSION"),"profiles":db.profiles()?,"closeToTray":db.setting("closeToTray")?.unwrap_or(json!(true)),"retentionDays":db.setting("retentionDays")?.unwrap_or(json!(30)),"interface":db.setting("interface")?.unwrap_or(json!(""))}),
    )
}
#[tauri::command]
pub fn set_preference(state: State<AppState>, key: String, value: Value) -> Result<()> {
    let valid = match key.as_str() {
        "closeToTray" => value.is_boolean(),
        "retentionDays" => value.as_u64().is_some_and(|v| (1..=365).contains(&v)),
        "interface" => value.as_str().is_some_and(|v| v.len() <= 256),
        _ => false,
    };
    if !valid {
        return Err("不支持的设置或取值".into());
    }
    state
        .monitor
        .store
        .lock()
        .unwrap()
        .set_setting(&key, &value)
}
#[tauri::command]
pub async fn clear_local_history(state: State<'_, AppState>) -> Result<()> {
    let monitor = state.monitor.clone();
    tauri::async_runtime::spawn_blocking(move || monitor.clear_history())
        .await
        .map_err(|e| e.to_string())?
}
#[tauri::command]
pub fn save_profile(
    state: State<AppState>,
    id: Option<String>,
    name: String,
    url: String,
) -> Result<Profile> {
    if let Some(id) = &id {
        state.nas.disconnect(id);
        traffic_lens_core::nas::forget_password(id)?;
    }
    state
        .monitor
        .store
        .lock()
        .unwrap()
        .save_profile(id.as_deref(), &name, &url)
}
#[tauri::command]
pub fn delete_profile(state: State<AppState>, id: String) -> Result<()> {
    state.nas.disconnect(&id);
    traffic_lens_core::nas::forget_password(&id)?;
    state.monitor.store.lock().unwrap().delete_profile(&id)
}
#[tauri::command]
pub async fn nas_login(
    state: State<'_, AppState>,
    id: String,
    password: Option<String>,
    remember: bool,
) -> Result<()> {
    let profile = state.monitor.store.lock().unwrap().profile(&id)?;
    state.nas.login(profile, password, remember).await
}
#[tauri::command]
pub async fn nas_logout(state: State<'_, AppState>, id: String) -> Result<()> {
    state.nas.logout(&id).await
}
#[tauri::command]
pub fn nas_disconnect(state: State<AppState>, id: String) {
    state.nas.disconnect(&id);
}
#[tauri::command]
pub async fn nas_request(
    state: State<'_, AppState>,
    request: ApiRequest,
    on_packet: Channel<Packet>,
) -> Result<()> {
    state
        .nas
        .request(request, move |packet| {
            on_packet.send(packet).map_err(|_| "页面已关闭".into())
        })
        .await
}
#[tauri::command]
pub fn nas_cancel(state: State<AppState>, id: String) {
    state.nas.cancel(&id);
}
#[tauri::command]
pub fn open_external(app: tauri::AppHandle, url: String) -> Result<()> {
    let parsed =
        traffic_lens_core::nas::endpoint(&url.split('/').take(3).collect::<Vec<_>>().join("/"))?;
    if !["http", "https"].contains(&parsed.scheme()) {
        return Err("不允许的链接".into());
    }
    app.opener()
        .open_url(url, None::<&str>)
        .map_err(|e| e.to_string())
}
#[tauri::command]
pub fn open_directory(app: tauri::AppHandle, kind: String) -> Result<()> {
    let path = match kind.as_str() {
        "data" => app.path().app_data_dir(),
        "logs" => app.path().app_log_dir(),
        _ => return Err("不支持的目录".into()),
    }
    .map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&path).map_err(|e| e.to_string())?;
    app.opener()
        .open_path(path.to_string_lossy().into_owned(), None::<&str>)
        .map_err(|e| e.to_string())
}
#[tauri::command]
pub fn quit_app(app: tauri::AppHandle) {
    app.exit(0);
}
