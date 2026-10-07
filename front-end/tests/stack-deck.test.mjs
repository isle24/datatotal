import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { StackMotion, prefersReducedMotion } from "../src/utils/stack-motion.js";

const source = await readFile(new URL("../src/App.vue", import.meta.url), "utf8");
const theme = await readFile(new URL("../src/styles/console-theme.css", import.meta.url), "utf8");
const base = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
const desktop = await readFile(new URL("../src/desktop/desktop.css", import.meta.url), "utf8");

function fakeCard(index) {
  const properties = new Map();
  const classes = new Set();
  return {
    index,
    properties,
    classes,
    parentElement: null,
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle: (name, force) => (force ? classes.add(name) : classes.delete(name)),
    },
    style: {
      setProperty: (name, value) => properties.set(name, value),
      removeProperty: (name) => properties.delete(name),
    },
  };
}

function fakeDeck(count) {
  const container = {
    classes: new Set(),
    classList: {
      add: (...names) => names.forEach((name) => container.classes.add(name)),
      remove: (...names) => names.forEach((name) => container.classes.delete(name)),
      contains: (name) => container.classes.has(name),
      toggle: (name, force) => (force ? container.classes.add(name) : container.classes.delete(name)),
    },
  };
  const cards = Array.from({ length: count }, (_, index) => fakeCard(index));
  for (const card of cards) {
    card.parentElement = container;
    card.compareDocumentPosition = (other) => (other.index > card.index ? 4 : 2);
  }
  return { container, cards };
}

test("deck geometry puts the last card in front and counts depth backwards", () => {
  const { container, cards } = fakeDeck(4);
  const motion = new StackMotion();
  cards.forEach((card) => motion.register(card));
  assert.equal(cards[0].properties.get("--stack-back"), "3");
  assert.equal(cards[1].properties.get("--stack-back"), "2");
  assert.equal(cards[3].properties.get("--stack-back"), "0");
  assert.equal(container.classes.has("stack-deck"), true);
  // Short stacks keep the inset deck look.
  assert.equal(container.classes.has("stack-deck-deep"), true);
});

test("long stacks stay full width but still overlap", () => {
  const { container, cards } = fakeDeck(9);
  const motion = new StackMotion();
  cards.forEach((card) => motion.register(card));
  assert.equal(container.classes.has("stack-deck-deep"), false);
  assert.equal(cards[0].properties.get("--stack-back"), "5", "depth is clamped so shadows stay readable");
  assert.equal(cards[8].properties.get("--stack-back"), "0");
});

test("unregistering the last card releases the deck classes", () => {
  const { container, cards } = fakeDeck(2);
  const motion = new StackMotion();
  cards.forEach((card) => motion.register(card));
  motion.unregister(cards[0]);
  motion.unregister(cards[1]);
  assert.equal(container.classes.has("stack-deck"), false);
  assert.equal(cards[0].properties.has("--stack-back"), false);
});

test("reduced motion disables the scroll-linked transform values", () => {
  const { cards } = fakeDeck(2);
  const motion = new StackMotion();
  cards.forEach((card) => motion.register(card));
  motion.measure();
  for (const card of cards) {
    assert.equal(card.properties.has("--stack-tilt"), false);
    assert.equal(card.properties.has("--stack-shift"), false);
  }
  assert.equal(prefersReducedMotion(), true, "no matchMedia in Node means motion stays off");
});

test("every accordion stack opts into the shared deck motion", () => {
  assert.match(source, /import \{ vStackMotion \} from "\.\/utils\/stack-motion\.js"/);
  const attached = source.match(/v-stack-motion/g) ?? [];
  assert.ok(attached.length >= 10, `expected the directive on every stack, found ${attached.length}`);
  assert.match(theme, /\.stack-deck > \* \{/);
  assert.match(theme, /--stack-back/);
  assert.match(theme, /perspective: 1500px/);
  assert.match(theme, /--deck-peek-deep/);
  assert.match(theme, /\.stack-deck > \*\.expanded \{/);
  assert.match(theme, /\.stack-deck > \*\.expanded \+ \* \{ margin-top: 10px; \}/);
});

test("the console palette has no green left anywhere", () => {
  const greenToken = /--green:\s*#/;
  assert.doesNotMatch(theme, greenToken);
  assert.match(theme, /--green: var\(--accent\)/);
  assert.doesNotMatch(base, /var\(--green\)/);
  assert.doesNotMatch(desktop, /#0d9c7c|#127c64|#147d65|#0f9d82/);
  // Sidebar chrome follows the blue-slate palette.
  assert.match(theme, /\.menu button\.active \{ color: #dceafb; background: #2f4257; border-color: #47617f; \}/);
  assert.match(theme, /\.menu button:hover \{ color: #f1f6fb; background: #2c3846; border-color: transparent; \}/);
  assert.match(theme, /\.brand-mark \{[^}]*background: #2b3a4a;/s);
  // Running/healthy states use the accent instead of green.
  assert.match(base, /\.state-running,\n\.rule-state\.enabled \{\n  color: var\(--accent\);/);
  assert.match(base, /\.fan-status\.running \{ color: var\(--accent\);/);
  assert.match(base, /\.live-dot \{[^}]*background: var\(--accent\);/s);
  assert.match(theme, /\.live-dot \{ animation: console-live-pulse/);
});

test("metric accents stay distinguishable without green", () => {
  assert.match(base, /\.accent-violet \{ border-left: 4px solid var\(--violet\); \}/);
  assert.match(theme, /--violet: #6d5bd0;/);
  assert.match(theme, /--violet: #a99cf0;/);
  assert.doesNotMatch(source, /accent="green"/);
  assert.doesNotMatch(source, /accent="teal"/);
});
