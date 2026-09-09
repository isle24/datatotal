#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod controllers;
mod navigation;
use std::sync::Arc;
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager,
};
use traffic_lens_core::{ai::AiService, monitor::Monitor, nas::NasClient};

pub struct AppState {
    monitor: Arc<Monitor>,
    nas: Arc<NasClient>,
    ai: Arc<AiService>,
}

fn show(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
        let _ = app.emit("desktop-visibility", true);
    }
}
fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| show(app)))
        .plugin(
            tauri_plugin_opener::Builder::new()
                .open_js_links_on_click(false)
                .build(),
        )
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_autostart::Builder::new().build())
        .plugin(
            tauri_plugin_log::Builder::new()
                .level(log::LevelFilter::Warn)
                .max_file_size(1024 * 1024)
                .rotation_strategy(tauri_plugin_log::RotationStrategy::KeepSome(3))
                .build(),
        )
        .setup(|app| {
            let data = app.path().app_data_dir()?;
            std::fs::create_dir_all(&data)?;
            let monitor =
                Monitor::start(&data.join("desktop.db")).map_err(std::io::Error::other)?;
            app.manage(AppState {
                ai: Arc::new(AiService::new(monitor.clone())),
                monitor,
                nas: Arc::new(NasClient::default()),
            });
            let open = MenuItem::with_id(app, "open", "打开 Traffic Lens", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出并停止本机监控", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("Traffic Lens · 本机监控运行中")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Focused(_)) {
                let visible =
                    window.is_visible().unwrap_or(false) && !window.is_minimized().unwrap_or(false);
                let _ = window.emit("desktop-visibility", visible);
            }
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let state = window.state::<AppState>();
                let background = state
                    .monitor
                    .store
                    .lock()
                    .unwrap()
                    .setting("closeToTray")
                    .ok()
                    .flatten()
                    .and_then(|v| v.as_bool())
                    .unwrap_or(true);
                if background {
                    api.prevent_close();
                    let _ = window.hide();
                    let _ = window.emit("desktop-visibility", false);
                } else {
                    window.app_handle().exit(0);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            navigation::local_navigation,
            navigation::save_navigation,
            navigation::delete_navigation,
            navigation::set_nas_layout,
            controllers::local_snapshot,
            controllers::local_history,
            controllers::desktop_config,
            controllers::set_preference,
            controllers::clear_local_history,
            controllers::save_profile,
            controllers::delete_profile,
            controllers::nas_login,
            controllers::nas_logout,
            controllers::nas_disconnect,
            controllers::nas_pause,
            controllers::local_ai_settings,
            controllers::local_ai_save,
            controllers::local_ai_models,
            controllers::local_ai_test,
            controllers::local_ai_proposal,
            controllers::local_ai_apply,
            controllers::local_ai_chat,
            controllers::local_ai_cancel,
            controllers::local_ai_chats,
            controllers::local_ai_messages,
            controllers::local_ai_delete,
            controllers::nas_request,
            controllers::nas_cancel,
            controllers::open_external,
            controllers::open_directory,
            controllers::quit_app
        ])
        .build(tauri::generate_context!())
        .expect("Traffic Lens could not start");
    app.run(|app, event| match event {
        tauri::RunEvent::Exit => {
            app.state::<AppState>().ai.cancel_all();
            app.state::<AppState>().monitor.stop();
        }
        #[cfg(target_os = "macos")]
        tauri::RunEvent::Reopen { .. } => show(app),
        _ => {}
    });
}
