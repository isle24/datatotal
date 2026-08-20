# AI Providers and Model Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 AI 配置 422 的可诊断性并提供多厂商配置、模型发现和 Claude 原生 API 支持。

**Architecture:** Keep AI protocol and bounded model caching in `server/services/ai.py`; keep validation, persistence, and routes in `server/main.py`; keep vendor selection, model loading, and error presentation in `front-end/src/App.vue`. Existing OpenAI-compatible payloads and SQLite settings are migrated through normalization defaults.

**Tech Stack:** FastAPI, Pydantic v2, Python standard-library `urllib`, SQLite settings, Vue 3, Vite, existing test scripts.

## Global Constraints

- Never log, display, commit, or document a real API key or password.
- Keep AI requests explicit and out of collection/background loops.
- Use only HTTP/HTTPS URLs without embedded credentials.
- Bound vendor response size, model count, model ID length, and answer length.
- Preserve old settings without `provider` and preserve masked-key behavior.
- Use `apply_patch` for manual edits and keep the implementation ASCII unless existing source requires otherwise.
- Increment `VERSION` from `2026.08.19-1` for the release.

### Task 1: Add failing backend AI provider tests

**Files:**
- Modify: `server/tests/test_ai.py`
- Test: `server/tests/test_ai.py`

**Interfaces:**
- Consumes: existing `server.services.ai` functions and `AISettingsPayload`.
- Produces: executable expectations for provider normalization, model parsing, request adapters, and bounded model discovery.

- [ ] **Step 1: Add tests for provider defaults and legacy settings**

```python
def test_provider_defaults_and_legacy_settings_are_compatible():
    assert default_ai_settings()["provider"] == "openai"
    assert normalize_ai_settings({"baseUrl": "https://api.openai.com/v1"})["provider"] == "openai"
    assert normalize_ai_settings({"provider": "deepseek"})["baseUrl"] == "https://api.deepseek.com/v1"
```

- [ ] **Step 2: Add tests for model response normalization**

```python
def test_model_payload_is_bounded_and_supports_openai_and_anthropic_shapes():
    from server.services.ai import normalize_model_list

    result = normalize_model_list({"data": [{"id": "gpt-a"}, {"id": "", "name": "ignored"}]})
    assert result == [{"id": "gpt-a", "name": "gpt-a"}]
    assert normalize_model_list({"data": [{"id": "claude-a", "display_name": "Claude A"}]}) == [{"id": "claude-a", "name": "Claude A"}]
```

- [ ] **Step 3: Add tests for request protocol adapters**

```python
def test_claude_request_uses_native_headers_and_message_shape():
    from server.services.ai import build_ai_request

    request = build_ai_request(
        normalize_ai_settings({"provider": "anthropic", "apiKey": "secret", "model": "claude-test"}),
        [{"role": "system", "content": "rules"}, {"role": "user", "content": "hello"}],
    )
    assert request.full_url.endswith("/messages")
    assert request.headers["x-api-key"] == "secret"
    assert "Authorization" not in request.headers
    assert json.loads(request.data)["system"] == "rules"
```

- [ ] **Step 4: Run the new tests and confirm they fail for missing behavior**

Run: `python3 -m unittest server.tests.test_ai -v`

Expected: FAIL because provider/model adapter functions and provider defaults do not exist yet.

### Task 2: Implement bounded provider adapters and model discovery

**Files:**
- Modify: `server/services/ai.py`
- Test: `server/tests/test_ai.py`

**Interfaces:**
- Consumes: failing tests from Task 1.
- Produces: `AI_PROVIDERS`, `default_ai_settings`, `normalize_ai_settings`, `build_ai_request`, `normalize_model_list`, `list_models`, and provider-aware `chat_completion`.

- [ ] **Step 1: Add provider metadata and normalization**

Implement immutable preset metadata for the six built-ins plus `custom`, add `provider` to defaults/public settings, infer `openai` for old records, and only apply preset URL/model defaults when a provider is explicitly selected or the old setting is empty.

- [ ] **Step 2: Add protocol-specific request builders**

Use Bearer auth and `/chat/completions` for compatible providers. Use `x-api-key`, `anthropic-version: 2023-06-01`, `/messages`, `system`, and `max_tokens` for Claude. Keep URL validation and bounded body construction.

- [ ] **Step 3: Add bounded response parsers and model cache**

Parse OpenAI/Anthropic model lists into `{id, name}`, ignore malformed entries, cap at 200 items, reject oversized bodies, and cache successful/failed lookups for 60 seconds under a key containing only a SHA-256 digest of the API key. Expose `list_models(settings, refresh=False)` with safe `AIServiceError` messages.

- [ ] **Step 4: Update chat response extraction**

Support OpenAI `choices[0].message.content` and Anthropic `content[*].text`, retaining the 20,000-character answer limit.

- [ ] **Step 5: Run backend tests**

Run: `python3 -m unittest server.tests.test_ai -v`

Expected: PASS, including the original normalization and Docker context tests.

### Task 3: Add validated backend settings and model route

**Files:**
- Modify: `server/main.py`
- Modify: `server/tests/test_ai.py`

**Interfaces:**
- Consumes: provider-aware AI service from Task 2.
- Produces: `AISettingsPayload.provider`, `GET /api/ai/models`, and safe collector delegation.

- [ ] **Step 1: Add request-model tests for provider and numeric bounds**

Assert built-in provider values are accepted, invalid provider values are rejected, and the existing timeout/token bounds remain explicit.

- [ ] **Step 2: Add the provider field and route**

Use a `Literal` provider type, retain current field limits, and add an async route that runs model discovery in a worker thread. Return `{ok, configured, provider, models, cached}` on success and `{ok: false, detail, models: []}` for configuration/vendor errors without leaking credentials.

- [ ] **Step 3: Run backend compile and tests**

Run: `python3 -m py_compile server/main.py server/services/*.py && python3 -m unittest server.tests.test_ai -v`

Expected: exit 0 and all AI tests pass.

### Task 4: Update frontend AI settings and 422 diagnostics

**Files:**
- Modify: `front-end/src/App.vue`
- Modify: `front-end/tests/ui-contract.test.mjs`

**Interfaces:**
- Consumes: `GET /api/ai/models` and provider-aware settings from Task 3.
- Produces: vendor selector, preset defaults, model select/manual fallback, readable validation errors, and normalized save payload.

- [ ] **Step 1: Add failing UI contract assertions**

Assert the template contains provider selection, model discovery action, `/api/ai/models`, and field-level validation formatting.

- [ ] **Step 2: Add provider form state and preset selection**

Expose labels for OpenAI, Claude, DeepSeek, Kimi, Qwen, MiniMax, and Custom. Selecting a provider fills the matching default URL/model while leaving later manual edits intact.

- [ ] **Step 3: Add model discovery**

Call the backend route only when the user clicks “读取模型”; populate a bounded select and keep the model input for manual values. Display a short non-sensitive failure message.

- [ ] **Step 4: Normalize save values and format FastAPI errors**

Clamp timeout to `5..30`, max tokens to `128..4096`, fall back for invalid/empty numeric values, and format `detail` arrays as `字段：原因` text. Preserve empty-key behavior.

- [ ] **Step 5: Run frontend tests and build**

Run: `npm test -- --runInBand` if available, `node front-end/tests/ui-contract.test.mjs`, and `npm run build` from `front-end`.

Expected: UI contract and build pass.

### Task 5: Documentation, version, full verification, and release

**Files:**
- Modify: `README.md`
- Modify: `doc/README.md`
- Modify: `VERSION`
- Test: existing server/frontend/Go/deployment tests

**Interfaces:**
- Consumes: completed provider/model behavior from Tasks 2-4.
- Produces: user-facing setup instructions and release artifact version.

- [ ] **Step 1: Document provider presets and model discovery**

Explain Claude API key requirements, compatible Base URL overrides, `/api/ai/models`, manual fallback, and that no real credentials belong in compose or documentation.

- [ ] **Step 2: Increment version**

Set `VERSION` to `2026.08.20-1`.

- [ ] **Step 3: Run full verification**

Run: `python3 -m py_compile server/main.py server/services/*.py`, `python3 -m unittest discover -s server/tests -v`, `node front-end/tests/ui-contract.test.mjs`, `npm run build` from `front-end`, `docker compose -f docker-compose.yml config`, and `git diff --check`.

Expected: all commands exit 0; report any unavailable optional Docker/image checks explicitly.

- [ ] **Step 4: Commit and push**

```bash
git add server front-end README.md doc VERSION docs/superpowers
git commit -m "feat: add AI providers and model discovery"
git push origin main
```
