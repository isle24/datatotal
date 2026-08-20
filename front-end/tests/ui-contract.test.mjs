import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { renderMarkdown, safeMarkdownUrl } from "../src/utils/markdown.js";

const source = await readFile(new URL("../src/App.vue", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
const markdownSource = await readFile(new URL("../src/utils/markdown.js", import.meta.url), "utf8");

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
  assert.match(source, /\/api\/ai\/models/);
  assert.match(source, /stream=true/);
  assert.match(source, /async function streamApi/);
  assert.match(source, /response\.body\.getReader\(\)/);
  assert.match(source, /providerPresets/);
  assert.match(source, /读取模型/);
  assert.match(source, /formatValidationError/);
  assert.match(source, /timeoutSeconds: clampNumber/);
  assert.match(source, /async function refreshAiSettings\(\)/);
  assert.match(source, /393216/);
  assert.match(source, /event\.truncated/);
  assert.match(source, /\/api\/ai\/history/);
  assert.match(source, /清空记录/);
  assert.match(source, /if \(activeView\.value === "settings"\) refreshDockerContainerOptions\(\)/);
  assert.match(source, /if \(activeView\.value === "ai"\) refreshAiSettings\(\)/);
  assert.match(source, /setView\("ai"\)/);
  assert.match(source, /manualOnly/);
  assert.match(source, /function dockerNetworkLabel/);
  assert.match(styles, /\.dashboard-board/);
  assert.match(styles, /\.accordion-stack/);
  assert.match(styles, /\.docker-card-trigger/);
});

test("monitor thresholds use readable transfer units and expose upload evidence", () => {
  assert.match(source, /thresholdUnitOptions/);
  assert.match(source, /thresholdValue/);
  assert.match(source, /thresholdUnit/);
  assert.match(source, /thresholdToBytes/);
  assert.match(source, /formatMonitorThreshold/);
  assert.match(source, /\/api\/alerts/);
  assert.match(source, /\/api\/diagnostics\/upload/);
  assert.match(source, /上传异常记录/);
  assert.match(source, /通知投递/);
});

test("AI assistant renders sanitized Markdown and supports Enter to send", () => {
  assert.match(markdownSource, /function renderMarkdown/);
  assert.match(markdownSource, /function escapeHtml/);
  assert.match(markdownSource, /safeMarkdownUrl/);
  assert.match(source, /v-html="renderMarkdown\(message\.content\)"/);
  assert.match(source, /message\.streaming/);
  assert.match(source, /@keydown="handleAiComposerKeydown"/);
  assert.match(source, /if \(event\.key !== "Enter" \|\| event\.shiftKey/);
  assert.match(styles, /\.ai-markdown/);
  assert.match(styles, /\.ai-markdown pre/);
});

test("AI settings assistant exposes preview and confirmation controls", () => {
  assert.match(source, /aiMode/);
  assert.match(source, /设置助手/);
  assert.match(source, /\/api\/ai\/configure/);
  assert.match(source, /\/api\/ai\/configure\/apply/);
  assert.match(source, /确认应用/);
  assert.match(source, /取消变更/);
  assert.match(source, /iconSource/);
});

test("Markdown renderer escapes HTML and blocks unsafe link protocols", () => {
  const html = renderMarkdown("# Result\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n- **safe**\n\n```sh\necho ok\n```");
  assert.match(html, /<h1>Result<\/h1>/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /href="javascript:/);
  assert.match(html, /href="#"/);
  assert.match(html, /<ul><li><strong>safe<\/strong><\/li><\/ul>/);
  assert.match(html, /<pre><code class="language-sh">echo ok<\/code><\/pre>/);
  assert.equal(safeMarkdownUrl("data:text/html,bad"), "#");
  assert.equal(safeMarkdownUrl("https://example.com"), "https://example.com");
});
