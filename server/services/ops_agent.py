"""Read-only operations agent.

A natural-language question becomes at most two model calls:

1. **plan** — pick one whitelisted read-only tool plus its arguments (strict JSON)
2. **answer** — explain the tool result in the user's language

Everything in between is deterministic code: argument validation against a
declarative schema, execution through a read-only collector facade, secret
redaction, size trimming and an audit trail. The model never sees a write tool,
never receives credentials, and never decides which code path runs.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import ai

RISK_READ = "read"

MAX_LIMIT = 50
DEFAULT_LIMIT = 10
MAX_STRING = 240
MAX_RESULT_CHARS = 6000

# Tool parameter schemas -----------------------------------------------------
_PERIOD_HISTORY = {"type": "enum", "values": ["day", "week", "month", "year"], "default": "day",
                   "description": "统计周期：day=今天，week=本周，month=本月，year=今年"}
_PERIOD_PROCESS = {"type": "enum", "values": ["30s", "today", "1d", "3d", "7d"], "default": "30s",
                   "description": "进程统计窗口：30s=实时快照，today=今天，1d/3d/7d=最近若干天"}
_METRIC = {"type": "enum", "values": ["upload", "download", "total"], "default": "upload",
           "description": "排行依据：upload=上传，download=下载，total=合计"}
_LIMIT = {"type": "int", "min": 1, "max": MAX_LIMIT, "default": DEFAULT_LIMIT,
          "description": f"返回条数上限（1-{MAX_LIMIT}）"}
_SCOPE = {"type": "enum", "values": ["wan", "lan", "all"], "default": "wan",
          "description": "连接范围：wan=公网，lan=内网，all=全部"}
_DIRECTION = {"type": "enum", "values": ["all", "rx", "tx"], "default": "all",
              "description": "方向：all/rx(下行)/tx(上行)"}
_CONTAINER = {"type": "string", "maxLength": 64, "required": True,
              "description": "容器名或 ID（支持部分匹配）"}

_SECRET_KEY_RE = re.compile(
    r"(pass(word|wd)?|token|secret|api[_-]?key|authorization|credential|webhook|apikey)",
    re.IGNORECASE,
)
_LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")


# -- formatting helpers ------------------------------------------------------
def format_bytes(value: Any) -> str:
    try:
        size = max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.0f} {units[index]}" if size >= 10 or index == 0 else f"{size:.1f} {units[index]}"


def format_rate(value: Any) -> str:
    return f"{format_bytes(value)}/s"


def format_duration(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        return "-"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}天{hours}小时"
    if hours:
        return f"{hours}小时{minutes}分"
    if minutes:
        return f"{minutes}分"
    return f"{total}秒"


# -- redaction ---------------------------------------------------------------
def redact(value: Any, key: str = "") -> Any:
    """Drop secrets and shorten long strings before anything leaves the box."""
    if key and _SECRET_KEY_RE.search(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(name): redact(item, str(name)) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        text = value if len(value) <= MAX_STRING else f"{value[:MAX_STRING]}…"
        return _LONG_TOKEN_RE.sub("[redacted]", text)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_STRING]


def trim_payload(payload: Any, max_chars: int = MAX_RESULT_CHARS) -> Any:
    """Guarantee a bounded tool result so one answer cannot blow up the context."""
    encoded = json.dumps(payload, ensure_ascii=False, default=str)
    if len(encoded) <= max_chars:
        return payload
    if isinstance(payload, dict):
        trimmed = {}
        for name, item in payload.items():
            candidate = {**trimmed, name: item}
            if len(json.dumps(candidate, ensure_ascii=False, default=str)) > max_chars:
                if isinstance(item, list):
                    kept = []
                    for entry in item:
                        trial = {**trimmed, name: kept + [entry]}
                        if len(json.dumps(trial, ensure_ascii=False, default=str)) > max_chars:
                            break
                        kept.append(entry)
                    trimmed[name] = kept
                    trimmed["truncated"] = True
                    break
                trimmed["truncated"] = True
                break
            trimmed = candidate
        return trimmed
    if isinstance(payload, list):
        return payload[:20]
    return str(payload)[:max_chars]


# -- tool handlers -----------------------------------------------------------
def _tool_traffic_summary(args: Dict[str, Any], ctx: Any) -> dict:
    overview = ctx.overview() or {}
    summary = overview.get("summary") or {}
    wan = summary.get("wan") or {}
    lan = summary.get("lan") or {}
    connections = overview.get("connectionSummary") or {}
    interfaces = summary.get("interfaces") or {}
    containers = overview.get("containerStatus") or {}
    return {
        "采集时间": overview.get("timestamp"),
        "公网": {
            "实时下行": format_rate(wan.get("rxBps")),
            "实时上行": format_rate(wan.get("txBps")),
            "累计下行": format_bytes(wan.get("rxBytes")),
            "累计上行": format_bytes(wan.get("txBytes")),
        },
        "内网": {
            "实时下行": format_rate(lan.get("rxBps")),
            "实时上行": format_rate(lan.get("txBps")),
            "累计下行": format_bytes(lan.get("rxBytes")),
            "累计上行": format_bytes(lan.get("txBytes")),
        },
        "连接": {
            "公网连接数": connections.get("wan"),
            "总连接数": connections.get("total"),
            "来源": connections.get("source"),
        },
        "网卡": {"活跃": interfaces.get("up"), "总数": interfaces.get("total")},
        "Docker": {"已接入": bool(containers.get("enabled")), "容器数": containers.get("count")},
    }


def _tool_traffic_history(args: Dict[str, Any], ctx: Any) -> dict:
    period = args["period"]
    payload = ctx.history(period) or {}
    totals = payload.get("totals") or {}
    buckets = payload.get("buckets") or []
    peak = None
    for bucket in buckets:
        wan = (bucket or {}).get("wan") or {}
        value = float(wan.get("txBytes") or 0) + float(wan.get("rxBytes") or 0)
        if peak is None or value > peak[1]:
            peak = (bucket.get("label"), value)
    return {
        "周期": period,
        "合计": {
            "公网下行": format_bytes((totals.get("wan") or {}).get("rxBytes")),
            "公网上行": format_bytes((totals.get("wan") or {}).get("txBytes")),
            "内网下行": format_bytes((totals.get("lan") or {}).get("rxBytes")),
            "内网上行": format_bytes((totals.get("lan") or {}).get("txBytes")),
        },
        "分桶数": len(buckets),
        "峰值时段": {"时段": peak[0], "该时段公网上下行合计": format_bytes(peak[1])} if peak else None,
        "最近时段": [
            {
                "时段": bucket.get("label"),
                "公网下行": format_bytes((bucket.get("wan") or {}).get("rxBytes")),
                "公网上行": format_bytes((bucket.get("wan") or {}).get("txBytes")),
                "公网下行字节": int((bucket.get("wan") or {}).get("rxBytes") or 0),
                "公网上行字节": int((bucket.get("wan") or {}).get("txBytes") or 0),
            }
            for bucket in buckets[-5:]
        ],
    }


def _tool_traffic_processes(args: Dict[str, Any], ctx: Any) -> dict:
    payload = ctx.processes(args["period"], args["limit"]) or {}
    rows = payload.get("processes") or []
    metric = args["metric"]

    def score(row: dict) -> float:
        rx = float(row.get("rxBytes") or 0)
        tx = float(row.get("txBytes") or 0)
        return {"upload": tx, "download": rx, "total": rx + tx}[metric]

    ordered = sorted(rows, key=score, reverse=True)[: args["limit"]]
    return {
        "窗口": payload.get("period") or args["period"],
        "排序": metric,
        "进程数": len(rows),
        "排行": [
            {
                "进程": row.get("name"),
                "PID": row.get("pid"),
                "上传": format_bytes(row.get("txBytes")),
                "下载": format_bytes(row.get("rxBytes")),
                "上传字节": int(row.get("txBytes") or 0),
                "下载字节": int(row.get("rxBytes") or 0),
                "命令": (row.get("cmdline") or "")[:120],
            }
            for row in ordered
        ],
    }


def _tool_traffic_connections(args: Dict[str, Any], ctx: Any) -> dict:
    payload = ctx.connections(args["scope"], args["direction"], args["limit"]) or {}
    rows = payload.get("connections") or []
    return {
        "范围": args["scope"],
        "方向": args["direction"],
        "连接数": (payload.get("pagination") or {}).get("total") or len(rows),
        "连接": [
            {
                "进程": ((row.get("process") or {}).get("name") if isinstance(row.get("process"), dict) else row.get("process")) or "未知",
                "容器": (((row.get("process") or {}).get("container") or {}).get("name") or "") if isinstance(row.get("process"), dict) else "",
                "来源": row.get("source"),
                "目标": row.get("dest"),
                "方向": row.get("direction"),
                "协议": row.get("proto"),
                "上行": format_bytes(row.get("txBytes")),
                "下行": format_bytes(row.get("rxBytes")),
                "时长": format_duration(row.get("durationSeconds")),
            }
            for row in rows[: args["limit"]]
        ],
    }


def _tool_system_status(args: Dict[str, Any], ctx: Any) -> dict:
    data = ctx.system() or {}
    cpu = data.get("cpu") or {}
    memory = data.get("memory") or {}
    disk = data.get("disk") or {}
    groups = data.get("temperatureGroups") or data.get("temperatures") or []
    hottest = None
    if isinstance(groups, list):
        for group in groups:
            # The API exposes per-sensor readings as `items`; older payloads used `readings`.
            readings = (group or {}).get("items") or (group or {}).get("readings") or []
            for reading in readings:
                current = reading.get("current")
                if current is None:
                    continue
                if hottest is None or current > hottest[1]:
                    hottest = (f"{(group or {}).get('name')}/{reading.get('label')}", current)
    elif isinstance(groups, dict):
        for name, readings in groups.items():
            for reading in readings or []:
                current = reading.get("current")
                if current is None:
                    continue
                if hottest is None or current > hottest[1]:
                    hottest = (f"{name}/{reading.get('label')}", current)
    return {
        "CPU": {
            "占用": f"{cpu.get('percent')}%",
            "核心": cpu.get("countLogical"),
            "负载": " / ".join(f"{round(float(value), 2)}" for value in (cpu.get("loadAverage") or [])[:3]) or None,
        },
        "内存": {"占用": f"{memory.get('percent')}%", "已用": format_bytes(memory.get("used")), "总量": format_bytes(memory.get("total"))},
        "磁盘": {"占用": f"{disk.get('percent')}%", "已用": format_bytes(disk.get("used")), "总量": format_bytes(disk.get("total"))},
        "最高温度": {"传感器": hottest[0], "温度": f"{hottest[1]:.1f}°C"} if hottest else None,
        "风扇": [
            {"名称": fan.get("name"), "转速": fan.get("rpm")} for fan in (data.get("fans") or [])[:4]
        ],
        "GPU": [
            {"名称": gpu.get("name"), "利用率": gpu.get("utilPercent"), "来源": gpu.get("driver")}
            for gpu in (data.get("gpu") or [])[:2]
        ],
        "NPU": [
            {"名称": npu.get("name"), "利用率": npu.get("utilPercent")} for npu in (data.get("npu") or [])[:2]
        ],
        "VPU": [
            {
                "名称": vpu.get("name"),
                "利用率": vpu.get("utilPercent"),
                "解码": vpu.get("decodePercent"),
                "编码": vpu.get("encodePercent"),
            }
            for vpu in (data.get("vpu") or [])[:2]
        ],
        "运行时长": format_duration(data.get("uptimeSeconds")),
    }


def _tool_docker_containers(args: Dict[str, Any], ctx: Any) -> dict:
    payload = ctx.docker_containers() or {}
    rows = payload.get("containers") or []
    keyword = (args.get("filter") or "").strip().lower()
    if keyword:
        rows = [
            row for row in rows
            if keyword in f"{row.get('name')} {row.get('image')} {row.get('state')}".lower()
        ]
    limit = args["limit"]
    return {
        "容器数": len(rows),
        "已启用发现": bool(payload.get("enabled")),
        "容器": [
            {
                "名称": row.get("name"),
                "镜像": row.get("image"),
                "状态": row.get("state"),
                "端口数": len(row.get("ports") or []),
                "保护": bool((row.get("protection") or {}).get("enabled")),
            }
            for row in rows[:limit]
        ],
        "截断": len(rows) > limit,
    }


def _resolve_container(rows: List[dict], keyword: str) -> Optional[dict]:
    needle = keyword.strip().lower()
    if not needle:
        return None
    for row in rows:
        if str(row.get("name") or "").lower() == needle:
            return row
    for row in rows:
        if str(row.get("id") or "").lower().startswith(needle):
            return row
    for row in rows:
        if needle in str(row.get("name") or "").lower():
            return row
    return None


def _tool_docker_container_stats(args: Dict[str, Any], ctx: Any) -> dict:
    listing = ctx.docker_containers() or {}
    rows = listing.get("containers") or []
    target = _resolve_container(rows, args["container"])
    if target is None:
        return {
            "错误": f"没有找到匹配「{args['container']}」的容器",
            "可用容器": [row.get("name") for row in rows[:20]],
        }
    payload = ctx.docker_stats(target.get("id") or target.get("name")) or {}
    stats = payload.get("stats") or {}
    blkio = stats.get("blkio") or {}
    network = stats.get("network") or {}
    return {
        "容器": target.get("name"),
        "镜像": target.get("image"),
        "状态": stats.get("state") or target.get("state"),
        "CPU": f"{stats.get('cpuPercent')}%",
        "内存": {"占用": f"{stats.get('memoryPercent')}%", "已用": format_bytes(stats.get("memoryUsedBytes"))},
        "磁盘": {"读": format_rate(blkio.get("readBps")), "写": format_rate(blkio.get("writeBps"))},
        "网络": {"下行": format_rate(network.get("rxBps")), "上行": format_rate(network.get("txBps"))},
        "端口": [
            f"{port.get('hostPort')}→{port.get('containerPort')}/{port.get('proto')}"
            for port in (target.get("ports") or [])[:8]
        ],
    }


_CONTAINER_METRIC = {
    "type": "enum",
    "values": ["disk_write", "disk_read", "cpu", "memory", "network"],
    "default": "disk_write",
    "description": "排行依据：disk_write=磁盘写入，disk_read=磁盘读取，cpu，memory，network=网络合计",
}
_MAX_SCAN_CONTAINERS = 12
_SCAN_WORKERS = 6


def _safe_stats(ctx: Any, row: dict) -> Optional[dict]:
    """One container's stats; a failure only removes that row from the ranking."""
    try:
        return ctx.docker_stats(row["id"]) or {}
    except Exception:  # noqa: BLE001 - a single container must not break the ranking
        return None


def _tool_docker_top_consumers(args: Dict[str, Any], ctx: Any) -> dict:
    """Rank containers by one resource so “谁在持续大量读写” can be answered."""
    metric = args["metric"]
    limit = args["limit"]
    listing = ctx.docker_containers() or {}
    rows = [row for row in (listing.get("containers") or []) if row.get("id")]
    # Sampling every container serially takes ~2s each; fan out instead.
    targets = rows[:_MAX_SCAN_CONTAINERS]
    with ThreadPoolExecutor(max_workers=_SCAN_WORKERS) as pool:
        sampled = list(pool.map(lambda item: _safe_stats(ctx, item), targets))
    scanned, failures = [], 0
    for row, payload in zip(targets, sampled):
        if payload is None:
            failures += 1
            continue
        stats = payload.get("stats") or {}
        blkio = stats.get("blkio") or {}
        network = stats.get("network") or {}
        values = {
            "disk_write": float(blkio.get("writeBps") or 0),
            "disk_read": float(blkio.get("readBps") or 0),
            "cpu": float(stats.get("cpuPercent") or 0),
            "memory": float(stats.get("memoryUsedBytes") or 0),
            "network": float(network.get("rxBps") or 0) + float(network.get("txBps") or 0),
        }
        scanned.append({
            "名称": row.get("name"),
            "状态": stats.get("state") or row.get("state"),
            "_value": values[metric],
            "磁盘写入": format_rate(blkio.get("writeBps")),
            "磁盘读取": format_rate(blkio.get("readBps")),
            "CPU": f"{stats.get('cpuPercent')}%",
            "内存": format_bytes(stats.get("memoryUsedBytes")),
            "网络": f"↓{format_rate(network.get('rxBps'))} ↑{format_rate(network.get('txBps'))}",
            "数值": values[metric],
            "磁盘写入Bps": int(blkio.get("writeBps") or 0),
            "磁盘读取Bps": int(blkio.get("readBps") or 0),
            "内存字节": int(stats.get("memoryUsedBytes") or 0),
            "网络Bps": int(float(network.get("rxBps") or 0) + float(network.get("txBps") or 0)),
        })
    scanned.sort(key=lambda entry: entry["_value"], reverse=True)
    ranked = []
    for entry in scanned[:limit]:
        entry = dict(entry)
        entry.pop("_value", None)
        ranked.append(entry)
    return {
        "排序依据": metric,
        "口径说明": "按实时速率排序；容器磁盘占用量（写入层大小）本接口未采集",
        "已扫描容器": len(scanned),
        "跳过容器": failures,
        "容器总数": len(rows),
        "未扫描": max(0, len(rows) - _MAX_SCAN_CONTAINERS),
        "排行": ranked,
    }


def _tool_alerts_recent(args: Dict[str, Any], ctx: Any) -> dict:
    payload = ctx.alerts(args["limit"]) or {}
    rows = payload.get("alerts") or []
    return {
        "条数": payload.get("count") or len(rows),
        "告警": [
            {
                "时间": row.get("createdAt") or row.get("timestamp"),
                "规则": row.get("ruleName") or row.get("ruleId"),
                "级别": row.get("severity") or row.get("level"),
                "内容": (row.get("message") or "")[:160],
                "状态": row.get("status"),
            }
            for row in rows[: args["limit"]]
        ],
    }


def _tool_settings_summary(args: Dict[str, Any], ctx: Any) -> dict:
    data = redact(ctx.settings() or {})
    monitor = data.get("monitor") or {}
    rules = monitor.get("rules") or []
    protection = monitor.get("containerRules") or []
    channels = monitor.get("channels") or []
    runtime = data.get("runtime") or {}
    ai_settings = data.get("ai") or {}
    return {
        "流量规则": [
            {"名称": rule.get("name"), "启用": rule.get("enabled"), "指标": rule.get("metric")} for rule in rules[:10]
        ],
        "容器保护规则": [
            {"名称": rule.get("name"), "启用": rule.get("enabled"), "动作": rule.get("action")}
            for rule in protection[:10]
        ],
        "通知渠道": [
            {"名称": channel.get("name"), "类型": channel.get("type"), "启用": channel.get("enabled")}
            for channel in channels[:10]
        ],
        "运行参数": {key: runtime.get(key) for key in ("sampleSeconds", "retentionSeconds", "dockerDiscovery")},
        "AI": {"已启用": bool(ai_settings.get("enabled")), "服务商": ai_settings.get("provider"), "模型": ai_settings.get("model")},
    }


TOOL_SPECS: List[dict] = [
    {
        "name": "traffic_summary",
        "label": "公网流量概览",
        "description": "当前公网/内网实时速率、累计流量、连接数与 Docker 概况。问“现在流量怎么样”时用这个。",
        "params": {},
        "handler": _tool_traffic_summary,
    },
    {
        "name": "traffic_history",
        "label": "历史流量统计",
        "description": "按周期统计公网/内网累计流量，含峰值时段与最近几个时段。问“今天/本周上传了多少”时用这个。",
        "params": {"period": _PERIOD_HISTORY},
        "handler": _tool_traffic_history,
    },
    {
        "name": "traffic_processes",
        "label": "进程流量排行",
        "description": "按上传/下载/合计对进程排行。问“哪个进程上传最多”时用这个。",
        "params": {"period": _PERIOD_PROCESS, "metric": _METRIC, "limit": _LIMIT},
        "handler": _tool_traffic_processes,
    },
    {
        "name": "traffic_connections",
        "label": "当前连接",
        "description": "列出当前公网/内网连接及其进程、远端地址、速率和时长。",
        "params": {"scope": _SCOPE, "direction": _DIRECTION, "limit": _LIMIT},
        "handler": _tool_traffic_connections,
    },
    {
        "name": "system_status",
        "label": "系统状态",
        "description": "CPU、内存、磁盘、温度、风扇，以及 GPU/NPU/VPU 利用率。",
        "params": {},
        "handler": _tool_system_status,
    },
    {
        "name": "docker_containers",
        "label": "容器列表",
        "description": "列出 Docker 容器及状态、端口数、是否启用保护，可按关键词过滤。",
        "params": {"filter": {"type": "string", "maxLength": 64, "description": "容器名/镜像关键词"},
                   "limit": _LIMIT},
        "handler": _tool_docker_containers,
    },
    {
        "name": "docker_container_stats",
        "label": "容器资源占用",
        "description": "单个容器的 CPU、内存、磁盘读写与网络速率。问“哪个容器占用磁盘最多”时先列容器再查具体容器。",
        "params": {"container": _CONTAINER},
        "handler": _tool_docker_container_stats,
    },
    {
        "name": "docker_top_consumers",
        "label": "容器资源排行（速率）",
        "description": "并发扫描容器并按磁盘写入/读取、CPU、内存或网络的实时速率排行。问“谁在大量读写磁盘/谁最费 CPU”时用这个；"
                       "注意这回答的是速率，不是容器占用的磁盘容量。",
        "params": {"metric": _CONTAINER_METRIC, "limit": _LIMIT},
        "handler": _tool_docker_top_consumers,
    },
    {
        "name": "alerts_recent",
        "label": "最近告警",
        "description": "最近的告警记录，含规则名、级别、内容与状态。",
        "params": {"limit": _LIMIT},
        "handler": _tool_alerts_recent,
    },
    {
        "name": "settings_summary",
        "label": "当前配置概况",
        "description": "监控规则、容器保护规则、通知渠道与运行参数概况（不含任何密钥）。",
        "params": {},
        "handler": _tool_settings_summary,
    },
]

_TOOLS_BY_NAME = {spec["name"]: spec for spec in TOOL_SPECS}


def tool_catalog() -> List[dict]:
    """Tool catalogue safe to hand to the model or the UI."""
    return [
        {
            "name": spec["name"],
            "label": spec["label"],
            "description": spec["description"],
            "risk": RISK_READ,
            "params": {
                name: {key: value for key, value in schema.items() if key != "handler"}
                for name, schema in spec["params"].items()
            },
        }
        for spec in TOOL_SPECS
    ]


def validate_args(tool_name: str, raw: Any) -> Tuple[Optional[dict], str]:
    """Validate model supplied arguments against the declarative schema."""
    spec = _TOOLS_BY_NAME.get(str(tool_name or "").strip())
    if spec is None:
        return None, f"未知工具：{tool_name}"
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return None, "参数必须是 JSON 对象"
    clean: Dict[str, Any] = {}
    for name, schema in spec["params"].items():
        value = raw.get(name, schema.get("default"))
        kind = schema["type"]
        if kind == "enum":
            text = str(value if value is not None else schema.get("default") or "").strip()
            if text not in schema["values"]:
                return None, f"参数 {name} 必须是 {'/'.join(schema['values'])} 之一"
            clean[name] = text
        elif kind == "int":
            try:
                number = int(float(value))
            except (TypeError, ValueError):
                return None, f"参数 {name} 必须是整数"
            low, high = schema.get("min", 1), schema.get("max", MAX_LIMIT)
            clean[name] = max(low, min(high, number))
        else:
            text = str(value or "").strip()
            if len(text) > int(schema.get("maxLength", 120)):
                return None, f"参数 {name} 过长"
            if not text and schema.get("required"):
                return None, f"缺少参数 {name}"
            if text:
                clean[name] = text
    unknown = sorted(set(raw) - set(spec["params"]))
    if unknown:
        return None, f"不支持的参数：{'、'.join(unknown)}"
    return clean, ""


def run_tool(tool_name: str, args: dict, ctx: Any) -> dict:
    """Execute one whitelisted read tool; never raises for data-level problems."""
    spec = _TOOLS_BY_NAME.get(tool_name)
    if spec is None:
        return {"ok": False, "tool": tool_name, "error": f"未知工具：{tool_name}"}
    started = time.monotonic()
    try:
        payload = spec["handler"](args, ctx)
        data = trim_payload(redact(payload))
        return {
            "ok": True,
            "tool": tool_name,
            "label": spec["label"],
            "args": args,
            "data": data,
            "durationMs": int((time.monotonic() - started) * 1000),
        }
    except Exception as error:  # noqa: BLE001 - surfaced to the user as a tool error
        return {
            "ok": False,
            "tool": tool_name,
            "label": spec["label"],
            "args": args,
            "error": f"{type(error).__name__}: {error}"[:300],
            "durationMs": int((time.monotonic() - started) * 1000),
        }


# -- prompts -----------------------------------------------------------------
PLAN_SYSTEM_PROMPT = (
    "你是 NAS 监控面板的只读查询助手。你只能从下面的工具里挑一个，并给出参数。"
    "只输出 JSON，不要输出解释或 Markdown 代码块。"
    '格式：{"tool": "<工具名>", "args": {...}, "reason": "<一句话原因>"}。'
    "如果用户的问题与监控数据无关，输出 {\"tool\": \"none\", \"args\": {}, \"reason\": \"<原因>\"}。"
)

ANSWER_SYSTEM_PROMPT = (
    "你是 NAS 监控面板的助手。只根据给定的工具返回数据回答，不要编造数字，不要给出与数据无关的建议。"
    "用简体中文、口语化、先给结论再给关键数字，控制在 120 字以内。"
    "如果数据里含 错误 字段，就直接说明查不到以及原因。"
)


def build_plan_messages(question: str) -> List[dict]:
    catalog = json.dumps(tool_catalog(), ensure_ascii=False)
    return [
        {"role": "system", "content": PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": f"可用工具：\n{catalog}\n\n用户问题：{question}"},
    ]


def build_answer_messages(question: str, tool_name: str, args: dict, result: dict) -> List[dict]:
    payload = json.dumps(result, ensure_ascii=False)
    return [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户问题：{question}\n"
                f"已调用工具：{tool_name}，参数：{json.dumps(args, ensure_ascii=False)}\n"
                f"工具返回：{payload}\n\n请回答用户。"
            ),
        },
    ]


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_plan(text: str) -> Tuple[Optional[dict], str]:
    """Extract the plan JSON from a model reply, tolerating code fences."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    match = _JSON_BLOCK_RE.search(raw)
    if not match:
        return None, "模型没有返回可解析的计划"
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None, "模型返回的计划不是合法 JSON"
    if not isinstance(parsed, dict):
        return None, "模型返回的计划格式不正确"
    return parsed, ""


def estimate_tokens(text: str) -> int:
    """Rough token estimate; CJK counts about one token per character."""
    if not text:
        return 0
    cjk = sum(1 for character in text if "\u4e00" <= character <= "\u9fff")
    return int(cjk + max(0, len(text) - cjk) / 4)


# -- orchestration -----------------------------------------------------------
def answer_question(question: str, ai_settings: dict, ctx: Any,
                    chat: Callable[[dict, List[dict]], dict] = ai.chat_completion,
                    max_calls: int = 2) -> dict:
    """Plan → validate → run → explain, with a full trace and usage estimate."""
    text = str(question or "").strip()
    if not text:
        return {"ok": False, "error": "请输入问题"}
    if len(text) > 500:
        return {"ok": False, "error": "问题过长，请精简到 500 字以内"}
    settings = dict(ai_settings or {})
    if not settings.get("enabled") or not settings.get("model"):
        return {"ok": False, "error": "AI 未启用或未配置模型，请先到「设置 → AI 配置」完成配置"}

    calls = 0
    tokens = 0
    trace: List[dict] = []

    plan_messages = build_plan_messages(text)
    plan_reply = chat(settings, plan_messages)
    calls += 1
    tokens += estimate_tokens("".join(message["content"] for message in plan_messages))
    plan_text = plan_reply.get("answer") if isinstance(plan_reply, dict) else str(plan_reply)
    tokens += estimate_tokens(plan_text or "")
    plan, error = parse_plan(plan_text or "")
    if plan is None:
        return {"ok": False, "error": error, "calls": calls, "tokensEstimate": tokens, "trace": trace}

    tool_name = str(plan.get("tool") or "").strip()
    trace.append({"step": "plan", "tool": tool_name, "args": plan.get("args") or {}, "reason": plan.get("reason") or ""})
    if tool_name in ("", "none"):
        reason = plan.get("reason") or "这个问题和监控数据无关"
        return {"ok": True, "answer": reason, "tool": "none", "args": {}, "data": None,
                "calls": calls, "tokensEstimate": tokens, "trace": trace, "direct": True}

    args, arg_error = validate_args(tool_name, plan.get("args") or {})
    if args is None:
        return {"ok": False, "error": arg_error, "tool": tool_name, "calls": calls,
                "tokensEstimate": tokens, "trace": trace}

    result = run_tool(tool_name, args, ctx)
    trace.append({"step": "tool", "tool": tool_name, "args": args, "ok": result.get("ok"),
                  "durationMs": result.get("durationMs"), "error": result.get("error") or ""})
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error") or "工具执行失败", "tool": tool_name,
                "args": args, "calls": calls, "tokensEstimate": tokens, "trace": trace}

    if calls >= max_calls:
        return {"ok": True, "answer": "", "tool": tool_name, "args": args, "data": result.get("data"),
                "calls": calls, "tokensEstimate": tokens, "trace": trace, "truncated": True}

    answer_messages = build_answer_messages(text, tool_name, args, result.get("data"))
    answer_reply = chat(settings, answer_messages)
    calls += 1
    tokens += estimate_tokens("".join(message["content"] for message in answer_messages))
    answer_text = answer_reply.get("answer") if isinstance(answer_reply, dict) else str(answer_reply)
    tokens += estimate_tokens(answer_text or "")
    trace.append({"step": "answer", "tokensEstimate": tokens})

    return {
        "ok": True,
        "answer": (answer_text or "").strip(),
        "tool": tool_name,
        "toolLabel": result.get("label"),
        "args": args,
        "data": result.get("data"),
        "calls": calls,
        "tokensEstimate": tokens,
        "trace": trace,
    }


class CollectorContext:
    """Read-only facade over the running collector for the agent tools."""

    def __init__(self, collector: Any, system_reader: Optional[Callable[[], dict]] = None):
        self.collector = collector
        self._system_reader = system_reader

    def overview(self) -> dict:
        return self.collector.api_overview("physical")

    def history(self, period: str) -> dict:
        return self.collector.history_summary(period)

    def processes(self, period: str, limit: int) -> dict:
        return self.collector.process_rank(period, limit)

    def connections(self, scope: str, direction: str, limit: int) -> dict:
        return self.collector.connection_detail(
            "capture", "physical", "all", scope, "all", direction, "", "", "", 0, 0, limit, 0
        )

    def system(self) -> dict:
        if self._system_reader is None:
            return {}
        return self._system_reader()

    def docker_containers(self) -> dict:
        return self.collector.docker_containers(False)

    def docker_stats(self, container_id: str) -> dict:
        return self.collector.docker_container_stats(container_id, False)

    def alerts(self, limit: int) -> dict:
        return self.collector.alert_history(None, None, limit)

    def settings(self) -> dict:
        return self.collector.get_settings()
