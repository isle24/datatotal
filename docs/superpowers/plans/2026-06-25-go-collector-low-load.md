# Go Collector Low Load Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the Go collector path, keep existing UI/API behavior compatible, and add a low-load profile for NAS deployments.

**Architecture:** Package Go libpcap as the production external collector and keep Python Scapy as fallback. Treat eBPF as experimental documentation only until it has a real buildable entrypoint. Low-load mode avoids packet capture and keeps only system interface counters plus lightweight connection counts.

**Tech Stack:** FastAPI/Python, Go + gopacket/libpcap, Vue/Vite, Docker multi-stage builds.

## Global Constraints

- Docker image must build for linux/amd64 and linux/arm64.
- Docker Hub push is not performed unless explicitly requested.
- `/proc` host volume must not be required.
- `DASHBOARD_PASSWORD` examples remain `123456`.
- Existing `/api/overview`, `/api/snapshot`, `/api/processes`, `/api/connections`, `/api/stage/*`, and `/api/diagnostics` response shapes must remain compatible.

---

### Task 1: Go Collector API Compatibility

**Files:**
- Create: `server/go-collector/collector/aggregator_test.go`
- Create: `server/go-collector/collector/capture_test.go`
- Modify: `server/go-collector/collector/types.go`
- Modify: `server/go-collector/collector/capture.go`
- Modify: `server/go-collector/collector/aggregator.go`
- Modify: `server/go-collector/main.go`

**Interfaces:**
- Produces `PacketEvent.SrcIP`, `PacketEvent.DstIP`, `PacketEvent.Src`, and `PacketEvent.Dst`.
- Produces `Aggregator.ConnectionEntries(activeSec, limit, offset int, filters ConnectionFilters) ([]ConnectionEntry, ConnectionPage, ConnectionSummary)`.

- [ ] Write failing Go tests for process matching with pure IP fields and endpoint rendering.
- [ ] Write failing Go tests for filtered, sorted, paginated connection responses.
- [ ] Implement minimal Go changes to pass tests.
- [ ] Run `cd server/go-collector && go test ./...`.

### Task 2: Python Proxy And Stage Compatibility

**Files:**
- Modify: `server/services/go_collector_client.py`
- Modify: `server/main.py`

**Interfaces:**
- Go client forwards query strings for `/api/connections`.
- Python stage endpoints call Go `/api/stage/*` when the external collector is active.
- Python diagnostics includes external collector status without losing local diagnostics.

- [ ] Add Python client query forwarding.
- [ ] Add retrying Go probe to avoid startup races.
- [ ] Proxy stage start/stop/reset/resume to Go when available.
- [ ] Run `python3 -m py_compile server/main.py server/services/*.py`.

### Task 3: Build And Low-Load Profile

**Files:**
- Modify: `Dockerfile`
- Modify: `server/entrypoint.sh`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.nas.yml`
- Modify: `README.md`
- Modify: `doc/README.md`
- Modify: `VERSION`

**Interfaces:**
- `COLLECTOR_MODE=auto|golibpcap|python|off|ebpf`.
- `COLLECTOR_PROFILE=low|balanced|diagnostic`.
- `GO_COLLECTOR_ENABLED=false` disables the external collector.

- [ ] Remove non-buildable eBPF Docker stage from production image.
- [ ] Start Go collector only when mode/profile allows packet capture.
- [ ] Document low-load profile and eBPF experimental status.
- [ ] Run frontend build, Go tests, Python compile, and Docker build for amd64/arm64.
