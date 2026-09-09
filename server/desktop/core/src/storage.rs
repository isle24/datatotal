use crate::Result;
use rusqlite::{params, Connection, OptionalExtension};
use serde::Serialize;
use serde_json::Value;
use std::path::Path;

#[derive(Clone, Serialize)]
pub struct Profile {
    pub id: String,
    pub name: String,
    pub url: String,
}
#[derive(Serialize)]
pub struct HistoryPoint {
    pub timestamp: i64,
    pub rx_bytes: u64,
    pub tx_bytes: u64,
}
#[derive(Serialize)]
pub struct History {
    pub rx_bytes: u64,
    pub tx_bytes: u64,
    pub points: Vec<HistoryPoint>,
}

pub struct Store {
    pub(crate) conn: Connection,
}

impl Store {
    pub fn open(path: &Path) -> Result<Self> {
        Self::init(Connection::open(path).map_err(|e| e.to_string())?)
    }
    pub fn open_in_memory() -> Result<Self> {
        Self::init(Connection::open_in_memory().map_err(|e| e.to_string())?)
    }
    fn init(conn: Connection) -> Result<Self> {
        conn.busy_timeout(std::time::Duration::from_secs(3))
            .map_err(|e| e.to_string())?;
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS traffic(minute INTEGER NOT NULL, interface TEXT NOT NULL, rx INTEGER NOT NULL, tx INTEGER NOT NULL, PRIMARY KEY(minute,interface));
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS ai_chats(id TEXT PRIMARY KEY, title TEXT NOT NULL, updated INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS ai_messages(id INTEGER PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES ai_chats(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL, model TEXT NOT NULL, created INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS ai_messages_chat ON ai_messages(chat_id,id);
            UPDATE ai_messages SET status='interrupted' WHERE status='streaming';
            CREATE TABLE IF NOT EXISTS navigation(id TEXT PRIMARY KEY, source_key TEXT, payload TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS navigation_source ON navigation(source_key) WHERE source_key IS NOT NULL;
            PRAGMA user_version=3;").map_err(|e| e.to_string())?;
        Ok(Self { conn })
    }
    pub fn save_profile(&mut self, id: Option<&str>, name: &str, address: &str) -> Result<Profile> {
        let url = crate::nas::endpoint(address)?.to_string();
        let name = name.trim();
        if name.is_empty() || name.len() > 120 {
            return Err("名称需为 1–120 字节".into());
        }
        let id = match id {
            Some(id) => {
                self.profile(id)?;
                id.to_owned()
            }
            None => {
                if self.profiles()?.len() >= 20 {
                    return Err("最多保存 20 个 NAS".into());
                }
                uuid::Uuid::new_v4().to_string()
            }
        };
        self.conn.execute("INSERT INTO profiles VALUES (?1,?2,?3) ON CONFLICT(id) DO UPDATE SET name=excluded.name,url=excluded.url",params![id,name,url]).map_err(|e| e.to_string())?;
        Ok(Profile {
            id,
            name: name.into(),
            url,
        })
    }
    pub fn profile(&self, id: &str) -> Result<Profile> {
        self.conn
            .query_row("SELECT id,name,url FROM profiles WHERE id=?1", [id], |r| {
                Ok(Profile {
                    id: r.get(0)?,
                    name: r.get(1)?,
                    url: r.get(2)?,
                })
            })
            .map_err(|_| "NAS 配置不存在".into())
    }
    pub fn profiles(&self) -> Result<Vec<Profile>> {
        let mut s = self
            .conn
            .prepare("SELECT id,name,url FROM profiles ORDER BY name")
            .map_err(|e| e.to_string())?;
        let result = s
            .query_map([], |r| {
                Ok(Profile {
                    id: r.get(0)?,
                    name: r.get(1)?,
                    url: r.get(2)?,
                })
            })
            .map_err(|e| e.to_string())?
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|e| e.to_string());
        result
    }
    pub fn delete_profile(&mut self, id: &str) -> Result<()> {
        self.conn
            .execute("DELETE FROM profiles WHERE id=?1", [id])
            .map_err(|e| e.to_string())?;
        Ok(())
    }
    pub fn set_setting(&mut self, key: &str, value: &Value) -> Result<()> {
        self.conn.execute("INSERT INTO settings VALUES (?1,?2) ON CONFLICT(key) DO UPDATE SET value=excluded.value",params![key,value.to_string()]).map_err(|e|e.to_string())?;
        Ok(())
    }
    pub fn setting(&self, key: &str) -> Result<Option<Value>> {
        let value: Option<String> = self
            .conn
            .query_row("SELECT value FROM settings WHERE key=?1", [key], |r| {
                r.get(0)
            })
            .optional()
            .map_err(|e| e.to_string())?;
        value
            .map(|v| serde_json::from_str(&v).map_err(|e| e.to_string()))
            .transpose()
    }
    pub fn add_traffic(&mut self, timestamp: i64, interface: &str, rx: u64, tx: u64) -> Result<()> {
        self.write_batch(&[(timestamp, interface.into(), rx, tx)])
    }
    pub fn write_batch(&mut self, rows: &[(i64, String, u64, u64)]) -> Result<()> {
        let tx = self.conn.transaction().map_err(|e| e.to_string())?;
        {
            let mut statement = tx.prepare_cached("INSERT INTO traffic VALUES (?1,?2,?3,?4) ON CONFLICT(minute,interface) DO UPDATE SET rx=rx+excluded.rx,tx=tx+excluded.tx").map_err(|e|e.to_string())?;
            for (time, name, rx, tx_bytes) in rows {
                statement
                    .execute(params![time / 60 * 60, name, rx, tx_bytes])
                    .map_err(|e| e.to_string())?;
            }
        }
        tx.commit().map_err(|e| e.to_string())
    }
    pub fn history(&self, start: i64, end: i64, interface: &str, bucket: i64) -> Result<History> {
        if start < 0
            || end <= start
            || end - start > 366 * 86400
            || bucket < 60
            || (end - start) / bucket > 1500
        {
            return Err("历史范围或粒度无效".into());
        }
        let mut statement = self.conn.prepare("SELECT ((minute - ?1) / ?4) * ?4 + ?1, SUM(rx), SUM(tx) FROM traffic WHERE minute>=?1 AND minute<?2 AND (?3='' OR interface=?3) GROUP BY 1 ORDER BY 1").map_err(|e|e.to_string())?;
        let points = statement
            .query_map(params![start / 60 * 60, end, interface, bucket], |r| {
                Ok(HistoryPoint {
                    timestamp: r.get(0)?,
                    rx_bytes: r.get(1)?,
                    tx_bytes: r.get(2)?,
                })
            })
            .map_err(|e| e.to_string())?
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|e| e.to_string())?;
        Ok(History {
            rx_bytes: points.iter().map(|p| p.rx_bytes).sum(),
            tx_bytes: points.iter().map(|p| p.tx_bytes).sum(),
            points,
        })
    }
    pub fn prune(&mut self, before: i64) -> Result<()> {
        self.conn
            .execute("DELETE FROM traffic WHERE minute<?1", [before])
            .map_err(|e| e.to_string())?;
        Ok(())
    }
    pub fn clear_history(&mut self) -> Result<()> {
        self.conn
            .execute("DELETE FROM traffic", [])
            .map_err(|e| e.to_string())?;
        Ok(())
    }
}
