use serde_json::json;
use traffic_lens_core::{navigation::NavigationEntry, storage::Store};

fn entry(value: serde_json::Value) -> NavigationEntry {
    serde_json::from_value(value).unwrap()
}

#[test]
fn navigation_persists_and_import_is_idempotent() {
    let mut store = Store::open_in_memory().unwrap();
    store.set_setting("closeToTray", &json!(true)).unwrap();
    let original =
        entry(json!({"name":"qb", "url":"http://nas:8080", "sourceKey":"docker:qb:8080"}));
    let mut saved = store.save_navigation(original.clone()).unwrap();
    saved.name = "Downloads".into();
    store.save_navigation(saved.clone()).unwrap();
    assert_eq!(store.save_navigation(original).unwrap().name, "Downloads");
    assert_eq!(store.navigation().unwrap().len(), 1);
    store.delete_navigation(&saved.id).unwrap();
    assert!(store.navigation().unwrap().is_empty());
    assert_eq!(store.setting("closeToTray").unwrap(), Some(json!(true)));
}

#[test]
fn navigation_rejects_unsafe_data_and_missing_updates() {
    let mut store = Store::open_in_memory().unwrap();
    for url in [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://a:b@nas",
        "http://nas:bad",
    ] {
        assert!(store
            .save_navigation(entry(json!({"name":"A", "url":url})))
            .is_err());
    }
    assert!(store
        .save_navigation(entry(
            json!({"name":"A", "url":"http://nas", "icon":"data:image/svg+xml;base64,PHN2Zz4="})
        ))
        .is_err());
    assert!(store
        .save_navigation(entry(json!({"id":"gone", "name":"A", "url":"http://nas"})))
        .is_err());
}

#[test]
fn layout_is_scoped_to_existing_profile() {
    let mut store = Store::open_in_memory().unwrap();
    let a = store.save_profile(None, "A", "http://nas-a").unwrap();
    let b = store.save_profile(None, "B", "http://nas-b").unwrap();
    store.set_nas_layout(&a.id, "web").unwrap();
    assert_eq!(store.nas_layout(&a.id).unwrap(), "web");
    assert_eq!(store.nas_layout(&b.id).unwrap(), "native");
    assert!(store.set_nas_layout("unknown", "web").is_err());
    assert!(store.set_nas_layout(&a.id, "arbitrary").is_err());
}
