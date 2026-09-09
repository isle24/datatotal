use crate::{storage::Store, Result};
use rusqlite::params;
use serde::Serialize;
use serde_json::{json, Value};

#[derive(Serialize)]
pub struct Chat {
    pub id: String,
    pub title: String,
    pub updated: i64,
}
#[derive(Clone, Serialize)]
pub struct ChatMessage {
    pub id: i64,
    pub role: String,
    pub content: String,
    pub status: String,
    pub model: String,
    pub created: i64,
}
#[derive(Serialize)]
pub struct MessagePage {
    pub messages: Vec<ChatMessage>,
    pub has_more: bool,
}

impl Store {
    pub fn ai_propose_preferences(&mut self, changes: &Value) -> Result<Value> {
        let entries = changes.as_object().ok_or("AI 未返回有效设置对象")?;
        if entries.is_empty() || entries.len() > 3 {
            return Err("AI 设置建议为空或条目过多".into());
        }
        let mut rows = Vec::new();
        for (key, value) in entries {
            let default = match key.as_str() {
                "retentionDays" if value.as_u64().is_some_and(|v| (1..=365).contains(&v)) => {
                    json!(30)
                }
                "closeToTray" if value.is_boolean() => json!(true),
                "interface"
                    if value
                        .as_str()
                        .is_some_and(|v| !v.is_empty() && v.len() <= 256) =>
                {
                    json!("")
                }
                _ => return Err("AI 只能建议修改历史保留天数、关闭窗口行为和默认网卡".into()),
            };
            rows.push(
                json!({"key":key,"before":self.setting(key)?.unwrap_or(default),"after":value}),
            );
        }
        let proposal = json!({"id":uuid::Uuid::new_v4().to_string(),"expires":chrono::Utc::now().timestamp()+600,"changes":rows});
        self.set_setting("localAiProposal", &proposal)?;
        Ok(proposal)
    }
    pub fn ai_apply_preferences(&mut self, id: &str) -> Result<()> {
        let proposal = self
            .setting("localAiProposal")?
            .ok_or("没有待确认的设置建议")?;
        if proposal["id"].as_str() != Some(id)
            || proposal["expires"].as_i64().unwrap_or(0) < chrono::Utc::now().timestamp()
        {
            return Err("设置建议已失效，请重新生成".into());
        }
        let entries = proposal["changes"].as_array().ok_or("设置建议无效")?;
        for row in entries {
            let key = row["key"].as_str().ok_or("设置字段无效")?;
            let default = match key {
                "retentionDays" => json!(30),
                "closeToTray" => json!(true),
                "interface" => json!(""),
                _ => return Err("不允许的设置字段".into()),
            };
            if self.setting(key)?.unwrap_or(default) != row["before"] {
                return Err("设置已被修改，请重新生成建议".into());
            }
        }
        let tx = self.conn.transaction().map_err(|e| e.to_string())?;
        for row in entries {
            tx.execute("INSERT INTO settings VALUES (?1,?2) ON CONFLICT(key) DO UPDATE SET value=excluded.value",params![row["key"].as_str(),row["after"].to_string()]).map_err(|e|e.to_string())?;
        }
        tx.execute("DELETE FROM settings WHERE key='localAiProposal'", [])
            .map_err(|e| e.to_string())?;
        tx.commit().map_err(|e| e.to_string())
    }
    pub fn create_chat(&mut self, title: &str) -> Result<String> {
        if self.chats()?.len() >= 100 {
            return Err("已保存 100 个对话，请删除不再需要的对话后重试".into());
        }
        let id = uuid::Uuid::new_v4().to_string();
        self.conn
            .execute(
                "INSERT INTO ai_chats VALUES (?1,?2,?3)",
                params![
                    id,
                    title.chars().take(80).collect::<String>(),
                    chrono::Utc::now().timestamp()
                ],
            )
            .map_err(|e| e.to_string())?;
        Ok(id)
    }
    pub fn chats(&self) -> Result<Vec<Chat>> {
        let mut query = self
            .conn
            .prepare(
                "SELECT id,title,updated FROM ai_chats ORDER BY updated DESC,rowid DESC LIMIT 100",
            )
            .map_err(|e| e.to_string())?;
        let rows = query
            .query_map([], |r| {
                Ok(Chat {
                    id: r.get(0)?,
                    title: r.get(1)?,
                    updated: r.get(2)?,
                })
            })
            .map_err(|e| e.to_string())?;
        rows.collect::<std::result::Result<_, _>>()
            .map_err(|e| e.to_string())
    }
    pub fn delete_chat(&mut self, id: &str) -> Result<()> {
        self.conn
            .execute("DELETE FROM ai_chats WHERE id=?1", [id])
            .map_err(|e| e.to_string())?;
        Ok(())
    }
    pub fn chat_messages(&self, id: &str, before: Option<i64>) -> Result<MessagePage> {
        let mut query = self.conn.prepare("SELECT id,role,content,status,model,created FROM ai_messages WHERE chat_id=?1 AND id<?2 ORDER BY id DESC LIMIT 41").map_err(|e| e.to_string())?;
        let rows = query
            .query_map(params![id, before.unwrap_or(i64::MAX)], |r| {
                Ok(ChatMessage {
                    id: r.get(0)?,
                    role: r.get(1)?,
                    content: r.get(2)?,
                    status: r.get(3)?,
                    model: r.get(4)?,
                    created: r.get(5)?,
                })
            })
            .map_err(|e| e.to_string())?;
        let mut messages = Vec::new();
        let mut bytes = 0;
        let mut has_more = false;
        for row in rows {
            let row = row.map_err(|e| e.to_string())?;
            if messages.len() >= 40
                || (!messages.is_empty() && bytes + row.content.len() > 4 * 1024 * 1024)
            {
                has_more = true;
                break;
            }
            bytes += row.content.len();
            messages.push(row);
        }
        messages.reverse();
        Ok(MessagePage { messages, has_more })
    }
    pub fn append_chat_message(
        &mut self,
        chat: &str,
        role: &str,
        content: &str,
        status: &str,
        model: &str,
    ) -> Result<i64> {
        if !["user", "assistant"].contains(&role) || content.len() > 2 * 1024 * 1024 {
            return Err("对话消息无效或过长".into());
        }
        let count: i64 = self
            .conn
            .query_row(
                "SELECT count(*) FROM ai_messages WHERE chat_id=?1",
                [chat],
                |r| r.get(0),
            )
            .map_err(|e| e.to_string())?;
        if count >= 400 {
            return Err("本对话已达 400 条消息，请新建对话".into());
        }
        let tx = self.conn.transaction().map_err(|e| e.to_string())?;
        let now = chrono::Utc::now().timestamp();
        tx.execute("INSERT INTO ai_messages(chat_id,role,content,status,model,created) VALUES (?1,?2,?3,?4,?5,?6)", params![chat,role,content,status,model,now]).map_err(|e| e.to_string())?;
        let id = tx.last_insert_rowid();
        tx.execute(
            "UPDATE ai_chats SET updated=?2 WHERE id=?1",
            params![chat, now],
        )
        .map_err(|e| e.to_string())?;
        tx.commit().map_err(|e| e.to_string())?;
        Ok(id)
    }
    pub fn update_chat_message(&mut self, id: i64, content: &str, status: &str) -> Result<()> {
        if content.len() > 2 * 1024 * 1024 {
            return Err("回复超过 2 MiB".into());
        }
        self.conn
            .execute(
                "UPDATE ai_messages SET content=?2,status=?3 WHERE id=?1",
                params![id, content, status],
            )
            .map_err(|e| e.to_string())?;
        Ok(())
    }
}
