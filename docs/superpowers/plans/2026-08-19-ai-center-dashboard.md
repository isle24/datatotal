# AI Center And Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the card-based dashboard, separated settings/monitoring pages, and safe on-demand AI analysis already integrated in NAS Traffic Lens.

**Architecture:** Keep Vue/Vite as a static frontend served by FastAPI. Store AI settings with the existing SQLite settings API, use a focused OpenAI-compatible client in `server/services/ai.py`, and build a bounded AI context from existing aggregate endpoints and caches. Docker metadata remains lazy and the AI context uses summary fields instead of container detail calls.

**Tech Stack:** Vue 3, Vite, ECharts, FastAPI, Pydantic, Python `urllib`, SQLite, Docker Buildx.

## Global Constraints

- Release version is `2026.08.19-1`.
- Recommended compose keeps only `APP_PORT` and `DASHBOARD_PASSWORD` in `environment`.
- Documentation examples use password `123456` only.
- No `/proc` volume mapping is required.
- Docker images are built for `linux/amd64` and `linux/arm64` without Docker Hub push.
- AI requests are user-triggered only and do not run in the collector loop.

---

### Task 1: Add The AI Service Boundary

**Files:**
- Create: `server/services/ai.py`
- Test: `server/tests/test_ai.py`

**Interfaces:**
- `default_ai_settings() -> dict`
- `normalize_ai_settings(payload: Optional[dict], existing: Optional[dict] = None) -> dict`
- `public_ai_settings(settings: Optional[dict]) -> dict`
- `chat_completion(settings: dict, messages: List[Dict[str, str]]) -> dict`

- [x] **Step 1: Define bounded defaults and normalization.** Accept only HTTP/HTTPS Base URLs, clamp timeout and max tokens, cap model/prompt/API Key lengths, and retain an existing Key when the submitted value is empty or masked.
- [x] **Step 2: Define public serialization.** Return configuration without the raw API Key and expose only `keyConfigured` and `apiKeyMasked`.
- [x] **Step 3: Define the OpenAI-compatible request.** Post JSON to `/chat/completions`, use the configured timeout, cap the response body at 2 MiB, cap extracted answer length, and convert network/HTTP/JSON failures to `AIServiceError`.
- [x] **Step 4: Test normalization and masking.** Run `python3 server/tests/test_ai.py`; expected output is `ai tests passed`.

### Task 2: Persist Settings And Add AI Endpoints

**Files:**
- Modify: `server/main.py`
- Modify: `server/services/ai.py`
- Test: `server/tests/test_ai.py`

**Interfaces:**
- `GET /api/settings/ai`
- `POST /api/settings/ai`
- `POST /api/ai/analyze`
- `POST /api/ai/chat`
- `TrafficCollector.ai_context(scope: str) -> dict`

- [x] **Step 1: Add Pydantic request models.** Validate AI settings, analysis scope/question, and a maximum of 20 chat messages with maximum message length.
- [x] **Step 2: Load and seed SQLite settings.** Normalize the `ai_settings` setting during startup and write defaults only when the setting does not exist.
- [x] **Step 3: Build bounded context.** Include aggregate overview/history, process top ten, no more than 50 Docker summaries, system status, rules, and 20 recent alerts. Use `portCount` from Docker summaries and fall back to a local port list only for compatibility.
- [x] **Step 4: Keep incomplete collector instances safe.** Use defaults when `ai_settings` is absent in `get_settings()` and preserve existing runtime/test initialization behavior.
- [x] **Step 5: Run backend checks.** Run `python3 server/tests/test_ai.py`, `python3 server/tests/test_deployment_config.py`, `python3 server/tests/test_go_snapshot_merge.py`, and `python3 -m py_compile server/main.py server/services/*.py`.

### Task 3: Build The Dashboard And Settings UX

**Files:**
- Modify: `front-end/src/App.vue`
- Modify: `front-end/src/styles.css`
- Test: `front-end/tests/ui-contract.test.mjs`

**Interfaces:**
- Navigation keys: `monitor`, `settings`, `ai`
- Lazy Docker detail/stats requests remain `/api/docker/containers/{id}` and `/stats`.

- [x] **Step 1: Add the dashboard board.** Show current WAN rate, colored RX/TX bars, cumulative WAN totals, WAN connection count, active interfaces, capture interfaces, refresh health, and an AI action.
- [x] **Step 2: Split monitoring from editing.** Render read-only accordion status cards in monitoring and move runtime, AI, rule, protection, and channel forms to settings.
- [x] **Step 3: Add the AI center.** Render configuration status, chat messages, loading/error states, and a bounded composer that calls the two backend AI endpoints.
- [x] **Step 4: Refresh card styling.** Add dark/light themes, responsive grids, vertical accordion stacks, icon states, mobile-safe controls, and no nested decorative card layout.
- [x] **Step 5: Keep Docker lazy.** Fetch a summary list first, fetch a single container detail on expansion, fetch stats only on demand, and stop the timer whenever the Docker view is hidden.
- [x] **Step 6: Run frontend checks.** Run `npm run build` and `node --test front-end/tests/ui-contract.test.mjs`.

### Task 4: Documentation And Release Packaging

**Files:**
- Modify: `README.md`
- Modify: `doc/README.md`
- Modify: `VERSION`
- Create: `docs/superpowers/specs/2026-08-19-ai-center-dashboard-design.md`
- Create: `docs/superpowers/plans/2026-08-19-ai-center-dashboard.md`

- [x] **Step 1: Align documentation with the UI.** Explain that settings are edited in “设置”, monitoring is status-only, and AI is configured in the AI settings card.
- [x] **Step 2: Document AI privacy and operation.** State that requests are on-demand, context is bounded/aggregated, the API Key is masked, and `/data` is sensitive.
- [x] **Step 3: Update release version.** Set `VERSION` to `2026.08.19-1`; keep compose tags on `latest` and document fixed-version tags for rollback.
- [x] **Step 4: Check documentation safety.** Search docs for real credentials, `/proc` volume mappings, stale “monitor center edits configuration” wording, and accidental raw API keys.

### Task 5: Verify And Build Local Images

**Files:**
- Modify: generated `front-end/dist/` during build only
- Modify: `nas-traffic-lens-amd64.tar`
- Modify: `nas-traffic-lens-arm64.tar`

- [x] **Step 1: Run source and frontend checks.** Use the commands from Tasks 2 and 3 plus `git diff --check`.
- [x] **Step 2: Build amd64 locally.** Run `docker buildx build --platform linux/amd64 -t isle204/nas-traffic-lens:2026.08.19-1-amd64 -t isle204/nas-traffic-lens:amd64 -t isle204/nas-traffic-lens:latest --load .` and export `nas-traffic-lens-amd64.tar`.
- [x] **Step 3: Build arm64 locally.** Run the equivalent `linux/arm64` build with `2026.08.19-1-arm64`, `arm64`, and `latest-arm64` tags, then export `nas-traffic-lens-arm64.tar`.
- [x] **Step 4: Verify image metadata.** Inspect `docker image inspect` for both architecture tags and verify tar files exist and contain the expected fixed-version and architecture tags.
- [x] **Step 5: Commit and push GitHub only.** Commit source, docs, tests, and build metadata to `main`, then push the branch. Docker Hub remains unpushed.
