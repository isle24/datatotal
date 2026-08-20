# Alert Evidence, Units, and AI Markdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make upload thresholds understandable in MB/GB, preserve actionable evidence when rules trigger, support date-based historical investigation through the UI and AI, and render AI Markdown with ergonomic Enter-to-send behavior.

**Architecture:** Keep bytes as the canonical storage and calculation unit for backward compatibility. Add a bounded SQLite alert-evidence table and persisted alert queries; evidence is generated from minute traffic/process aggregates and current connection/container summaries at trigger time. Expose only bounded, structured diagnostic data to the AI context. Use the existing Vue UI and a small safe Markdown renderer without introducing a runtime dependency.

**Tech Stack:** FastAPI/Pydantic, SQLite, Vue 3/Vite, ECharts, Python standard library, existing notification adapters.

## Global Constraints

- Existing byte-valued SQLite rules remain valid; `53687091200` continues to mean 50 GiB.
- UI units are decimal labels (`MB`, `GB`, `MB/s`, `GB/s`) with binary-compatible conversion constants matching existing byte display behavior.
- AI receives bounded aggregates only; it cannot execute SQL, arbitrary commands, or access API keys.
- Alert evidence is capped per alert and old evidence follows the existing history retention policy.
- `Enter` sends AI messages; `Shift+Enter` inserts a newline.
- All changes require focused tests before production implementation and full regression verification before commit.

### Task 1: Canonical threshold units

**Files:**
- Modify: `server/main.py`
- Modify: `front-end/src/App.vue`
- Test: `server/tests/test_deployment_config.py`
- Test: `front-end/tests/ui-contract.test.mjs`

**Interfaces:**
- Backend continues to accept canonical `threshold` bytes.
- Frontend adds display-only `thresholdValue` and `thresholdUnit` fields and converts them to bytes in `saveRules()`.

- [x] Add tests for 50 GiB conversion, MB/GB formatting, and rule save payload conversion.
- [x] Run focused tests and observe failure against the raw-byte-only UI.
- [x] Add unit helpers and a daily upload threshold control with MB/GB selection; preserve raw values when loading old rules.
- [x] Add optional human-readable environment defaults while retaining old byte variables.
- [x] Run focused tests and verify they pass.

### Task 2: Persist alert evidence and notification outcomes

**Files:**
- Modify: `server/main.py`
- Modify: `server/services/notifications.py`
- Test: `server/tests/test_deployment_config.py`
- Test: `server/tests/test_go_snapshot_merge.py`

**Interfaces:**
- `TrafficDB.add_alert_evidence(alert_id, evidence)` stores bounded JSON evidence.
- `TrafficDB.query_alerts(start, end, limit)` returns alerts with evidence and notification status.
- `record_alert()` creates evidence for daily and sustained upload triggers.

- [x] Add failing tests for evidence persistence, retention, and notification result capture.
- [x] Run focused tests and observe failure.
- [x] Create/migrate the evidence schema, collect process/interface/connection/container summaries, and persist a readable reason.
- [x] Make notification dispatch return a bounded result and persist per-channel success/failure without logging secrets.
- [x] Add alert list/detail API routes and clear-alert cleanup.
- [x] Run focused tests and verify they pass.

### Task 3: Historical upload investigation and AI context

**Files:**
- Modify: `server/main.py`
- Modify: `front-end/src/App.vue`
- Test: `server/tests/test_ai.py`
- Test: `front-end/tests/ui-contract.test.mjs`

**Interfaces:**
- `GET /api/diagnostics/upload?date=YYYY-MM-DD` returns bounded daily WAN totals, top processes, interfaces, and related alerts.
- AI context includes recent alert evidence and a date-specific diagnostic block when the user asks about a date.

- [x] Add failing tests for date parsing, daily process aggregation, and AI context inclusion.
- [x] Run focused tests and observe failure.
- [x] Implement bounded diagnostics using existing `minute_stats` and `process_minute_stats` queries; do not expose raw SQL or unbounded rows.
- [x] Add a monitor/history investigation view that can show the date, totals, top process evidence, and alert delivery outcome.
- [x] Run focused tests and verify they pass.

### Task 4: Markdown AI rendering and keyboard interaction

**Files:**
- Modify: `front-end/src/App.vue`
- Modify: `front-end/src/styles.css`
- Test: `front-end/tests/ui-contract.test.mjs`

**Interfaces:**
- `renderMarkdown(text)` returns sanitized HTML for headings, paragraphs, emphasis, lists, code, blockquotes, and links.
- AI composer handles `keydown`: Enter sends, Shift+Enter preserves a newline.

- [x] Add UI contract tests for Markdown rendering, escaping, `v-html`, and Enter/Shift+Enter handling.
- [x] Run focused tests and observe failure.
- [x] Implement a bounded Markdown renderer with HTML escaping and safe link protocol filtering; render assistant messages only.
- [x] Add keyboard behavior and polished Markdown styles without changing mobile layout.
- [x] Run focused tests and verify they pass.

### Task 5: Documentation, version, and full verification

**Files:**
- Modify: `README.md`
- Modify: `doc/README.md`
- Modify: `VERSION`

- [x] Document canonical units, old variable compatibility, evidence retention, date diagnostics, AI data boundaries, and notification result interpretation.
- [x] Increment `VERSION` to `2026.08.20-4`.
- [x] Run the complete Python, Go, frontend, build, compose, compile, and diff checks.
- [ ] Commit and push GitHub.
- [ ] Build amd64 and arm64 images and report Docker Hub status accurately.
