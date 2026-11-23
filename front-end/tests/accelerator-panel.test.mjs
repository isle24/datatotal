import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// Git may check files out with CRLF on Windows; contracts are written against LF.
const readSource = async (url) => (await readFile(url, "utf8")).replace(/\r\n/g, "\n");

const source = await readSource(new URL("../src/App.vue", import.meta.url));
const theme = await readSource(new URL("../src/styles/console-theme.css", import.meta.url));
const desktop = await readSource(new URL("../src/desktop/desktop.css", import.meta.url));
const base = await readSource(new URL("../src/styles.css", import.meta.url));

test("system page shows GPU and NPU utilization from the accelerator API", () => {
  assert.match(source, /const acceleratorCards = computed/);
  assert.match(source, /function acceleratorPercent/);
  assert.match(source, /function acceleratorStatus/);
  assert.match(source, /function percentBarWidth/);
  assert.match(source, /<CardHead :title="acceleratorSectionTitle"/);
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

test("the console and desktop share the light and dark theme tokens", () => {
  assert.match(base, /--accent: #0071e3;/);
  assert.match(base, /--accent-soft: #e5f0fd;/);
  assert.match(base, /--bg: #f5f5f7;/);
  assert.match(base, /:root\[data-theme="dark"\][^}]*--bg: #07080b;/s);
  assert.match(base, /:root\[data-theme="dark"\][^}]*--panel: #111319;/s);
  // Normal temperature chips and bars follow the accent; warning and critical keep theirs.
  assert.match(theme, /\.temp-value:not\(\.warning\):not\(\.critical\) \{ background: color-mix\(in srgb, var\(--accent\) 12%/);
  assert.match(theme, /\.temp-reading-bar i\.warning \{ background: var\(--orange\); \}/);
  assert.match(theme, /\.temp-reading-bar i\.critical \{ background: var\(--red\); \}/);
  assert.match(theme, /\.fan-speed-bar i \{ background: var\(--accent\); \}/);
  assert.match(desktop, /--ds-accent: var\(--accent\);/);
});

test("VPU cores are surfaced alongside the GPU and NPU cards", () => {
  assert.match(source, /const vpus = \(system\.value\?\.vpu \|\| \[\]\)\.map/);
  assert.match(source, /return \[\.\.\.gpus, \.\.\.npus, \.\.\.vpus\];/);
  assert.match(source, /function vpuRoleLabel\(role\)/);
  assert.match(source, /function acceleratorIcon\(item\)/);
  assert.match(source, /<template v-if="item\.kind === 'vpu'">/);
  assert.match(source, /v-for="core in item\.cores"/);
  assert.match(source, /解码峰值/);
  assert.match(source, /编码峰值/);
  assert.match(source, /活跃核心/);
  // devfreq backed GPU/NPU also expose the raw governor load.
  assert.match(source, /驱动负载/);
  assert.match(source, /item\.loadRaw/);
});

test("the accelerator section title follows the devices that are present", () => {
  assert.match(source, /const acceleratorSectionTitle = computed/);
  assert.match(source, /<CardHead :title="acceleratorSectionTitle"/);
  assert.match(source, /\["gpu", "npu", "vpu"\]\.filter\(\(kind\) => kinds\.has\(kind\)\)/);
});
