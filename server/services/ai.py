"""Small OpenAI-compatible client used only for explicit user-triggered analysis."""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional


DEFAULT_AI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_AI_MODEL = "gpt-4o-mini"
DEFAULT_AI_SYSTEM_PROMPT = (
    "你是 NAS Traffic Lens 的流量分析助手。请基于提供的统计摘要回答问题，"
    "区分公网和内网，不要把未知数据猜成事实。优先给出结论、证据和可执行建议。"
)
MAX_AI_RESPONSE_BYTES = 2 * 1024 * 1024


class AIServiceError(RuntimeError):
    """An actionable, user-safe error from the AI provider."""


def default_ai_settings() -> dict:
    return {
        "enabled": False,
        "baseUrl": DEFAULT_AI_BASE_URL,
        "apiKey": "",
        "model": DEFAULT_AI_MODEL,
        "timeoutSeconds": 30,
        "maxTokens": 1200,
        "systemPrompt": DEFAULT_AI_SYSTEM_PROMPT,
    }


def _clean_base_url(value: str) -> str:
    cleaned = str(value or "").strip().rstrip("/")
    if len(cleaned) > 300:
        return ""
    try:
        parsed = urllib.parse.urlsplit(cleaned)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username or parsed.password:
        return ""
    return cleaned


def normalize_ai_settings(payload: Optional[dict], existing: Optional[dict] = None) -> dict:
    current = {**default_ai_settings(), **(existing or {})}
    data = payload if isinstance(payload, dict) else {}
    base_url = _clean_base_url(data.get("baseUrl")) or _clean_base_url(current.get("baseUrl")) or DEFAULT_AI_BASE_URL
    api_key = str(data.get("apiKey") or "").strip()
    if not api_key or ("..." in api_key and current.get("apiKey")):
        api_key = str(current.get("apiKey") or "").strip()
    try:
        timeout = max(5, min(30, int(data.get("timeoutSeconds", current.get("timeoutSeconds", 30)))))
    except (TypeError, ValueError):
        timeout = 30
    try:
        max_tokens = max(128, min(4096, int(data.get("maxTokens", current.get("maxTokens", 1200)))))
    except (TypeError, ValueError):
        max_tokens = 1200
    model = str(data.get("model", current.get("model", DEFAULT_AI_MODEL)) or DEFAULT_AI_MODEL).strip()[:160]
    prompt = str(data.get("systemPrompt", current.get("systemPrompt", DEFAULT_AI_SYSTEM_PROMPT)) or DEFAULT_AI_SYSTEM_PROMPT).strip()[:4000]
    return {
        "enabled": bool(data.get("enabled", current.get("enabled", False))),
        "baseUrl": base_url,
        "apiKey": api_key[:512],
        "model": model or DEFAULT_AI_MODEL,
        "timeoutSeconds": timeout,
        "maxTokens": max_tokens,
        "systemPrompt": prompt or DEFAULT_AI_SYSTEM_PROMPT,
    }


def public_ai_settings(settings: Optional[dict]) -> dict:
    normalized = normalize_ai_settings(settings)
    key = normalized["apiKey"]
    masked = f"{key[:3]}...{key[-3:]}" if len(key) > 6 else ("*" * len(key))
    return {
        "enabled": normalized["enabled"],
        "baseUrl": normalized["baseUrl"],
        "model": normalized["model"],
        "timeoutSeconds": normalized["timeoutSeconds"],
        "maxTokens": normalized["maxTokens"],
        "systemPrompt": normalized["systemPrompt"],
        "keyConfigured": bool(key),
        "apiKeyMasked": masked,
    }


def _response_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise AIServiceError("AI 服务没有返回内容")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    content = str(content or "").strip()
    if not content:
        raise AIServiceError("AI 服务返回了空内容")
    return content[:20000]


def chat_completion(settings: dict, messages: List[Dict[str, str]]) -> dict:
    normalized = normalize_ai_settings(settings)
    if not normalized["enabled"] or not normalized["apiKey"]:
        raise AIServiceError("请先在设置中启用 AI 并填写 API Key")
    endpoint = normalized["baseUrl"].rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": normalized["model"],
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": normalized["maxTokens"],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {normalized['apiKey']}",
            "User-Agent": "NAS-Traffic-Lens/AI",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=normalized["timeoutSeconds"]) as response:
            raw = response.read(MAX_AI_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(4096).decode("utf-8", errors="replace")
        except OSError:
            detail = ""
        raise AIServiceError(f"AI 服务 HTTP {exc.code}：{detail[:300] or exc.reason}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AIServiceError(f"AI 服务连接失败：{str(exc)[:240]}") from None
    if len(raw) > MAX_AI_RESPONSE_BYTES:
        raise AIServiceError("AI 服务响应过大")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AIServiceError("AI 服务返回了无效 JSON") from None
    return {"answer": _response_text(data), "model": normalized["model"], "usage": data.get("usage") or {}}
