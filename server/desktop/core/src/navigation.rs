use crate::{storage::Store, Result};
use base64::{engine::general_purpose::STANDARD, Engine};
use rusqlite::{params, OptionalExtension};
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct NavigationEntry {
    pub id: String,
    pub name: String,
    pub url: String,
    pub icon: String,
    pub group: String,
    pub notes: String,
    pub sort_order: i32,
    pub source_key: String,
}
impl NavigationEntry {
    fn validate(&mut self) -> Result<()> {
        self.name = self.name.trim().into();
        self.url = self.url.trim().into();
        self.group = self.group.trim().into();
        if self.name.is_empty()
            || self.name.chars().count() > 120
            || self.url.len() > 2048
            || self.group.chars().count() > 60
            || self.notes.chars().count() > 500
            || self.source_key.len() > 256
            || self.id.len() > 64
            || !(-10000..=10000).contains(&self.sort_order)
        {
            return Err("导航字段过长或排序无效".into());
        }
        let url = url::Url::parse(&self.url).map_err(|_| "无效的服务地址")?;
        if !matches!(url.scheme(), "http" | "https")
            || url.host_str().is_none()
            || !url.username().is_empty()
            || url.password().is_some()
            || self.url.chars().any(|c| c.is_control() || c == '\\')
        {
            return Err("地址须为不含账号密码的 HTTP/HTTPS URL".into());
        }
        if !self.icon.is_empty() {
            let (prefix, data) = self.icon.split_once(',').ok_or("无效的图标")?;
            if self.icon.len() > 32768
                || !matches!(
                    prefix,
                    "data:image/png;base64"
                        | "data:image/jpeg;base64"
                        | "data:image/webp;base64"
                        | "data:image/gif;base64"
                )
            {
                return Err("图标须为上传的位图".into());
            }
            let data = STANDARD.decode(data).map_err(|_| "无效的图标编码")?;
            if !(data.starts_with(b"\x89PNG\r\n\x1a\n")
                || data.starts_with(b"\xff\xd8\xff")
                || data.starts_with(b"GIF87a")
                || data.starts_with(b"GIF89a")
                || (data.starts_with(b"RIFF") && data.get(8..12) == Some(b"WEBP")))
            {
                return Err("图标格式无效".into());
            }
        }
        Ok(())
    }
}
impl Store {
    pub fn navigation(&self) -> Result<Vec<NavigationEntry>> {
        let mut statement = self
            .conn
            .prepare("SELECT payload FROM navigation")
            .map_err(|e| e.to_string())?;
        let rows = statement
            .query_map([], |r| r.get::<_, String>(0))
            .map_err(|e| e.to_string())?;
        let mut entries: Vec<NavigationEntry> = rows
            .map(|row| {
                serde_json::from_str(&row.map_err(|e| e.to_string())?).map_err(|e| e.to_string())
            })
            .collect::<Result<_>>()?;
        entries.sort_by(|a, b| (a.sort_order, &a.name, &a.id).cmp(&(b.sort_order, &b.name, &b.id)));
        Ok(entries)
    }
    pub fn save_navigation(&mut self, mut entry: NavigationEntry) -> Result<NavigationEntry> {
        entry.validate()?;
        let tx = self.conn.transaction().map_err(|e| e.to_string())?;
        if !entry.id.is_empty() {
            let source: Option<Option<String>> = tx
                .query_row(
                    "SELECT source_key FROM navigation WHERE id=?1",
                    [&entry.id],
                    |r| r.get(0),
                )
                .optional()
                .map_err(|e| e.to_string())?;
            entry.source_key = source.ok_or("导航项目不存在")?.unwrap_or_default();
        } else {
            if !entry.source_key.is_empty() {
                let existing: Option<String> = tx
                    .query_row(
                        "SELECT payload FROM navigation WHERE source_key=?1",
                        [&entry.source_key],
                        |r| r.get(0),
                    )
                    .optional()
                    .map_err(|e| e.to_string())?;
                if let Some(existing) = existing {
                    return serde_json::from_str(&existing).map_err(|e| e.to_string());
                }
            }
            let count: i64 = tx
                .query_row("SELECT COUNT(*) FROM navigation", [], |r| r.get(0))
                .map_err(|e| e.to_string())?;
            if count >= 200 {
                return Err("最多保存 200 个导航项目".into());
            }
            entry.id = uuid::Uuid::new_v4().to_string();
        }
        tx.execute("INSERT INTO navigation VALUES (?1,?2,?3) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
            params![entry.id, if entry.source_key.is_empty() { None } else { Some(&entry.source_key) }, serde_json::to_string(&entry).map_err(|e|e.to_string())?]).map_err(|e|e.to_string())?;
        tx.commit().map_err(|e| e.to_string())?;
        Ok(entry)
    }
    pub fn delete_navigation(&mut self, id: &str) -> Result<()> {
        if self
            .conn
            .execute("DELETE FROM navigation WHERE id=?1", [id])
            .map_err(|e| e.to_string())?
            == 0
        {
            return Err("导航项目不存在".into());
        }
        Ok(())
    }
    pub fn nas_layout(&self, id: &str) -> Result<String> {
        Ok(self
            .setting(&format!("nasLayout:{id}"))?
            .and_then(|v| v.as_str().map(String::from))
            .filter(|v| v == "web")
            .unwrap_or("native".into()))
    }
    pub fn set_nas_layout(&mut self, id: &str, layout: &str) -> Result<()> {
        self.profile(id)?;
        if !matches!(layout, "native" | "web") {
            return Err("不支持的界面模式".into());
        }
        self.set_setting(&format!("nasLayout:{id}"), &serde_json::json!(layout))
    }
}
