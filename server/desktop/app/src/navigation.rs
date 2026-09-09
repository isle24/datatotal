use crate::AppState;
use tauri::State;
use traffic_lens_core::{navigation::NavigationEntry, Result};

#[tauri::command]
pub fn local_navigation(state: State<AppState>) -> Result<Vec<NavigationEntry>> {
    state.monitor.store.lock().unwrap().navigation()
}
#[tauri::command]
pub fn save_navigation(state: State<AppState>, entry: NavigationEntry) -> Result<NavigationEntry> {
    state.monitor.store.lock().unwrap().save_navigation(entry)
}
#[tauri::command]
pub fn delete_navigation(state: State<AppState>, id: String) -> Result<()> {
    state.monitor.store.lock().unwrap().delete_navigation(&id)
}
#[tauri::command]
pub fn set_nas_layout(state: State<AppState>, id: String, layout: String) -> Result<()> {
    state
        .monitor
        .store
        .lock()
        .unwrap()
        .set_nas_layout(&id, &layout)
}
