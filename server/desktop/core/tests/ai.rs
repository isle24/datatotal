use serde_json::json;
use traffic_lens_core::{
    ai::{AiSettings, StreamDecoder},
    storage::Store,
};

#[test]
fn ai_settings_reject_secrets_in_urls_and_invalid_limits() {
    let mut settings = AiSettings {
        base_url: "https://user:secret@example.test/v1".into(),
        ..AiSettings::default()
    };
    assert!(settings.validate().is_err());
    settings.base_url = "https://example.test/v1?key=secret".into();
    assert!(settings.validate().is_err());
    settings.base_url = "https://example.test/v1".into();
    settings.max_tokens = 393216;
    assert!(settings.validate().is_ok());
    settings.max_tokens = 0;
    assert!(settings.validate().is_err());
}

#[test]
fn decoder_handles_fragmented_utf8_and_reports_truncation() {
    let body = "data: {\"choices\":[{\"delta\":{\"content\":\"你好\"}}]}\r\n\r\ndata: {\"choices\":[{\"finish_reason\":\"length\"}]}\n\ndata: [DONE]\n\n";
    let mut decoder = StreamDecoder::default();
    let mut text = String::new();
    for byte in body.as_bytes() {
        text.push_str(&decoder.push(&[*byte]).unwrap());
    }
    assert_eq!(text, "你好");
    assert_eq!(decoder.finish().unwrap(), "length");
    let mut incomplete = StreamDecoder::default();
    incomplete
        .push(b"data: {\"choices\":[{\"delta\":{\"content\":\"partial\"}}]}\n\n")
        .unwrap();
    assert!(incomplete.finish().is_err());
}

#[test]
fn anthropic_decoder_and_error_events() {
    let mut decoder = StreamDecoder::default();
    assert_eq!(decoder.push(b"event: content_block_delta\ndata: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"hello\"}}\n\n").unwrap(), "hello");
    decoder.push(b"data: {\"type\":\"message_delta\",\"delta\":{\"stop_reason\":\"end_turn\"}}\n\ndata: {\"type\":\"message_stop\"}\n\n").unwrap();
    assert_eq!(decoder.finish().unwrap(), "stop");
    assert!(StreamDecoder::default()
        .push(b"data: {\"error\":{\"message\":\"secret should not escape\"}}\n\n")
        .is_err());
}

#[test]
fn chat_survives_restart_without_affecting_monitor_settings() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("desktop.db");
    let id;
    {
        let mut db = Store::open(&path).unwrap();
        db.set_setting("retentionDays", &json!(90)).unwrap();
        id = db.create_chat("分析本周").unwrap();
        db.append_chat_message(&id, "user", "分析本周", "complete", "")
            .unwrap();
        db.append_chat_message(&id, "assistant", "已收到部分", "interrupted", "mock")
            .unwrap();
    }
    let mut db = Store::open(&path).unwrap();
    assert_eq!(db.chat_messages(&id, None).unwrap().messages.len(), 2);
    assert_eq!(
        db.chat_messages(&id, None).unwrap().messages[1].status,
        "interrupted"
    );
    db.clear_history().unwrap();
    assert_eq!(db.chats().unwrap().len(), 1);
    db.delete_chat(&id).unwrap();
    assert!(db.chats().unwrap().is_empty());
    assert_eq!(db.setting("retentionDays").unwrap(), Some(json!(90)));
}

#[test]
fn ai_preference_proposals_are_allowlisted_and_reject_stale_writes() {
    let mut db = Store::open_in_memory().unwrap();
    assert!(db
        .ai_propose_preferences(&json!({"apiKey":"do-not-store"}))
        .is_err());
    assert!(db
        .ai_propose_preferences(&json!({"retentionDays":999}))
        .is_err());
    let proposal = db
        .ai_propose_preferences(&json!({"retentionDays":90,"closeToTray":false}))
        .unwrap();
    assert_eq!(db.setting("retentionDays").unwrap(), None);
    db.set_setting("retentionDays", &json!(7)).unwrap();
    assert!(db
        .ai_apply_preferences(proposal["id"].as_str().unwrap())
        .is_err());
    let proposal = db
        .ai_propose_preferences(&json!({"retentionDays":90,"closeToTray":false}))
        .unwrap();
    db.ai_apply_preferences(proposal["id"].as_str().unwrap())
        .unwrap();
    assert_eq!(db.setting("retentionDays").unwrap(), Some(json!(90)));
    assert_eq!(db.setting("closeToTray").unwrap(), Some(json!(false)));
    assert!(db
        .ai_apply_preferences(proposal["id"].as_str().unwrap())
        .is_err());
}
