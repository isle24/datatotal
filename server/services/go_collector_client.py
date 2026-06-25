import json
import os
import urllib.request
from typing import Dict, List, Optional

GO_COLLECTOR_URL = os.getenv("GO_COLLECTOR_URL", "http://127.0.0.1:18088")


def _get(path: str) -> Optional[dict]:
    try:
        req = urllib.request.Request(
            f"{GO_COLLECTOR_URL}{path}",
            headers={"user-agent": "nas-traffic-lens/1.0"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = resp.read(65536)
            return json.loads(data.decode(errors="ignore"))
    except Exception:
        return None


def probe() -> bool:
    result = _get("/api/health")
    return bool(result and result.get("ok"))


def snapshot() -> Optional[dict]:
    return _get("/api/snapshot")


def processes(period: str = "30s", limit: int = 30) -> Optional[dict]:
    return _get(f"/api/processes?period={period}&limit={limit}")


def connections(mode: str = "capture") -> Optional[dict]:
    return _get(f"/api/connections?mode={mode}")


def diagnostics() -> Optional[dict]:
    return _get("/api/diagnostics")


def stage_start() -> Optional[dict]:
    return _get("/api/stage/start")


def stage_stop() -> Optional[dict]:
    return _get("/api/stage/stop")


def stage_reset() -> Optional[dict]:
    return _get("/api/stage/reset")


def stage_info() -> Optional[dict]:
    return _get("/api/stage/info")
