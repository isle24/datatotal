import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../src/App.vue", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");

test("dashboard UI exposes the refreshed screen contracts", () => {
  assert.match(source, /class="dashboard-board"/);
  assert.match(source, /实时监控台/);
  assert.match(source, /dockerStateIcon/);
  assert.match(source, /expandedMonitorCards/);
  assert.match(source, /expandedDockerCards/);
  assert.match(source, /class="collapse-toggle"/);
  assert.match(source, /v-if="isMonitorCardExpanded\('traffic'/);
  assert.match(source, /v-if="isMonitorCardExpanded\('container'/);
  assert.match(source, /v-if="isMonitorCardExpanded\('channel'/);
  assert.match(source, /key: "monitor", label: "监控中心"/);
  assert.match(source, /key: "settings", label: "设置"/);
  assert.match(source, /key: "ai", label: "AI 中心"/);
  assert.match(source, /\/api\/ai\/analyze/);
  assert.match(source, /\/api\/ai\/chat/);
  assert.match(source, /async function refreshAiSettings\(\)/);
  assert.match(source, /if \(activeView\.value === "settings"\) refreshDockerContainerOptions\(\)/);
  assert.match(source, /if \(activeView\.value === "ai"\) refreshAiSettings\(\)/);
  assert.match(source, /setView\("ai"\)/);
  assert.match(source, /manualOnly/);
  assert.match(source, /function dockerNetworkLabel/);
  assert.match(styles, /\.dashboard-board/);
  assert.match(styles, /\.accordion-stack/);
  assert.match(styles, /\.docker-card-trigger/);
});
