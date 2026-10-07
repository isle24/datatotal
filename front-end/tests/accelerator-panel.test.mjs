import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../src/App.vue", import.meta.url), "utf8");
const theme = await readFile(new URL("../src/styles/console-theme.css", import.meta.url), "utf8");
const desktop = await readFile(new URL("../src/desktop/desktop.css", import.meta.url), "utf8");

test("system page shows GPU and NPU utilization from the accelerator API", () => {
  assert.match(source, /const acceleratorCards = computed/);
  assert.match(source, /function acceleratorPercent/);
  assert.match(source, /function acceleratorStatus/);
  assert.match(source, /function percentBarWidth/);
  assert.match(source, /title="GPU 与 NPU"/);
  assert.match(source, /v-for="item in acceleratorCards"/);
  assert.match(source, /isSystemCardExpanded\('accel'/);
  assert.match(source, /toggleSystemCard\('accel'/);
  assert.match(source, /engine\.busyPercent/);
  assert.match(source, /item\.idleResidencyPercent/);
  assert.match(source, /item\.memoryBytes/);
  assert.match(source, /item\.busyTimeUs/);
  // A device without counters must explain why instead of claiming a percentage.
  assert.match(source, /item\.hint/);
  assert.match(theme, /\.accel-badge\.busy/);
  assert.match(theme, /\.system-card-note/);
});

test("console palette leads with light blue and keeps green for status only", () => {
  assert.match(theme, /--accent: #2578b8;/);
  assert.match(theme, /--accent-soft: #e6f1fa;/);
  assert.match(theme, /--accent: #7db8e8;/);
  assert.doesNotMatch(theme, /--accent: #176a58/);
  assert.doesNotMatch(theme, /--accent: #8ecbb3/);
  // Neutral surfaces are cool grey instead of green tinted.
  assert.match(theme, /--bg: #f3f5f8;/);
  assert.match(theme, /--line: #d9e0e9;/);
  assert.doesNotMatch(theme, /--line: #d7ded8/);
  // Normal temperature chips and bars follow the accent; warning and critical keep theirs.
  assert.match(theme, /\.temp-value:not\(\.warning\):not\(\.critical\) \{ background: color-mix\(in srgb, var\(--accent\) 12%/);
  assert.match(theme, /\.temp-reading-bar i\.warning \{ background: var\(--orange\); \}/);
  assert.match(theme, /\.temp-reading-bar i\.critical \{ background: var\(--red\); \}/);
  assert.match(theme, /\.fan-speed-bar i \{ background: var\(--accent\); \}/);
  assert.match(desktop, /--ds-accent: #2578b8;/);
  assert.match(desktop, /--ds-accent: #7db8e8;/);
  assert.doesNotMatch(desktop, /--ds-accent: #0b8068/);
});
