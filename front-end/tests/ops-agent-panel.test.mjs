import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// Git may check files out with CRLF on Windows; contracts are written against LF.
const readSource = async (url) => (await readFile(url, "utf8")).replace(/\r\n/g, "\n");

const source = await readSource(new URL("../src/App.vue", import.meta.url));
const theme = await readSource(new URL("../src/styles/console-theme.css", import.meta.url));

test("the AI center exposes a read-only operations agent panel", () => {
  assert.match(source, /const agentQuestion = ref\(""\)/);
  assert.match(source, /const agentUsage = ref\(null\)/);
  assert.match(source, /async function refreshAgentTools\(\)/);
  assert.match(source, /async function askAgent\(question\)/);
  assert.match(source, /function agentToolLabel\(tool\)/);
  assert.match(source, /await api\("\/api\/agent\/tools", \{ localError: true \}\)/);
  assert.match(source, /await api\("\/api\/agent\/query", \{/);
  // The agent lives in a tab next to the chat and the configuration assistant.
  assert.match(source, /<button type="button" :class="\{ active: aiMode === 'agent' \}" @click="aiMode = 'agent'"/);
  assert.match(source, /<div v-if="aiMode === 'agent'" class="agent-body">/);
  assert.doesNotMatch(source, /class="card agent-panel"/);
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

test("the agent shows a staged thinking indicator while it waits", () => {
  assert.match(source, /const AGENT_STAGES = \["正在理解问题", "正在调用只读工具", "正在整理结论"\]/);
  assert.match(source, /const agentThinkingStage = ref\(0\)/);
  assert.match(source, /function startAgentThinking\(\)/);
  assert.match(source, /function stopAgentThinking\(options = \{\}\)/);
  assert.match(source, /function resetAgent\(\)/);
  assert.match(source, /startAgentThinking\(\);/);
  assert.match(source, /stopAgentThinking\(\);/);
  assert.match(source, /class="agent-thinking" role="status" aria-live="polite"/);
  assert.match(source, /v-for="\(stage, index\) in AGENT_STAGES"/);
  assert.match(source, /已用 \{\{ agentThinkingElapsed\.toFixed\(1\) \}\} 秒/);
  // Only visible while a query is running, so the finished answer is not covered.
  assert.match(source, /<div v-if="agentLoading" class="agent-thinking"/);
  assert.match(theme, /\.app-shell \.agent-thinking \{/);
  assert.match(theme, /@keyframes agent-dot/);
  assert.match(theme, /\.agent-thinking-steps li\.active/);
  // The three AI modes share one tab strip.
  assert.match(source, /const aiMode = ref\('agent'\);/);
  assert.match(source, /const aiModeTitle = computed/);
  assert.match(source, /aiMode === 'analysis' \}" @click="aiMode = 'analysis'"/);
  assert.match(source, /aiMode === 'configure' \}" @click="aiMode = 'configure'"/);
});

test("each AI tab renders exactly its own body", () => {
  // The configuration assistant must not leak into the other tabs.
  assert.match(source, /<div v-else-if="aiMode === 'configure'" class="ai-configure-panel">/);
  assert.doesNotMatch(source, /<div v-else class="ai-configure-panel">/);
});
