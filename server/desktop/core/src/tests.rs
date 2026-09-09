use std::collections::BTreeMap;

#[test]
fn first_sample_and_resets_do_not_create_traffic() {
    let mut meter = crate::metrics::NetworkMeter::default();
    let counters = |rx, tx| BTreeMap::from([("en0".to_owned(), (rx, tx))]);
    assert_eq!(meter.update(100, counters(1000, 500))[0].rx_bytes, 0);
    let row = meter.update(102, counters(1400, 600)).remove(0);
    assert_eq!((row.rx_bytes, row.tx_bytes, row.rx_bps), (400, 100, 200.0));
    assert_eq!(meter.update(103, counters(10, 10))[0].rx_bytes, 0);
    assert_eq!(meter.update(200, counters(10000, 10000))[0].rx_bytes, 0);
}

#[test]
fn history_cleanup_keeps_profiles_and_settings() {
    let mut db = crate::storage::Store::open_in_memory().unwrap();
    let profile = db
        .save_profile(None, "Test NAS", "http://127.0.0.1:8088")
        .unwrap();
    db.set_setting("closeToTray", &serde_json::json!(true))
        .unwrap();
    db.add_traffic(120, "en0", 100, 50).unwrap();
    db.add_traffic(180, "en0", 200, 75).unwrap();
    assert_eq!(db.history(100, 200, "en0", 60).unwrap().rx_bytes, 300);
    db.clear_history().unwrap();
    assert_eq!(db.history(100, 200, "en0", 60).unwrap().rx_bytes, 0);
    assert_eq!(db.profiles().unwrap()[0].id, profile.id);
    assert_eq!(
        db.setting("closeToTray").unwrap(),
        Some(serde_json::json!(true))
    );
}

#[test]
fn targets_reject_credentials_paths_and_cross_origin_requests() {
    use crate::nas::{endpoint, request_url};
    assert!(endpoint("http://user:password@localhost:8088").is_err());
    assert!(endpoint("file:///tmp/data").is_err());
    assert!(endpoint("https://example.test/base?token=x").is_err());
    let base = endpoint("http://localhost:8088/").unwrap();
    assert!(request_url(&base, "//example.test/api/settings").is_err());
    assert!(request_url(&base, "/api/../login").is_err());
    assert!(request_url(&base, "/api/%2e%2e/login").is_err());
    assert!(request_url(&base, "/api/auth/login").is_err());
    assert_eq!(
        request_url(&base, "/api/history?period=week")
            .unwrap()
            .host_str(),
        Some("localhost")
    );
}

#[test]
fn sqlite_restart_preserves_period_totals_and_interface_isolation() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("desktop.db");
    {
        let mut db = crate::storage::Store::open(&path).unwrap();
        db.add_traffic(86400, "en0", 100, 200).unwrap();
        db.add_traffic(86460, "en0", 300, 400).unwrap();
        db.add_traffic(172800, "en0", 500, 600).unwrap();
        db.add_traffic(86400, "utun0", 999, 999).unwrap();
    }
    let mut db = crate::storage::Store::open(&path).unwrap();
    let first = db.history(86400, 172800, "en0", 3600).unwrap();
    assert_eq!(
        (first.rx_bytes, first.tx_bytes, first.points.len()),
        (400, 600, 1)
    );
    assert_eq!(
        db.history(86400, 259200, "en0", 3600).unwrap().rx_bytes,
        900
    );
    db.prune(172800).unwrap();
    assert_eq!(
        db.history(86400, 259200, "en0", 3600).unwrap().rx_bytes,
        500
    );
}

#[test]
fn historical_buckets_align_to_the_selected_local_period() {
    let mut db = crate::storage::Store::open_in_memory().unwrap();
    db.add_traffic(600, "en0", 100, 50).unwrap();
    let history = db.history(600, 7200, "en0", 3600).unwrap();
    assert_eq!(history.points[0].timestamp, 600);
}
