import asyncio
import base64
import hashlib
import hmac
import json
import ipaddress
import os
import sqlite3
import socket
import struct
import sys
import threading
import time
import urllib.parse
import urllib.request
import traceback
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psutil
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from scapy.all import IP, TCP, UDP, IPv6, AsyncSniffer, conf

from server.services.notifications import (
    DEFAULT_NOTIFY_BODY_TEMPLATE,
    DEFAULT_NOTIFY_TITLE_TEMPLATE,
    sanitize_http_url,
    send_notification_alert as dispatch_notification_alert,
)
from server.services.system_status import system_status


APP_NAME = "NAS Traffic Lens"


def load_app_version() -> str:
    version_file = Path(os.getenv("APP_VERSION_FILE", Path(__file__).resolve().parents[1] / "VERSION"))
    try:
        value = version_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    return "dev"


APP_VERSION = load_app_version()
APP_PORT = int(os.getenv("APP_PORT", "8088"))
DEFAULT_SAMPLE_SECONDS = float(os.getenv("SAMPLE_SECONDS", "1"))
DEFAULT_RETENTION_SECONDS = int(os.getenv("RETENTION_SECONDS", "3600"))
DEFAULT_CONNECTION_ACTIVE_SECONDS = int(os.getenv("CONNECTION_ACTIVE_SECONDS", "120"))
DEFAULT_CONNECTION_RETENTION_SECONDS = int(os.getenv("CONNECTION_RETENTION_SECONDS", "900"))
CONNECTION_COUNT_SOURCE = os.getenv("CONNECTION_COUNT_SOURCE", "conntrack").strip().lower()
DEFAULT_AUTO_START_STAGE = os.getenv("AUTO_START_STAGE", "true").strip().lower() in {"1", "true", "yes", "on"}
DEFAULT_CONNTRACK_REFRESH_SECONDS = int(os.getenv("CONNTRACK_REFRESH_SECONDS", "5"))
DOCKER_WEB_PROBE_TTL_SECONDS = int(os.getenv("DOCKER_WEB_PROBE_TTL_SECONDS", "86400"))
DOCKER_WEB_PROBE_TIMEOUT = float(os.getenv("DOCKER_WEB_PROBE_TIMEOUT", "1.0"))
DOCKER_LIST_CACHE_SECONDS = float(os.getenv("DOCKER_LIST_CACHE_SECONDS", "20"))
DOCKER_STATS_CACHE_SECONDS = float(os.getenv("DOCKER_STATS_CACHE_SECONDS", "5"))
CONNTRACK_COUNT_MODE = os.getenv("CONNTRACK_COUNT_MODE", "active").strip().lower()
CONNTRACK_TCP_STATES = {
    item.strip().upper()
    for item in os.getenv("CONNTRACK_TCP_STATES", "ESTABLISHED").split(",")
    if item.strip()
}
CONNTRACK_UDP_REQUIRE_ASSURED = os.getenv("CONNTRACK_UDP_REQUIRE_ASSURED", "true").strip().lower() in {"1", "true", "yes", "on"}
CONNTRACK_INCLUDE_UNREPLIED = os.getenv("CONNTRACK_INCLUDE_UNREPLIED", "false").strip().lower() in {"1", "true", "yes", "on"}
CONNTRACK_MIN_TIMEOUT_SECONDS = int(os.getenv("CONNTRACK_MIN_TIMEOUT_SECONDS", "3"))
SOCKET_TCP_STATES = {
    item.strip().upper()
    for item in os.getenv("SOCKET_TCP_STATES", "ESTABLISHED").split(",")
    if item.strip()
}
SOCKET_REFRESH_SECONDS = int(os.getenv("SOCKET_REFRESH_SECONDS", "10"))
INTERFACE_REFRESH_SECONDS = int(os.getenv("INTERFACE_REFRESH_SECONDS", "30"))
DEFAULT_PERSIST_INTERVAL_SECONDS = int(os.getenv("PERSIST_INTERVAL_SECONDS", "60"))
DEFAULT_HISTORY_RETENTION_DAYS = int(os.getenv("HISTORY_RETENTION_DAYS", "400"))
SAMPLE_SECONDS = DEFAULT_SAMPLE_SECONDS
RETENTION_SECONDS = DEFAULT_RETENTION_SECONDS
CONNECTION_ACTIVE_SECONDS = DEFAULT_CONNECTION_ACTIVE_SECONDS
CONNECTION_RETENTION_SECONDS = DEFAULT_CONNECTION_RETENTION_SECONDS
AUTO_START_STAGE = DEFAULT_AUTO_START_STAGE
CONNTRACK_REFRESH_SECONDS = DEFAULT_CONNTRACK_REFRESH_SECONDS
PERSIST_INTERVAL_SECONDS = DEFAULT_PERSIST_INTERVAL_SECONDS
HISTORY_RETENTION_DAYS = DEFAULT_HISTORY_RETENTION_DAYS
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", Path(__file__).resolve().parents[1] / "front-end"))
DB_PATH = Path(os.getenv("DB_PATH", "/data/traffic.db"))
ENABLE_DOCKER_DISCOVERY = os.getenv("ENABLE_DOCKER_DISCOVERY", "false").strip().lower() in {"1", "true", "yes", "on"}
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "").strip()
APP_SECRET = os.getenv("APP_SECRET", "").strip()
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "604800"))
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "ntl_session")
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "10"))
LOGIN_LOCK_SECONDS = int(os.getenv("LOGIN_LOCK_SECONDS", "300"))
LOGIN_FAILURE_CLIENT_LIMIT = int(os.getenv("LOGIN_FAILURE_CLIENT_LIMIT", "256"))

ALERT_WAN_TX_BPS = int(os.getenv("ALERT_WAN_TX_BPS", "0"))
ALERT_WAN_TX_SECONDS = int(os.getenv("ALERT_WAN_TX_SECONDS", "0"))
ALERT_STAGE_TX_BYTES = int(os.getenv("ALERT_STAGE_TX_BYTES", "0"))
ALERT_DAILY_TX_BYTES = int(os.getenv("ALERT_DAILY_TX_BYTES", "0"))
ALERT_NOTIFY_CHANNEL = os.getenv("ALERT_NOTIFY_CHANNEL", "webhook").strip().lower()
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "").strip()
ALERT_WEBHOOK_TIMEOUT = float(os.getenv("ALERT_WEBHOOK_TIMEOUT", "5"))

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]

VIRTUAL_PREFIXES = ("veth", "docker", "br-", "virbr", "ifb", "tap", "tun", "zt", "tailscale")
PHYSICAL_PREFIXES = ("eth", "enp", "eno", "ens", "em", "p", "bond", "wlan")
INTERFACE_VIEW_MODES = {"physical", "captured", "virtual", "all"}


def now() -> float:
    return time.time()


def is_lan_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return True
    return any(ip in network for network in PRIVATE_NETWORKS)


def is_private_ip(value: str) -> bool:
    return is_lan_ip(value)


def traffic_scope(src: str, dst: str) -> str:
    return "lan" if is_lan_ip(src) and is_lan_ip(dst) else "wan"


def connection_endpoint_ip(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("[") and "]" in text:
        return text[1 : text.index("]")]
    if ":" in text:
        return text.rsplit(":", 1)[0]
    return text


def classify_connection_scope(source: str, dest: str) -> str:
    src_ip = connection_endpoint_ip(source)
    dst_ip = connection_endpoint_ip(dest)
    if not src_ip or not dst_ip:
        return "wan"
    return "lan" if is_lan_ip(src_ip) and is_lan_ip(dst_ip) else "wan"


def format_endpoint_text(ip: str, port: int) -> str:
    text = str(ip or "").strip()
    if not text:
        return ""
    if ":" in text and not text.startswith("["):
        text = f"[{text}]"
    if port:
        return f"{text}:{int(port)}"
    return text


def parse_proc_net(path: str, proto: str) -> Dict[Tuple[str, str, str, int, int], int]:
    sockets: Dict[Tuple[str, str, str, int, int], int] = {}
    file_path = Path(path)
    if not file_path.exists():
        return sockets

    try:
        lines = file_path.read_text(errors="ignore").splitlines()[1:]
    except OSError:
        return sockets

    for line in lines:
        parts = line.split()
        if len(parts) < 10:
            continue
        local, remote, inode = parts[1], parts[2], parts[9]
        try:
            local_ip, local_port = decode_proc_address(local)
            remote_ip, remote_port = decode_proc_address(remote)
            sockets[(proto, local_ip, remote_ip, local_port, remote_port)] = int(inode)
        except (ValueError, OSError):
            continue
    return sockets


def decode_proc_address(value: str) -> Tuple[str, int]:
    raw_ip, raw_port = value.split(":")
    port = int(raw_port, 16)

    if len(raw_ip) == 8:
        packed = struct.pack("<L", int(raw_ip, 16))
        return socket.inet_ntop(socket.AF_INET, packed), port

    groups = [raw_ip[index : index + 8] for index in range(0, len(raw_ip), 8)]
    packed = b"".join(struct.pack("<L", int(group, 16)) for group in groups)
    return socket.inet_ntop(socket.AF_INET6, packed), port


def proc_inode_process_map() -> Dict[int, dict]:
    inode_map: Dict[int, dict] = {}
    proc_root = Path("/host/proc") if Path("/host/proc").exists() else Path("/proc")
    if not proc_root.exists():
        return inode_map

    try:
        pid_dirs = list(proc_root.iterdir())
    except OSError:
        return inode_map

    for pid_dir in pid_dirs:
        if not pid_dir.name.isdigit():
            continue
        fd_dir = pid_dir / "fd"
        if not fd_dir.exists():
            continue

        proc_info = {
            "pid": int(pid_dir.name),
            "name": read_first_line(pid_dir / "comm") or "unknown",
            "cmdline": read_cmdline(pid_dir / "cmdline"),
        }

        try:
            for fd in fd_dir.iterdir():
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue
                if target.startswith("socket:[") and target.endswith("]"):
                    inode_map[int(target[8:-1])] = proc_info
        except OSError:
            continue
    return inode_map


def read_first_line(path: Path) -> Optional[str]:
    try:
        return path.read_text(errors="ignore").splitlines()[0].strip()
    except (OSError, IndexError):
        return None


def read_cmdline(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode(errors="ignore").strip()


def read_sys_text(iface: str, name: str) -> str:
    try:
        return (Path("/sys/class/net") / iface / name).read_text(errors="ignore").strip()
    except OSError:
        return ""


def get_default_route_interfaces() -> set:
    interfaces = set()
    try:
        for line in Path("/proc/net/route").read_text(errors="ignore").splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "00000000":
                interfaces.add(parts[0])
    except OSError:
        pass
    return interfaces


def classify_interface(name: str, isup: bool, default_routes: set) -> dict:
    lowered = name.lower()
    sys_path = Path("/sys/class/net") / name
    is_bridge = (sys_path / "bridge").exists()
    has_device = (sys_path / "device").exists()
    is_default = name in default_routes

    role = "其他接口"
    note = "系统网络接口"
    virtual = not has_device
    priority = 80

    if lowered == "lo":
        role, note, virtual, priority = "回环接口", "本机内部通信", True, 100
    elif lowered.startswith("veth"):
        role, note, virtual, priority = "容器 veth", "容器虚拟链路，常与 docker 网桥成对出现", True, 70
    elif lowered == "docker0":
        role, note, virtual, priority = "Docker 默认网桥", "Docker 容器默认桥接网络", True, 55
    elif lowered.startswith("br-"):
        role, note, virtual, priority = "Docker 自定义网桥", "Docker Compose 或自定义容器网络", True, 58
    elif lowered.startswith("virbr"):
        role, note, virtual, priority = "虚拟化网桥", "虚拟机或系统虚拟网络", True, 60
    elif lowered.startswith("ifb"):
        role, note, virtual, priority = "流控镜像接口", "Linux IFB 流量整形接口，可能重复映射物理口流量", True, 65
    elif is_bridge:
        role, note, virtual, priority = "系统网桥", "Linux bridge，可能承载 NAS 或容器桥接流量", True, 40
    elif lowered.startswith("bond"):
        role, note, virtual, priority = "链路聚合", "多网口聚合接口", False, 15
    elif has_device or lowered.startswith(PHYSICAL_PREFIXES):
        role, note, virtual, priority = "物理网卡", "NAS 对外物理网络接口", False, 10

    if is_default:
        role = f"{role} / 默认路由"
        priority = min(priority, 5)

    capture_recommended = isup and lowered != "lo" and (not virtual or is_default)
    if lowered.startswith(VIRTUAL_PREFIXES) and not is_default:
        capture_recommended = False

    return {
        "role": role,
        "note": note,
        "virtual": virtual,
        "defaultRoute": is_default,
        "captureRecommended": capture_recommended,
        "priority": priority,
    }


def get_interface_details(captured: Optional[set] = None) -> Dict[str, dict]:
    captured = captured or set()
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    default_routes = get_default_route_interfaces()
    details = {}

    for name in sorted(set(addrs.keys()) | set(stats.keys())):
        stat = stats.get(name)
        classified = classify_interface(name, bool(stat and stat.isup), default_routes)
        ips = []
        mac = ""
        for addr in addrs.get(name, []):
            if addr.family in (socket.AF_INET, socket.AF_INET6):
                ips.append(addr.address.split("%")[0])
            elif getattr(psutil, "AF_LINK", object()) == addr.family:
                mac = addr.address

        details[name] = {
            "name": name,
            "isUp": bool(stat and stat.isup),
            "duplex": str(stat.duplex) if stat else "",
            "speedMbps": stat.speed if stat else 0,
            "mtu": stat.mtu if stat else 0,
            "mac": mac or read_sys_text(name, "address"),
            "ips": ips,
            "operstate": read_sys_text(name, "operstate"),
            "ifindex": read_sys_text(name, "ifindex"),
            "iflink": read_sys_text(name, "iflink"),
            "captured": name in captured,
            **classified,
        }
    return details


def get_capture_interfaces_from_details(details: Dict[str, dict]) -> List[str]:
    requested = os.getenv("CAPTURE_INTERFACES", "").strip()
    if requested.lower() == "all":
        return [name for name, item in details.items() if item["isUp"] and name != "lo"]
    if requested:
        return [item.strip() for item in requested.split(",") if item.strip()]

    selected = [
        name
        for name, item in details.items()
        if item["isUp"] and item["captureRecommended"] and not str(name).lower().startswith(VIRTUAL_PREFIXES)
    ]
    if selected:
        return sorted(selected, key=lambda name: details[name]["priority"])

    return [
        name
        for name, item in sorted(details.items(), key=lambda row: row[1]["priority"])
        if item["isUp"] and name != "lo"
    ][:1]


@dataclass
class Counter:
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    first_seen: float = field(default_factory=now)
    last_seen: float = field(default_factory=now)

    def add(self, direction: str, size: int) -> None:
        if direction == "rx":
            self.rx_bytes += size
            self.rx_packets += 1
        else:
            self.tx_bytes += size
            self.tx_packets += 1
        self.last_seen = now()

    def snapshot(self) -> dict:
        return {
            "rxBytes": self.rx_bytes,
            "txBytes": self.tx_bytes,
            "rxPackets": self.rx_packets,
            "txPackets": self.tx_packets,
            "totalBytes": self.rx_bytes + self.tx_bytes,
            "firstSeen": self.first_seen,
            "lastSeen": self.last_seen,
            "durationSeconds": max(0, now() - self.first_seen),
        }


@dataclass
class PacketEvent:
    timestamp: float
    iface: str
    scope: str
    direction: str
    proto: str
    src: str
    dst: str
    sport: int
    dport: int
    size: int
    process: dict


class LoginRequest(BaseModel):
    password: str


class AlertSettings(BaseModel):
    highWanTxBps: int = 0
    highWanTxSeconds: int = 0
    stageWanTxBytes: int = 0
    dailyWanTxBytes: int = 0


class NotifySettings(BaseModel):
    channel: str = "webhook"
    webhookUrl: str = ""
    webhookTimeout: float = 5


class MonitorRule(BaseModel):
    id: str
    name: str
    metric: str
    operator: str = "gte"
    threshold: int = 0
    durationSeconds: int = 0
    scope: str = "wan"
    direction: str = "tx"
    window: str = "realtime"
    enabled: bool = True
    channelIds: List[str] = Field(default_factory=list)


class MonitorRulesPayload(BaseModel):
    rules: List[MonitorRule]


class NotificationChannel(BaseModel):
    id: str
    name: str
    type: str = "webhook"
    enabled: bool = False
    url: str = ""
    token: str = ""
    timeout: float = 5
    titleTemplate: str = ""
    bodyTemplate: str = ""
    urlTemplate: str = ""
    msgType: str = "text"
    htmlHeight: int = 200


class NotificationChannelsPayload(BaseModel):
    channels: List[NotificationChannel]


class RuntimeSettingsPayload(BaseModel):
    sampleSeconds: float = Field(default=DEFAULT_SAMPLE_SECONDS, ge=0.5, le=30)
    retentionSeconds: int = Field(default=DEFAULT_RETENTION_SECONDS, ge=60, le=86400)
    persistIntervalSeconds: int = Field(default=DEFAULT_PERSIST_INTERVAL_SECONDS, ge=10, le=3600)
    historyRetentionDays: int = Field(default=DEFAULT_HISTORY_RETENTION_DAYS, ge=1, le=3650)
    connectionActiveSeconds: int = Field(default=DEFAULT_CONNECTION_ACTIVE_SECONDS, ge=10, le=3600)
    connectionRetentionSeconds: int = Field(default=DEFAULT_CONNECTION_RETENTION_SECONDS, ge=60, le=86400)
    conntrackRefreshSeconds: int = Field(default=DEFAULT_CONNTRACK_REFRESH_SECONDS, ge=2, le=300)
    autoStartStage: bool = DEFAULT_AUTO_START_STAGE


class NotificationTestPayload(BaseModel):
    channelId: str


class LabelPayload(BaseModel):
    key: str
    label: str


class DockerPortPayload(BaseModel):
    proto: str = "tcp"
    hostPort: int = Field(default=0, ge=0, le=65535)
    containerPort: int = Field(default=0, ge=0, le=65535)
    label: str = ""
    service: str = ""
    accessMode: str = "auto"
    scheme: str = "http"
    path: str = ""
    enabled: bool = True
    manual: bool = True


class DockerContainerPortsPayload(BaseModel):
    containerId: str = ""
    containerName: str = ""
    icon: str = ""
    ports: List[DockerPortPayload] = Field(default_factory=list)


class DockerActionPayload(BaseModel):
    containerId: str = ""
    action: str = ""


class DockerImagePullPayload(BaseModel):
    image: str = ""


class DockerPortProbePayload(BaseModel):
    host: str = ""
    port: int = Field(default=0, ge=1, le=65535)
    path: str = "/"
    refresh: bool = False


class TrafficDB:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.RLock()
        self.conn: Optional[sqlite3.Connection] = None

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS minute_stats (
                bucket INTEGER NOT NULL,
                iface TEXT NOT NULL,
                scope TEXT NOT NULL,
                rx_bytes INTEGER NOT NULL DEFAULT 0,
                tx_bytes INTEGER NOT NULL DEFAULT 0,
                rx_packets INTEGER NOT NULL DEFAULT 0,
                tx_packets INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (bucket, iface, scope)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                ts INTEGER NOT NULL,
                type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                value INTEGER NOT NULL,
                threshold INTEGER NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS labels (
                key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS process_minute_stats (
                bucket INTEGER NOT NULL,
                process_key TEXT NOT NULL,
                rx_bytes INTEGER NOT NULL DEFAULT 0,
                tx_bytes INTEGER NOT NULL DEFAULT 0,
                rx_packets INTEGER NOT NULL DEFAULT 0,
                tx_packets INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (bucket, process_key)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_minute_stats_bucket_scope ON minute_stats(bucket, scope)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_process_minute_bucket ON process_minute_stats(bucket)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts)")
        self.conn.commit()

    def add_minute(self, bucket: int, rows: List[dict]) -> None:
        if not self.conn or not rows:
            return
        with self.lock:
            self.conn.executemany(
                """
                INSERT INTO minute_stats (bucket, iface, scope, rx_bytes, tx_bytes, rx_packets, tx_packets)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bucket, iface, scope) DO UPDATE SET
                    rx_bytes = rx_bytes + excluded.rx_bytes,
                    tx_bytes = tx_bytes + excluded.tx_bytes,
                    rx_packets = rx_packets + excluded.rx_packets,
                    tx_packets = tx_packets + excluded.tx_packets
                """,
                [
                    (
                        bucket,
                        row["iface"],
                        row["scope"],
                        row["rxBytes"],
                        row["txBytes"],
                        row["rxPackets"],
                        row["txPackets"],
                    )
                    for row in rows
                ],
            )
            self.conn.commit()

    def add_process_minute(self, bucket: int, rows: List[dict]) -> None:
        if not self.conn or not rows:
            return
        with self.lock:
            self.conn.executemany(
                """
                INSERT INTO process_minute_stats (bucket, process_key, rx_bytes, tx_bytes, rx_packets, tx_packets)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(bucket, process_key) DO UPDATE SET
                    rx_bytes = rx_bytes + excluded.rx_bytes,
                    tx_bytes = tx_bytes + excluded.tx_bytes,
                    rx_packets = rx_packets + excluded.rx_packets,
                    tx_packets = tx_packets + excluded.tx_packets
                """,
                [
                    (
                        bucket,
                        row["processKey"],
                        row["rxBytes"],
                        row["txBytes"],
                        row["rxPackets"],
                        row["txPackets"],
                    )
                    for row in rows
                ],
            )
            self.conn.commit()

    def add_alert(self, alert: dict) -> None:
        if not self.conn:
            return
        with self.lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO alerts (id, ts, type, severity, message, value, threshold)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert["id"],
                    int(alert["timestamp"]),
                    alert["type"],
                    alert["severity"],
                    alert["message"],
                    int(alert["value"]),
                    int(alert["threshold"]),
                ),
            )
            self.conn.commit()

    def query_history(self, period: str) -> dict:
        if not self.conn:
            return {"period": period, "buckets": [], "totals": empty_totals()}

        if period not in {"day", "week", "month", "year"}:
            period = "day"
        start, mode = history_range(period)

        with self.lock:
            rows = self.conn.execute(
                """
                SELECT bucket, scope, SUM(rx_bytes), SUM(tx_bytes)
                FROM minute_stats
                WHERE bucket >= ?
                GROUP BY bucket, scope
                ORDER BY bucket
                """,
                (start,),
            ).fetchall()

        grouped: Dict[str, dict] = {}
        totals = empty_totals()
        for bucket, scope, rx_bytes, tx_bytes in rows:
            label = bucket_label(int(bucket), mode)
            item = grouped.setdefault(label, {"label": label, "timestamp": int(bucket), "wan": empty_pair(), "lan": empty_pair()})
            pair = item.setdefault(scope, empty_pair())
            pair["rxBytes"] += int(rx_bytes or 0)
            pair["txBytes"] += int(tx_bytes or 0)
            if scope in totals:
                totals[scope]["rxBytes"] += int(rx_bytes or 0)
                totals[scope]["txBytes"] += int(tx_bytes or 0)

        return {"period": period, "buckets": list(grouped.values()), "totals": totals}

    def total_since(self, start: int, scope: str) -> dict:
        if not self.conn:
            return empty_pair()
        with self.lock:
            row = self.conn.execute(
                """
                SELECT SUM(rx_bytes), SUM(tx_bytes)
                FROM minute_stats
                WHERE bucket >= ? AND scope = ?
                """,
                (start, scope),
            ).fetchone()
        return {"rxBytes": int(row[0] or 0), "txBytes": int(row[1] or 0)}

    def query_processes(self, start: int, end: int, limit: int) -> List[dict]:
        if not self.conn:
            return []
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT process_key,
                       SUM(rx_bytes), SUM(tx_bytes),
                       SUM(rx_packets), SUM(tx_packets),
                       MIN(bucket), MAX(bucket)
                FROM process_minute_stats
                WHERE bucket >= ? AND bucket <= ?
                GROUP BY process_key
                ORDER BY SUM(rx_bytes + tx_bytes) DESC
                LIMIT ?
                """,
                (start, end, limit),
            ).fetchall()

        result = []
        for process_key, rx_bytes, tx_bytes, rx_packets, tx_packets, first_bucket, last_bucket in rows:
            item = parse_process_key(process_key)
            item.update(
                {
                    "rxBytes": int(rx_bytes or 0),
                    "txBytes": int(tx_bytes or 0),
                    "rxPackets": int(rx_packets or 0),
                    "txPackets": int(tx_packets or 0),
                    "totalBytes": int(rx_bytes or 0) + int(tx_bytes or 0),
                    "firstSeen": int(first_bucket or start),
                    "lastSeen": int(last_bucket or end),
                    "durationSeconds": max(0, int(last_bucket or end) - int(first_bucket or start) + 60),
                }
            )
            result.append(item)
        return result

    def prune_old(self, before: int) -> None:
        if not self.conn:
            return
        with self.lock:
            self.conn.execute("DELETE FROM minute_stats WHERE bucket < ?", (before,))
            self.conn.execute("DELETE FROM process_minute_stats WHERE bucket < ?", (before,))
            self.conn.execute("DELETE FROM alerts WHERE ts < ?", (before,))
            self.conn.commit()

    def get_labels(self) -> Dict[str, str]:
        if not self.conn:
            return {}
        with self.lock:
            rows = self.conn.execute("SELECT key, label FROM labels").fetchall()
        return {row[0]: row[1] for row in rows}

    def set_label(self, key: str, label: str) -> dict:
        if not self.conn:
            return {"ok": False}
        cleaned = label.strip()
        with self.lock:
            if cleaned:
                self.conn.execute(
                    """
                    INSERT INTO labels (key, label, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET label = excluded.label, updated_at = excluded.updated_at
                    """,
                    (key, cleaned, int(now())),
                )
            else:
                self.conn.execute("DELETE FROM labels WHERE key = ?", (key,))
            self.conn.commit()
        return {"ok": True}

    def get_setting(self, key: str) -> Optional[dict]:
        if not self.conn:
            return None
        with self.lock:
            row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None

    def set_setting(self, key: str, value: dict) -> dict:
        if not self.conn:
            return {"ok": False}
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, json.dumps(value, ensure_ascii=False, separators=(",", ":")), int(now())),
            )
            self.conn.commit()
        return {"ok": True}


def empty_pair() -> dict:
    return {"rxBytes": 0, "txBytes": 0}


def empty_totals() -> dict:
    return {"wan": empty_pair(), "lan": empty_pair()}


def bucket_label(timestamp: int, mode: str) -> str:
    dt = datetime.fromtimestamp(timestamp)
    if mode == "month":
        return dt.strftime("%Y-%m")
    if mode == "day":
        return dt.strftime("%m-%d")
    return dt.strftime("%H:00")


def history_range(period: str) -> Tuple[int, str]:
    current = datetime.fromtimestamp(now())
    if period == "week":
        start_dt = datetime.combine((current - timedelta(days=current.weekday())).date(), datetime.min.time())
        return int(start_dt.timestamp()), "day"
    if period == "month":
        start_dt = datetime(current.year, current.month, 1)
        return int(start_dt.timestamp()), "day"
    if period == "year":
        start_dt = datetime(current.year, 1, 1)
        return int(start_dt.timestamp()), "month"
    start_dt = datetime.combine(current.date(), datetime.min.time())
    return int(start_dt.timestamp()), "hour"


def default_monitor_rules() -> List[dict]:
    return [
        {
            "id": "high_wan_upload",
            "name": "公网持续高上传",
            "metric": "wan_tx_bps",
            "operator": "gte",
            "threshold": ALERT_WAN_TX_BPS,
            "durationSeconds": ALERT_WAN_TX_SECONDS,
            "scope": "wan",
            "direction": "tx",
            "window": "realtime",
            "enabled": ALERT_WAN_TX_BPS > 0,
            "channelIds": ["webhook"],
        },
        {
            "id": "high_wan_connections",
            "name": "公网连接数过高",
            "metric": "wan_connections",
            "operator": "gte",
            "threshold": 0,
            "durationSeconds": 60,
            "scope": "wan",
            "direction": "both",
            "window": "realtime",
            "enabled": False,
            "channelIds": ["webhook"],
        },
        {
            "id": "stage_wan_upload",
            "name": "阶段公网上传超限",
            "metric": "stage_wan_tx_bytes",
            "operator": "gte",
            "threshold": ALERT_STAGE_TX_BYTES,
            "durationSeconds": 0,
            "scope": "wan",
            "direction": "tx",
            "window": "stage",
            "enabled": ALERT_STAGE_TX_BYTES > 0,
            "channelIds": ["webhook"],
        },
        {
            "id": "daily_wan_upload",
            "name": "今日公网上传超限",
            "metric": "daily_wan_tx_bytes",
            "operator": "gte",
            "threshold": ALERT_DAILY_TX_BYTES,
            "durationSeconds": 0,
            "scope": "wan",
            "direction": "tx",
            "window": "day",
            "enabled": ALERT_DAILY_TX_BYTES > 0,
            "channelIds": ["webhook"],
        },
    ]


def default_notification_channels() -> List[dict]:
    webhook_url = sanitize_http_url(ALERT_WEBHOOK_URL)
    return [
        {
            "id": "webhook",
            "name": "Webhook",
            "type": ALERT_NOTIFY_CHANNEL if ALERT_NOTIFY_CHANNEL in {"webhook", "iyuu", "meow"} else "webhook",
            "enabled": bool(webhook_url),
            "url": webhook_url,
            "token": "",
            "timeout": ALERT_WEBHOOK_TIMEOUT,
            "titleTemplate": DEFAULT_NOTIFY_TITLE_TEMPLATE,
            "bodyTemplate": DEFAULT_NOTIFY_BODY_TEMPLATE,
            "urlTemplate": "",
            "msgType": "text",
            "htmlHeight": 200,
        },
        {
            "id": "iyuu",
            "name": "IYUU",
            "type": "iyuu",
            "enabled": False,
            "url": "",
            "token": "",
            "timeout": 5,
            "titleTemplate": DEFAULT_NOTIFY_TITLE_TEMPLATE,
            "bodyTemplate": DEFAULT_NOTIFY_BODY_TEMPLATE,
            "urlTemplate": "",
            "msgType": "text",
            "htmlHeight": 200,
        },
        {
            "id": "meow",
            "name": "Meow",
            "type": "meow",
            "enabled": False,
            "url": "",
            "token": "",
            "timeout": 5,
            "titleTemplate": DEFAULT_NOTIFY_TITLE_TEMPLATE,
            "bodyTemplate": DEFAULT_NOTIFY_BODY_TEMPLATE,
            "urlTemplate": "",
            "msgType": "text",
            "htmlHeight": 200,
        },
    ]


def sanitize_monitor_rule(rule: MonitorRule) -> dict:
    cleaned = MonitorRule(
        id=(rule.id or f"rule-{int(now())}").strip()[:64],
        name=(rule.name or "未命名规则").strip()[:80],
        metric=(rule.metric or "wan_tx_bps").strip(),
        operator=(rule.operator or "gte").strip(),
        threshold=max(0, int(rule.threshold or 0)),
        durationSeconds=max(0, int(rule.durationSeconds or 0)),
        scope=(rule.scope or "wan").strip(),
        direction=(rule.direction or "tx").strip(),
        window=(rule.window or "realtime").strip(),
        enabled=bool(rule.enabled),
        channelIds=[str(item).strip()[:64] for item in (rule.channelIds or []) if str(item).strip()],
    )
    if cleaned.operator not in {"gte", "lte"}:
        cleaned.operator = "gte"
    if cleaned.scope not in {"wan", "lan", "all"}:
        cleaned.scope = "wan"
    if cleaned.direction not in {"rx", "tx", "both"}:
        cleaned.direction = "tx"
    return cleaned.model_dump()


def sanitize_notification_channel(channel: NotificationChannel) -> dict:
    cleaned = NotificationChannel(
        id=(channel.id or f"channel-{int(now())}").strip()[:64],
        name=(channel.name or "通知渠道").strip()[:80],
        type=(channel.type or "webhook").strip().lower(),
        enabled=bool(channel.enabled),
        url=sanitize_http_url(channel.url or ""),
        token=(channel.token or "").strip(),
        timeout=max(1, min(30, float(channel.timeout or 5))),
        titleTemplate=(channel.titleTemplate or DEFAULT_NOTIFY_TITLE_TEMPLATE).strip()[:500],
        bodyTemplate=(channel.bodyTemplate or DEFAULT_NOTIFY_BODY_TEMPLATE).strip()[:4000],
        urlTemplate=(channel.urlTemplate or "").strip()[:1000],
        msgType=(channel.msgType or "text").strip().lower(),
        htmlHeight=max(100, min(1200, int(channel.htmlHeight or 200))),
    )
    if cleaned.type not in {"webhook", "iyuu", "meow"}:
        cleaned.type = "webhook"
    if cleaned.msgType not in {"text", "html"}:
        cleaned.msgType = "text"
    return cleaned.model_dump()


def docker_container_key(container_id: str = "", container_name: str = "") -> str:
    cid = str(container_id or "").strip().lstrip("/")[:12]
    name = str(container_name or "").strip().lstrip("/")
    return cid or name


def normalize_docker_scheme(value: str) -> str:
    cleaned = str(value or "http").strip().lower()
    return cleaned if cleaned in {"http", "https"} else "http"


SERVICE_PORT_HINTS = {
    20: ("ftp-data", "tcp"),
    21: ("ftp", "tcp"),
    22: ("ssh", "tcp"),
    25: ("smtp", "tcp"),
    53: ("dns", "udp"),
    80: ("web", "http"),
    110: ("pop3", "tcp"),
    143: ("imap", "tcp"),
    443: ("web", "https"),
    445: ("smb", "tcp"),
    465: ("smtps", "tcp"),
    587: ("smtp", "tcp"),
    631: ("ipp", "tcp"),
    873: ("rsync", "tcp"),
    993: ("imaps", "tcp"),
    995: ("pop3s", "tcp"),
    1433: ("sqlserver", "tcp"),
    1883: ("mqtt", "tcp"),
    2049: ("nfs", "tcp"),
    2375: ("docker", "tcp"),
    2376: ("docker-tls", "tcp"),
    3306: ("mysql", "tcp"),
    3389: ("rdp", "tcp"),
    5432: ("postgresql", "tcp"),
    5672: ("amqp", "tcp"),
    5900: ("vnc", "tcp"),
    6379: ("redis", "tcp"),
    6881: ("bt", "tcp"),
    8000: ("web", "http"),
    8008: ("web", "http"),
    8080: ("web", "http"),
    8081: ("web", "http"),
    8088: ("web", "http"),
    8443: ("web", "https"),
    8888: ("web", "http"),
    9000: ("web", "http"),
    9090: ("web", "http"),
    9200: ("elasticsearch", "http"),
    9418: ("git", "tcp"),
    10000: ("web", "http"),
    11211: ("memcached", "tcp"),
    15672: ("web", "http"),
    27017: ("mongodb", "tcp"),
}
WEB_IMAGE_HINTS = (
    "nginx",
    "apache",
    "httpd",
    "caddy",
    "traefik",
    "qbittorrent",
    "transmission",
    "jellyfin",
    "emby",
    "plex",
    "sonarr",
    "radarr",
    "prowlarr",
    "jackett",
    "alist",
    "filebrowser",
    "vaultwarden",
    "portainer",
    "homepage",
    "dash",
    "grafana",
    "prometheus",
    "nextcloud",
    "wordpress",
)


def normalize_access_mode(value: str) -> str:
    cleaned = str(value or "auto").strip().lower()
    return cleaned if cleaned in {"auto", "web", "copy", "hidden"} else "auto"


def normalize_service_name(value: str) -> str:
    cleaned = str(value or "").strip().lower()[:40]
    return "".join(ch for ch in cleaned if ch.isalnum() or ch in {"-", "_"})


def docker_container_stats(container_id: str) -> dict:
    selected = str(container_id or "").strip()[:12]
    if not selected:
        return {}
    stats = docker_api_get(f"/containers/{selected}/stats?stream=false")
    if not isinstance(stats, dict):
        return {}

    cpu_stats = stats.get("cpu_stats") if isinstance(stats.get("cpu_stats"), dict) else {}
    precpu_stats = stats.get("precpu_stats") if isinstance(stats.get("precpu_stats"), dict) else {}
    cpu_usage = cpu_stats.get("cpu_usage") if isinstance(cpu_stats.get("cpu_usage"), dict) else {}
    precpu_usage = precpu_stats.get("cpu_usage") if isinstance(precpu_stats.get("cpu_usage"), dict) else {}
    cpu_delta = max(0, int(cpu_usage.get("total_usage") or 0) - int(precpu_usage.get("total_usage") or 0))
    system_delta = max(0, int(cpu_stats.get("system_cpu_usage") or 0) - int(precpu_stats.get("system_cpu_usage") or 0))
    cpu_count = len(cpu_usage.get("percpu_usage") or []) or int(stats.get("online_cpus") or 1)
    cpu_percent = round((cpu_delta / system_delta) * cpu_count * 100.0, 2) if cpu_delta and system_delta else 0.0

    memory_stats = stats.get("memory_stats") if isinstance(stats.get("memory_stats"), dict) else {}
    memory_usage = int(memory_stats.get("usage") or 0)
    memory_limit = int(memory_stats.get("limit") or 0)
    memory_detail = memory_stats.get("stats") if isinstance(memory_stats.get("stats"), dict) else {}
    inactive_file = int(memory_detail.get("inactive_file") or memory_detail.get("total_inactive_file") or 0)
    memory_working_set = max(0, memory_usage - inactive_file) if inactive_file else memory_usage

    network_rx = 0
    network_tx = 0
    networks = stats.get("networks") if isinstance(stats.get("networks"), dict) else {}
    for item in networks.values():
        if not isinstance(item, dict):
            continue
        network_rx += int(item.get("rx_bytes") or 0)
        network_tx += int(item.get("tx_bytes") or 0)

    return {
        "cpuPercent": cpu_percent,
        "memoryUsedBytes": memory_working_set,
        "memoryUsageBytes": memory_usage,
        "memoryLimitBytes": memory_limit,
        "netRxBytes": network_rx,
        "netTxBytes": network_tx,
    }


def infer_port_access(host_port: int, container_port: int, proto: str, image: str = "", name: str = "") -> dict:
    ports = [int(host_port or 0), int(container_port or 0)]
    service = ""
    mode = "copy"
    scheme = "http"
    for port in ports:
        hint = SERVICE_PORT_HINTS.get(port)
        if hint:
            service, hint_scheme = hint
            if service == "web":
                mode = "web"
                scheme = hint_scheme
            elif hint_scheme in {"http", "https"}:
                mode = "web"
                scheme = hint_scheme
            else:
                mode = "copy"
            break
    haystack = f"{image} {name}".lower()
    if not service and any(keyword in haystack for keyword in WEB_IMAGE_HINTS):
        service = "web"
        mode = "web"
    if proto == "udp" and service != "web":
        mode = "copy"
    return {"service": service or "unknown", "accessMode": mode, "scheme": scheme}


def sanitize_docker_icon(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    if not cleaned.startswith("data:image/"):
        return ""
    header, sep, payload = cleaned.partition(",")
    if not sep:
        return ""
    mime = header[5:].split(";", 1)[0].lower()
    if mime not in {"image/png", "image/jpeg", "image/webp"}:
        return ""
    try:
        base64.b64decode(payload, validate=True)
    except Exception:
        return ""
    return cleaned


def docker_port_probe_key(port: int, path: str = "/") -> str:
    cleaned_path = normalize_docker_path(path or "/") or "/"
    return f"{int(port)}:{cleaned_path}"


def probe_web_endpoint(host: str, port: int, path: str = "/") -> dict:
    cleaned_host = str(host or "").strip() or "127.0.0.1"
    cleaned_path = normalize_docker_path(path or "/") or "/"
    results = []
    for scheme in ("http", "https"):
        url = f"{scheme}://{cleaned_host}:{int(port)}{cleaned_path}"
        try:
            request = urllib.request.Request(url, method="GET", headers={"user-agent": "nas-traffic-lens-probe/1.0"})
            with urllib.request.urlopen(request, timeout=max(0.2, min(5.0, DOCKER_WEB_PROBE_TIMEOUT))) as response:
                content_type = response.headers.get("content-type", "")
                return {
                    "ok": True,
                    "isWeb": True,
                    "scheme": scheme,
                    "status": response.status,
                    "contentType": content_type,
                    "url": url,
                    "checkedAt": int(now()),
                }
        except Exception as exc:
            results.append(f"{scheme}: {str(exc)[:120]}")
    return {
        "ok": True,
        "isWeb": False,
        "scheme": "http",
        "status": None,
        "contentType": "",
        "detail": "; ".join(results),
        "checkedAt": int(now()),
    }


def normalize_docker_path(value: str) -> str:
    cleaned = str(value or "").strip()[:300]
    if not cleaned:
        return ""
    if cleaned.startswith(("http://", "https://")):
        return ""
    return cleaned if cleaned.startswith("/") else f"/{cleaned}"


def docker_port_label_key(container_name: str, proto: str, host_port: int) -> str:
    return f"container:{container_name}:{proto}:{int(host_port)}"


def sanitize_docker_port(port: DockerPortPayload, container_id: str, container_name: str) -> Optional[dict]:
    proto = str(port.proto or "tcp").strip().lower()
    if proto not in {"tcp", "udp"}:
        proto = "tcp"
    host_port = int(port.hostPort or 0)
    container_port = int(port.containerPort or host_port or 0)
    if not host_port or host_port < 1 or host_port > 65535:
        return None
    if container_port < 0 or container_port > 65535:
        container_port = host_port
    name = str(container_name or container_id or "unknown").strip().lstrip("/")[:120] or "unknown"
    key = docker_port_label_key(name, proto, host_port)
    inferred = infer_port_access(host_port, container_port, proto, name=name)
    service = normalize_service_name(port.service) or inferred["service"]
    access_mode = normalize_access_mode(port.accessMode)
    if access_mode == "auto":
        access_mode = inferred["accessMode"]
    scheme = normalize_docker_scheme(port.scheme or inferred["scheme"])
    return {
        "id": str(container_id or "").strip()[:12],
        "name": name,
        "hostPort": host_port,
        "containerPort": container_port or host_port,
        "proto": proto,
        "labelKey": key,
        "label": str(port.label or "").strip()[:120],
        "service": service,
        "accessMode": access_mode,
        "scheme": scheme,
        "path": normalize_docker_path(port.path),
        "enabled": bool(port.enabled),
        "manual": bool(port.manual),
    }


def sanitize_docker_overrides(payload: DockerContainerPortsPayload) -> dict:
    container_id = str(payload.containerId or "").strip()[:12]
    container_name = str(payload.containerName or "").strip().lstrip("/")[:120]
    key = docker_container_key(container_id, container_name)
    if not key:
        raise ValueError("missing container")
    ports = []
    seen = set()
    for raw_port in payload.ports:
        item = sanitize_docker_port(raw_port, container_id, container_name or container_id)
        if not item or not item.get("enabled"):
            continue
        port_key = (item["proto"], item["hostPort"])
        if port_key in seen:
            continue
        seen.add(port_key)
        ports.append(item)
    return {
        "key": key,
        "containerId": container_id,
        "containerName": container_name,
        "icon": sanitize_docker_icon(payload.icon),
        "ports": sorted(ports, key=lambda row: (row.get("hostPort", 0), row.get("proto", ""))),
    }


def alert_settings_from_rules(rules: List[dict]) -> dict:
    result = {"highWanTxBps": 0, "highWanTxSeconds": 0, "stageWanTxBytes": 0, "dailyWanTxBytes": 0}
    for rule in rules:
        if not rule.get("enabled"):
            continue
        metric = rule.get("metric")
        if metric == "wan_tx_bps":
            result["highWanTxBps"] = int(rule.get("threshold") or 0)
            result["highWanTxSeconds"] = int(rule.get("durationSeconds") or 0)
        elif metric == "stage_wan_tx_bytes":
            result["stageWanTxBytes"] = int(rule.get("threshold") or 0)
        elif metric == "daily_wan_tx_bytes":
            result["dailyWanTxBytes"] = int(rule.get("threshold") or 0)
    return result


def rules_from_alert_settings(settings: AlertSettings) -> List[dict]:
    rules = default_monitor_rules()
    for rule in rules:
        if rule["metric"] == "wan_tx_bps":
            rule["threshold"] = max(0, int(settings.highWanTxBps or 0))
            rule["durationSeconds"] = max(0, int(settings.highWanTxSeconds or 0))
            rule["enabled"] = rule["threshold"] > 0
        elif rule["metric"] == "stage_wan_tx_bytes":
            rule["threshold"] = max(0, int(settings.stageWanTxBytes or 0))
            rule["enabled"] = rule["threshold"] > 0
        elif rule["metric"] == "daily_wan_tx_bytes":
            rule["threshold"] = max(0, int(settings.dailyWanTxBytes or 0))
            rule["enabled"] = rule["threshold"] > 0
    return rules


def empty_docker_overrides() -> dict:
    return {"containers": {}}


def docker_override_for(overrides: dict, container_id: str, container_name: str) -> dict:
    containers = overrides.get("containers") if isinstance(overrides, dict) else {}
    if not isinstance(containers, dict):
        return {}
    for key in (docker_container_key(container_id, container_name), str(container_id or "")[:12], str(container_name or "").lstrip("/")):
        if key and isinstance(containers.get(key), dict):
            return containers[key]
    return {}


def normalize_override_port(raw: dict, container_id: str, container_name: str) -> Optional[dict]:
    try:
        return sanitize_docker_port(DockerPortPayload(**raw), container_id, container_name)
    except Exception:
        return None


def merge_container_ports(
    automatic_ports: List[dict],
    override: dict,
    container_id: str,
    container_name: str,
    web_probes: Optional[dict] = None,
) -> List[dict]:
    merged: Dict[Tuple[str, int], dict] = {}
    manual_keys = set()
    icon = sanitize_docker_icon(override.get("icon") or "")
    web_probes = web_probes or {}
    for raw in override.get("ports") or []:
        item = normalize_override_port(raw, container_id, container_name)
        if not item or not item.get("enabled", True):
            continue
        item["manual"] = True
        merged[(item["proto"], int(item["hostPort"]))] = item
        manual_keys.add((item["proto"], int(item["hostPort"])))

    for item in automatic_ports:
        key = (item.get("proto"), int(item.get("hostPort") or 0))
        if key in manual_keys:
            manual = merged[key]
            item = {
                **item,
                "label": manual.get("label", item.get("label", "")),
                "service": manual.get("service", item.get("service", "unknown")),
                "scheme": manual.get("scheme", item.get("scheme", "http")),
                "path": manual.get("path", item.get("path", "")),
                "accessMode": manual.get("accessMode", item.get("accessMode", "copy")),
                "manual": False,
            }
        merged[key] = item
    result = sorted(merged.values(), key=lambda row: (row.get("hostPort", 0), row.get("proto", "")))
    if icon:
        for item in result:
            item["containerIcon"] = icon
    for item in result:
        probe = web_probes.get(docker_port_probe_key(int(item.get("hostPort") or 0), item.get("path") or "/"))
        if isinstance(probe, dict):
            item["webProbe"] = probe
            if item.get("accessMode") != "hidden":
                item["accessMode"] = "web" if probe.get("isWeb") else "copy"
                if probe.get("isWeb") and probe.get("scheme"):
                    item["scheme"] = probe.get("scheme")
    return result


def discover_containers(
    labels: Dict[str, str],
    overrides: Optional[dict] = None,
    stats_cache: Optional[dict] = None,
    web_probes: Optional[dict] = None,
) -> Tuple[Dict[Tuple[str, int], dict], List[dict]]:
    ports: Dict[Tuple[str, int], dict] = {}
    rows: List[dict] = []
    overrides = overrides or empty_docker_overrides()
    stats_cache = stats_cache or {}
    if not ENABLE_DOCKER_DISCOVERY:
        for override in (overrides.get("containers") or {}).values():
            if not isinstance(override, dict):
                continue
            container_id = str(override.get("containerId") or "")[:12]
            name = str(override.get("containerName") or container_id or "manual").lstrip("/")
            container_ports = merge_container_ports([], override, container_id, name, web_probes)
            for item in container_ports:
                ports[(item["proto"], int(item["hostPort"]))] = item
            rows.append(
                {
                    "id": container_id or name,
                    "name": name,
                    "image": "",
                    "state": "manual",
                    "status": "手动端口配置",
                    "created": 0,
                    "networkMode": "manual",
                    "containerIcon": sanitize_docker_icon(override.get("icon") or ""),
                    "ports": container_ports,
                    "manualOnly": True,
                }
            )
        rows.sort(key=lambda row: (row.get("name", ""), row.get("id", "")))
        return ports, rows
    containers = docker_api_get("/containers/json")
    if not isinstance(containers, list):
        return ports, rows

    for container in containers:
        if not isinstance(container, dict):
            continue
        try:
            cid = str(container.get("Id") or "")[:12]
            names = container.get("Names") or []
            raw_name = str(names[0]) if names else cid
            name = raw_name.lstrip("/") or cid or "unknown"
            image = str(container.get("Image") or "")
            state = str(container.get("State") or "")
            status = str(container.get("Status") or "")
            created = int(container.get("Created") or 0)
            host_config = container.get("HostConfig") if isinstance(container.get("HostConfig"), dict) else {}
            network_mode = str(host_config.get("NetworkMode") or "")
            container_ports = []
            for proto, host_port, container_port in parse_docker_api_ports(container.get("Ports") or []):
                key = docker_port_label_key(name, proto, host_port)
                inferred = infer_port_access(host_port, container_port, proto, image=image, name=name)
                item = {
                    "id": cid,
                    "name": name,
                    "image": image,
                    "hostPort": host_port,
                    "containerPort": container_port,
                    "proto": proto,
                    "labelKey": key,
                    "label": labels.get(key, ""),
                    "service": inferred["service"],
                    "accessMode": inferred["accessMode"],
                    "scheme": inferred["scheme"],
                    "path": "",
                    "manual": False,
                }
                container_ports.append(item)
            override = docker_override_for(overrides, cid, name)
            container_ports = merge_container_ports(container_ports, override, cid, name, web_probes)
            for item in container_ports:
                ports[(item["proto"], int(item["hostPort"]))] = item
            stats = stats_cache.get(cid) or {}
            rows.append(
                {
                    "id": cid,
                    "name": name,
                    "image": image,
                    "state": state,
                    "status": status,
                    "created": created,
                    "networkMode": network_mode,
                    **stats,
                    "uptimeSeconds": max(0, int(now()) - created) if created else None,
                    "containerIcon": sanitize_docker_icon((override or {}).get("icon") or ""),
                    "ports": container_ports,
                }
            )
        except Exception as exc:
            print(f"skip docker container metadata: {exc}", flush=True)
    rows.sort(key=lambda row: (row.get("name", ""), row.get("id", "")))
    return ports, rows


def discover_container_ports(labels: Dict[str, str], overrides: Optional[dict] = None) -> Dict[Tuple[str, int], dict]:
    ports, _rows = discover_containers(labels, overrides)
    return ports


def docker_api_request(method: str, path: str, body: bytes = b"", timeout: float = 2.0) -> dict:
    headers = [
        f"{method.upper()} {path} HTTP/1.1",
        "Host: docker",
        "Connection: close",
    ]
    if body:
        headers.append("Content-Type: application/json")
        headers.append(f"Content-Length: {len(body)}")
    request = ("\r\n".join(headers) + "\r\n\r\n").encode() + body
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(DOCKER_SOCKET)
            sock.sendall(request)
            chunks = []
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                chunks.append(data)
    except OSError as exc:
        return {"ok": False, "status": 0, "json": None, "body": "", "detail": str(exc)}
    raw = b"".join(chunks)
    header, _, body = raw.partition(b"\r\n\r\n")
    status_line = header.splitlines()[0] if header else b""
    status = 0
    try:
        status = int(status_line.split()[1])
    except (IndexError, ValueError):
        status = 0
    decoded = dechunk_http_body(body).decode(errors="ignore")
    parsed = None
    try:
        parsed = json.loads(decoded) if decoded.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return {"ok": 200 <= status < 300, "status": status, "json": parsed, "body": decoded[:4000], "detail": ""}


def docker_api_get(path: str):
    result = docker_api_request("GET", path)
    if not result.get("ok"):
        return []
    return result.get("json") if result.get("json") is not None else []


def dechunk_http_body(body: bytes) -> bytes:
    if b"\r\n" not in body:
        return body
    output = bytearray()
    rest = body
    while rest:
        line, sep, tail = rest.partition(b"\r\n")
        if not sep:
            return body
        try:
            size = int(line.split(b";", 1)[0], 16)
        except ValueError:
            return body
        if size == 0:
            return bytes(output)
        output.extend(tail[:size])
        rest = tail[size + 2 :]
    return bytes(output)


def parse_docker_api_ports(items: List[dict]) -> List[Tuple[str, int, int]]:
    found: List[Tuple[str, int, int]] = []
    for item in items:
        try:
            public_port = item.get("PublicPort")
            private_port = item.get("PrivatePort")
            proto = str(item.get("Type") or "tcp").lower()
            if public_port and private_port:
                found.append((proto, int(public_port), int(private_port)))
        except (AttributeError, TypeError, ValueError):
            continue
    return found


def parse_docker_ports(text: str) -> List[Tuple[str, int, int]]:
    found: List[Tuple[str, int, int]] = []
    if not text:
        return found
    for chunk in text.split(","):
        item = chunk.strip()
        if not item or "/" not in item:
            continue
        proto = item.rsplit("/", 1)[1].strip().lower()
        left = item.rsplit("/", 1)[0]
        try:
            if "->" in left:
                host, container = left.split("->", 1)
                host_port = int(host.rsplit(":", 1)[-1])
                container_port = int(container.rsplit(":", 1)[-1])
            else:
                host_port = int(left.rsplit(":", 1)[-1])
                container_port = host_port
        except ValueError:
            continue
        found.append((proto, host_port, container_port))
    return found


def unique_containers(items: List[dict]) -> List[dict]:
    seen = {}
    for item in items:
        key = item.get("labelKey") or f"{item.get('name')}:{item.get('proto')}:{item.get('hostPort')}"
        seen[key] = item
    return sorted(seen.values(), key=lambda row: (row.get("name", ""), row.get("hostPort", 0)))


DOCKER_STATS_FIELDS = {
    "cpuPercent",
    "memoryUsedBytes",
    "memoryUsageBytes",
    "memoryLimitBytes",
    "netRxBytes",
    "netTxBytes",
}


def docker_container_lookup_keys(row: dict) -> List[str]:
    values = [
        row.get("id"),
        str(row.get("id") or "")[:12],
        row.get("name"),
        docker_container_key(row.get("id") or "", row.get("name") or ""),
    ]
    seen = []
    for value in values:
        cleaned = str(value or "").strip().lstrip("/")
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def docker_container_summary(row: dict) -> dict:
    ports = row.get("ports") or []
    return {
        key: value
        for key, value in row.items()
        if key not in {"ports", "containerIcon", *DOCKER_STATS_FIELDS}
    } | {
        "portCount": len(ports),
        "hasIcon": bool(row.get("containerIcon")),
    }


def serialize_docker_container_detail(row: dict) -> dict:
    return {
        key: value
        for key, value in row.items()
        if key not in DOCKER_STATS_FIELDS
    }


def normalize_interface_view(value: str) -> str:
    cleaned = str(value or "physical").strip().lower()
    return cleaned if cleaned in INTERFACE_VIEW_MODES else "physical"


def interface_in_view(item: dict, view: str) -> bool:
    if view == "all":
        return True
    detail = item.get("detail") or {}
    if view == "captured":
        return bool(detail.get("captured"))
    if view == "virtual":
        return bool(detail.get("virtual"))
    return bool(detail.get("captured") or detail.get("defaultRoute") or not detail.get("virtual"))


def filter_interfaces(interfaces: dict, view: str) -> dict:
    if view == "all":
        return interfaces
    filtered = {name: item for name, item in interfaces.items() if interface_in_view(item, view)}
    return filtered or interfaces


def filter_rates(rates: dict, interface_names: set) -> dict:
    if not interface_names:
        return rates
    return {name: value for name, value in rates.items() if name in interface_names}


def summarize_interfaces(interfaces: dict, rates: dict) -> dict:
    summary = {
        "wan": {"rxBps": 0, "txBps": 0, "rxBytes": 0, "txBytes": 0},
        "lan": {"rxBps": 0, "txBps": 0, "rxBytes": 0, "txBytes": 0},
        "system": {"rxBps": 0, "txBps": 0, "rxBytes": 0, "txBytes": 0},
        "interfaces": {
            "total": len(interfaces),
            "up": 0,
            "captured": 0,
            "virtual": 0,
        },
    }
    for name, item in interfaces.items():
        detail = item.get("detail") or {}
        if detail.get("isUp"):
            summary["interfaces"]["up"] += 1
        if detail.get("captured"):
            summary["interfaces"]["captured"] += 1
        if detail.get("virtual"):
            summary["interfaces"]["virtual"] += 1

        rate = rates.get(name) or {}
        summary["system"]["rxBps"] += rate.get("systemRxBps", 0)
        summary["system"]["txBps"] += rate.get("systemTxBps", 0)
        summary["system"]["rxBytes"] += (item.get("system") or {}).get("rxBytes", 0)
        summary["system"]["txBytes"] += (item.get("system") or {}).get("txBytes", 0)

        for scope in ("wan", "lan"):
            scope_rate = (rate.get("scopes") or {}).get(scope) or {}
            scope_total = (item.get("scopes") or {}).get(scope) or {}
            summary[scope]["rxBps"] += scope_rate.get("rxBps", 0)
            summary[scope]["txBps"] += scope_rate.get("txBps", 0)
            summary[scope]["rxBytes"] += scope_total.get("rxBytes", 0)
            summary[scope]["txBytes"] += scope_total.get("txBytes", 0)
    return summary


def summarize_stage(stage_totals: Dict[str, Dict[str, Counter]], started_at: Optional[float]) -> dict:
    summary = {
        "active": bool(started_at),
        "startedAt": started_at,
        "durationSeconds": max(0, int(now() - started_at)) if started_at else 0,
        "wan": empty_pair(),
        "lan": empty_pair(),
    }
    for scopes in stage_totals.values():
        for scope in ("wan", "lan"):
            counter = scopes.get(scope)
            if not counter:
                continue
            snapshot = counter.snapshot()
            summary[scope]["rxBytes"] += snapshot.get("rxBytes", 0)
            summary[scope]["txBytes"] += snapshot.get("txBytes", 0)
    return summary


def normalize_process_period(value: str) -> str:
    cleaned = str(value or "30s").strip().lower()
    return cleaned if cleaned in {"30s", "today", "1d", "3d", "7d", "30d", "custom"} else "30s"


def process_period_seconds(period: str) -> int:
    if period == "today":
        current = datetime.fromtimestamp(now())
        return max(60, int((current - current.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()))
    if period == "3d":
        return 3 * 86400
    if period == "7d":
        return 7 * 86400
    if period == "30d":
        return 30 * 86400
    return 86400


class TrafficCollector:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.db = TrafficDB(DB_PATH)
        self.iface_totals: Dict[str, Dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
        self.process_totals: Dict[str, Counter] = defaultdict(Counter)
        self.port_totals: Dict[str, Counter] = defaultdict(Counter)
        self.conn_totals: Dict[str, Counter] = defaultdict(Counter)
        self.history = deque(maxlen=max(60, RETENTION_SECONDS))
        self.process_recent: Dict[int, Dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
        self.alerts = deque(maxlen=200)
        self.monitor_rules = default_monitor_rules()
        self.notification_channels = default_notification_channels()
        self.alert_settings = AlertSettings(**alert_settings_from_rules(self.monitor_rules))
        self.notify_settings = NotifySettings(
            channel=self.notification_channels[0]["type"],
            webhookUrl=self.notification_channels[0]["url"],
            webhookTimeout=self.notification_channels[0]["timeout"],
        )
        self.last_rates: Dict[str, dict] = {}
        self.stage_started_at: Optional[float] = None
        self.stage_totals: Dict[str, Dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
        self.sniffers: List[AsyncSniffer] = []
        self.socket_map: Dict[Tuple[str, str, str, int, int], dict] = {}
        self.last_socket_refresh = 0.0
        self.local_addresses = set()
        self.interface_details: Dict[str, dict] = {}
        self.capture_interfaces: List[str] = []
        self.container_ports: Dict[Tuple[str, int], dict] = {}
        self.container_rows: List[dict] = []
        self.container_rows_by_id: Dict[str, dict] = {}
        self.docker_stats_cache: Dict[str, dict] = {}
        self.docker_web_probe_cache: Dict[str, dict] = {}
        self.docker_overrides = empty_docker_overrides()
        self.container_status = {"enabled": ENABLE_DOCKER_DISCOVERY, "count": 0, "lastRefresh": None}
        self.last_container_refresh = 0.0
        self.container_refresh_lock = threading.Lock()
        self.conntrack_summary = {"available": False, "source": "capture", "total": None, "wan": None, "lan": None}
        self.last_conntrack_refresh = 0.0
        self.last_persist_totals: Optional[dict] = None
        self.last_process_persist_totals: Optional[dict] = None
        self.high_tx_started_at: Optional[float] = None
        self.high_tx_alert_active = False
        self.stage_alert_active = False
        self.stage_paused_at: Optional[float] = None
        self.stage_accumulated_seconds = 0.0
        self.daily_alert_date = ""
        self.rule_states: Dict[str, dict] = {}

    def start(self) -> None:
        if getattr(self, "started", False):
            return
        self.started = True
        conf.use_pcap = False
        self.db.start()
        self.load_saved_settings()
        self.local_addresses = get_local_addresses()
        self.refresh_interface_details()
        self.refresh_container_ports()
        self.refresh_socket_map()
        self.refresh_conntrack_summary()
        if AUTO_START_STAGE and not self.stage_started_at:
            self.stage_started_at = now()
            self.stage_totals = defaultdict(lambda: defaultdict(Counter))
            self.stage_accumulated_seconds = 0.0

        for iface in self.capture_interfaces:
            sniffer = AsyncSniffer(iface=iface, prn=lambda packet, name=iface: self.handle_packet(name, packet), store=False)
            try:
                sniffer.start()
                self.sniffers.append(sniffer)
            except Exception as exc:
                print(f"failed to start sniffer on {iface}: {exc}", flush=True)

        threading.Thread(target=self.rate_loop, daemon=True).start()
        threading.Thread(target=self.socket_loop, daemon=True).start()
        threading.Thread(target=self.interface_loop, daemon=True).start()
        threading.Thread(target=self.conntrack_loop, daemon=True).start()

    def load_saved_settings(self) -> None:
        global SAMPLE_SECONDS, RETENTION_SECONDS, CONNECTION_ACTIVE_SECONDS, CONNECTION_RETENTION_SECONDS
        global AUTO_START_STAGE, CONNTRACK_REFRESH_SECONDS, PERSIST_INTERVAL_SECONDS, HISTORY_RETENTION_DAYS
        alerts = self.db.get_setting("alerts")
        notify = self.db.get_setting("notify")
        rules = self.db.get_setting("monitor_rules")
        channels = self.db.get_setting("notification_channels")
        runtime = self.db.get_setting("runtime_settings")
        docker_overrides = self.db.get_setting("docker_overrides")
        if rules and isinstance(rules.get("rules"), list):
            try:
                self.monitor_rules = [sanitize_monitor_rule(MonitorRule(**item)) for item in rules["rules"]]
            except Exception as exc:
                print(f"ignore invalid saved monitor rules: {exc}", flush=True)
        elif alerts:
            try:
                self.monitor_rules = rules_from_alert_settings(AlertSettings(**alerts))
            except Exception as exc:
                print(f"ignore invalid saved alert settings: {exc}", flush=True)

        if channels and isinstance(channels.get("channels"), list):
            try:
                self.notification_channels = [sanitize_notification_channel(NotificationChannel(**item)) for item in channels["channels"]]
            except Exception as exc:
                print(f"ignore invalid saved notification channels: {exc}", flush=True)
        elif notify:
            try:
                legacy = NotifySettings(**notify)
                self.notification_channels[0].update(
                    {
                        "type": legacy.channel if legacy.channel in {"webhook", "iyuu", "meow"} else "webhook",
                        "enabled": bool(legacy.webhookUrl),
                        "url": legacy.webhookUrl,
                        "timeout": legacy.webhookTimeout,
                    }
                )
            except Exception as exc:
                print(f"ignore invalid saved notify settings: {exc}", flush=True)

        if runtime:
            try:
                settings = RuntimeSettingsPayload(**runtime)
                SAMPLE_SECONDS = float(settings.sampleSeconds)
                RETENTION_SECONDS = int(settings.retentionSeconds)
                PERSIST_INTERVAL_SECONDS = int(settings.persistIntervalSeconds)
                HISTORY_RETENTION_DAYS = int(settings.historyRetentionDays)
                CONNECTION_ACTIVE_SECONDS = int(settings.connectionActiveSeconds)
                CONNECTION_RETENTION_SECONDS = int(settings.connectionRetentionSeconds)
                CONNTRACK_REFRESH_SECONDS = int(settings.conntrackRefreshSeconds)
                AUTO_START_STAGE = bool(settings.autoStartStage)
            except Exception as exc:
                print(f"ignore invalid saved runtime settings: {exc}", flush=True)

        if docker_overrides and isinstance(docker_overrides.get("containers"), dict):
            self.docker_overrides = docker_overrides

        self.sync_legacy_settings()

    def sync_legacy_settings(self) -> None:
        self.alert_settings = AlertSettings(**alert_settings_from_rules(self.monitor_rules))
        primary = next((item for item in self.notification_channels if item.get("id") == "webhook"), None)
        primary = primary or (self.notification_channels[0] if self.notification_channels else default_notification_channels()[0])
        self.notify_settings = NotifySettings(
            channel=primary.get("type") or "webhook",
            webhookUrl=primary.get("url") or "",
            webhookTimeout=primary.get("timeout") or 5,
        )

    def refresh_interface_details(self) -> None:
        details = get_interface_details(set(self.capture_interfaces))
        if not self.capture_interfaces:
            self.capture_interfaces = get_capture_interfaces_from_details(details)
            details = get_interface_details(set(self.capture_interfaces))
        with self.lock:
            self.interface_details = details

    def socket_loop(self) -> None:
        while True:
            self.refresh_socket_map()
            self.local_addresses = get_local_addresses()
            time.sleep(max(3, SOCKET_REFRESH_SECONDS))

    def interface_loop(self) -> None:
        while True:
            self.refresh_interface_details()
            time.sleep(max(10, INTERFACE_REFRESH_SECONDS))

    def conntrack_loop(self) -> None:
        while True:
            self.refresh_conntrack_summary()
            time.sleep(max(2, CONNTRACK_REFRESH_SECONDS))

    def refresh_conntrack_summary(self) -> None:
        summary = read_conntrack_summary()
        with self.lock:
            self.conntrack_summary = summary
            self.last_conntrack_refresh = now()

    def refresh_container_ports(self, force: bool = False) -> None:
        current_time = now()
        with self.lock:
            cache_fresh = self.last_container_refresh and current_time - self.last_container_refresh < max(1.0, DOCKER_LIST_CACHE_SECONDS)
        if cache_fresh and not force:
            return
        block_refresh = force or not self.last_container_refresh
        if not self.container_refresh_lock.acquire(blocking=block_refresh):
            return
        try:
            with self.lock:
                cache_fresh = self.last_container_refresh and now() - self.last_container_refresh < max(1.0, DOCKER_LIST_CACHE_SECONDS)
                if cache_fresh and not force:
                    return
                labels = self.db.get_labels()
                overrides = dict(self.docker_overrides)
                web_probes = dict(self.docker_web_probe_cache)
            ports, rows = discover_containers(labels, overrides, web_probes=web_probes)
            rows_by_id = {}
            for row in rows:
                for key in docker_container_lookup_keys(row):
                    rows_by_id[key] = row
            with self.lock:
                self.container_ports = ports
                self.container_rows = rows
                self.container_rows_by_id = rows_by_id
                self.last_container_refresh = now()
                self.container_status = {
                    "enabled": ENABLE_DOCKER_DISCOVERY,
                    "socket": DOCKER_SOCKET,
                    "count": len(ports),
                    "containerCount": len(rows),
                    "lastRefresh": self.last_container_refresh,
                    "cacheSeconds": DOCKER_LIST_CACHE_SECONDS,
                    "note": "disabled; manual ports only" if not ENABLE_DOCKER_DISCOVERY and rows else ("disabled" if not ENABLE_DOCKER_DISCOVERY else ""),
                }
        finally:
            self.container_refresh_lock.release()

    def refresh_socket_map(self) -> None:
        inode_to_process = proc_inode_process_map()
        socket_tables = {}
        for root in ("/host/proc/net", "/proc/net"):
            socket_tables.update(parse_proc_net(f"{root}/tcp", "tcp"))
            socket_tables.update(parse_proc_net(f"{root}/udp", "udp"))
            socket_tables.update(parse_proc_net(f"{root}/tcp6", "tcp"))
            socket_tables.update(parse_proc_net(f"{root}/udp6", "udp"))
            if socket_tables:
                break

        mapped = {}
        for key, inode in socket_tables.items():
            process = inode_to_process.get(inode)
            if process:
                proto, local_ip, remote_ip, local_port, remote_port = key
                mapped[(proto, local_ip, remote_ip, local_port, remote_port)] = process
                mapped[(proto, local_ip, "0.0.0.0", local_port, 0)] = process
                mapped[(proto, local_ip, "::", local_port, 0)] = process

        with self.lock:
            self.socket_map = mapped
            self.last_socket_refresh = now()

    def handle_packet(self, iface: str, packet) -> None:
        parsed = parse_packet(packet)
        if not parsed:
            return

        src, dst, proto, sport, dport, size = parsed
        local_addresses = self.local_addresses
        if src in local_addresses and dst not in local_addresses:
            direction = "tx"
            local_ip, remote_ip, local_port, remote_port = src, dst, sport, dport
        elif dst in local_addresses and src not in local_addresses:
            direction = "rx"
            local_ip, remote_ip, local_port, remote_port = dst, src, dport, sport
        else:
            direction = "tx" if is_private_ip(src) else "rx"
            local_ip, remote_ip = (src, dst) if direction == "tx" else (dst, src)
            local_port, remote_port = (sport, dport) if direction == "tx" else (dport, sport)

        process = self.find_process(proto, local_ip, remote_ip, local_port, remote_port)
        self.record(
            PacketEvent(
                timestamp=now(),
                iface=iface,
                scope=traffic_scope(src, dst),
                direction=direction,
                proto=proto,
                src=src,
                dst=dst,
                sport=sport,
                dport=dport,
                size=size,
                process=process,
            )
        )

    def find_process(self, proto: str, local_ip: str, remote_ip: str, local_port: int, remote_port: int) -> dict:
        candidates = [
            (proto, local_ip, remote_ip, local_port, remote_port),
            (proto, "0.0.0.0", remote_ip, local_port, remote_port),
            (proto, "::", remote_ip, local_port, remote_port),
            (proto, local_ip, "0.0.0.0", local_port, 0),
            (proto, local_ip, "::", local_port, 0),
            (proto, "0.0.0.0", "0.0.0.0", local_port, 0),
            (proto, "::", "::", local_port, 0),
        ]
        with self.lock:
            for key in candidates:
                process = self.socket_map.get(key)
                if process:
                    return process
        return {"pid": None, "name": "unknown", "cmdline": ""}

    def find_container(self, proto: str, ports: List[int]) -> dict:
        with self.lock:
            for port in ports:
                item = self.container_ports.get((proto, int(port)))
                if item:
                    return item
        return {}

    def record(self, event: PacketEvent) -> None:
        container = self.find_container(event.proto, [event.sport, event.dport])
        if container:
            event.process = {**event.process, "container": container}
        process_key = process_key_for(event.process)
        port_key = f"{event.proto}:{event.sport}->{event.dport}"
        conn_key = (
            f"{event.iface}|{event.scope}|{event.proto}|"
            f"{event.src}:{event.sport}|{event.dst}:{event.dport}|{process_key}"
        )

        with self.lock:
            self.iface_totals[event.iface][event.scope].add(event.direction, event.size)
            self.process_totals[process_key].add(event.direction, event.size)
            self.port_totals[port_key].add(event.direction, event.size)
            self.conn_totals[conn_key].add(event.direction, event.size)
            self.process_recent[int(event.timestamp)][process_key].add(event.direction, event.size)
            if self.stage_started_at:
                self.stage_totals[event.iface][event.scope].add(event.direction, event.size)

    def rate_loop(self) -> None:
        previous = None
        last_persist = 0.0
        last_prune = 0.0
        while True:
            current = self.snapshot_interfaces()
            current_time = now()
            if previous:
                elapsed = max(0.001, current_time - previous["timestamp"])
                rates = diff_rates(previous["interfaces"], current, elapsed)
                with self.lock:
                    self.last_rates = rates
                    self.history.append({"timestamp": current_time, "rates": rates})
                self.evaluate_alerts(rates, current_time)
            if current_time - last_persist >= PERSIST_INTERVAL_SECONDS:
                self.persist_minute(current, current_time)
                self.persist_process_minute(current_time)
                self.evaluate_daily_alert(current_time)
                last_persist = current_time
            if current_time - last_prune >= 60:
                self.prune_stale()
                self.prune_recent_processes(current_time)
                self.db.prune_old(int(current_time - HISTORY_RETENTION_DAYS * 86400))
                last_prune = current_time
            previous = {"timestamp": current_time, "interfaces": current}
            time.sleep(max(0.5, SAMPLE_SECONDS))

    def snapshot_interfaces(self) -> dict:
        io = psutil.net_io_counters(pernic=True)
        with self.lock:
            details = dict(self.interface_details)
            capture_set = set(self.capture_interfaces)
            interfaces = {}
            for iface, raw in io.items():
                detail = details.get(iface, {"name": iface, "captured": iface in capture_set})
                detail = {**detail, "captured": iface in capture_set}
                scopes = {
                    scope: counter.snapshot()
                    for scope, counter in self.iface_totals.get(iface, {}).items()
                }
                interfaces[iface] = {
                    "detail": detail,
                    "scopes": scopes,
                    "system": {
                        "rxBytes": raw.bytes_recv,
                        "txBytes": raw.bytes_sent,
                        "rxPackets": raw.packets_recv,
                        "txPackets": raw.packets_sent,
                    },
                }

            for iface, counters in self.iface_totals.items():
                interfaces.setdefault(
                    iface,
                    {
                        "detail": {**details.get(iface, {"name": iface}), "captured": iface in capture_set},
                        "scopes": {scope: counter.snapshot() for scope, counter in counters.items()},
                        "system": {"rxBytes": 0, "txBytes": 0, "rxPackets": 0, "txPackets": 0},
                    },
                )

            return interfaces

    def snapshot_totals(self, interface_view: str = "physical") -> dict:
        with self.lock:
            conn_items = list(self.conn_totals.items())

        interfaces = filter_interfaces(self.snapshot_interfaces(), interface_view)
        interface_names = set(interfaces.keys())
        connection_summary = self.connection_summary(conn_items, interface_names)
        return {
            "interfaces": interfaces,
            "connectionSummary": connection_summary,
        }

    def connection_counts(self) -> dict:
        with self.lock:
            conntrack = dict(self.conntrack_summary)
            conn_items = list(self.conn_totals.items())
            socket_summary = socket_connection_summary(self.socket_map)
        fallback = self.connection_summary(conn_items, set())
        prefer_socket = CONNECTION_COUNT_SOURCE == "socket" and socket_summary.get("available")
        prefer_conntrack = CONNECTION_COUNT_SOURCE == "conntrack" and conntrack.get("available")
        source = "capture"
        total = wan = lan = None
        if prefer_socket:
            source = "socket"
            total = socket_summary.get("total")
            wan = socket_summary.get("wan")
            lan = socket_summary.get("lan")
        elif prefer_conntrack:
            source = "conntrack"
            total = conntrack.get("total")
            wan = conntrack.get("wan")
            lan = conntrack.get("lan")
        elif socket_summary.get("available"):
            source = "socket"
            total = socket_summary.get("total")
            wan = socket_summary.get("wan")
            lan = socket_summary.get("lan")
        return {
            "source": source,
            "available": source != "capture",
            "total": int(total if total is not None else fallback.get("total", 0)),
            "wan": int(wan if wan is not None else fallback.get("wan", 0)),
            "lan": int(lan if lan is not None else fallback.get("lan", 0)),
            "rawTotal": conntrack.get("rawTotal"),
            "countMode": conntrack.get("mode"),
            "mode": conntrack.get("mode") if source == "conntrack" else CONNECTION_COUNT_SOURCE,
        }

    def rank_items(self, values: List[Tuple[str, Counter]], formatter, limit: int) -> List[dict]:
        rows = []
        for key, counter in values:
            try:
                item = formatter(key)
                item.update(counter.snapshot())
                rows.append(item)
            except Exception:
                print(f"skip malformed traffic key: {key}", flush=True)
        rows.sort(key=lambda row: row["totalBytes"], reverse=True)
        return rows[:limit]

    def connection_rows(self, values: List[Tuple[str, Counter]], interface_names: set, limit: Optional[int] = None) -> Tuple[List[dict], dict]:
        rows = []
        summary = {"total": 0, "wan": 0, "lan": 0}
        active_cutoff = now() - max(10, CONNECTION_ACTIVE_SECONDS)
        for key, counter in values:
            try:
                if counter.last_seen < active_cutoff:
                    continue
                item = parse_connection_key(key)
                if interface_names and item.get("iface") not in interface_names:
                    continue
                item.update(counter.snapshot())
                scope = item.get("scope")
                summary["total"] += 1
                if scope in ("wan", "lan"):
                    summary[scope] += 1
                rows.append(item)
            except Exception:
                print(f"skip malformed connection key: {key}", flush=True)
        rows.sort(key=lambda row: row["totalBytes"], reverse=True)
        return (rows[:limit] if limit else rows), summary

    def connection_summary(self, values: List[Tuple[str, Counter]], interface_names: set) -> dict:
        summary = {"total": 0, "wan": 0, "lan": 0}
        active_cutoff = now() - max(10, CONNECTION_ACTIVE_SECONDS)
        for key, counter in values:
            if counter.last_seen < active_cutoff:
                continue
            item = parse_connection_key(key)
            if interface_names and item.get("iface") not in interface_names:
                continue
            scope = item.get("scope")
            summary["total"] += 1
            if scope in ("wan", "lan"):
                summary[scope] += 1
        return summary

    def api_snapshot(self, interface_view: str = "physical") -> dict:
        interface_view = normalize_interface_view(interface_view)
        totals = self.snapshot_totals(interface_view)
        with self.lock:
            stage = {
                "active": bool(self.stage_started_at),
                "startedAt": self.stage_started_at,
                "interfaces": {
                    iface: {scope: counter.snapshot() for scope, counter in scopes.items()}
                    for iface, scopes in self.stage_totals.items()
                },
            }
            rates = filter_rates(self.last_rates, set(totals["interfaces"].keys()))
            alerts = list(self.alerts)[-20:]
            settings = self.alert_settings.model_dump()
            capture_interfaces = list(self.capture_interfaces)
            container_status = dict(self.container_status)

        return {
            "app": APP_NAME,
            "version": APP_VERSION,
            "timestamp": now(),
            "authEnabled": bool(DASHBOARD_PASSWORD),
            "interfaceView": interface_view,
            "captureInterfaces": capture_interfaces,
            "containerStatus": container_status,
            "rates": rates,
            "stage": stage,
            "alerts": alerts,
            "alertSettings": settings,
            **totals,
        }

    def api_overview(self, interface_view: str = "physical") -> dict:
        interface_view = normalize_interface_view(interface_view)
        interfaces = filter_interfaces(self.snapshot_interfaces(), interface_view)
        interface_names = set(interfaces.keys())
        with self.lock:
            rates = filter_rates(self.last_rates, interface_names)
            alerts = list(self.alerts)[-8:]
            capture_interfaces = list(self.capture_interfaces)
            container_status = dict(self.container_status)
            stage_summary = summarize_stage(self.stage_totals, self.stage_started_at)
            stage_summary["durationSeconds"] += int(self.stage_accumulated_seconds)
        return {
            "app": APP_NAME,
            "version": APP_VERSION,
            "timestamp": now(),
            "authEnabled": bool(DASHBOARD_PASSWORD),
            "interfaceView": interface_view,
            "summary": summarize_interfaces(interfaces, rates),
            "stageSummary": stage_summary,
            "connectionSummary": self.connection_counts(),
            "alerts": alerts,
            "captureInterfaces": capture_interfaces,
            "containerStatus": container_status,
        }

    def process_rank(self, period: str = "30s", limit: int = 30, start: Optional[int] = None, end: Optional[int] = None) -> dict:
        period = normalize_process_period(period)
        limit = max(1, min(100, int(limit or 30)))
        current = int(now())
        if start and end:
            start_ts = int(start)
            end_ts = int(end)
            source = "history"
        elif period == "30s":
            start_ts = current - 30
            end_ts = current
            source = "memory"
        else:
            seconds = process_period_seconds(period)
            start_ts = current - seconds
            end_ts = current
            source = "history"

        if source == "memory":
            rows = self.process_rank_from_events(start_ts, end_ts, limit)
        else:
            rows = self.db.query_processes(int(start_ts // 60) * 60, int(end_ts // 60) * 60, limit)

        return {"period": period, "start": start_ts, "end": end_ts, "source": source, "processes": rows}

    def process_rank_from_events(self, start_ts: int, end_ts: int, limit: int) -> List[dict]:
        counters: Dict[str, Counter] = defaultdict(Counter)
        with self.lock:
            buckets = {
                bucket: dict(processes)
                for bucket, processes in self.process_recent.items()
                if start_ts <= bucket <= end_ts
            }
        for bucket, processes in buckets.items():
            for process_key, counter in processes.items():
                target = counters[process_key]
                target.rx_bytes += counter.rx_bytes
                target.tx_bytes += counter.tx_bytes
                target.rx_packets += counter.rx_packets
                target.tx_packets += counter.tx_packets
                target.first_seen = min(target.first_seen, float(bucket))
                target.last_seen = max(target.last_seen, float(bucket))
        return self.rank_items(list(counters.items()), parse_process_key, limit)

    def prune_recent_processes(self, timestamp: float) -> None:
        cutoff = int(timestamp) - max(120, RETENTION_SECONDS)
        with self.lock:
            for bucket in list(self.process_recent.keys()):
                if bucket < cutoff:
                    del self.process_recent[bucket]

    def connection_detail(
        self,
        mode: str = "capture",
        interface_view: str = "physical",
        iface: str = "all",
        scope: str = "all",
        proto: str = "all",
        direction: str = "all",
        owner: str = "",
        source: str = "",
        dest: str = "",
        min_bytes: int = 0,
        min_duration: int = 0,
        limit: int = 120,
        offset: int = 0,
    ) -> dict:
        mode = "conntrack" if str(mode or "").strip().lower() == "conntrack" else "capture"
        if mode == "conntrack":
            return read_conntrack_connections(scope, proto, direction, owner, source, dest, min_bytes, min_duration, limit, offset)

        interface_view = normalize_interface_view(interface_view)
        limit = max(1, min(300, int(limit or 120)))
        offset = max(0, int(offset or 0))
        interfaces = filter_interfaces(self.snapshot_interfaces(), interface_view)
        interface_names = set(interfaces.keys())
        with self.lock:
            conn_items = list(self.conn_totals.items())
        rows, summary = self.connection_rows(conn_items, interface_names)
        filtered = []
        owner_lower = owner.lower().strip()
        source_lower = source.lower().strip()
        dest_lower = dest.lower().strip()
        for item in rows:
            container = item.get("process", {}).get("container") or {}
            owner_text = " ".join(
                str(value or "")
                for value in (
                    item.get("process", {}).get("name"),
                    item.get("process", {}).get("pid"),
                    container.get("name"),
                    container.get("image"),
                    container.get("label"),
                )
            ).lower()
            if iface != "all" and item.get("iface") != iface:
                continue
            if scope != "all" and item.get("scope") != scope:
                continue
            if proto != "all" and item.get("proto") != proto:
                continue
            if direction == "rx" and int(item.get("rxBytes") or 0) <= 0:
                continue
            if direction == "tx" and int(item.get("txBytes") or 0) <= 0:
                continue
            if owner_lower and owner_lower not in owner_text:
                continue
            if source_lower and source_lower not in str(item.get("source", "")).lower():
                continue
            if dest_lower and dest_lower not in str(item.get("dest", "")).lower():
                continue
            if min_bytes and int(item.get("totalBytes") or 0) < int(min_bytes):
                continue
            if min_duration and float(item.get("durationSeconds") or 0) < int(min_duration):
                continue
            filtered.append(item)
        total_filtered = len(filtered)
        page_rows = filtered[offset : offset + limit]
        return {
            "source": "capture",
            "interfaceView": interface_view,
            "summary": summary,
            "pagination": {
                "total": total_filtered,
                "limit": limit,
                "offset": offset,
                "page": int(offset // limit) + 1,
                "pages": max(1, int((total_filtered + limit - 1) // limit)),
            },
            "connections": page_rows,
        }

    def persist_minute(self, interfaces: dict, timestamp: float) -> None:
        rows = []
        current_totals = {}
        for iface, item in interfaces.items():
            for scope, counter in item.get("scopes", {}).items():
                current_totals.setdefault(iface, {})[scope] = counter

        if self.last_persist_totals is None:
            self.last_persist_totals = current_totals
            return

        for iface, scopes in current_totals.items():
            for scope, counter in scopes.items():
                prev = self.last_persist_totals.get(iface, {}).get(scope, {})
                rx_delta = max(0, counter.get("rxBytes", 0) - prev.get("rxBytes", 0))
                tx_delta = max(0, counter.get("txBytes", 0) - prev.get("txBytes", 0))
                rxp_delta = max(0, counter.get("rxPackets", 0) - prev.get("rxPackets", 0))
                txp_delta = max(0, counter.get("txPackets", 0) - prev.get("txPackets", 0))
                if rx_delta or tx_delta or rxp_delta or txp_delta:
                    rows.append(
                        {
                            "iface": iface,
                            "scope": scope,
                            "rxBytes": rx_delta,
                            "txBytes": tx_delta,
                            "rxPackets": rxp_delta,
                            "txPackets": txp_delta,
                        }
                    )

        self.last_persist_totals = current_totals
        self.db.add_minute(int(timestamp // 60) * 60, rows)

    def persist_process_minute(self, timestamp: float) -> None:
        with self.lock:
            current_totals = {
                key: counter.snapshot()
                for key, counter in self.process_totals.items()
            }

        if self.last_process_persist_totals is None:
            self.last_process_persist_totals = current_totals
            return

        rows = []
        for key, counter in current_totals.items():
            prev = self.last_process_persist_totals.get(key, {})
            rx_delta = max(0, counter.get("rxBytes", 0) - prev.get("rxBytes", 0))
            tx_delta = max(0, counter.get("txBytes", 0) - prev.get("txBytes", 0))
            rxp_delta = max(0, counter.get("rxPackets", 0) - prev.get("rxPackets", 0))
            txp_delta = max(0, counter.get("txPackets", 0) - prev.get("txPackets", 0))
            if rx_delta or tx_delta or rxp_delta or txp_delta:
                rows.append(
                    {
                        "processKey": key,
                        "rxBytes": rx_delta,
                        "txBytes": tx_delta,
                        "rxPackets": rxp_delta,
                        "txPackets": txp_delta,
                    }
                )

        self.last_process_persist_totals = current_totals
        self.db.add_process_minute(int(timestamp // 60) * 60, rows)

    def evaluate_alerts(self, rates: dict, timestamp: float) -> None:
        wan_tx_bps = sum(scope.get("wan", {}).get("txBps", 0) for scope in [item.get("scopes", {}) for item in rates.values()])
        wan_rx_bps = sum(scope.get("wan", {}).get("rxBps", 0) for scope in [item.get("scopes", {}) for item in rates.values()])
        lan_tx_bps = sum(scope.get("lan", {}).get("txBps", 0) for scope in [item.get("scopes", {}) for item in rates.values()])
        lan_rx_bps = sum(scope.get("lan", {}).get("rxBps", 0) for scope in [item.get("scopes", {}) for item in rates.values()])
        counts = self.connection_counts()
        self.evaluate_monitor_rule("wan_tx_bps", wan_tx_bps, timestamp)
        self.evaluate_monitor_rule("wan_rx_bps", wan_rx_bps, timestamp)
        self.evaluate_monitor_rule("lan_tx_bps", lan_tx_bps, timestamp)
        self.evaluate_monitor_rule("lan_rx_bps", lan_rx_bps, timestamp)
        self.evaluate_monitor_rule("wan_connections", counts.get("wan", 0), timestamp)
        self.evaluate_monitor_rule("total_connections", counts.get("total", 0), timestamp)
        stage_rules = [
            rule
            for rule in self.monitor_rules
            if rule.get("enabled") and rule.get("metric") == "stage_wan_tx_bytes" and int(rule.get("threshold") or 0) > 0
        ]
        if stage_rules and self.stage_started_at:
            stage_tx = 0
            with self.lock:
                for scopes in self.stage_totals.values():
                    stage_tx += scopes.get("wan", Counter()).tx_bytes
            self.evaluate_monitor_rule("stage_wan_tx_bytes", stage_tx, timestamp)

    def evaluate_daily_alert(self, timestamp: float) -> None:
        daily_rules = [
            rule
            for rule in self.monitor_rules
            if rule.get("enabled") and rule.get("metric") == "daily_wan_tx_bytes" and int(rule.get("threshold") or 0) > 0
        ]
        if not daily_rules:
            return
        day_key = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        if self.daily_alert_date == day_key:
            return
        day_start = int(datetime.fromtimestamp(timestamp).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        totals = self.db.total_since(day_start, "wan")
        if self.evaluate_monitor_rule("daily_wan_tx_bytes", totals["txBytes"], timestamp):
            self.daily_alert_date = day_key

    def evaluate_monitor_rule(self, metric: str, value: float, timestamp: float) -> bool:
        triggered = False
        for rule in self.monitor_rules:
            if not rule.get("enabled") or rule.get("metric") != metric:
                continue
            threshold = int(rule.get("threshold") or 0)
            if threshold <= 0:
                continue
            matched = value >= threshold if rule.get("operator", "gte") == "gte" else value <= threshold
            state = self.rule_states.setdefault(rule["id"], {"active": False, "startedAt": None})
            if matched:
                if state["startedAt"] is None:
                    state["startedAt"] = timestamp
                sustained = timestamp - state["startedAt"]
                if sustained >= max(0, int(rule.get("durationSeconds") or 0)) and not state["active"]:
                    state["active"] = True
                    triggered = True
                    self.record_alert(rule["id"], "warning", rule.get("name") or "监控规则触发", int(value), threshold, rule)
            else:
                state["active"] = False
                state["startedAt"] = None
        return triggered

    def record_alert(self, alert_type: str, severity: str, message: str, value: int, threshold: int, rule: Optional[dict] = None) -> None:
        alert = {
            "id": f"{alert_type}-{int(now())}",
            "timestamp": now(),
            "type": alert_type,
            "severity": severity,
            "message": message,
            "value": value,
            "threshold": threshold,
            "ruleId": rule.get("id") if rule else alert_type,
            "channelIds": rule.get("channelIds", []) if rule else [],
        }
        with self.lock:
            self.alerts.append(alert)
        self.db.add_alert(alert)
        self.notify_alert(alert)

    def notify_alert(self, alert: dict) -> None:
        channel_ids = set(alert.get("channelIds") or [])
        channels = [
            channel
            for channel in self.notification_channels
            if channel.get("enabled") and (not channel_ids or channel.get("id") in channel_ids)
        ]
        for channel in channels:
            threading.Thread(
                target=dispatch_notification_alert,
                args=(alert, channel, APP_NAME, APP_VERSION),
                daemon=True,
            ).start()

    def prune_stale(self) -> None:
        traffic_cutoff = now() - max(600, RETENTION_SECONDS)
        connection_cutoff = now() - max(60, CONNECTION_RETENTION_SECONDS)
        with self.lock:
            for store in (self.port_totals, self.process_totals):
                for key in list(store.keys()):
                    if store[key].last_seen < traffic_cutoff:
                        del store[key]
            for key in list(self.conn_totals.keys()):
                if self.conn_totals[key].last_seen < connection_cutoff:
                    del self.conn_totals[key]
            for iface in list(self.iface_totals.keys()):
                for scope in list(self.iface_totals[iface].keys()):
                    if self.iface_totals[iface][scope].last_seen < traffic_cutoff:
                        del self.iface_totals[iface][scope]
                if not self.iface_totals[iface]:
                    del self.iface_totals[iface]

    def start_stage(self, interface_view: str = "physical") -> dict:
        with self.lock:
            self.stage_started_at = now()
            self.stage_totals = defaultdict(lambda: defaultdict(Counter))
            self.stage_paused_at = None
            self.stage_accumulated_seconds = 0.0
            self.stage_alert_active = False
        return self.api_snapshot(interface_view)

    def stop_stage(self, interface_view: str = "physical") -> dict:
        with self.lock:
            if self.stage_started_at:
                self.stage_accumulated_seconds += max(0, now() - self.stage_started_at)
            self.stage_paused_at = now()
            self.stage_started_at = None
        return self.api_snapshot(interface_view)

    def resume_stage(self, interface_view: str = "physical") -> dict:
        with self.lock:
            if not self.stage_started_at:
                self.stage_started_at = now()
            self.stage_paused_at = None
        return self.api_snapshot(interface_view)

    def reset_stage(self, interface_view: str = "physical") -> dict:
        with self.lock:
            self.stage_started_at = now() if AUTO_START_STAGE else None
            self.stage_totals = defaultdict(lambda: defaultdict(Counter))
            self.stage_paused_at = None
            self.stage_accumulated_seconds = 0.0
            self.stage_alert_active = False
        return self.api_snapshot(interface_view)

    def history_summary(self, period: str) -> dict:
        return self.db.query_history(period)

    def get_settings(self) -> dict:
        self.sync_legacy_settings()
        return {
            "appPort": APP_PORT,
            "version": APP_VERSION,
            "dbPath": str(DB_PATH),
            "authEnabled": bool(DASHBOARD_PASSWORD),
            "captureInterfaces": self.capture_interfaces,
            "alerts": self.alert_settings.model_dump(),
            "notify": {
                **self.notify_settings.model_dump(),
                "webhookEnabled": bool(self.notify_settings.webhookUrl),
            },
            "monitor": {
                "rules": self.monitor_rules,
                "channels": self.notification_channels,
            },
            "runtime": {
                "appPort": APP_PORT,
                "version": APP_VERSION,
                "sampleSeconds": SAMPLE_SECONDS,
                "retentionSeconds": RETENTION_SECONDS,
                "persistIntervalSeconds": PERSIST_INTERVAL_SECONDS,
                "historyRetentionDays": HISTORY_RETENTION_DAYS,
                "connectionActiveSeconds": CONNECTION_ACTIVE_SECONDS,
                "connectionRetentionSeconds": CONNECTION_RETENTION_SECONDS,
                "autoStartStage": AUTO_START_STAGE,
                "conntrackRefreshSeconds": CONNTRACK_REFRESH_SECONDS,
                "dbPath": str(DB_PATH),
                "logDir": os.getenv("LOG_DIR", "/logs"),
                "dockerDiscovery": ENABLE_DOCKER_DISCOVERY,
                "dockerSocket": DOCKER_SOCKET,
                "captureInterfaces": self.capture_interfaces,
                "conntrackSource": self.conntrack_summary.get("source"),
                "conntrackAvailable": self.conntrack_summary.get("available"),
            },
                "labels": self.db.get_labels(),
                "dockerOverrides": self.docker_overrides,
                "dockerDiscovery": self.container_status,
        }

    def docker_containers(self) -> dict:
        self.refresh_container_ports()
        with self.lock:
            return {
                "enabled": ENABLE_DOCKER_DISCOVERY,
                "status": dict(self.container_status),
                "containers": [docker_container_summary(row) for row in self.container_rows],
                "overrides": self.docker_overrides,
            }

    def docker_container_detail(self, container_id: str) -> dict:
        self.refresh_container_ports()
        selected = str(container_id or "").strip().lstrip("/")
        with self.lock:
            row = self.container_rows_by_id.get(selected) or self.container_rows_by_id.get(selected[:12])
            status = dict(self.container_status)
        if not row:
            return {"ok": False, "detail": "container not found", "status": status}
        return {"ok": True, "enabled": ENABLE_DOCKER_DISCOVERY, "status": status, "container": serialize_docker_container_detail(row)}

    def docker_container_stats(self, container_id: str, refresh: bool = False) -> dict:
        selected = str(container_id or "").strip().lstrip("/")[:12]
        if not selected:
            return {"ok": False, "detail": "missing container id"}
        self.refresh_container_ports()
        with self.lock:
            row = self.container_rows_by_id.get(selected)
        if not row:
            return {"ok": False, "detail": "container not found", "stats": {}}
        current_time = now()
        with self.lock:
            cached = self.docker_stats_cache.get(selected)
            if cached and not refresh and current_time - float(cached.get("cachedAt") or 0) < max(1.0, DOCKER_STATS_CACHE_SECONDS):
                return {"ok": True, "cached": True, "stats": cached.get("stats") or {}}
        stats = docker_container_stats(selected)
        cached = {"cachedAt": now(), "stats": stats}
        with self.lock:
            self.docker_stats_cache[selected] = cached
        return {"ok": bool(stats), "cached": False, "stats": stats, "cachedAt": cached["cachedAt"]}

    def docker_port_probe(self, payload: DockerPortProbePayload) -> dict:
        port = int(payload.port)
        path = normalize_docker_path(payload.path or "/") or "/"
        key = docker_port_probe_key(port, path)
        current_time = now()
        with self.lock:
            cached = self.docker_web_probe_cache.get(key)
            if cached and not payload.refresh and current_time - float(cached.get("checkedAt") or 0) < max(60, DOCKER_WEB_PROBE_TTL_SECONDS):
                return {"ok": True, "cached": True, **cached}
        host = payload.host or "127.0.0.1"
        result = probe_web_endpoint(host, port, path)
        with self.lock:
            self.docker_web_probe_cache[key] = result
        self.refresh_container_ports(force=True)
        return {"cached": False, **result}

    def update_alert_settings(self, settings: AlertSettings) -> dict:
        self.monitor_rules = rules_from_alert_settings(settings)
        with self.lock:
            self.high_tx_started_at = None
            self.high_tx_alert_active = False
            self.stage_alert_active = False
        self.db.set_setting("monitor_rules", {"rules": self.monitor_rules})
        self.sync_legacy_settings()
        return self.get_settings()

    def update_notify_settings(self, settings: NotifySettings) -> dict:
        primary = {
            "id": "webhook",
            "name": "Webhook",
            "type": (settings.channel or "webhook").strip().lower(),
            "enabled": bool(sanitize_http_url(settings.webhookUrl or "")),
            "url": sanitize_http_url(settings.webhookUrl or ""),
            "token": "",
            "timeout": max(1, min(30, float(settings.webhookTimeout or 5))),
            "titleTemplate": DEFAULT_NOTIFY_TITLE_TEMPLATE,
            "bodyTemplate": DEFAULT_NOTIFY_BODY_TEMPLATE,
            "urlTemplate": "",
            "msgType": "text",
            "htmlHeight": 200,
        }
        self.notification_channels = [primary, *[channel for channel in self.notification_channels if channel.get("id") != "webhook"]]
        self.db.set_setting("notification_channels", {"channels": self.notification_channels})
        self.sync_legacy_settings()
        return self.get_settings()

    def update_monitor_rules(self, payload: MonitorRulesPayload) -> dict:
        self.monitor_rules = [sanitize_monitor_rule(rule) for rule in payload.rules]
        self.db.set_setting("monitor_rules", {"rules": self.monitor_rules})
        self.sync_legacy_settings()
        return self.get_settings()

    def update_notification_channels(self, payload: NotificationChannelsPayload) -> dict:
        self.notification_channels = [sanitize_notification_channel(channel) for channel in payload.channels]
        self.db.set_setting("notification_channels", {"channels": self.notification_channels})
        self.sync_legacy_settings()
        return self.get_settings()

    def update_runtime_settings(self, payload: RuntimeSettingsPayload) -> dict:
        global SAMPLE_SECONDS, RETENTION_SECONDS, CONNECTION_ACTIVE_SECONDS, CONNECTION_RETENTION_SECONDS
        global AUTO_START_STAGE, CONNTRACK_REFRESH_SECONDS, PERSIST_INTERVAL_SECONDS, HISTORY_RETENTION_DAYS
        settings = RuntimeSettingsPayload(**payload.model_dump())
        SAMPLE_SECONDS = float(settings.sampleSeconds)
        RETENTION_SECONDS = int(settings.retentionSeconds)
        PERSIST_INTERVAL_SECONDS = int(settings.persistIntervalSeconds)
        HISTORY_RETENTION_DAYS = int(settings.historyRetentionDays)
        CONNECTION_ACTIVE_SECONDS = int(settings.connectionActiveSeconds)
        CONNECTION_RETENTION_SECONDS = int(settings.connectionRetentionSeconds)
        CONNTRACK_REFRESH_SECONDS = int(settings.conntrackRefreshSeconds)
        AUTO_START_STAGE = bool(settings.autoStartStage)
        self.db.set_setting("runtime_settings", settings.model_dump())
        return self.get_settings()

    def test_notification_channel(self, channel_id: str) -> dict:
        channel = next((item for item in self.notification_channels if item.get("id") == channel_id), None)
        if not channel:
            return {"ok": False, "detail": "channel not found"}
        alert = {
            "id": f"test-{int(now())}",
            "timestamp": now(),
            "type": "test",
            "severity": "info",
            "message": "通知渠道测试",
            "value": 1,
            "threshold": 1,
            "ruleId": "notification-test",
            "channelIds": [channel_id],
        }
        result = dispatch_notification_alert(alert, channel, APP_NAME, APP_VERSION, raise_error=False)
        return {"ok": result.get("ok", False), **result}

    def clear_alerts(self) -> dict:
        with self.lock:
            self.alerts.clear()
        return {"ok": True}

    def set_label(self, key: str, label: str) -> dict:
        result = self.db.set_label(key, label)
        self.refresh_container_ports(force=True)
        return result

    def update_docker_container_ports(self, payload: DockerContainerPortsPayload) -> dict:
        try:
            cleaned = sanitize_docker_overrides(payload)
        except ValueError as exc:
            return {"ok": False, "detail": str(exc)}
        with self.lock:
            containers = dict((self.docker_overrides or {}).get("containers") or {})
            if cleaned["ports"]:
                containers[cleaned["key"]] = {
                    "containerId": cleaned["containerId"],
                    "containerName": cleaned["containerName"],
                    "icon": cleaned["icon"],
                    "ports": cleaned["ports"],
                    "updatedAt": int(now()),
                }
            else:
                containers.pop(cleaned["key"], None)
            self.docker_overrides = {"containers": containers}
        self.db.set_setting("docker_overrides", self.docker_overrides)
        self.refresh_container_ports(force=True)
        return self.docker_containers()


def log_status() -> dict:
    log_dir = Path(os.getenv("LOG_DIR", "/logs"))
    files = []
    if log_dir.exists():
        for path in sorted(log_dir.glob("*.log")):
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append({"name": path.name, "size": stat.st_size, "modified": stat.st_mtime})
    return {"dir": str(log_dir), "files": files}


def parse_packet(packet) -> Optional[Tuple[str, str, str, int, int, int]]:
    try:
        if packet.haslayer(IP):
            ip = packet[IP]
            src, dst = ip.src, ip.dst
        elif packet.haslayer(IPv6):
            ip = packet[IPv6]
            src, dst = ip.src, ip.dst
        else:
            return None

        if packet.haslayer(TCP):
            layer = packet[TCP]
            proto = "tcp"
        elif packet.haslayer(UDP):
            layer = packet[UDP]
            proto = "udp"
        else:
            return None

        return src, dst, proto, int(layer.sport), int(layer.dport), len(packet)
    except Exception:
        return None


def get_local_addresses() -> set:
    addresses = set()
    for addr_list in psutil.net_if_addrs().values():
        for addr in addr_list:
            if addr.family in (socket.AF_INET, socket.AF_INET6):
                addresses.add(addr.address.split("%")[0])
    return addresses


def conntrack_paths() -> List[Path]:
    return [
        Path("/host/proc/net/nf_conntrack"),
        Path("/proc/net/nf_conntrack"),
        Path("/host/proc/net/ip_conntrack"),
        Path("/proc/net/ip_conntrack"),
    ]


def selected_conntrack_path() -> Optional[Path]:
    return next((path for path in conntrack_paths() if path.exists()), None)


def parse_conntrack_line(line: str) -> Optional[dict]:
    parts = line.split()
    proto_index = next((index for index, value in enumerate(parts) if value.lower() in {"tcp", "udp"}), None)
    if proto_index is None:
        return None
    proto = parts[proto_index].lower()

    timeout = 0
    int_values = []
    for value in parts[proto_index + 1 :]:
        if "=" in value or value.startswith("["):
            break
        try:
            int_values.append(int(value))
        except ValueError:
            continue
    if int_values:
        timeout = int_values[-1]

    state = ""
    for value in parts[proto_index + 1 :]:
        if "=" in value:
            break
        cleaned = value.strip("[]").upper()
        if cleaned in {
            "SYN_SENT",
            "SYN_RECV",
            "ESTABLISHED",
            "FIN_WAIT",
            "TIME_WAIT",
            "CLOSE",
            "CLOSE_WAIT",
            "LAST_ACK",
            "LISTEN",
        }:
            state = cleaned
            break

    flags = {value.strip("[]").upper() for value in parts if value.startswith("[") and value.endswith("]")}
    values: Dict[str, List[str]] = defaultdict(list)
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        values[key].append(value)

    src_values = values.get("src", [])
    dst_values = values.get("dst", [])
    sport_values = values.get("sport", [])
    dport_values = values.get("dport", [])
    bytes_values = values.get("bytes", [])
    packet_values = values.get("packets", [])
    if not src_values or not dst_values:
        return None

    def parse_int(items: List[str], index: int = 0) -> int:
        try:
            return int(items[index])
        except (IndexError, TypeError, ValueError):
            return 0

    addresses = []
    for value in [*src_values, *dst_values]:
        try:
            ipaddress.ip_address(value)
            addresses.append(value)
        except ValueError:
            continue

    return {
        "proto": proto,
        "state": state,
        "flags": flags,
        "timeout": timeout,
        "src": src_values[0],
        "dst": dst_values[0],
        "sport": parse_int(sport_values),
        "dport": parse_int(dport_values),
        "replySrc": src_values[1] if len(src_values) > 1 else "",
        "replyDst": dst_values[1] if len(dst_values) > 1 else "",
        "replySport": parse_int(sport_values, 1),
        "replyDport": parse_int(dport_values, 1),
        "txBytes": parse_int(bytes_values),
        "rxBytes": parse_int(bytes_values, 1),
        "txPackets": parse_int(packet_values),
        "rxPackets": parse_int(packet_values, 1),
        "addresses": addresses,
    }


def conntrack_entry_is_active(entry: dict) -> bool:
    if CONNTRACK_COUNT_MODE == "raw":
        return True
    if int(entry.get("timeout") or 0) < max(0, CONNTRACK_MIN_TIMEOUT_SECONDS):
        return False
    flags = entry.get("flags") or set()
    if "UNREPLIED" in flags and not CONNTRACK_INCLUDE_UNREPLIED:
        return False
    proto = entry.get("proto")
    if proto == "tcp":
        state = (entry.get("state") or "").upper()
        return state in CONNTRACK_TCP_STATES
    if proto == "udp":
        return not CONNTRACK_UDP_REQUIRE_ASSURED or "ASSURED" in flags
    return False


def conntrack_scope(entry: dict) -> str:
    addresses = entry.get("addresses") or []
    return "lan" if addresses and all(is_lan_ip(value) for value in addresses) else "wan"


def read_conntrack_summary() -> dict:
    selected = selected_conntrack_path()
    if not selected:
        return {
            "available": False,
            "source": "capture",
            "detail": "",
            "mode": CONNTRACK_COUNT_MODE,
            "rawTotal": 0,
            "total": None,
            "wan": None,
            "lan": None,
        }

    total = 0
    wan = 0
    lan = 0
    raw_total = 0
    try:
        with selected.open("r", errors="ignore") as file:
            for line in file:
                raw_total += 1
                entry = parse_conntrack_line(line)
                if not entry or not conntrack_entry_is_active(entry):
                    continue
                total += 1
                if conntrack_scope(entry) == "lan":
                    lan += 1
                else:
                    wan += 1
    except OSError:
        return {
            "available": False,
            "source": "capture",
            "detail": "",
            "mode": CONNTRACK_COUNT_MODE,
            "rawTotal": 0,
            "total": None,
            "wan": None,
            "lan": None,
        }

    return {
        "available": True,
        "source": "conntrack",
        "detail": str(selected),
        "mode": CONNTRACK_COUNT_MODE,
        "rawTotal": raw_total,
        "total": total,
        "wan": wan,
        "lan": lan,
    }


def read_conntrack_connections(
    scope: str = "all",
    proto: str = "all",
    direction: str = "all",
    owner: str = "",
    source: str = "",
    dest: str = "",
    min_bytes: int = 0,
    min_duration: int = 0,
    limit: int = 120,
    offset: int = 0,
) -> dict:
    selected = selected_conntrack_path()
    limit = max(1, min(300, int(limit or 120)))
    offset = max(0, int(offset or 0))
    if not selected:
        return {
            "source": "conntrack",
            "summary": {"total": 0, "wan": 0, "lan": 0},
            "pagination": {"total": 0, "limit": limit, "offset": offset, "page": 1, "pages": 1},
            "connections": [],
        }

    owner_lower = owner.lower().strip()
    source_lower = source.lower().strip()
    dest_lower = dest.lower().strip()
    rows = []
    summary = {"total": 0, "wan": 0, "lan": 0}
    try:
        with selected.open("r", errors="ignore") as file:
            for line in file:
                entry = parse_conntrack_line(line)
                if not entry or not conntrack_entry_is_active(entry):
                    continue
                row_scope = conntrack_scope(entry)
                if scope != "all" and row_scope != scope:
                    continue
                if proto != "all" and entry.get("proto") != proto:
                    continue
                src_ip = entry.get("replySrc") or entry.get("src") or ""
                dst_ip = entry.get("replyDst") or entry.get("dst") or ""
                src_text = f"{src_ip}:{entry.get('replySport') or entry.get('sport') or 0}"
                dst_text = f"{dst_ip}:{entry.get('replyDport') or entry.get('dport') or 0}"
                endpoint_scope = classify_connection_scope(src_text, dst_text)
                if scope != "all" and endpoint_scope != scope and row_scope != scope:
                    continue
                owner_text = " ".join(
                    str(value or "")
                    for value in (
                        entry.get("state"),
                        entry.get("proto"),
                        src_text,
                        dst_text,
                    )
                ).lower()
                if owner_lower and owner_lower not in owner_text:
                    continue
                if source_lower and source_lower not in src_text.lower():
                    continue
                if dest_lower and dest_lower not in dst_text.lower():
                    continue
                rx_bytes = int(entry.get("rxBytes") or 0)
                tx_bytes = int(entry.get("txBytes") or 0)
                if direction == "rx" and rx_bytes <= 0:
                    continue
                if direction == "tx" and tx_bytes <= 0:
                    continue
                if min_bytes and (rx_bytes + tx_bytes) < int(min_bytes):
                    continue
                duration = max(0, int(entry.get("timeout") or 0))
                if min_duration and duration < int(min_duration):
                    continue
                summary["total"] += 1
                if endpoint_scope in ("wan", "lan"):
                    summary[endpoint_scope] += 1
                rows.append(
                    {
                        "iface": "conntrack",
                        "scope": endpoint_scope,
                        "proto": entry.get("proto") or "unknown",
                        "direction": direction if direction in {"rx", "tx"} else ("tx" if tx_bytes >= rx_bytes else "rx"),
                        "source": src_text,
                        "dest": dst_text,
                        "rxBytes": rx_bytes,
                        "txBytes": tx_bytes,
                        "durationSeconds": duration,
                        "process": {"pid": None, "name": "conntrack", "cmdline": "", "container": {}},
                        "container": {},
                        "labelKey": "",
                        "label": "",
                    }
                )
    except OSError:
        return {
            "source": "conntrack",
            "summary": {"total": 0, "wan": 0, "lan": 0},
            "pagination": {"total": 0, "limit": limit, "offset": offset, "page": 1, "pages": 1},
            "connections": [],
        }

    rows.sort(key=lambda row: row.get("txBytes", 0) + row.get("rxBytes", 0), reverse=True)
    total_filtered = len(rows)
    page_rows = rows[offset : offset + limit]
    return {
        "source": "conntrack",
        "summary": summary,
        "pagination": {
            "total": total_filtered,
            "limit": limit,
            "offset": offset,
            "page": int(offset // limit) + 1,
            "pages": max(1, int((total_filtered + limit - 1) // limit)),
        },
        "connections": page_rows,
    }


def socket_connection_summary(socket_map: Dict[Tuple[str, str, str, int, int], dict]) -> dict:
    seen = set()
    total = wan = lan = 0
    for (proto, local_ip, remote_ip, local_port, remote_port), _process in socket_map.items():
        if remote_ip in {"0.0.0.0", "::"} and remote_port == 0:
            continue
        key = (proto, local_ip, remote_ip, int(local_port), int(remote_port))
        if key in seen:
            continue
        seen.add(key)
        total += 1
        if is_lan_ip(local_ip) and is_lan_ip(remote_ip):
            lan += 1
        else:
            wan += 1
    return {"available": bool(total), "total": total, "wan": wan, "lan": lan}


def process_key_for(process: dict) -> str:
    payload = {
        "pid": process.get("pid"),
        "name": process.get("name") or "unknown",
        "cmdline": process.get("cmdline") or "",
        "container": process.get("container") or {},
    }
    return b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())


def parse_process_key(key: str) -> dict:
    try:
        padded = key + "=" * (-len(key) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        return {
            "pid": data.get("pid"),
            "name": data.get("name") or "unknown",
            "cmdline": data.get("cmdline") or "",
            "container": data.get("container") or {},
        }
    except Exception:
        try:
            pid, name, cmdline = key.split("|", 2)
            return {"pid": None if pid == "unknown" else int(pid), "name": name, "cmdline": cmdline, "container": {}}
        except Exception:
            return {"pid": None, "name": key or "unknown", "cmdline": "", "container": {}}


def parse_port_key(key: str) -> dict:
    try:
        proto, rest = key.split(":", 1)
        src, dst = rest.split("->", 1)
        return {"proto": proto, "sourcePort": int(src), "destPort": int(dst)}
    except Exception:
        return {"proto": "unknown", "sourcePort": 0, "destPort": 0}


def parse_connection_key(key: str) -> dict:
    try:
        iface, scope, proto, src, dst, process = key.split("|", 5)
        proc = parse_process_key(process)
        return {"iface": iface, "scope": scope, "proto": proto, "source": src, "dest": dst, "process": proc}
    except Exception:
        return {
            "iface": "unknown",
            "scope": "wan",
            "proto": "unknown",
            "source": "",
            "dest": "",
            "process": {"pid": None, "name": "unknown", "cmdline": "", "container": {}},
        }


def diff_rates(previous: dict, current: dict, elapsed: float) -> dict:
    result = {}
    for iface, current_item in current.items():
        previous_item = previous.get(iface, {"scopes": {}, "system": {}})
        scopes = {}
        for scope, current_counter in current_item.get("scopes", {}).items():
            prev_counter = previous_item.get("scopes", {}).get(scope, {"rxBytes": 0, "txBytes": 0})
            scopes[scope] = {
                "rxBps": max(0, current_counter["rxBytes"] - prev_counter.get("rxBytes", 0)) / elapsed,
                "txBps": max(0, current_counter["txBytes"] - prev_counter.get("txBytes", 0)) / elapsed,
            }
        current_system = current_item.get("system", {})
        previous_system = previous_item.get("system", {})
        result[iface] = {
            "scopes": scopes,
            "systemRxBps": max(0, current_system.get("rxBytes", 0) - previous_system.get("rxBytes", 0)) / elapsed,
            "systemTxBps": max(0, current_system.get("txBytes", 0) - previous_system.get("txBytes", 0)) / elapsed,
        }
    return result


def auth_secret() -> bytes:
    seed = APP_SECRET or f"{APP_NAME}:{DASHBOARD_PASSWORD}"
    return hashlib.sha256(seed.encode()).digest()


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def create_session_token() -> str:
    payload = b64url(json.dumps({"exp": int(now()) + SESSION_TTL_SECONDS}, separators=(",", ":")).encode())
    sig = b64url(hmac.new(auth_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def valid_session_token(token: str) -> bool:
    try:
        payload, sig = token.split(".", 1)
        expected = b64url(hmac.new(auth_secret(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return False
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        return int(data.get("exp", 0)) >= int(now())
    except Exception:
        return False


def is_public_path(path: str) -> bool:
    return path in {"/login", "/api/auth/login", "/api/auth/status", "/favicon.ico"}


LOGIN_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>NAS Traffic Lens 登录</title>
  <style>
    *{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f5f7fa;color:#14213d;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.box{width:min(380px,calc(100vw - 32px));background:#fff;border:1px solid #dce3ec;border-radius:8px;padding:22px}h1{margin:0 0 14px;font-size:22px}input,button{width:100%;height:42px;border-radius:7px;font-size:15px}input{border:1px solid #cbd5e1;padding:0 12px}button{margin-top:12px;border:0;background:#2563eb;color:#fff;font-weight:700;cursor:pointer}.err{min-height:22px;margin-top:10px;color:#b42318;font-size:13px}
  </style>
</head>
<body>
  <form class="box" id="form">
    <h1>NAS Traffic Lens</h1>
    <input id="password" type="password" placeholder="访问密码" autofocus />
    <button type="submit">登录</button>
    <div class="err" id="err"></div>
  </form>
  <script>
    document.getElementById("form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const password = document.getElementById("password").value;
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({password})
      });
      if (response.ok) location.href = "/";
      else document.getElementById("err").textContent = "密码不正确";
    });
  </script>
</body>
</html>
"""


collector = TrafficCollector()
login_failures: Dict[str, deque] = defaultdict(lambda: deque(maxlen=LOGIN_MAX_ATTEMPTS))
app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    try:
        if not DASHBOARD_PASSWORD or is_public_path(request.url.path):
            return await call_next(request)

        token = request.cookies.get(AUTH_COOKIE_NAME, "")
        if valid_session_token(token):
            return await call_next(request)

        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        return RedirectResponse("/login", status_code=302)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "internal server error"}, status_code=500)
        return HTMLResponse("Internal Server Error", status_code=500)


@app.on_event("startup")
async def startup_event() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, collector.start)


@app.get("/login")
async def login_page() -> HTMLResponse:
    if not DASHBOARD_PASSWORD:
        return HTMLResponse("<script>location.href='/'</script>")
    return HTMLResponse(LOGIN_HTML)


@app.get("/api/auth/status")
async def auth_status(request: Request) -> dict:
    return {
        "enabled": bool(DASHBOARD_PASSWORD),
        "authenticated": not DASHBOARD_PASSWORD or valid_session_token(request.cookies.get(AUTH_COOKIE_NAME, "")),
    }


@app.post("/api/auth/login")
async def auth_login(payload: LoginRequest, request: Request) -> JSONResponse:
    client = request.client.host if request.client else "unknown"
    if client not in login_failures and len(login_failures) >= max(16, LOGIN_FAILURE_CLIENT_LIMIT):
        oldest_client = min(
            login_failures,
            key=lambda key: login_failures[key][0] if login_failures[key] else now(),
        )
        login_failures.pop(oldest_client, None)
    attempts = login_failures[client]
    cutoff = now() - LOGIN_LOCK_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    if DASHBOARD_PASSWORD and len(attempts) >= LOGIN_MAX_ATTEMPTS:
        return JSONResponse({"detail": "too many attempts"}, status_code=429)

    if not DASHBOARD_PASSWORD or hmac.compare_digest(payload.password, DASHBOARD_PASSWORD):
        attempts.clear()
        response = JSONResponse({"ok": True})
        response.set_cookie(
            AUTH_COOKIE_NAME,
            create_session_token(),
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            samesite="lax",
        )
        return response
    attempts.append(now())
    return JSONResponse({"detail": "invalid password"}, status_code=401)


@app.post("/api/auth/logout")
async def auth_logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response


@app.get("/api/snapshot")
async def snapshot(interfaces: str = "physical") -> dict:
    return collector.api_snapshot(interfaces)


@app.get("/api/overview")
async def overview(interfaces: str = "physical") -> dict:
    return collector.api_overview(interfaces)


@app.get("/api/processes")
async def processes(period: str = "30s", limit: int = 30, start: Optional[int] = None, end: Optional[int] = None) -> dict:
    return collector.process_rank(period, limit, start, end)


@app.get("/api/connections")
async def connections(
    mode: str = "capture",
    interfaces: str = "physical",
    iface: str = "all",
    scope: str = "all",
    proto: str = "all",
    direction: str = "all",
    owner: str = "",
    source: str = "",
    dest: str = "",
    min_bytes: int = 0,
    min_duration: int = 0,
    limit: int = 120,
    offset: int = 0,
) -> dict:
    return collector.connection_detail(
        mode,
        interfaces,
        iface,
        scope,
        proto,
        direction,
        owner,
        source,
        dest,
        min_bytes,
        min_duration,
        limit,
        offset,
    )


@app.get("/api/history")
async def history(period: str = "day") -> dict:
    return collector.history_summary(period)


@app.get("/api/settings")
async def settings() -> dict:
    return collector.get_settings()


@app.post("/api/settings/alerts")
async def update_alerts(settings_payload: AlertSettings) -> dict:
    return collector.update_alert_settings(settings_payload)


@app.post("/api/settings/notify")
async def update_notify(settings_payload: NotifySettings) -> dict:
    return collector.update_notify_settings(settings_payload)


@app.post("/api/settings/monitor")
async def update_monitor(payload: MonitorRulesPayload) -> dict:
    return collector.update_monitor_rules(payload)


@app.post("/api/settings/channels")
async def update_channels(payload: NotificationChannelsPayload) -> dict:
    return collector.update_notification_channels(payload)


@app.post("/api/settings/runtime")
async def update_runtime(payload: RuntimeSettingsPayload) -> dict:
    return collector.update_runtime_settings(payload)


@app.post("/api/notifications/test")
async def test_notification(payload: NotificationTestPayload) -> dict:
    return collector.test_notification_channel(payload.channelId)


@app.post("/api/labels")
async def set_label(payload: LabelPayload) -> dict:
    return collector.set_label(payload.key, payload.label)


@app.post("/api/alerts/clear")
async def clear_alerts() -> dict:
    return collector.clear_alerts()


@app.get("/api/logs")
async def logs() -> dict:
    return log_status()


@app.get("/api/docker/containers")
async def docker_containers() -> dict:
    return collector.docker_containers()


@app.get("/api/docker/containers/{container_id}")
async def docker_container_detail_api(container_id: str) -> dict:
    return collector.docker_container_detail(container_id)


@app.get("/api/docker/containers/{container_id}/stats")
async def docker_container_stats_api(container_id: str, refresh: bool = False) -> dict:
    return collector.docker_container_stats(container_id, refresh)


@app.post("/api/docker/containers/ports")
async def update_docker_ports(payload: DockerContainerPortsPayload) -> dict:
    return collector.update_docker_container_ports(payload)


@app.post("/api/docker/ports/probe")
async def probe_docker_port(payload: DockerPortProbePayload) -> dict:
    return collector.docker_port_probe(payload)


@app.get("/api/system")
async def system() -> dict:
    return system_status()


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "version": APP_VERSION,
        "sniffers": len(collector.sniffers),
        "captureInterfaces": collector.capture_interfaces,
        "containerStatus": collector.container_status,
        "timestamp": now(),
    }


@app.post("/api/stage/start")
async def stage_start(interfaces: str = "physical") -> dict:
    return collector.start_stage(interfaces)


@app.post("/api/stage/stop")
async def stage_stop(interfaces: str = "physical") -> dict:
    return collector.stop_stage(interfaces)


@app.post("/api/stage/resume")
async def stage_resume(interfaces: str = "physical") -> dict:
    return collector.resume_stage(interfaces)


@app.post("/api/stage/reset")
async def stage_reset(interfaces: str = "physical") -> dict:
    return collector.reset_stage(interfaces)


if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


@app.get("/{path:path}")
async def frontend(path: str):
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": APP_NAME, "version": APP_VERSION, "api": "/api/snapshot"}
