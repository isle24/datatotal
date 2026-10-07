import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../src/App.vue", import.meta.url), "utf8");
const base = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
const theme = await readFile(new URL("../src/styles/console-theme.css", import.meta.url), "utf8");
const indexHtml = await readFile(new URL("../index.html", import.meta.url), "utf8");

test("typography uses a self-hosted display face with tabular figures", async () => {
  // The NAS can be offline, so the font ships with the bundle instead of a CDN.
  assert.match(base, /@font-face \{\n  font-family: "Geist";/);
  assert.match(base, /url\("\.\/assets\/fonts\/geist-latin\.woff2"\) format\("woff2-variations"\)/);
  assert.match(base, /font-display: swap;/);
  assert.match(base, /--font-sans: "Geist", -apple-system/);
  assert.match(base, /font-family: var\(--font-sans\);/);
  const font = await stat(new URL("../src/assets/fonts/geist-latin.woff2", import.meta.url));
  assert.ok(font.size > 10_000, "the bundled font must be a real file");
  // Data-heavy UI: numbers must not jump around while refreshing.
  assert.match(theme, /font-variant-numeric: tabular-nums;/);
  assert.match(theme, /letter-spacing: -\.015em;/);
  assert.match(theme, /text-wrap: balance;/);
});

test("surfaces get one light direction, grain and a width limit", () => {
  assert.match(theme, /\.app-shell::before \{\n  content: "";\n  position: fixed;/);
  assert.match(theme, /radial-gradient\(120% 60% at 50% -10%/);
  assert.match(theme, /\.app-shell::after \{\n  content: "";\n  position: fixed;/);
  assert.match(theme, /feTurbulence type='fractalNoise'/);
  assert.match(theme, /> \.main > :is\(\.topbar, \.view\) \{\n  width: 100%;\n  max-width: 1480px;/);
  assert.match(base, /--radius-xl: 18px;/);
  assert.match(base, /--radius-sm: 7px;/);
});

test("interactive controls have press feedback, focus rings and smooth scrolling", () => {
  assert.match(theme, /:root \.app-shell :is\(button, \[role="button"\]\):not\(:disabled\):active \{\n  transform: translateY\(1px\) scale\(\.994\);/);
  assert.match(theme, /:root \.app-shell :focus-visible \{\n  outline: 2px solid/);
  assert.match(theme, /\.skip-link \{/);
  assert.match(theme, /\.skip-link:focus \{ transform: translate\(-50%, 0\); \}/);
  assert.match(base, /html \{ scroll-behavior: smooth; \}/);
  assert.match(base, /@media \(prefers-reduced-motion: reduce\) \{ html \{ scroll-behavior: auto; \} \}/);
});

test("loading and empty states are designed, not bare text", () => {
  assert.match(theme, /\.app-shell \.skeleton \{/);
  assert.match(theme, /@keyframes skeleton-shimmer/);
  assert.match(theme, /\.skeleton-service \{ min-height: 68px; \}/);
  assert.match(source, /class="skeleton skeleton-service"/);
  assert.match(theme, /\.app-shell \.empty \{\n  display: grid;\n  justify-items: center;/);
  assert.match(theme, /\.app-shell \.empty::before \{/);
});

test("document head carries the branding the audit asks for", () => {
  assert.match(indexHtml, /<html lang="zh-CN">/);
  assert.match(indexHtml, /<meta name="description" content="[^"]{40,}" \/>/);
  assert.match(indexHtml, /<meta name="theme-color" content="#f4f6f8"/);
  assert.match(indexHtml, /<link\n      rel="icon"\n      href="data:image\/svg\+xml,/);
  assert.match(source, /<a v-if="!native" class="skip-link" href="#main">跳到主要内容<\/a>/);
  assert.match(source, /<main class="main" id="main">/);
});

test("accents stay disciplined: one brand accent, red reserved for alerts", () => {
  assert.doesNotMatch(source, /accent="red"/);
  assert.doesNotMatch(source, /accent="violet"/);
  assert.match(source, /<MetricCard title="公网连接数" accent="blue"/);
  assert.match(source, /<MetricCard title="运行时间" accent="muted"/);
  assert.match(theme, /\.metric-card\.accent-muted \{ border-left-color: var\(--line\); \}/);
});
