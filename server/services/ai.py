"""AI provider adapters used only for explicit user-triggered requests."""

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Iterator, List, Optional


DEFAULT_AI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_AI_MODEL = "gpt-4o-mini"
DEFAULT_AI_SYSTEM_PROMPT = (
    "你是 NAS Traffic Lens 的流量分析助手。请基于提供的统计摘要回答问题，"
    "区分公网和内网，不要把未知数据猜成事实。优先给出结论、证据和可执行建议。"
)
MAX_AI_OUTPUT_TOKENS = 393216
MAX_AI_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_AI_RESPONSE_CHARS = 2_000_000
MIN_AI_RESPONSE_CHARS = 20_000
MAX_AI_STREAM_LINE_BYTES = 256 * 1024
MAX_AI_MODELS = 200
MAX_AI_MODEL_ID_LENGTH = 160
AI_MODEL_CACHE_TTL_SECONDS = 60
AI_MODEL_CACHE_MAX_ENTRIES = 16
ANTHROPIC_VERSION = "2023-06-01"


AI_PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "baseUrl": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "protocol": "openai",
        "maxTokens": 1200,
        "contextWindow": 128000,
    },
    "claude": {
        "label": "Claude",
        "baseUrl": "https://api.anthropic.com/v1",
        "model": "claude-3-5-haiku-latest",
        "protocol": "anthropic",
        "maxTokens": 4096,
        "contextWindow": 200000,
    },
    "deepseek": {
        "label": "DeepSeek",
        "baseUrl": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "protocol": "openai",
        "maxTokens": MAX_AI_OUTPUT_TOKENS,
        "contextWindow": 1_000_000,
    },
    "kimi": {
        "label": "Kimi",
        "baseUrl": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "protocol": "openai",
        "maxTokens": 4096,
        "contextWindow": 8192,
    },
    "qwen": {
        "label": "Qwen",
        "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "protocol": "openai",
        "maxTokens": 4096,
        "contextWindow": 131072,
    },
    "minimax": {
        "label": "MiniMax",
        "baseUrl": "https://api.minimaxi.com/v1",
        "model": "MiniMax-Text-01",
        "protocol": "openai",
        "maxTokens": 4096,
        "contextWindow": 1000000,
    },
    "custom": {
        "label": "自定义兼容接口",
        "baseUrl": "",
        "model": "",
        "protocol": "openai",
        "maxTokens": 1200,
        "contextWindow": 128000,
    },
}
_PROVIDER_ALIASES = {"anthropic": "claude", "claude": "claude"}
_model_cache = {}
_model_cache_lock = threading.Lock()


class AIServiceError(RuntimeError):
    """An actionable, user-safe error from the AI provider."""


def default_ai_settings() -> dict:
    preset = AI_PROVIDERS["openai"]
    return {
        "enabled": False,
        "provider": "openai",
        "baseUrl": preset["baseUrl"],
        "apiKey": "",
        "model": preset["model"],
        "timeoutSeconds": 60,
        "maxTokens": preset["maxTokens"],
        "systemPrompt": DEFAULT_AI_SYSTEM_PROMPT,
    }


def _provider_name(value: object) -> str:
    normalized = str(value or "openai").strip().lower()
    normalized = _PROVIDER_ALIASES.get(normalized, normalized)
    return normalized if normalized in AI_PROVIDERS else "custom"


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
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ""
    try:
        if not parsed.hostname or parsed.port is not None and not (1 <= parsed.port <= 65535):
            return ""
    except ValueError:
        return ""
    if re.search(r"(?:api[_-]?key|token|secret|password)", cleaned.lower()):
        return ""
    return cleaned


def normalize_ai_settings(payload: Optional[dict], existing: Optional[dict] = None) -> dict:
    current = {**default_ai_settings(), **(existing or {})}
    data = payload if isinstance(payload, dict) else {}
    provider = _provider_name(data.get("provider", current.get("provider", "openai")))
    preset = AI_PROVIDERS[provider]
    current_provider = _provider_name(current.get("provider", "openai"))
    provider_changed = "provider" in data and provider != current_provider

    requested_base = data.get("baseUrl")
    if provider_changed and (
        not str(requested_base or "").strip()
        or _clean_base_url(requested_base) == _clean_base_url(current.get("baseUrl"))
        or _clean_base_url(requested_base) == DEFAULT_AI_BASE_URL
    ):
        requested_base = preset["baseUrl"]
    base_url = (
        _clean_base_url(requested_base)
        or _clean_base_url(current.get("baseUrl"))
        or _clean_base_url(preset["baseUrl"])
        or DEFAULT_AI_BASE_URL
    )

    api_key = str(data.get("apiKey") or "").strip()
    if not api_key or ("..." in api_key and current.get("apiKey")):
        api_key = str(current.get("apiKey") or "").strip()
    try:
        timeout = max(5, min(180, int(data.get("timeoutSeconds", current.get("timeoutSeconds", 60)))))
    except (TypeError, ValueError, OverflowError):
        timeout = 60
    try:
        requested_max_tokens = data.get("maxTokens")
        if requested_max_tokens is None:
            requested_max_tokens = preset["maxTokens"] if provider_changed else current.get("maxTokens", preset["maxTokens"])
        max_tokens = max(128, min(MAX_AI_OUTPUT_TOKENS, int(requested_max_tokens)))
    except (TypeError, ValueError, OverflowError):
        max_tokens = preset["maxTokens"]

    requested_model = data.get("model")
    if provider_changed and (
        not str(requested_model or "").strip()
        or str(requested_model).strip() == str(current.get("model") or DEFAULT_AI_MODEL).strip()
    ):
        requested_model = preset["model"]
    model = str(requested_model if requested_model is not None else current.get("model", preset["model"]) or "").strip()[:160]
    if not model:
        model = str(preset["model"] or DEFAULT_AI_MODEL)
    prompt = str(data.get("systemPrompt", current.get("systemPrompt", DEFAULT_AI_SYSTEM_PROMPT)) or DEFAULT_AI_SYSTEM_PROMPT).strip()[:4000]
    return {
        "enabled": bool(data.get("enabled", current.get("enabled", False))),
        "provider": provider,
        "baseUrl": base_url,
        "apiKey": api_key[:512],
        "model": model,
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
        "provider": normalized["provider"],
        "baseUrl": normalized["baseUrl"],
        "model": normalized["model"],
        "timeoutSeconds": normalized["timeoutSeconds"],
        "maxTokens": normalized["maxTokens"],
        "systemPrompt": normalized["systemPrompt"],
        "keyConfigured": bool(key),
        "apiKeyMasked": masked,
    }


def _provider_protocol(settings: dict) -> str:
    provider = _provider_name(settings.get("provider"))
    return AI_PROVIDERS[provider]["protocol"]


def _request_headers(settings: dict) -> dict:
    normalized = normalize_ai_settings(settings)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "NAS-Traffic-Lens/AI",
    }
    if _provider_protocol(normalized) == "anthropic":
        headers.update({"x-api-key": normalized["apiKey"], "anthropic-version": ANTHROPIC_VERSION})
    else:
        headers["Authorization"] = f"Bearer {normalized['apiKey']}"
    return headers


def _endpoint(settings: dict, suffix: str) -> str:
    normalized = normalize_ai_settings(settings)
    return normalized["baseUrl"].rstrip("/") + suffix


def _anthropic_messages(messages: List[Dict[str, str]]) -> tuple[str, list]:
    system_parts = []
    converted = []
    for item in messages:
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "")
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        converted.append({"role": "assistant" if role == "assistant" else "user", "content": content})
    return "\n\n".join(system_parts), converted


def build_ai_request(
    settings: dict,
    messages: List[Dict[str, str]],
    stream: bool = False,
) -> urllib.request.Request:
    normalized = normalize_ai_settings(settings)
    if _provider_protocol(normalized) == "anthropic":
        system, converted = _anthropic_messages(messages)
        payload = {
            "model": normalized["model"],
            "messages": converted,
            "max_tokens": normalized["maxTokens"],
            "temperature": 0.2,
        }
        if system:
            payload["system"] = system
        endpoint = _endpoint(normalized, "/messages")
    else:
        payload = {
            "model": normalized["model"],
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": normalized["maxTokens"],
        }
        endpoint = _endpoint(normalized, "/chat/completions")
    if stream:
        payload["stream"] = True
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return urllib.request.Request(endpoint, data=body, method="POST", headers=_request_headers(normalized))


def _models_request(settings: dict) -> urllib.request.Request:
    return urllib.request.Request(
        _endpoint(settings, "/models"),
        method="GET",
        headers=_request_headers(settings),
    )


def _safe_error_detail(value: object, secret: str = "") -> str:
    detail = str(value or "")
    if secret:
        detail = detail.replace(secret, "[redacted]")
    return detail[:300]


def _read_json(request: urllib.request.Request, timeout: int, secret: str = "") -> dict:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_AI_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(4096).decode("utf-8", errors="replace")
        except OSError:
            detail = ""
        raise AIServiceError(f"AI 服务 HTTP {exc.code}：{_safe_error_detail(detail, secret) or exc.reason}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AIServiceError(f"AI 服务连接失败：{_safe_error_detail(exc, secret)[:240]}") from None
    if len(raw) > MAX_AI_RESPONSE_BYTES:
        raise AIServiceError("AI 服务响应过大")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AIServiceError("AI 服务返回了无效 JSON") from None
    if not isinstance(data, dict):
        raise AIServiceError("AI 服务返回了无效数据")
    return data


def _finish_reason(value: object) -> str:
    return "length" if str(value or "").strip().lower() in {"length", "max_tokens"} else "stop"


def _completion_metadata(data: dict, protocol: str) -> tuple[str, bool]:
    if protocol == "anthropic":
        reason = data.get("stop_reason")
    else:
        choices = data.get("choices") or []
        reason = choices[0].get("finish_reason") if choices and isinstance(choices[0], dict) else None
    if not reason:
        return "stop", False
    normalized = _finish_reason(reason)
    return normalized, normalized == "length"


def _response_char_limit(settings: dict) -> int:
    normalized = normalize_ai_settings(settings)
    return min(MAX_AI_RESPONSE_CHARS, max(MIN_AI_RESPONSE_CHARS, normalized["maxTokens"] * 4))


def _response_text(data: dict, protocol: str = "openai", max_chars: int = MAX_AI_RESPONSE_CHARS) -> tuple[str, str, bool]:
    if protocol == "anthropic":
        content = data.get("content") or []
        text = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict) and item.get("type") == "text")
    else:
        choices = data.get("choices") or []
        if not choices:
            raise AIServiceError("AI 服务没有返回内容")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
        text = str(content or "")
    text = text.strip()
    if not text:
        raise AIServiceError("AI 服务返回了空内容")
    finish_reason, provider_truncated = _completion_metadata(data, protocol)
    text_truncated = len(text) > max_chars
    return text[:max_chars], finish_reason if not text_truncated else "client_limit", provider_truncated or text_truncated


def chat_completion(settings: dict, messages: List[Dict[str, str]]) -> dict:
    normalized = normalize_ai_settings(settings)
    if not normalized["enabled"] or not normalized["apiKey"]:
        raise AIServiceError("请先在设置中启用 AI 并填写 API Key")
    data = _read_json(build_ai_request(normalized, messages), normalized["timeoutSeconds"], normalized["apiKey"])
    answer, finish_reason, truncated = _response_text(data, _provider_protocol(normalized), _response_char_limit(normalized))
    return {
        "answer": answer,
        "model": normalized["model"],
        "usage": data.get("usage") or {},
        "finishReason": finish_reason,
        "truncated": truncated,
    }


def _stream_text(data: dict, protocol: str) -> str:
    if protocol == "anthropic":
        if data.get("type") != "content_block_delta":
            return ""
        delta = data.get("delta") or {}
        return str(delta.get("text") or "") if delta.get("type") == "text_delta" else ""
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    content = (choices[0].get("delta") or {}).get("content")
    if isinstance(content, list):
        return "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return str(content or "")


def _stream_usage(data: dict, protocol: str, current: dict) -> dict:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return current
    if protocol == "anthropic":
        return {**current, **usage}
    return usage


def _stream_error(data: dict) -> str:
    if data.get("type") != "error":
        return ""
    error = data.get("error") or {}
    if isinstance(error, dict):
        return str(error.get("message") or error.get("type") or "AI 服务流式响应失败")
    return str(error or "AI 服务流式响应失败")


def chat_completion_stream(settings: dict, messages: List[Dict[str, str]]) -> Iterator[dict]:
    normalized = normalize_ai_settings(settings)
    if not normalized["enabled"] or not normalized["apiKey"]:
        raise AIServiceError("请先在设置中启用 AI 并填写 API Key")

    request = build_ai_request(normalized, messages, stream=True)
    protocol = _provider_protocol(normalized)
    answer_parts = []
    answer_length = 0
    total_bytes = 0
    usage = {}
    finish_reason = "connection_closed"
    provider_marker_seen = False
    truncated = False
    response_char_limit = _response_char_limit(normalized)
    try:
        with urllib.request.urlopen(request, timeout=normalized["timeoutSeconds"]) as response:
            while True:
                raw_line = response.readline(MAX_AI_STREAM_LINE_BYTES + 1)
                if not raw_line:
                    break
                total_bytes += len(raw_line)
                if len(raw_line) > MAX_AI_STREAM_LINE_BYTES or total_bytes > MAX_AI_RESPONSE_BYTES:
                    raise AIServiceError("AI 服务流式响应过大")
                try:
                    line = raw_line.decode("utf-8").strip()
                except UnicodeDecodeError:
                    raise AIServiceError("AI 服务返回了无效流式数据") from None
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload:
                    continue
                if payload == "[DONE]":
                    provider_marker_seen = True
                    finish_reason = finish_reason if finish_reason == "length" else "stop"
                    break
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    raise AIServiceError("AI 服务返回了无效流式 JSON") from None
                if not isinstance(data, dict):
                    continue
                if protocol == "anthropic" and data.get("type") == "message_stop":
                    provider_marker_seen = True
                    finish_reason = finish_reason if finish_reason == "length" else "stop"
                if protocol == "anthropic":
                    delta = data.get("delta") or {}
                    if isinstance(delta, dict) and delta.get("stop_reason"):
                        finish_reason = _finish_reason(delta.get("stop_reason"))
                else:
                    choices = data.get("choices") or []
                    if choices and isinstance(choices[0], dict) and choices[0].get("finish_reason"):
                        finish_reason = _finish_reason(choices[0].get("finish_reason"))
                provider_error = _stream_error(data)
                if provider_error:
                    raise AIServiceError(f"AI 服务返回错误：{_safe_error_detail(provider_error, normalized['apiKey'])}")
                usage = _stream_usage(data, protocol, usage)
                content = _stream_text(data, protocol)
                if not content:
                    continue
                remaining = response_char_limit - answer_length
                if remaining <= 0:
                    finish_reason = "client_limit"
                    truncated = True
                    break
                content = content[:remaining]
                answer_parts.append(content)
                answer_length += len(content)
                yield {"type": "delta", "content": content}
                if len(content) < len(_stream_text(data, protocol)):
                    finish_reason = "client_limit"
                    truncated = True
                    break
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(4096).decode("utf-8", errors="replace")
        except OSError:
            detail = ""
        raise AIServiceError(
            f"AI 服务 HTTP {exc.code}：{_safe_error_detail(detail, normalized['apiKey']) or exc.reason}"
        ) from None
    except AIServiceError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AIServiceError(
            f"AI 服务连接失败：{_safe_error_detail(exc, normalized['apiKey'])[:240]}"
        ) from None

    answer = "".join(answer_parts).strip()
    if not answer:
        raise AIServiceError("AI 服务返回了空内容")
    if not provider_marker_seen and not truncated and finish_reason != "length":
        finish_reason = "connection_closed"
    truncated = truncated or finish_reason in {"length", "connection_closed", "client_limit"}
    yield {
        "type": "done",
        "answer": answer,
        "model": normalized["model"],
        "usage": usage,
        "finishReason": finish_reason,
        "truncated": truncated,
    }


def normalize_model_list(data: dict) -> list:
    raw_models = data.get("data") if isinstance(data, dict) else []
    if not isinstance(raw_models, list) and isinstance(data, dict):
        raw_models = data.get("models")
    if not isinstance(raw_models, list):
        return []
    models = []
    seen = set()
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id or len(model_id) > MAX_AI_MODEL_ID_LENGTH or model_id in seen:
            continue
        name = str(item.get("display_name") or item.get("name") or model_id).strip()[:200] or model_id
        models.append({"id": model_id, "name": name})
        seen.add(model_id)
        if len(models) >= MAX_AI_MODELS:
            break
    return models


def _model_cache_key(settings: dict) -> tuple:
    normalized = normalize_ai_settings(settings)
    digest = hashlib.sha256(normalized["apiKey"].encode("utf-8")).hexdigest()[:16]
    return normalized["provider"], normalized["baseUrl"], digest


def list_models(settings: dict, refresh: bool = False) -> dict:
    normalized = normalize_ai_settings(settings)
    if not normalized["apiKey"]:
        raise AIServiceError("请先填写 API Key")
    key = _model_cache_key(normalized)
    current_time = time.monotonic()
    with _model_cache_lock:
        cached = _model_cache.get(key)
        if cached and not refresh and current_time - cached["cachedAt"] < AI_MODEL_CACHE_TTL_SECONDS:
            if cached.get("error"):
                raise AIServiceError(cached["error"])
            return {"provider": normalized["provider"], "models": cached["models"], "cached": True}
    try:
        data = _read_json(_models_request(normalized), normalized["timeoutSeconds"], normalized["apiKey"])
        models = normalize_model_list(data)
        if not models:
            raise AIServiceError("AI 服务未返回可用模型，请手动填写模型名称")
    except AIServiceError as exc:
        with _model_cache_lock:
            _model_cache[key] = {"cachedAt": current_time, "models": [], "error": str(exc)}
        raise
    with _model_cache_lock:
        _model_cache[key] = {"cachedAt": current_time, "models": models}
        while len(_model_cache) > AI_MODEL_CACHE_MAX_ENTRIES:
            oldest = min(_model_cache, key=lambda item: _model_cache[item]["cachedAt"])
            _model_cache.pop(oldest, None)
    return {"provider": normalized["provider"], "models": models, "cached": False}
