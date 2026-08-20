# Docker Icons and AI Settings Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bundled Docker service icons and a secure, confirmation-based AI assistant that can configure validated non-secret application settings.

**Architecture:** Keep icon matching in a dependency-free `server/services/docker_icons.py`. Keep proposal parsing, schema and short-lived storage in `server/services/config_assistant.py`; keep current-value collection, Pydantic sanitization, SQLite writes and FastAPI routes in `server/main.py`. Extend the existing Vue AI center with a settings-assistant mode and use returned icon metadata in the Docker accordion cards.

**Tech Stack:** FastAPI/Pydantic v2, SQLite, Python standard library, Vue 3/Vite, existing AI provider adapter, existing Node contract tests.

## Global Constraints

- Do not expose or modify dashboard passwords, AI API keys, notification tokens, Docker socket paths, database paths, log paths, SQL, host commands or arbitrary Docker commands through AI.
- AI configuration is proposal-first: `POST /api/ai/configure` never persists changes; `POST /api/ai/configure/apply` accepts only a server-issued short-lived proposal ID.
- Proposal state is process-local, bounded, single-use and expires after 10 minutes; restart invalidates all proposals.
- Icons are bundled local SVG data URLs; no runtime CDN or external image download is added.
- Keep existing manual Docker icon uploads and settings payloads backward-compatible.
- Keep Docker stats and web probing on-demand; icon matching must not add a Docker socket call.
- Use ASCII for new code where practical, preserve existing Chinese UI text, and use `apply_patch` for manual edits.
- Increment `VERSION` from `2026.08.20-4` to `2026.08.20-5` only after behavior and tests pass.
- Do not push Docker Hub images; build local `linux/amd64` and `linux/arm64` images/tar files after verification.

---

### Task 1: Add failing Docker icon tests

**Files:**
- Create: `server/services/docker_icons.py`
- Modify: `server/tests/test_deployment_config.py`

**Interfaces:**
- Produces `DOCKER_ICON_REGISTRY`, `normalize_icon_match_text(value: str) -> str`, `match_docker_icon(name: str = "", image: str = "", compose_service: str = "") -> dict`, and `list_docker_icons() -> list[dict]`.
- Each icon result has `key`, `label`, `dataUrl`, and `source`; automatic matches use `source == "builtin"`.

- [ ] **Step 1: Write focused failing tests**

Add these tests to `server/tests/test_deployment_config.py`:

```python
def test_builtin_docker_icons_match_names_images_and_compose_aliases():
    from server.services.docker_icons import match_docker_icon

    assert match_docker_icon(name="qbittorrent-nox")["key"] == "qbittorrent"
    assert match_docker_icon(image="redis:7-alpine")["key"] == "redis"
    assert match_docker_icon(compose_service="moviepolite")["key"] == "moviepilot"
    assert match_docker_icon(name="postgres")["key"] == "postgresql"


def test_builtin_docker_icon_list_is_bounded_and_local():
    from server.services.docker_icons import list_docker_icons

    icons = list_docker_icons()
    assert len(icons) >= 5
    assert all(item["dataUrl"].startswith("data:image/svg+xml,") for item in icons)
    assert all(len(item["dataUrl"]) < 65536 for item in icons)


def test_unknown_docker_service_does_not_receive_a_guess():
    from server.services.docker_icons import match_docker_icon

    assert match_docker_icon(name="totally-unrelated-service") == {}
```

- [ ] **Step 2: Run the tests and verify the expected red failure**

Run:

```bash
./.venv/bin/python - <<'PY'
import server.tests.test_deployment_config as test
for name in ("test_builtin_docker_icons_match_names_images_and_compose_aliases", "test_builtin_docker_icon_list_is_bounded_and_local", "test_unknown_docker_service_does_not_receive_a_guess"):
    getattr(test, name)()
PY
```

Expected: `ModuleNotFoundError` for `server.services.docker_icons`.

- [ ] **Step 3: Implement the smallest local registry**

Create the module with inline SVG data URLs and a registry entry shape like:

```python
DOCKER_ICON_REGISTRY = {
    "qbittorrent": {"label": "qBittorrent", "aliases": ("qbittorrent", "qb"), "svg": "..."},
    "redis": {"label": "Redis", "aliases": ("redis",), "svg": "..."},
    "mysql": {"label": "MySQL", "aliases": ("mysql",), "svg": "..."},
    "mariadb": {"label": "MariaDB", "aliases": ("mariadb",), "svg": "..."},
    "postgresql": {"label": "PostgreSQL", "aliases": ("postgresql", "postgres", "pgsql"), "svg": "..."},
    "moviepilot": {"label": "MoviePilot", "aliases": ("moviepilot", "moviepolite"), "svg": "..."},
}
```

Use normalized lowercase text with separators converted to spaces, compare exact tokens/segments before substring matches, and return a copy containing a `data:image/svg+xml,` URL. Keep SVGs simple and license-safe; do not fetch them at runtime.

- [ ] **Step 4: Run icon tests and the existing deployment tests**

Run the focused Python tests followed by:

```bash
./.venv/bin/python - <<'PY'
import server.tests.test_deployment_config as deployment
for name in sorted(dir(deployment)):
    if name.startswith("test_"):
        getattr(deployment, name)()
print("deployment tests passed")
PY
```

Expected: all tests pass.

- [ ] **Step 5: Commit the icon registry**

```bash
git add server/services/docker_icons.py server/tests/test_deployment_config.py
git commit -m "feat: bundle common Docker service icons"
git push origin main
```

### Task 2: Attach automatic icons to Docker responses

**Files:**
- Modify: `server/main.py`
- Modify: `server/tests/test_deployment_config.py`

**Interfaces:**
- `discover_containers(...)` adds `iconKey` and `iconSource` to every automatic/manual row without changing old `containerIcon` behavior.
- `GET /api/docker/icons` returns `{ "icons": [...] }`.
- Manual `docker_overrides.containers[*].icon` remains higher priority than an automatic icon.

- [ ] **Step 1: Add failing response tests**

Add a test that patches `server.main.docker_api_get` and asserts automatic matching and manual priority:

```python
def test_docker_discovery_adds_builtin_icon_and_manual_icon_wins():
    original = main.ENABLE_DOCKER_DISCOVERY
    main.ENABLE_DOCKER_DISCOVERY = True
    try:
        with patch("server.main.docker_api_get", return_value=[{
            "Id": "abcdef1234567890",
            "Names": ["/qbittorrent-nox"],
            "Image": "linuxserver/qbittorrent:latest",
            "Labels": {},
            "State": "running",
            "Status": "Up",
            "Created": 1,
            "HostConfig": {"NetworkMode": "bridge"},
            "Ports": [],
        }]):
            _ports, rows = main.discover_containers({}, main.empty_docker_overrides())
        assert rows[0]["iconKey"] == "qbittorrent"
        assert rows[0]["iconSource"] == "builtin"
        custom = {"containers": {"abcdef123456": {"containerId": "abcdef123456", "containerName": "qbittorrent-nox", "icon": "data:image/png;base64," + "a" * 32}}}
        with patch("server.main.docker_api_get", return_value=[{
            "Id": "abcdef1234567890", "Names": ["/qbittorrent-nox"], "Image": "qbittorrent", "Labels": {},
            "State": "running", "Status": "Up", "Created": 1, "HostConfig": {}, "Ports": [],
        }]):
            _ports, rows = main.discover_containers({}, custom)
        assert rows[0]["iconSource"] == "custom"
        assert rows[0]["containerIcon"].startswith("data:image/png,")
    finally:
        main.ENABLE_DOCKER_DISCOVERY = original
```

- [ ] **Step 2: Run the new test and verify it fails**

Expected: `KeyError: 'iconKey'`.

- [ ] **Step 3: Integrate the registry without adding Docker calls**

Import `match_docker_icon` and `list_docker_icons`. For each row, calculate the automatic result once from `name`, `image`, and `composeService`; use custom override icon when present, otherwise use the built-in `dataUrl`. Return:

```python
"iconKey": custom_icon and "custom" or builtin.get("key", ""),
"iconSource": "custom" if custom_icon else ("builtin" if builtin else ""),
"containerIcon": custom_icon or builtin.get("dataUrl", ""),
```

Keep port entries compatible by adding `containerIcon` only where the existing code already does so. Add the authenticated FastAPI route beside the Docker routes:

```python
@app.get("/api/docker/icons")
async def docker_icons() -> dict:
    return {"icons": list_docker_icons()}
```

- [ ] **Step 4: Run backend tests and compile**

```bash
./.venv/bin/python -m py_compile server/main.py server/services/docker_icons.py
./.venv/bin/python - <<'PY'
import server.tests.test_deployment_config as deployment
for name in sorted(dir(deployment)):
    if name.startswith("test_"):
        getattr(deployment, name)()
print("deployment tests passed")
PY
```

Expected: pass.

- [ ] **Step 5: Commit and push**

```bash
git add server/main.py server/services/docker_icons.py server/tests/test_deployment_config.py
git commit -m "feat: expose automatic Docker icons"
git push origin main
```

### Task 3: Add failing AI proposal policy tests

**Files:**
- Create: `server/services/config_assistant.py`
- Modify: `server/tests/test_ai.py`

**Interfaces:**
- Produces `CONFIGURATION_SCHEMA`, `configuration_schema()`, `parse_configuration_response(text: str) -> list[dict]`, `validate_configuration_changes(changes: list[dict], current: dict) -> list[dict]`, and `ProposalStore`.
- Validated changes use `{path: str, value: JSON-compatible scalar/list/dict, summary: str, risk: str}` and never include secrets.

- [ ] **Step 1: Write policy tests before implementation**

Add tests:

```python
def test_configuration_schema_excludes_secrets_and_host_controls():
    from server.services.config_assistant import configuration_schema

    paths = {item["path"] for item in configuration_schema()["fields"]}
    assert "runtime.sampleSeconds" in paths
    assert "ai.apiKey" not in paths
    assert "runtime.dbPath" not in paths
    assert all("token" not in path.lower() and "password" not in path.lower() for path in paths)


def test_configuration_response_requires_bounded_json_change_list():
    from server.services.config_assistant import parse_configuration_response

    assert parse_configuration_response('{"changes":[{"path":"runtime.sampleSeconds","value":2,"summary":"采样间隔 2 秒","risk":"低"}]}')[0]["path"] == "runtime.sampleSeconds"
    with pytest.raises(ValueError):
        parse_configuration_response("not json")


def test_configuration_changes_reject_sensitive_and_unknown_paths():
    from server.services.config_assistant import validate_configuration_changes

    current = {"runtime": {"sampleSeconds": 1}}
    with pytest.raises(ValueError, match="不允许"):
        validate_configuration_changes([{"path": "ai.apiKey", "value": "secret"}], current)
    with pytest.raises(ValueError, match="未知"):
        validate_configuration_changes([{"path": "runtime.execute", "value": "rm -rf /"}], current)


def test_proposal_store_is_single_use_and_expires():
    from server.services.config_assistant import ProposalStore

    store = ProposalStore(ttl_seconds=1)
    proposal_id = store.put({"changes": []}, now_value=100)
    assert store.take(proposal_id, now_value=100)["changes"] == []
    assert store.take(proposal_id, now_value=100) is None
    expired = store.put({"changes": []}, now_value=100)
    assert store.take(expired, now_value=102) is None
```

Use the repository's current test style; if `pytest` is unavailable, replace `pytest.raises` with `try/except` assertions matching the existing tests.

- [ ] **Step 2: Run the tests and verify the intended red failure**

Expected: import failure for `server.services.config_assistant`.

- [ ] **Step 3: Implement bounded schema, parser and store**

Define explicit fields for runtime settings, monitor rules, notification non-secret fields, container protection and AI non-secret fields. Validate path segments against the fixed schema, constrain change count to 50, summaries to 240 characters, serialized values to 32 KiB, and proposal IDs to `secrets.token_urlsafe(24)`. `ProposalStore.take` must delete before returning so a proposal cannot be replayed.

- [ ] **Step 4: Run AI policy tests and existing AI tests**

```bash
./.venv/bin/python - <<'PY'
import server.tests.test_ai as ai
for name in sorted(dir(ai)):
    if name.startswith("test_"):
        getattr(ai, name)()
print("AI tests passed")
PY
```

Expected: pass.

- [ ] **Step 5: Commit and push**

```bash
git add server/services/config_assistant.py server/tests/test_ai.py
git commit -m "feat: validate AI configuration proposals"
git push origin main
```

### Task 4: Add backend AI configure/schema/apply endpoints

**Files:**
- Modify: `server/main.py`
- Modify: `server/services/config_assistant.py`
- Modify: `server/tests/test_ai.py`

**Interfaces:**
- `GET /api/ai/configure/schema` returns the non-secret schema.
- `POST /api/ai/configure` accepts `{request: str, messages?: AIChatMessage[]}` and returns a proposal preview without writing settings.
- `POST /api/ai/configure/apply` accepts `{proposalId: str}` and returns the refreshed settings after one atomic validated apply.

- [ ] **Step 1: Add failing route/service tests**

Test the collector-level operations so tests do not require a live ASGI server:

```python
def test_ai_configuration_proposal_does_not_persist_until_apply():
    collector = make_ai_settings_collector(MemorySettingsDB())
    result = collector.create_ai_configuration_proposal("把采样间隔改为 2 秒")
    assert result["requiresConfirmation"] is True
    assert collector.db.get_setting("runtime_settings") is None
    applied = collector.apply_ai_configuration_proposal(result["proposal"]["id"])
    assert applied["runtime"]["sampleSeconds"] == 2


def test_ai_configuration_apply_rejects_replay_and_sensitive_changes():
    collector = make_ai_settings_collector(MemorySettingsDB())
    proposal = collector.create_ai_configuration_proposal("设置 API Key 为 secret")
    assert proposal["ok"] is False
    assert "API Key" in proposal["detail"] or "敏感" in proposal["detail"]
```

The test helper may patch `server.main.chat_completion` to return a bounded JSON proposal so no vendor request is made.

- [ ] **Step 2: Run the route/service tests and confirm failure**

Expected: `AttributeError` because the collector methods do not exist.

- [ ] **Step 3: Build the current configuration snapshot and apply dispatcher**

Add collector methods that build a snapshot from `runtime_settings`, `monitor_rules`, `notification_channels`, `container_protection_rules`, `ai_settings` public fields, and Docker overrides. Pass only that redacted snapshot plus `configuration_schema()` to the existing AI chat service with a system prompt requiring JSON:

```json
{"changes":[{"path":"runtime.sampleSeconds","value":2,"summary":"...","risk":"低"}]}
```

Parse and validate the model response, then store a proposal containing the current settings version, changes, and creation time. Apply by taking the proposal, reloading current settings, rejecting stale sensitive/unknown values, and dispatching each supported root through existing methods (`apply_runtime_settings`, `sanitize_monitor_rule`, `sanitize_notification_channel`, `sanitize_container_protection_rule`, `normalize_ai_settings`, and Docker override sanitization). Persist all settings under the existing keys while preserving API keys and notification tokens from the current database. If any validation fails, write nothing.

- [ ] **Step 4: Add schema and HTTP routes with bounded async work**

Use `asyncio.to_thread` for model calls and SQLite work:

```python
@app.get("/api/ai/configure/schema")
async def ai_configuration_schema() -> dict:
    return configuration_schema()

@app.post("/api/ai/configure")
async def ai_configure(payload: AIConfigurePayload) -> dict:
    return await asyncio.to_thread(collector.create_ai_configuration_proposal, payload.request, payload.messages)

@app.post("/api/ai/configure/apply")
async def ai_configure_apply(payload: AIConfigureApplyPayload) -> dict:
    return await asyncio.to_thread(collector.apply_ai_configuration_proposal, payload.proposalId)
```

Return user-safe errors with no stack trace or model secret. Do not add any background task.

- [ ] **Step 5: Run backend compile and all Python tests**

```bash
./.venv/bin/python -m py_compile server/main.py server/services/*.py
./.venv/bin/python - <<'PY'
import server.tests.test_deployment_config as deployment
import server.tests.test_ai as ai
import server.tests.test_go_snapshot_merge as go
for module in (deployment, ai, go):
    for name in sorted(dir(module)):
        if name.startswith("test_"):
            getattr(module, name)()
print("all python tests passed")
PY
```

Expected: pass.

- [ ] **Step 6: Commit and push**

```bash
git add server/main.py server/services/config_assistant.py server/tests/test_ai.py
git commit -m "feat: add confirmation-based AI settings assistant"
git push origin main
```

### Task 5: Add frontend icon display and AI settings assistant UI

**Files:**
- Modify: `front-end/src/App.vue`
- Modify: `front-end/src/styles.css`
- Modify: `front-end/tests/ui-contract.test.mjs`

**Interfaces:**
- Docker cards use `container.containerIcon` and show the automatic/custom source only as accessible metadata.
- AI page has `aiMode` values `"analysis"` and `"configure"`, `aiConfigureInput`, `aiConfigureProposal`, and confirmation/cancel handlers.

- [ ] **Step 1: Add failing UI contract assertions**

Add assertions:

```javascript
test("AI settings assistant exposes preview and confirmation controls", () => {
  assert.match(source, /aiMode/);
  assert.match(source, /设置助手/);
  assert.match(source, /\/api\/ai\/configure/);
  assert.match(source, /\/api\/ai\/configure\/apply/);
  assert.match(source, /确认应用/);
  assert.match(source, /取消变更/);
  assert.match(source, /iconSource/);
});
```

- [ ] **Step 2: Run the contract test and verify it fails**

```bash
node front-end/tests/ui-contract.test.mjs
```

Expected: assertion failure for `aiMode`.

- [ ] **Step 3: Implement compact settings-assistant mode**

Add a segmented mode control in the existing AI center. Analysis mode keeps the existing streaming chat. Settings mode sends the user's natural-language request to `/api/ai/configure`, renders each `proposal.changes` item with path/old/new/summary/risk, and only enables `确认应用` when a proposal exists. On apply, call `/api/ai/configure/apply`, clear the proposal, refresh settings and show a toast. On cancel, clear only the local proposal. Display API errors through the existing `formatValidationError` path.

- [ ] **Step 4: Render automatic/custom icon metadata without extra requests**

Update the Docker card image binding to use the returned `containerIcon`; add a fallback icon component when it is empty and an accessible label/title based on `container.name` and `container.iconSource`. Do not call `/api/docker/icons` for every card; optionally fetch it once when opening the Docker editor to provide an icon select, and use the existing uploaded icon as the custom option.

- [ ] **Step 5: Add responsive styles and run frontend tests/build**

Add styles for the mode control, proposal change rows and compact icon fallback using the existing theme variables, with `min-width: 0` and mobile stacking. Run:

```bash
node front-end/tests/ui-contract.test.mjs
cd front-end && npm run build
```

Expected: contract test and Vite build pass.

- [ ] **Step 6: Commit and push**

```bash
git add front-end/src/App.vue front-end/src/styles.css front-end/tests/ui-contract.test.mjs
git commit -m "feat: add AI settings assistant and Docker icon UI"
git push origin main
```

### Task 6: Documentation, version, full verification and local multi-arch build

**Files:**
- Modify: `README.md`
- Modify: `doc/README.md`
- Modify: `VERSION`
- Modify: `docker-compose.yml` only if the new feature needs a bootstrap variable; prefer no compose changes.

- [ ] **Step 1: Document bundled icons and AI confirmation flow**

Document the icon matching sources, manual override precedence, supported AI-managed settings, confirmation requirement, forbidden sensitive operations, proposal expiration, and the fact that AI API keys remain configured manually. Do not include any real password, token or API key.

- [ ] **Step 2: Increment the release version**

Write exactly `2026.08.20-5` to `VERSION`; do not hard-code this string in application source.

- [ ] **Step 3: Run complete verification before claiming success**

```bash
./.venv/bin/python -m py_compile server/main.py server/services/*.py
./.venv/bin/python - <<'PY'
import server.tests.test_deployment_config as deployment
import server.tests.test_ai as ai
import server.tests.test_go_snapshot_merge as go
for module in (deployment, ai, go):
    for name in sorted(dir(module)):
        if name.startswith("test_"):
            getattr(module, name)()
print("all python tests passed")
PY
cd front-end && node tests/ui-contract.test.mjs && npm run build
cd .. && go test ./server/go-collector/...
docker compose -f docker-compose.yml config
git diff --check
```

Expected: every command exits 0. Report unavailable Docker/Go tooling instead of hiding it.

- [ ] **Step 4: Build local amd64 and arm64 artifacts without pushing**

```bash
VERSION=$(tr -d '\n' < VERSION)
docker buildx build --platform linux/amd64 -t isle204/nas-traffic-lens:${VERSION}-amd64 -t isle204/nas-traffic-lens:latest-amd64 --load .
docker save isle204/nas-traffic-lens:${VERSION}-amd64 isle204/nas-traffic-lens:latest-amd64 -o nas-traffic-lens-${VERSION}-amd64.tar
docker buildx build --platform linux/arm64 -t isle204/nas-traffic-lens:${VERSION}-arm64 -t isle204/nas-traffic-lens:latest-arm64 --load .
docker save isle204/nas-traffic-lens:${VERSION}-arm64 isle204/nas-traffic-lens:latest-arm64 -o nas-traffic-lens-${VERSION}-arm64.tar
```

- [ ] **Step 5: Commit and push release documentation**

```bash
git add README.md doc/README.md VERSION
git commit -m "release: add Docker icons and AI settings assistant"
git push origin main
```

## Plan Self-Review

- The Docker icon requirement is covered by Tasks 1-2 and does not add external requests.
- The AI settings requirement is covered by Tasks 3-5, including generation, preview, confirmation, persistence and frontend errors.
- Sensitive data restrictions are enforced in the service policy and rechecked during apply.
- Performance constraints are covered by bounded in-memory proposals, no background AI requests and existing on-demand Docker stats.
- Every production change has a preceding failing test task and a verification command.
- No placeholder or unspecified release step remains.
