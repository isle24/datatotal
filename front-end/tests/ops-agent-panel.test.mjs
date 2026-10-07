import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../src/App.vue", import.meta.url), "utf8");
const theme = await readFile(new URL("../src/styles/console-theme.css", import.meta.url), "utf8");

test("the AI center exposes a read-only operations agent panel", () => {
  assert.match(source, /const agentQuestion = ref\(""\)/);
  assert.match(source, /const agentUsage = ref\(null\)/);
  assert.match(source, /async function refreshAgentTools\(\)/);
  assert.match(source, /async function askAgent\(question\)/);
  assert.match(source, /function agentToolLabel\(tool\)/);
  assert.match(source, /await api\("\/api\/agent\/tools", \{ localError: true \}\)/);
  assert.match(source, /await api\("\/api\/agent\/query", \{/);
  assert.match(source, /class="card agent-panel"/);
  assert.match(source, /class="agent-ask"/);
  assert.match(source, /v-for="question in agentSuggestions"/);
  assert.match(source, /class="agent-answer-card"/);
  assert.match(source, /查看原始数据/);
  assert.match(source, /只读工具不会修改任何配置或容器/);
  // The panel loads its catalogue and usage together with the AI settings.
  assert.match(source, /if \(activeView\.value === "ai"\) \{\n    await refreshAiSettings\(\);\n    await refreshAgentTools\(\);/);
  // Questions are bounded before they leave the browser.
  assert.match(source, /maxlength="500"/);
  assert.match(theme, /\.app-shell \.agent-ask \{/);
  assert.match(theme, /\.app-shell \.agent-answer-card \{/);
  assert.match(theme, /\.app-shell \.agent-chips button:hover:not\(:disabled\)/);
});
