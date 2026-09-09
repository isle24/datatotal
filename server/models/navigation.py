import base64
import json
import re
import uuid
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class NavigationEntry(BaseModel):
    id: str = Field(default='', max_length=64)
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)
    icon: str = Field(default='', max_length=32768)
    group: str = Field(default='常用', max_length=60)
    notes: str = Field(default='', max_length=500)
    sortOrder: int = Field(default=0, ge=-10000, le=10000)
    sourceKey: str = Field(default='', max_length=256)

    @field_validator('name', 'group', 'notes', 'url')
    @classmethod
    def trim(cls, value, info):
        value = value.strip()
        if info.field_name == 'name' and not value:
            raise ValueError('名称不能为空')
        return value

    @field_validator('url')
    @classmethod
    def validate_url(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or '\\' in value or any(ord(c) < 32 for c in value)):
            raise ValueError('地址须为不含账号密码的 HTTP/HTTPS URL')
        _ = parsed.port
        return value

    @field_validator('icon')
    @classmethod
    def validate_icon(cls, value):
        if not value:
            return value
        if not re.fullmatch(r'data:image/(png|jpeg|webp|gif);base64,[A-Za-z0-9+/]+=*', value):
            raise ValueError('图标须为上传的位图')
        data = base64.b64decode(value.split(',', 1)[1], validate=True)
        if not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff')
                or data.startswith((b'GIF87a', b'GIF89a')) or (data.startswith(b'RIFF') and data[8:12] == b'WEBP')):
            raise ValueError('图标格式无效')
        return value


class NavigationRepository:
    def __init__(self, db):
        self.db = db

    def _connection(self):
        conn = self.db.conn
        if conn is None:
            raise RuntimeError('数据库尚未就绪')
        conn.execute('CREATE TABLE IF NOT EXISTS navigation(id TEXT PRIMARY KEY, source_key TEXT, payload TEXT NOT NULL)')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS navigation_source ON navigation(source_key) WHERE source_key IS NOT NULL')
        return conn

    def list(self):
        with self.db.lock:
            rows = self._connection().execute('SELECT payload FROM navigation').fetchall()
        return sorted((json.loads(row[0]) for row in rows), key=lambda e: (e['sortOrder'], e['name'], e['id']))

    def save(self, entry):
        with self.db.lock:
            conn = self._connection()
            with conn:
                if entry.id:
                    existing = conn.execute('SELECT source_key FROM navigation WHERE id=?', (entry.id,)).fetchone()
                    if existing is None:
                        raise KeyError('导航项目不存在')
                    entry.sourceKey = existing[0] or ''
                else:
                    if entry.sourceKey:
                        existing = conn.execute('SELECT payload FROM navigation WHERE source_key=?', (entry.sourceKey,)).fetchone()
                        if existing:
                            return json.loads(existing[0])
                    if conn.execute('SELECT COUNT(*) FROM navigation').fetchone()[0] >= 200:
                        raise ValueError('最多保存 200 个导航项目')
                    entry = entry.model_copy(update={'id': str(uuid.uuid4())})
                data = entry.model_dump()
                conn.execute('INSERT INTO navigation VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                             (entry.id, entry.sourceKey or None, json.dumps(data, ensure_ascii=False)))
        return data

    def delete(self, entry_id):
        with self.db.lock:
            conn = self._connection()
            with conn:
                if not conn.execute('DELETE FROM navigation WHERE id=?', (entry_id,)).rowcount:
                    raise KeyError('导航项目不存在')
