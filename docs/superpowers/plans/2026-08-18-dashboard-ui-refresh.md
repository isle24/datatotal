# Dashboard UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the Vue frontend into a concise responsive dashboard with icon-led Docker states and collapsed editable monitoring cards.

**Architecture:** Keep the existing Vue 3 single-page controller and API/timer behavior. Add presentation-only state for collapsed cards, small computed labels, and CSS layout tokens; do not add a UI framework or background polling.

**Tech Stack:** Vue 3, Vite, Lucide Vue, ECharts, CSS custom properties.

## Global Constraints

- Preserve all existing API paths and request lifecycles.
- Keep Docker stats lazy and page-scoped.
- Do not expose or change authentication/configuration behavior.
- Keep light/dark mode and use icons from `@lucide/vue`.
- Verify the frontend build and existing backend tests before completion.

### Task 1: Add UI contract checks

**Files:**
- Create: `front-end/tests/ui-contract.test.mjs`

- [ ] **Step 1: Write the failing contract test**

Check that the Vue template contains the dashboard heading, icon-based Docker state renderer, and collapsed-card state bindings. The test should fail against the current template because those markers do not exist yet.

```js
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../src/App.vue", import.meta.url), "utf8");

test("dashboard UI exposes the refreshed card contracts", () => {
  assert.match(source, /class="dashboard-hero"/);
  assert.match(source, /dockerStateIcon/);
  assert.match(source, /expandedMonitorCards/);
});
```

- [ ] **Step 2: Run the test and confirm the expected failure**

Run: `node --test front-end/tests/ui-contract.test.mjs`

Expected: FAIL because the new dashboard and collapsed-card markers are not present.

### Task 2: Implement dashboard hierarchy and icon-led Docker states

**Files:**
- Modify: `front-end/src/App.vue`
- Modify: `front-end/src/styles.css`

- [ ] **Step 1: Add dashboard summary markup and collector freshness state**

Add a dashboard hero/status row on the overview page. Reuse `summary`, `connectionSummary`, and `stageSummary`; track the latest overview request separately from the payload so a failed poll renders a delayed state. Keep historical curves on the dedicated history page and do not create a new polling endpoint.

- [ ] **Step 2: Add localized Docker state helpers and icons**

Add `dockerStateMeta(state)` and render the returned Lucide component, label, and state class in each Docker card. Keep the raw state available as a tooltip/title.

- [ ] **Step 3: Add the CSS layout and responsive rules**

Define dashboard hero, summary rail, card headers, state badges, and narrow-screen rules. Keep border radii at 8px or below and use existing color variables.

- [ ] **Step 4: Run the contract test and build**

Run: `node --test front-end/tests/ui-contract.test.mjs && npm run build` from `front-end`.

Expected: PASS and a successful Vite build.

### Task 3: Collapse monitoring center cards

**Files:**
- Modify: `front-end/src/App.vue`
- Modify: `front-end/src/styles.css`
- Modify: `front-end/tests/ui-contract.test.mjs`

- [ ] **Step 1: Add failing assertions for collapsed editing regions**

Assert that rules and channels use `expandedMonitorCards` and expose an expand button with an accessible label.

- [ ] **Step 2: Add expansion state and compact card summaries**

Initialize all existing cards collapsed. New rules/channels/protection rules are added to the expansion set. Keep card summaries visible without mounting the form grid.

- [ ] **Step 3: Move existing fields behind expansion guards**

Wrap the existing rule, container protection, and notification form fields in `v-if` blocks. Preserve all existing `v-model`, save, delete, test, channel multi-select, and condition handlers.

- [ ] **Step 4: Add responsive card CSS and verify**

Run: `node --test front-end/tests/ui-contract.test.mjs && npm run build && git diff --check`.

Expected: PASS, successful build, and no whitespace errors.

### Task 4: Version, package, and verify

**Files:**
- Modify: `VERSION`
- Modify: `README.md` only if the UI navigation screenshots/claims need adjustment

- [ ] **Step 1: Bump the application version to `2026.08.18-1`**

- [ ] **Step 2: Run the full verification set**

```bash
python3 -m py_compile server/main.py server/services/notifications.py server/tests/test_deployment_config.py
python3 server/tests/test_go_snapshot_merge.py
python3 server/tests/test_deployment_config.py
node --test front-end/tests/ui-contract.test.mjs
npm run build
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.nas.yml config --quiet
git diff --check
```

- [ ] **Step 3: Build local `linux/amd64` and `linux/arm64` images without pushing**

Use the repository's existing Docker build workflow and tag both the version and architecture-specific latest tags. Confirm the embedded version after each build.

- [ ] **Step 4: Commit and push the changes to GitHub**

```bash
git add front-end/src/App.vue front-end/src/styles.css front-end/tests/ui-contract.test.mjs VERSION docs/superpowers/specs/2026-08-18-dashboard-ui-design.md docs/superpowers/plans/2026-08-18-dashboard-ui-refresh.md
git commit -m "feat: refresh dashboard card ui"
git push origin main
```
