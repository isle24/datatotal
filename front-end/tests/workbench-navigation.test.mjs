import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../src/App.vue", import.meta.url), "utf8");
const theme = await readFile(new URL("../src/styles/console-theme.css", import.meta.url), "utf8");

test("navigation is a site wide drawer instead of a permanent column", () => {
  assert.match(source, /const menuOpen = ref\(false\)/);
  assert.match(source, /const menuPinned = ref\(localStorage\.getItem\("ntl-menu-pinned"\)/);
  assert.match(source, /function toggleMenu\(\)/);
  assert.match(source, /function closeMenu\(\)/);
  assert.match(source, /function setMenuPinned\(value\)/);
  assert.match(source, /function handleMenuKeydown\(event\)/);
  assert.match(source, /localStorage\.setItem\("ntl-menu-pinned"/);
  assert.match(source, /class="sidebar-backdrop"/);
  assert.match(source, /:class="\{ 'sidebar-open': menuOpen \}"/);
  assert.match(source, /'menu-open': menuOpen/);
  assert.match(source, /class="icon-button menu-toggle"/);
  assert.match(source, /class="sidebar-tools"/);
  // Nav entries go through navigate() so the drawer closes after picking a page.
  assert.match(source, /@click="navigate\(item\.key\)"/);
  assert.doesNotMatch(source, /@click="setView\(item\.key\)"/);
  assert.match(source, /window\.addEventListener\("keydown", handleMenuKeydown\)/);
  assert.match(source, /window\.removeEventListener\("keydown", handleMenuKeydown\)/);
});

test("drawer styles keep the content full width and support a pinned menu", () => {
  assert.match(theme, /:root \.app-shell \{ grid-template-columns: minmax\(0, 1fr\); \}/);
  assert.match(theme, /\.sidebar-backdrop \{/);
  assert.match(theme, /\.sidebar-backdrop\.show \{ opacity: 1; pointer-events: auto; \}/);
  assert.match(theme, /> \.sidebar\.sidebar-open \{/);
  assert.match(theme, /transform: translateX\(-104%\)/);
  assert.match(theme, /\.app-shell\.menu-pinned:not\(\.nas-native-content\) \{ grid-template-columns: 218px minmax\(0, 1fr\); \}/);
  assert.match(theme, /\.app-shell\.menu-pinned > \.sidebar \{/);
  assert.match(theme, /\.sidebar-tools button\.active/);
  // The old mobile-only switcher is replaced by the drawer.
  assert.match(theme, /\.app-shell \.mobile-page-select \{ display: none; \}/);
});

test("home page is a clean portal launcher", () => {
  assert.match(source, /const portalCards = computed/);
  assert.match(source, /const portalLinks = computed/);
  assert.match(source, /const portalStatusLine = computed/);
  assert.match(source, /class="view portal"/);
  assert.match(source, /class="portal-cards"/);
  assert.match(source, /v-for="card in portalCards"/);
  assert.match(source, /v-for="item in portalLinks"/);
  assert.match(source, /@click="navigate\(card\.key\)"/);
  assert.match(source, /:class="\{ quiet: activeView === 'home' \}"/);
  // The portal is the browser default, while the desktop shell keeps its own view.
  assert.match(source, /const activeView = ref\(props\.view \|\| \(props\.native \? "overview" : "home"\)\)/);
  assert.match(source, /key: "home", label: "首页"/);
  // The dashboard tiles moved out: the overview page keeps only the readout.
  assert.doesNotMatch(source, /workbenchTiles/);
  assert.doesNotMatch(source, /class="workbench"/);
  for (const key of ["overview", "docker", "monitor", "history", "system", "navigation"]) {
    assert.match(source, new RegExp(`key: "${key}", label:`), `portal needs a ${key} card`);
  }
  assert.match(theme, /\.app-shell \.portal-card:hover/);
  assert.match(theme, /\.app-shell \.portal-links button/);
  assert.match(theme, /\.app-shell \.topbar\.quiet \.top-actions \{ opacity: \.16;/);
  assert.match(theme, /\.topbar\.quiet:focus-within \.top-actions \{ opacity: 1; \}/);
});
