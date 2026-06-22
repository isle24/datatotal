import os
import subprocess
import threading
import time
from typing import Dict, List, Optional

import psutil


SYSTEM_STATUS_CACHE_SECONDS = float(os.getenv("SYSTEM_STATUS_CACHE_SECONDS", "5"))
_SYSTEM_STATUS_CACHE = {"timestamp": 0.0, "data": None}
_SYSTEM_STATUS_LOCK = threading.Lock()


def _read_first(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            return file.readline().strip()
    except OSError:
        return ""


def _read_number(path: str) -> Optional[float]:
    value = _read_first(path)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def read_intel_dri_stats() -> dict:
    engines = []
    busy_values = []
    for card in sorted(name for name in os.listdir("/sys/class/drm") if name.startswith("card")) if os.path.isdir("/sys/class/drm") else []:
        engine_root = os.path.join("/sys/class/drm", card, "engine")
        if not os.path.isdir(engine_root):
            continue
        for engine in sorted(os.listdir(engine_root)):
            busy = _read_number(os.path.join(engine_root, engine, "busy"))
            if busy is None:
                continue
            busy_values.append(busy)
            engines.append({"card": card, "name": engine, "busyPercent": round(busy, 2)})
    return {
        "engines": engines,
        "utilPercent": round(max(busy_values), 2) if busy_values else None,
    }


def read_gpu_stats() -> List[dict]:
    gpus = []
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=2,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        output = ""
    if output:
        for index, line in enumerate(output.splitlines()):
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 5:
                continue
            try:
                gpus.append(
                    {
                        "index": index,
                        "name": parts[0],
                        "type": "nvidia",
                        "available": True,
                        "utilPercent": float(parts[1]),
                        "memoryUsedMB": float(parts[2]),
                        "memoryTotalMB": float(parts[3]),
                        "temperatureC": float(parts[4]),
                    }
                )
            except ValueError:
                continue
    dri_path = "/dev/dri"
    if os.path.isdir(dri_path):
        devices = sorted(name for name in os.listdir(dri_path) if name.startswith(("card", "renderD")))
        if devices and not gpus:
            intel_stats = read_intel_dri_stats()
            gpus.append(
                {
                    "index": 0,
                    "name": "Intel/DRI 核显",
                    "type": "dri",
                    "available": True,
                    "devices": devices,
                    "utilPercent": intel_stats.get("utilPercent"),
                    "engines": intel_stats.get("engines") or [],
                    "memoryUsedMB": None,
                    "memoryTotalMB": None,
                    "temperatureC": None,
                    "status": "ok" if intel_stats.get("utilPercent") is not None else "mapped-no-utilization",
                    "hint": "已映射 /dev/dri；当前内核未暴露 i915 engine busy 指标" if intel_stats.get("utilPercent") is None else "",
                }
            )
    return gpus


def read_npu_stats() -> List[dict]:
    npus = []
    sys_accel = "/sys/class/accel"
    if os.path.isdir(sys_accel):
        for index, name in enumerate(sorted(os.listdir(sys_accel))):
            device_path = os.path.join(sys_accel, name, "device")
            vendor = _read_first(os.path.join(device_path, "vendor"))
            device = _read_first(os.path.join(device_path, "device"))
            npus.append(
                {
                    "index": index,
                    "name": name,
                    "type": "accel",
                    "available": True,
                    "vendor": vendor,
                    "device": device,
                    "path": f"/sys/class/accel/{name}",
                    "status": "detected",
                    "hint": "已识别 NPU/加速设备；利用率取决于宿主驱动是否暴露统计接口",
                }
            )

    dev_accel = "/dev/accel"
    if os.path.isdir(dev_accel):
        devices = sorted(os.listdir(dev_accel))
        if devices and not npus:
            npus.append(
                {
                    "index": 0,
                    "name": "NPU/Acceleration device",
                    "type": "dev-accel",
                    "available": True,
                    "devices": devices,
                    "path": "/dev/accel",
                    "status": "mapped",
                    "hint": "已映射 /dev/accel；利用率取决于宿主驱动是否暴露统计接口",
                }
            )

    if not npus:
        try:
            output = subprocess.check_output(["lspci", "-nn"], text=True, timeout=2, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            output = ""
        for index, line in enumerate(output.splitlines()):
            lowered = line.lower()
            if any(keyword in lowered for keyword in ("npu", "neural", "ai boost", "processing accelerator")):
                npus.append({"index": index, "name": line.strip(), "type": "pci", "available": True, "status": "pci-only", "hint": "PCI 可见但设备节点未映射到容器"})
    return npus


def friendly_temperature_group(raw_name: str, index: int) -> str:
    name = (raw_name or "").lower()
    if name.startswith(("coretemp", "k10temp", "zenpower")):
        return "CPU"
    if name.startswith(("nvme",)):
        return f"NVMe {index}"
    if name.startswith(("drivetemp", "hddtemp")):
        return f"硬盘 {index}"
    if name.startswith(("iwlwifi", "wifi")):
        return "无线网卡"
    if name.startswith(("amdgpu", "radeon")):
        return "GPU"
    if name.startswith(("acpitz", "pch_", "thermal_zone")):
        return "主板/机箱"
    return raw_name or f"传感器 {index}"


def friendly_temperature_label(raw_name: str, raw_label: str, group: str, index: int) -> str:
    name = (raw_name or "").lower()
    label = (raw_label or "").strip()
    lower_label = label.lower()
    if "package" in lower_label or lower_label in {"physical id 0", "tctl", "tdie"}:
        return "CPU 封装"
    if lower_label.startswith("core "):
        return label.replace("Core", "核心")
    if name.startswith("nvme"):
        return "控制器"
    if name.startswith(("drivetemp", "hddtemp")):
        return "盘体"
    if name.startswith(("acpitz", "thermal_zone")):
        return label or group
    return label or group


def friendly_temperatures(raw: Dict[str, list]) -> List[dict]:
    grouped = []
    family_counts: Dict[str, int] = {}
    for raw_name, entries in raw.items():
        lowered = (raw_name or "sensor").lower()
        if lowered.startswith("nvme"):
            key = "nvme"
        elif lowered.startswith(("drivetemp", "hddtemp")):
            key = "disk"
        elif lowered.startswith(("coretemp", "k10temp", "zenpower")):
            key = "cpu"
        elif lowered.startswith(("acpitz", "thermal_zone")):
            key = "board"
        else:
            key = lowered.split("-", 1)[0]
        family_counts[key] = family_counts.get(key, 0) + 1
        group = friendly_temperature_group(raw_name, family_counts[key])
        values = []
        for index, item in enumerate(entries, start=1):
            current = item.get("current")
            values.append(
                {
                    "label": friendly_temperature_label(raw_name, item.get("label") or "", group, index),
                    "rawLabel": item.get("label") or raw_name,
                    "current": current,
                    "high": item.get("high"),
                    "critical": item.get("critical"),
                    "level": temperature_level(current, item.get("critical"), item.get("high")),
                }
            )
        grouped.append({"name": group, "rawName": raw_name, "items": values})
    return grouped


def temperature_level(current, critical, high) -> str:
    try:
        value = float(current)
    except (TypeError, ValueError):
        return "unknown"
    if critical and value >= float(critical):
        return "critical"
    if high and value >= float(high):
        return "warning"
    if value >= 80:
        return "warning"
    return "ok"


def collect_system_status() -> dict:
    cpu_freq = psutil.cpu_freq()
    per_cpu = psutil.cpu_percent(interval=None, percpu=True)
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    temps = {}
    try:
        for name, entries in psutil.sensors_temperatures(fahrenheit=False).items():
            temps[name] = [
                {"label": item.label or name, "current": item.current, "high": item.high, "critical": item.critical}
                for item in entries
            ]
    except (AttributeError, OSError):
        temps = {}
    boot = psutil.boot_time()
    return {
        "timestamp": time.time(),
        "cpu": {
            "percent": round(sum(per_cpu) / len(per_cpu), 2) if per_cpu else 0,
            "perCpu": per_cpu,
            "countLogical": psutil.cpu_count(logical=True),
            "countPhysical": psutil.cpu_count(logical=False),
            "frequencyMhz": cpu_freq.current if cpu_freq else None,
            "loadAverage": os.getloadavg() if hasattr(os, "getloadavg") else None,
        },
        "memory": {"total": memory.total, "used": memory.used, "available": memory.available, "percent": memory.percent},
        "swap": {"total": swap.total, "used": swap.used, "free": swap.free, "percent": swap.percent},
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free, "percent": disk.percent},
        "temperatures": temps,
        "temperatureGroups": friendly_temperatures(temps),
        "gpu": read_gpu_stats(),
        "npu": read_npu_stats(),
        "uptimeSeconds": max(0, int(time.time() - boot)),
    }


def system_status() -> dict:
    current = time.time()
    ttl = max(0.0, SYSTEM_STATUS_CACHE_SECONDS)
    with _SYSTEM_STATUS_LOCK:
        cached = _SYSTEM_STATUS_CACHE.get("data")
        if cached and ttl and current - float(_SYSTEM_STATUS_CACHE.get("timestamp") or 0) < ttl:
            return cached
        data = collect_system_status()
        _SYSTEM_STATUS_CACHE["timestamp"] = current
        _SYSTEM_STATUS_CACHE["data"] = data
        return data
