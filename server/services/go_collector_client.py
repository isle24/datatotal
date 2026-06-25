import json
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

GO_COLLECTOR_URL = os.getenv("GO_COLLECTOR_URL", "http://127.0.0.1:18088")


def _request(path: str, method: str = "GET") -> Optional[dict]:
    try:
        req = urllib.request.Request(
            f"{GO_COLLECTOR_URL}{path}",
            headers={"user-agent": "nas-traffic-lens/1.0"},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = resp.read(65536)
            return json.loads(data.decode(errors="ignore"))
    except Exception:
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
    return _get("/api/snapshot")


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
    return _post("/api/stage/start")


def stage_stop() -> Optional[dict]:
    return _post("/api/stage/stop")


def stage_reset() -> Optional[dict]:
    return _post("/api/stage/reset")


def stage_info() -> Optional[dict]:
    return _get("/api/stage/info")
