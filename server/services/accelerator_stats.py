"""Intel iGPU (i915 PMU) and NPU (intel_vpu sysfs) utilization readers.

Both drivers expose cumulative busy counters rather than a ready-made
percentage: the iGPU through perf PMU events (the same source intel_gpu_top
uses) and the NPU through /sys/class/accel/*/device/npu_busy_time_us. The
utilization is therefore the delta between two samples, which a small
background sampler collects so API responses never wait on a measurement
window. Every reader degrades to an explanatory hint when the kernel, the
device node or the container permission does not expose the counters.
"""
from __future__ import annotations

import ctypes
import os
import platform
import struct
import threading
import time
from typing import Dict, List, Optional, Tuple

I915_PMU_ROOT = "/sys/bus/event_source/devices/i915"
DRM_ROOT = "/sys/class/drm"
ACCEL_ROOT = "/sys/class/accel"

SAMPLE_SECONDS = 2.0
FIRST_SAMPLE_SECONDS = 0.3
READY_TIMEOUT_SECONDS = 3.0

PERF_FORMAT_TOTAL_TIME_ENABLED = 1
PERF_FORMAT_TOTAL_TIME_RUNNING = 2
PERF_ATTR_SIZE = 128
PERF_COUNTER_SIZE = 24

_PERF_EVENT_OPEN_SYSCALL = {"x86_64": 298, "amd64": 298, "aarch64": 241, "arm64": 241}

_ENGINE_LABELS = {
    "rcs0": "Render/3D",
    "ccs0": "Compute",
    "vcs0": "Video",
    "vcs1": "Video",
    "vecs0": "Video Enhance",
    "bcs0": "Blitter",
}

_HINT_NO_PMU = "未找到 i915 PMU；需要 5.8+ 内核并映射 /sys 与 /dev/dri"
_HINT_NO_PERF = "i915 PMU 存在但 perf_event_open 被拒绝；需要 privileged 或 CAP_PERFMON"
_HINT_NO_MEDIA = "容器内未见 /dev/dri；privileged 运行或映射 devices: /dev/dri"


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _read_number(path: str) -> Optional[float]:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_perf_config(text: Optional[str]) -> Optional[int]:
    """Parse an i915 PMU event description such as ``config=0x2000``."""
    if not text:
        return None
    config = 0
    found = False
    for part in text.split(","):
        key, _, value = part.partition("=")
        if key.strip() != "config":
            continue
        try:
            config |= int(value.strip(), 16)
        except ValueError:
            return None
        found = True
    return config if found else None


def perf_event_open(perf_type: int, config: int) -> Optional[int]:
    """Open a counting perf event; returns a file descriptor or None."""
    number = _PERF_EVENT_OPEN_SYSCALL.get(platform.machine().lower())
    if number is None:
        return None
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
    except OSError:
        return None
    attr = ctypes.create_string_buffer(PERF_ATTR_SIZE)
    struct.pack_into(
        "<IIQQQQ",
        attr,
        0,
        perf_type,
        PERF_ATTR_SIZE,
        config,
        0,
        0,
        PERF_FORMAT_TOTAL_TIME_ENABLED | PERF_FORMAT_TOTAL_TIME_RUNNING,
    )
    # pid=-1, cpu=0: device PMU events are read system wide.
    fd = libc.syscall(number, ctypes.byref(attr), -1, 0, -1, 0)
    return fd if fd >= 0 else None


def read_perf_counter(fd: int) -> Optional[Tuple[int, int, int]]:
    """Read (value, time_enabled, time_running) from an open perf counter."""
    try:
        data = os.read(fd, PERF_COUNTER_SIZE)
    except OSError:
        return None
    if len(data) != PERF_COUNTER_SIZE:
        return None
    return struct.unpack("<QQQ", data)


def busy_percent(previous: Tuple[int, int, int], current: Tuple[int, int, int]) -> Optional[float]:
    """Busy share between two perf samples, normalized by the enabled time."""
    busier, enabled_now = current[0], current[1]
    busy_before, enabled_before = previous[0], previous[1]
    enabled_delta = enabled_now - enabled_before
    if enabled_delta <= 0:
        return None
    busy_delta = busier - busy_before
    if busy_delta < 0:
        return None
    return round(max(0.0, min(100.0, busy_delta / enabled_delta * 100)), 2)


def counter_percent(previous_value: Optional[float], previous_at: Optional[float],
                    value: float, now: float, unit_scale: float) -> Optional[float]:
    """Busy share for a cumulative counter expressed in ``unit_scale`` per second."""
    if previous_value is None or previous_at is None:
        return None
    elapsed = now - previous_at
    if elapsed <= 0:
        return None
    delta = value - previous_value
    if delta < 0:
        return None
    return round(max(0.0, min(100.0, delta / (elapsed * unit_scale) * 100)), 2)


class _I915Pmu:
    """Reads the i915 PMU ``*-busy`` events for every render/media engine."""

    def __init__(self, root: str = I915_PMU_ROOT):
        self.root = root
        self.fds: Dict[str, int] = {}
        self.last: Dict[str, Tuple[int, int, int]] = {}
        self.hint = ""

    def open(self) -> bool:
        perf_type = _read_number(os.path.join(self.root, "type"))
        events = os.path.join(self.root, "events")
        if perf_type is None or not os.path.isdir(events):
            self.hint = _HINT_NO_PMU
            return False
        for entry in sorted(os.listdir(events)):
            if not entry.endswith("-busy"):
                continue
            config = parse_perf_config(_read_text(os.path.join(events, entry)))
            if config is None:
                continue
            fd = perf_event_open(int(perf_type), config)
            if fd is not None:
                self.fds[entry[: -len("-busy")]] = fd
        if not self.fds:
            self.hint = _HINT_NO_PERF
            return False
        return True

    def sample(self) -> Optional[List[dict]]:
        current: Dict[str, Tuple[int, int, int]] = {}
        for name, fd in self.fds.items():
            counter = read_perf_counter(fd)
            if counter is not None:
                current[name] = counter
        engines = []
        for name, counter in sorted(current.items()):
            previous = self.last.get(name)
            if previous is None:
                continue
            percent = busy_percent(previous, counter)
            if percent is None:
                continue
            engines.append({"name": name, "label": _ENGINE_LABELS.get(name, name), "busyPercent": percent})
        self.last = current
        return engines or None

    def close(self) -> None:
        for fd in self.fds.values():
            try:
                os.close(fd)
            except OSError:
                pass
        self.fds = {}


class _NpuCounter:
    """Cumulative NPU busy time from the intel_vpu sysfs attributes."""

    def __init__(self, device: str):
        self.device = device
        self._busy: Optional[float] = None
        self._at: Optional[float] = None

    def sample(self, now: float) -> Optional[float]:
        busy = _read_number(os.path.join(self.device, "npu_busy_time_us"))
        if busy is None:
            return None
        percent = counter_percent(self._busy, self._at, busy, now, 1_000_000.0)
        self._busy, self._at = busy, now
        return percent

    def describe(self) -> dict:
        busy = _read_number(os.path.join(self.device, "npu_busy_time_us"))
        memory = _read_number(os.path.join(self.device, "npu_memory_utilization"))
        current = _read_number(os.path.join(self.device, "npu_current_frequency_mhz"))
        maximum = _read_number(os.path.join(self.device, "npu_max_frequency_mhz"))
        info = {"busyTimeUs": int(busy) if busy is not None else None}
        if memory is not None:
            info["memoryBytes"] = int(memory)
        if current is not None:
            info["frequencyMhz"] = int(current)
        if maximum is not None:
            info["maxFrequencyMhz"] = int(maximum)
        for key, name in (("power_state", "powerState"), ("sched_mode", "schedMode")):
            value = _read_text(os.path.join(self.device, key))
            if value:
                info[name] = value
        return info


def _dri_devices(drm_root: str) -> List[str]:
    try:
        return sorted(name for name in os.listdir(drm_root) if name.startswith("card"))
    except OSError:
        return []


def _dri_driver(drm_root: str, card: str) -> str:
    link = os.path.join(drm_root, card, "device", "driver")
    try:
        return os.path.basename(os.path.realpath(link))
    except OSError:
        return ""


class AcceleratorSampler:
    """Background sampler for iGPU engines and NPU busy time."""

    def __init__(self, drm_root: str = DRM_ROOT, accel_root: str = ACCEL_ROOT,
                 pmu_root: str = I915_PMU_ROOT, interval: float = SAMPLE_SECONDS,
                 first_sample_seconds: float = FIRST_SAMPLE_SECONDS):
        self.drm_root = drm_root
        self.accel_root = accel_root
        self.interval = interval
        self.first_sample_seconds = first_sample_seconds
        self._pmu = _I915Pmu(pmu_root)
        self._npu_counters: Dict[str, _NpuCounter] = {}
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._gpu: List[dict] = []
        self._npu: List[dict] = []
        self._gpu_error = ""
        self._pmu_ok = False
        self._rc6: Optional[Tuple[float, float]] = None

    # -- lifecycle ---------------------------------------------------------
    def _ensure_started(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._run, name="accelerator-sampler", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._pmu.close()

    # -- sampling ----------------------------------------------------------
    def _cards(self) -> List[str]:
        return _dri_devices(self.drm_root)

    def _sample_gpu(self, now: float) -> List[dict]:
        engines = self._pmu.sample() if self._pmu_ok else None
        devices = self._cards()
        if not devices:
            self._gpu_error = _HINT_NO_MEDIA
            return []
        card = devices[0]
        driver = _dri_driver(self.drm_root, card)
        frequency = _read_number(os.path.join(self.drm_root, card, "gt", "gt0", "rps_act_freq_mhz"))
        rc6 = _read_number(os.path.join(self.drm_root, card, "gt", "gt0", "rc6_residency_ms"))
        rc6_percent = None
        if rc6 is not None:
            previous = self._rc6
            if previous is not None and now > previous[1]:
                rc6_percent = round(max(0.0, min(100.0, (rc6 - previous[0]) / ((now - previous[1]) * 1000) * 100)), 2)
            self._rc6 = (rc6, now)
        util = None
        if engines:
            util = max(engine["busyPercent"] for engine in engines)
        elif driver in ("amdgpu", "radeon"):
            # amdgpu exposes a ready-made percentage instead of PMU counters.
            busy = _read_number(os.path.join(self.drm_root, card, "device", "gpu_busy_percent"))
            if busy is not None:
                util = round(max(0.0, min(100.0, busy)), 2)
        entry = {
            "index": 0,
            "name": "Intel 核显" if driver in ("i915", "xe") else f"{driver or 'DRM'} 显卡",
            "type": "dri",
            "available": True,
            "driver": driver or "drm",
            "path": os.path.join("/dev/dri", card),
            "utilPercent": util,
            "engines": engines or [],
            "frequencyMhz": int(frequency) if frequency is not None else None,
            "idleResidencyPercent": rc6_percent,
            "status": "busy" if (util or 0) >= 1 else "idle",
        }
        entry["hint"] = "" if util is not None else (self._pmu.hint or "等待第二次采样以计算利用率")
        return [entry]

    def _sample_npu(self, now: float) -> List[dict]:
        try:
            entries = sorted(name for name in os.listdir(self.accel_root) if name.startswith("accel"))
        except OSError:
            entries = []
        npus = []
        for index, name in enumerate(entries):
            device = os.path.join(self.accel_root, name, "device")
            counter = self._npu_counters.setdefault(name, _NpuCounter(device))
            percent = counter.sample(now) if os.path.isdir(device) else None
            info = counter.describe() if os.path.isdir(device) else {}
            entry = {
                "index": index,
                "name": "Intel NPU",
                "type": "accel",
                "available": True,
                "driver": _read_text(os.path.join(device, "driver")) or "intel_vpu",
                "path": f"/sys/class/accel/{name}",
                "device": f"/dev/accel/{name}",
                "utilPercent": percent,
                "status": "busy" if (percent or 0) >= 1 else "idle",
                **info,
            }
            if percent is None and "busyTimeUs" not in info:
                entry["hint"] = "该内核未暴露 npu_busy_time_us；需要 6.11+ 与 ACCEL 驱动"
            npus.append(entry)
        if not npus and os.path.isdir("/dev/accel"):
            npus.append({
                "index": 0,
                "name": "Intel NPU",
                "type": "dev-accel",
                "available": True,
                "path": "/dev/accel",
                "utilPercent": None,
                "hint": "已映射 /dev/accel，但容器内未见 /sys/class/accel 统计接口",
            })
        return npus

    def _run(self) -> None:
        self._pmu_ok = self._pmu.open()
        # Baseline both counters first so the very first published snapshot already
        # carries a measured window instead of an empty value.
        start = time.monotonic()
        self._sample_gpu(start)
        self._sample_npu(start)
        deadline = time.monotonic() + self.first_sample_seconds
        while time.monotonic() < deadline and not self._stop.is_set():
            time.sleep(0.05)
        while not self._stop.is_set():
            now = time.monotonic()
            gpu = self._sample_gpu(now)
            npu = self._sample_npu(now)
            with self._lock:
                self._gpu, self._npu = gpu, npu
            self._ready.set()
            self._stop.wait(self.interval)

    # -- public API --------------------------------------------------------
    def snapshot(self) -> dict:
        self._ensure_started()
        self._ready.wait(timeout=READY_TIMEOUT_SECONDS)
        with self._lock:
            return {"gpus": [dict(entry) for entry in self._gpu],
                    "npus": [dict(entry) for entry in self._npu]}


_sampler: Optional[AcceleratorSampler] = None
_sampler_lock = threading.Lock()


def read_accelerator_stats() -> dict:
    """Cached iGPU/NPU snapshot; starts the sampler on first use."""
    global _sampler
    with _sampler_lock:
        if _sampler is None:
            _sampler = AcceleratorSampler()
    return _sampler.snapshot()
