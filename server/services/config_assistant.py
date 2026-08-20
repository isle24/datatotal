"""Policy and short-lived state for confirmation-based AI configuration."""

import copy
import json
import secrets
import threading
import time
from typing import Optional


MAX_CONFIGURATION_CHANGES = 50
MAX_CONFIGURATION_VALUE_BYTES = 32 * 1024
MAX_CONFIGURATION_RESPONSE_CHARS = 128 * 1024
MAX_CONFIGURATION_PROPOSALS = 64
DEFAULT_PROPOSAL_TTL_SECONDS = 600


_FIELDS = (
    {"path": "runtime.sampleSeconds", "type": "number", "min": 0.5, "max": 30, "label": "采样间隔（秒）"},
    {"path": "runtime.retentionSeconds", "type": "integer", "min": 60, "max": 86400, "label": "实时数据保留（秒）"},
    {"path": "runtime.persistIntervalSeconds", "type": "integer", "min": 10, "max": 3600, "label": "历史写入间隔（秒）"},
    {"path": "runtime.historyRetentionDays", "type": "integer", "min": 1, "max": 3650, "label": "历史保留（天）"},
    {"path": "runtime.connectionActiveSeconds", "type": "integer", "min": 10, "max": 3600, "label": "连接活动窗口（秒）"},
    {"path": "runtime.connectionRetentionSeconds", "type": "integer", "min": 60, "max": 86400, "label": "连接明细保留（秒）"},
    {"path": "runtime.conntrackRefreshSeconds", "type": "integer", "min": 2, "max": 300, "label": "Conntrack 刷新（秒）"},
    {"path": "runtime.autoStartStage", "type": "boolean", "label": "自动阶段统计"},
    {"path": "runtime.dockerDiscovery", "type": "boolean", "label": "Docker 自动发现"},
    {"path": "monitor.rules", "type": "array", "maxItems": 100, "label": "流量监控规则"},
    {"path": "notifications.channels", "type": "array", "maxItems": 50, "label": "通知渠道非敏感配置"},
    {"path": "containerProtection.rules", "type": "array", "maxItems": 100, "label": "容器保护规则"},
    {"path": "docker.containers", "type": "object", "maxItems": 500, "label": "Docker 端口和标签配置"},
    {"path": "ai.enabled", "type": "boolean", "label": "启用 AI"},
    {
        "path": "ai.provider",
        "type": "string",
        "enum": ["openai", "claude", "deepseek", "kimi", "qwen", "minimax", "custom"],
        "label": "AI 厂商",
    },
    {"path": "ai.baseUrl", "type": "string", "maxLength": 300, "label": "AI Base URL"},
    {"path": "ai.model", "type": "string", "maxLength": 160, "label": "AI 模型"},
    {"path": "ai.timeoutSeconds", "type": "integer", "min": 5, "max": 180, "label": "AI 超时（秒）"},
    {"path": "ai.maxTokens", "type": "integer", "min": 128, "max": 393216, "label": "AI 最大输出 Token"},
    {"path": "ai.systemPrompt", "type": "string", "maxLength": 4000, "label": "AI 系统提示词"},
)

CONFIGURATION_SCHEMA = {item["path"]: dict(item) for item in _FIELDS}
_SENSITIVE_PARTS = {
    "apikey",
    "api_key",
    "token",
    "password",
    "secret",
    "dockersocket",
    "dbpath",
    "logpath",
    "logdir",
    "command",
    "sql",
    "environment",
    "env",
}


def configuration_schema() -> dict:
    return {
        "version": 1,
        "maxChanges": MAX_CONFIGURATION_CHANGES,
        "proposalTtlSeconds": DEFAULT_PROPOSAL_TTL_SECONDS,
        "fields": [copy.deepcopy(item) for item in _FIELDS],
        "rules": [
            "Only return paths listed in fields.",
            "Never request, read, replace or remove passwords, API keys, tokens, sockets, paths, SQL or commands.",
            "Return JSON only with a changes array.",
        ],
    }


def parse_configuration_response(text: str) -> list[dict]:
    cleaned = str(text or "").strip()
    if not cleaned or len(cleaned) > MAX_CONFIGURATION_RESPONSE_CHARS:
        raise ValueError("AI 配置响应为空或过大")
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        payload = json.loads(cleaned)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("AI 未返回有效的设置 JSON") from None
    changes = payload.get("changes") if isinstance(payload, dict) else None
    if not isinstance(changes, list) or not changes:
        raise ValueError("AI 设置 JSON 缺少 changes")
    if len(changes) > MAX_CONFIGURATION_CHANGES:
        raise ValueError("AI 设置变更数量过多")
    return changes


def _path_value(current: dict, path: str):
    value = current
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return copy.deepcopy(value)


def _has_sensitive_part(value: str) -> bool:
    sensitive = {part.replace("_", "") for part in _SENSITIVE_PARTS}
    extended = {"authtoken", "accesstoken", "refreshtoken", "webhooktoken", "apitoken"}
    for part in str(value or "").split("."):
        normalized = part.replace("-", "").replace("_", "").lower()
        if normalized in sensitive or normalized in extended:
            return True
    return False


def _assert_no_sensitive_keys(value) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if _has_sensitive_part(str(key)):
                raise ValueError(f"不允许修改敏感字段：{key}")
            _assert_no_sensitive_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_sensitive_keys(nested)


def _validate_value(field: dict, value):
    value_type = field["type"]
    if value_type == "boolean":
        valid = isinstance(value, bool)
    elif value_type == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif value_type == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif value_type == "string":
        valid = isinstance(value, str)
    elif value_type == "array":
        valid = isinstance(value, list)
    elif value_type == "object":
        valid = isinstance(value, dict)
    else:
        valid = False
    if not valid:
        raise ValueError(f"设置 {field['path']} 的类型无效")
    if "min" in field and value < field["min"]:
        raise ValueError(f"设置 {field['path']} 低于最小值 {field['min']}")
    if "max" in field and value > field["max"]:
        raise ValueError(f"设置 {field['path']} 高于最大值 {field['max']}")
    if "maxLength" in field and len(value) > field["maxLength"]:
        raise ValueError(f"设置 {field['path']} 文字过长")
    if "maxItems" in field and len(value) > field["maxItems"]:
        raise ValueError(f"设置 {field['path']} 项目过多")
    if field.get("enum") and value not in field["enum"]:
        raise ValueError(f"设置 {field['path']} 的值不在允许范围")
    _assert_no_sensitive_keys(value)
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        raise ValueError(f"设置 {field['path']} 的值不能序列化") from None
    if len(encoded) > MAX_CONFIGURATION_VALUE_BYTES:
        raise ValueError(f"设置 {field['path']} 的值过大")
    return copy.deepcopy(value)


def validate_configuration_changes(changes: list[dict], current: dict) -> list[dict]:
    if not isinstance(changes, list) or not changes:
        raise ValueError("AI 没有生成设置变更")
    if len(changes) > MAX_CONFIGURATION_CHANGES:
        raise ValueError("AI 设置变更数量过多")
    validated = []
    seen = set()
    for item in changes:
        if not isinstance(item, dict):
            raise ValueError("AI 设置变更格式无效")
        path = str(item.get("path") or "").strip()
        if _has_sensitive_part(path):
            raise ValueError(f"不允许修改敏感设置：{path}")
        field = CONFIGURATION_SCHEMA.get(path)
        if not field:
            raise ValueError(f"未知设置路径：{path or '-'}")
        if path in seen:
            raise ValueError(f"设置路径重复：{path}")
        seen.add(path)
        value = item.get("value", item.get("newValue"))
        validated.append(
            {
                "path": path,
                "oldValue": _path_value(current, path),
                "newValue": _validate_value(field, value),
                "summary": str(item.get("summary") or field["label"]).strip()[:240],
                "risk": str(item.get("risk") or "低").strip()[:40],
            }
        )
    return validated


class ProposalStore:
    def __init__(self, ttl_seconds: int = DEFAULT_PROPOSAL_TTL_SECONDS, max_entries: int = MAX_CONFIGURATION_PROPOSALS):
        self.ttl_seconds = max(1, min(3600, int(ttl_seconds)))
        self.max_entries = max(1, min(256, int(max_entries)))
        self._lock = threading.Lock()
        self._items: dict[str, dict] = {}

    def _prune(self, now_value: float) -> None:
        expired = [key for key, item in self._items.items() if float(item.get("expiresAt") or 0) < now_value]
        for key in expired:
            self._items.pop(key, None)
        while len(self._items) >= self.max_entries:
            oldest = min(self._items, key=lambda key: float(self._items[key].get("createdAt") or 0))
            self._items.pop(oldest, None)

    def put(self, proposal: dict, now_value: Optional[float] = None) -> str:
        timestamp = float(time.time() if now_value is None else now_value)
        proposal_id = secrets.token_urlsafe(24)
        stored = copy.deepcopy(proposal if isinstance(proposal, dict) else {})
        stored.update({"id": proposal_id, "createdAt": timestamp, "expiresAt": timestamp + self.ttl_seconds})
        with self._lock:
            self._prune(timestamp)
            self._items[proposal_id] = stored
        return proposal_id

    def get(self, proposal_id: str, now_value: Optional[float] = None) -> Optional[dict]:
        timestamp = float(time.time() if now_value is None else now_value)
        with self._lock:
            self._prune(timestamp)
            item = self._items.get(str(proposal_id or ""))
            return copy.deepcopy(item) if item else None

    def take(self, proposal_id: str, now_value: Optional[float] = None) -> Optional[dict]:
        timestamp = float(time.time() if now_value is None else now_value)
        with self._lock:
            self._prune(timestamp)
            item = self._items.pop(str(proposal_id or ""), None)
            return copy.deepcopy(item) if item else None
