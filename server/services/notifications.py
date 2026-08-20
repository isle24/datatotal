import json
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime
from typing import Optional


DEFAULT_NOTIFY_TITLE_TEMPLATE = "{app} {rule_name}"
LEGACY_NOTIFY_BODY_TEMPLATE = (
    "告警：{message}\n"
    "当前值：{value}\n"
    "阈值：{threshold}\n"
    "时间：{timestamp}\n"
    "规则：{rule_id}"
)
DEFAULT_NOTIFY_BODY_TEMPLATE = LEGACY_NOTIFY_BODY_TEMPLATE.replace("{value}", "{value_human}").replace(
    "{threshold}", "{threshold_human}"
)


def safe_notification_detail(value: str, channel: dict) -> str:
    cleaned = str(value or "")
    secrets = {
        str(channel.get("token") or "").strip(),
        str(channel.get("url") or "").strip(),
        channel_target_url(channel),
    }
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned[:500]


def sanitize_http_url(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    try:
        parsed = urllib.parse.urlparse(cleaned)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return cleaned


def channel_target_url(channel: dict) -> str:
    url = sanitize_http_url(channel.get("url") or "")
    token = (channel.get("token") or "").strip()
    channel_type = (channel.get("type") or "webhook").strip().lower()
    if url:
        return url
    if channel_type == "iyuu" and token:
        return f"https://iyuu.cn/{urllib.parse.quote(token, safe='')}.send"
    if channel_type == "meow" and token:
        return f"https://api.chuckfang.com/{urllib.parse.quote(token, safe='')}"
    return ""


def notification_context(alert: dict, channel: dict, app_name: str, app_version: str) -> dict:
    ts = float(alert.get("timestamp") or datetime.now().timestamp())
    metrics = alert.get("metrics") or []
    matched_metrics = alert.get("matchedMetrics") or []
    evidence = alert.get("evidence") or {}
    actual = evidence.get("actual") or {}
    threshold_meta = evidence.get("threshold") or {}
    return {
        "app": app_name,
        "version": app_version,
        "channel_id": channel.get("id") or "",
        "channel_name": channel.get("name") or "",
        "channel_type": channel.get("type") or "",
        "alert_id": alert.get("id") or "",
        "rule_id": alert.get("ruleId") or alert.get("type") or "",
        "rule_name": alert.get("message") or "",
        "message": alert.get("message") or "",
        "severity": alert.get("severity") or "",
        "value": alert.get("value", ""),
        "threshold": alert.get("threshold", ""),
        "value_human": actual.get("label") or alert.get("value", ""),
        "threshold_human": threshold_meta.get("label") or alert.get("threshold", ""),
        "timestamp": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
        "iso_time": datetime.fromtimestamp(ts).isoformat(timespec="seconds"),
        "container_id": alert.get("containerId") or "",
        "container_name": alert.get("containerName") or "",
        "container_action": alert.get("action") or "",
        "container_state": (alert.get("state") or {}).get("lastAction") or "",
        "container_reason": (alert.get("state") or {}).get("reason") or "",
        "matched_metrics": ", ".join(str(item) for item in matched_metrics if item) or "",
        "container_metrics": ", ".join(
            f"{item.get('metric')}={item.get('value')}"
            for item in metrics
            if isinstance(item, dict)
        ),
    }


def render_template(template: str, context: dict) -> str:
    source = template or ""
    try:
        return source.format_map(defaultdict(str, {key: str(value) for key, value in context.items()}))
    except Exception:
        result = source
        for key, value in context.items():
            result = result.replace("{" + key + "}", str(value))
        return result


def build_notification_request(alert: dict, channel: dict, app_name: str, app_version: str) -> Optional[urllib.request.Request]:
    target = channel_target_url(channel)
    if not target:
        return None
    channel_type = (channel.get("type") or "webhook").strip().lower()
    context = notification_context(alert, channel, app_name, app_version)
    title = render_template(channel.get("titleTemplate") or DEFAULT_NOTIFY_TITLE_TEMPLATE, context)[:500]
    body = render_template(channel.get("bodyTemplate") or DEFAULT_NOTIFY_BODY_TEMPLATE, context)[:4000]
    link = sanitize_http_url(render_template(channel.get("urlTemplate") or "", context))
    msg_type = (channel.get("msgType") or "text").strip().lower()
    msg_type = msg_type if msg_type in {"text", "html"} else "text"
    html_height = max(100, min(1200, int(channel.get("htmlHeight") or 200)))

    if channel_type == "iyuu":
        data = urllib.parse.urlencode({"text": title or app_name, "desp": body}).encode()
        return urllib.request.Request(
            target,
            data=data,
            headers={"content-type": "application/x-www-form-urlencoded", "user-agent": "nas-traffic-lens/1.0"},
            method="POST",
        )

    if channel_type == "meow":
        parsed = urllib.parse.urlparse(target)
        query = urllib.parse.urlencode({"msgType": msg_type, "htmlHeight": html_height})
        target = urllib.parse.urlunparse(parsed._replace(query=query))
        data = json.dumps({"title": title or app_name, "msg": body, "url": link}, ensure_ascii=False, separators=(",", ":")).encode()
        return urllib.request.Request(
            target,
            data=data,
            headers={"content-type": "application/json", "user-agent": "nas-traffic-lens/1.0"},
            method="POST",
        )

    payload = {
        "app": app_name,
        "version": app_version,
        "channel": {"id": channel.get("id"), "name": channel.get("name"), "type": channel.get("type")},
        "alert": alert,
        "title": title,
        "text": body,
        "url": link,
        "timestamp": int(alert.get("timestamp") or datetime.now().timestamp()),
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return urllib.request.Request(
        target,
        data=data,
        headers={"content-type": "application/json", "user-agent": "nas-traffic-lens/1.0"},
        method="POST",
    )


def send_notification_alert(alert: dict, channel: dict, app_name: str, app_version: str, raise_error: bool = False) -> dict:
    request = build_notification_request(alert, channel, app_name, app_version)
    if not request:
        result = {"ok": False, "detail": "missing notification target"}
        if raise_error:
            raise ValueError(result["detail"])
        return result
    try:
        with urllib.request.urlopen(request, timeout=max(1, min(30, float(channel.get("timeout") or 5)))) as response:
            body = response.read(2048).decode(errors="ignore")
            return {"ok": 200 <= response.status < 300, "status": response.status, "body": safe_notification_detail(body, channel)}
    except Exception as exc:
        if raise_error:
            raise
        return {"ok": False, "detail": safe_notification_detail(str(exc), channel)}
