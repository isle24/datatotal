import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../src/App.vue", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");

test("dashboard UI exposes the refreshed card contracts", () => {
  assert.match(source, /class="dashboard-hero card"/);
  assert.match(source, /dockerStateIcon/);
  assert.match(source, /expandedMonitorCards/);
  assert.match(source, /class="collapse-toggle"/);
  assert.match(source, /v-if="isMonitorCardExpanded\('traffic'/);
  assert.match(source, /v-if="isMonitorCardExpanded\('container'/);
  assert.match(source, /v-if="isMonitorCardExpanded\('channel'/);
  assert.match(source, /const overviewFresh = ref\(false\)/);
  assert.match(source, /manualOnly/);
  assert.match(source, /function dockerNetworkLabel/);
  assert.match(styles, /grid-template-columns: minmax\(0, 1fr\)/);
});
