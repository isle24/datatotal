import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

GO_COLLECTOR_URL = os.getenv("GO_COLLECTOR_URL", "http://127.0.0.1:18088")
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_snapshot_lock = threading.Lock()
_snapshot_value = None
_snapshot_at = None
_request_error = ""
_last_warning = 0.0


def request_status() -> dict:
    return {"error": _request_error}


def clear_snapshot_cache() -> None:
    global _snapshot_value, _snapshot_at
    with _snapshot_lock:
        _snapshot_value, _snapshot_at = None, None


def _request(path: str, method: str = "GET") -> Optional[dict]:
    global _request_error, _last_warning
    try:
        req = urllib.request.Request(
            f"{GO_COLLECTOR_URL}{path}",
            headers={"user-agent": "nas-traffic-lens/1.0"},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise ValueError("collector response too large")
            result = json.loads(data.decode("utf-8"))
            if not isinstance(result, dict):
                raise ValueError("collector response must be an object")
            _request_error = ""
            return result
    except (OSError, ValueError) as exc:
        _request_error = "collector response too large" if str(exc) == "collector response too large" else "collector response unavailable or invalid"
        timestamp = time.monotonic()
        if timestamp - _last_warning >= 30:
            logging.getLogger(__name__).warning("%s (%s)", _request_error, type(exc).__name__)
            _last_warning = timestamp
        return None


def _get(path: str) -> Optional[dict]:
    return _request(path)


def _post(path: str) -> Optional[dict]:
    return _request(path, method="POST")


def _query(path: str, params: dict) -> str:
    cleaned = {
        key: value
        for key, value in params.items()
        if value is not None and str(value) != ""
    }
    if not cleaned:
        return path
    return f"{path}?{urllib.parse.urlencode(cleaned)}"


def probe() -> bool:
    result = _get("/api/health")
    return bool(result and result.get("ok") and result.get("captureReady"))


def wait_for_probe(attempts: int = 10, delay: float = 0.2) -> bool:
    for _ in range(max(1, attempts)):
        if probe():
            return True
        time.sleep(max(0.05, delay))
    return False


def snapshot() -> Optional[dict]:
    global _snapshot_value, _snapshot_at
    with _snapshot_lock:
        if _snapshot_at is not None and time.monotonic() - _snapshot_at < 1.0:
            return _snapshot_value
        _snapshot_value = _get("/api/snapshot")
        _snapshot_at = time.monotonic()
        return _snapshot_value


def process_totals() -> Optional[dict]:
    return _get("/api/process-totals")


def processes(period: str = "30s", limit: int = 30) -> Optional[dict]:
    return _get(f"/api/processes?period={period}&limit={limit}")


def connections(
    mode: str = "capture",
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
) -> Optional[dict]:
    return _get(
        _query(
            "/api/connections",
            {
                "mode": mode,
                "iface": iface,
                "scope": scope,
                "proto": proto,
                "direction": direction,
                "owner": owner,
                "source": source,
                "dest": dest,
                "min_bytes": min_bytes,
                "min_duration": min_duration,
                "limit": limit,
                "offset": offset,
            },
        )
    )


def diagnostics() -> Optional[dict]:
    return _get("/api/diagnostics")


def stage_start() -> Optional[dict]:
    clear_snapshot_cache()
    return _post("/api/stage/start")


def stage_stop() -> Optional[dict]:
    clear_snapshot_cache()
    return _post("/api/stage/stop")


def stage_reset() -> Optional[dict]:
    clear_snapshot_cache()
    return _post("/api/stage/reset")


def stage_info() -> Optional[dict]:
    return _get("/api/stage/info")
