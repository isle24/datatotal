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

test("home page is a workbench with live launcher tiles", () => {
  assert.match(source, /const workbenchTiles = computed/);
  assert.match(source, /class="workbench"/);
  assert.match(source, /class="workbench-head"/);
  assert.match(source, /class="workbench-tiles"/);
  assert.match(source, /v-for="tile in workbenchTiles"/);
  assert.match(source, /@click="navigate\(tile\.key\)"/);
  assert.match(source, /class="workbench-menu-button"/);
  for (const key of ["docker", "monitor", "history", "system", "processes", "navigation", "ai", "settings"]) {
    assert.match(source, new RegExp(`key: "${key}", label:`), `workbench needs a ${key} tile`);
  }
  assert.match(theme, /\.app-shell \.workbench-tiles \{/);
  assert.match(theme, /\.app-shell \.workbench-tile:hover \{/);
  assert.match(theme, /\.app-shell \.workbench-tile-icon \{/);
});
