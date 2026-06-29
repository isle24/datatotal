# Container Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add container-level auto-protection rules that can restart or stop a selected Docker container when CPU, memory, or block I/O thresholds stay exceeded for a configured duration.

**Architecture:** Reuse the existing monitor rule and notification system, but add a dedicated container-protection rule type that targets one container by ID/name. Docker stats are sampled on demand and cached briefly; rule evaluation happens in the existing collector loop with cooldown and max-action counters to prevent restart loops. When a rule fires, the app records an alert and reuses the existing notification channels; if the configured action budget is exceeded, it stops the container and records the stop reason.

**Tech Stack:** FastAPI/Python, Docker Engine HTTP API over socket, Vue/Vite, existing SQLite settings storage, existing notification templates/channels.

## Global Constraints

- Docker image must build for linux/amd64 and linux/arm64.
- Docker Hub push is not performed unless explicitly requested.
- `/proc` host volume must not be required.
- `DASHBOARD_PASSWORD` examples remain `123456`.
- Existing `/api/overview`, `/api/snapshot`, `/api/processes`, `/api/connections`, `/api/stage/*`, and `/api/diagnostics` response shapes must remain compatible.
- Existing notification channels and alert delivery behavior must be reused.
- Container protection must degrade safely if Docker socket write access is unavailable.

---

### Task 1: Container Protection Data Model And Evaluation

**Files:**
- Modify: `server/main.py`
- Modify: `server/tests/test_go_snapshot_merge.py`

**Interfaces:**
- Produces a new saved settings payload for container protection rules.
- Consumes existing Docker container stats from `docker_container_stats(container_id)`.
- Reuses existing `record_alert()` and `notify_alert()` for rule output.

- [ ] Write a failing test that a container rule with `AND` only fires when all selected metrics stay over threshold for the configured duration.
- [ ] Write a failing test that a container rule with `OR` fires when any selected metric stays over threshold for the configured duration.
- [ ] Write a failing test that exceeding the max action count turns the action into a hard stop and records the reason.
- [ ] Implement the minimal container-rule model, sanitization, persistence, and evaluation helpers.
- [ ] Run `python3 -m py_compile server/main.py` and the targeted Python test file.

### Task 2: Docker Action Support

**Files:**
- Modify: `server/main.py`
- Modify: `server/tests/test_go_snapshot_merge.py`

**Interfaces:**
- Produces `docker_container_action(container_id, action)` or equivalent helper.
- Consumes Docker Engine API via the existing `docker_api_request()` helper.
- Reuses existing Docker socket configuration.

- [ ] Write a failing test for restarting a container through the Docker API helper.
- [ ] Write a failing test for stopping a container through the Docker API helper.
- [ ] Implement the Docker action helper and wire it into the container-rule evaluator.
- [ ] Verify the action helper refuses empty IDs and returns actionable errors for non-2xx Docker responses.

### Task 3: UI For Container Protection Rules

**Files:**
- Modify: `front-end/src/App.vue`
- Modify: `front-end/src/styles.css`

**Interfaces:**
- Consumes `settings.monitor.containerRules` or equivalent settings data.
- Produces saved rule payloads that match the backend schema.
- Reuses the existing monitor section and notification-channel selector UI.

- [ ] Add a failing UI test or targeted state assertion if the project has a lightweight front-end test hook; otherwise add a minimal manual-verification checklist in the plan note.
- [ ] Add a container-protection rule editor with container selector, metric multi-select, `AND/OR` selector, threshold inputs, duration, max action count, action selector, and channel picker.
- [ ] Expose the rule list in the settings view without disturbing existing traffic-monitor rules.
- [ ] Update the container card to show whether protection is enabled for that container.

### Task 4: Verification And Documentation

**Files:**
- Modify: `README.md`
- Modify: `doc/README.md`
- Modify: `VERSION` only if the feature ships as a new release tag

**Interfaces:**
- Documents the new container-protection settings and Docker socket write requirement.
- Documents the fact that notification channels are reused for both alerts and auto-protection events.

- [ ] Add the new settings to the docs with exact field names and operator semantics.
- [ ] Run the relevant backend tests, front-end build, and a live Docker-action smoke test if Docker socket write access is available.
- [ ] Commit the feature once verification passes.
