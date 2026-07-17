# Simplified Compose Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the recommended compose files to deployment-only inputs, enable Docker discovery by default, and persist user-adjustable runtime defaults in SQLite.

**Architecture:** Keep process bootstrap values in environment variables and mounts. Add Docker discovery to `RuntimeSettingsPayload`, seed runtime defaults into SQLite on first start, and let saved SQLite values override the environment-derived first-run default. Preserve advanced environment overrides in code and documentation without showing them in compose.

**Tech Stack:** Docker Compose YAML, Python 3.12, FastAPI/Pydantic, SQLite, Vue 3, Markdown.

## Global Constraints

- Recommended compose environment keys are exactly `APP_PORT` and `DASHBOARD_PASSWORD`.
- `DASHBOARD_PASSWORD` example remains `123456`; no real password is written to documentation.
- Docker discovery defaults to enabled and Docker socket is mounted read-only by default.
- Missing or inaccessible Docker socket must not stop the application.
- NAS and local compose target `linux/amd64`.
- Release version is `2026.07.17-1` and images are built for amd64 and arm64 without pushing Docker Hub.

---

### Task 1: Deployment and Runtime Configuration Tests

**Files:**
- Create: `server/tests/test_deployment_config.py`
- Test: `server/tests/test_deployment_config.py`

**Interfaces:**
- Consumes: `server.main.env_bool`, `server.main.RuntimeSettingsPayload`, `docker-compose.yml`, `docker-compose.nas.yml`.
- Produces: regression checks for compose environment keys, required mounts, and Docker discovery defaults.

- [x] **Step 1: Write the failing tests**

```python
import os
from pathlib import Path
from unittest.mock import patch
import yaml

import server.main as main

ROOT = Path(__file__).resolve().parents[2]

def test_compose_files_only_expose_bootstrap_environment():
    for name in ("docker-compose.yml", "docker-compose.nas.yml"):
        service = yaml.safe_load((ROOT / name).read_text())["services"]["nas-traffic-lens"]
        assert service["environment"] == {"APP_PORT": "8088", "DASHBOARD_PASSWORD": "123456"}
        assert "./data:/data" in service["volumes"]
        assert "./logs:/logs" in service["volumes"]
        assert "/var/run/docker.sock:/var/run/docker.sock:ro" in service["volumes"]

def test_docker_discovery_defaults_on_and_can_be_disabled():
    with patch.dict(os.environ, {}, clear=True):
        assert main.env_bool("ENABLE_DOCKER_DISCOVERY", True) is True
    with patch.dict(os.environ, {"ENABLE_DOCKER_DISCOVERY": "false"}, clear=True):
        assert main.env_bool("ENABLE_DOCKER_DISCOVERY", True) is False
    assert main.RuntimeSettingsPayload().dockerDiscovery is True
```

- [x] **Step 2: Run tests and verify RED**

Run: `python3 server/tests/test_deployment_config.py`

Expected: fail because compose contains extra variables and `env_bool`/`dockerDiscovery` do not exist.

- [x] **Step 3: Leave tests failing until Tasks 2 and 3 implement the behavior**

No production code is changed in this task.

### Task 2: SQLite Runtime Defaults and Docker Discovery

**Files:**
- Modify: `server/main.py`
- Modify: `front-end/src/App.vue`
- Test: `server/tests/test_deployment_config.py`

**Interfaces:**
- Consumes: existing `RuntimeSettingsPayload`, `TrafficCollector.load_saved_settings`, `TrafficCollector.update_runtime_settings`.
- Produces: `env_bool(name: str, default: bool) -> bool` and `RuntimeSettingsPayload.dockerDiscovery: bool`.

- [x] **Step 1: Add environment boolean parsing and default Docker discovery to enabled**

```python
def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on"}

DEFAULT_ENABLE_DOCKER_DISCOVERY = env_bool("ENABLE_DOCKER_DISCOVERY", True)
ENABLE_DOCKER_DISCOVERY = DEFAULT_ENABLE_DOCKER_DISCOVERY
```

- [x] **Step 2: Add Docker discovery to SQLite runtime settings**

```python
class RuntimeSettingsPayload(BaseModel):
    # existing fields unchanged
    dockerDiscovery: bool = DEFAULT_ENABLE_DOCKER_DISCOVERY
```

`load_saved_settings()` constructs `RuntimeSettingsPayload(**(runtime or {}))`, applies all values including `dockerDiscovery`, and writes `runtime_settings` to SQLite when no row exists. `update_runtime_settings()` applies and saves the same field, invalidates the Docker list cache, and refreshes container metadata.

- [x] **Step 3: Add the Web toggle**

Add a checkbox/toggle bound to `runtimeForm.dockerDiscovery` in the editable runtime settings card. Keep Docker socket path read-only in the startup information card.

- [x] **Step 4: Run the configuration tests**

Run: `python3 server/tests/test_deployment_config.py`

Expected: Docker default assertions pass; compose assertions remain failing until Task 3.

### Task 3: Simplify Compose and Documentation

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.nas.yml`
- Modify: `README.md`
- Modify: `doc/README.md`
- Test: `server/tests/test_deployment_config.py`

**Interfaces:**
- Consumes: bootstrap defaults `/data/traffic.db`, `/logs`, port `8088`, password example `123456`.
- Produces: two minimal compose templates and aligned deployment documentation.

- [x] **Step 1: Replace compose environment and volume sections**

Both compose files use exactly:

```yaml
environment:
  APP_PORT: "8088"
  DASHBOARD_PASSWORD: "123456"
volumes:
  - ./data:/data
  - ./logs:/logs
  - /var/run/docker.sock:/var/run/docker.sock:ro
```

- [x] **Step 2: Rewrite deployment guidance**

README examples match `docker-compose.nas.yml`. Explain that monitoring, notifications, Docker discovery, sampling and retention are configured in the Web UI and stored in SQLite. Move low-level environment variables under an explicitly optional advanced section.

- [x] **Step 3: Run configuration tests**

Run: `python3 server/tests/test_deployment_config.py`

Expected: all deployment configuration tests pass.

### Task 4: Release Verification, Versioning, Images, and GitHub

**Files:**
- Modify: `VERSION`

**Interfaces:**
- Consumes: completed implementation and tests.
- Produces: version `2026.07.17-1`, local amd64/arm64 images, Git commit, and GitHub `main` push.

- [x] **Step 1: Run full verification**

Run:

```bash
python3 -m py_compile server/main.py server/services/notifications.py
python3 server/tests/test_go_snapshot_merge.py
python3 server/tests/test_deployment_config.py
npm run build --prefix front-end
docker compose -f docker-compose.yml config
docker compose -f docker-compose.nas.yml config
```

Expected: all commands exit 0.

- [x] **Step 2: Bump version**

Set `VERSION` to `2026.07.17-1`, then rerun `python3 server/tests/test_deployment_config.py`.

- [x] **Step 3: Build Docker images**

Build amd64 tags `latest`, `latest-amd64`, `2026.07.17-1`, `2026.07.17-1-amd64`; build arm64 tags `latest-arm64`, `2026.07.17-1-arm64`. Use `--load` and do not push Docker Hub.

- [x] **Step 4: Verify image architecture and embedded version**

Use `docker image inspect` for architecture and run each architecture image with `cat /app/VERSION`; both must report `2026.07.17-1`.

- [ ] **Step 5: Commit and push GitHub**

Run `git add` for the plan, source, tests, compose, docs and version; commit with `feat: simplify compose runtime configuration`; push `main` to `origin`.
