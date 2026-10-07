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

test("home page is a clean portal launcher with services and search", () => {
  assert.match(source, /const portalServiceMatches = computed/);
  assert.match(source, /const portalPageMatches = computed/);
  assert.match(source, /const portalFirstResult = computed/);
  assert.match(source, /const portalSearchInput = ref\(null\)/);
  assert.match(source, /async function loadPortalServices\(\)/);
  assert.match(source, /async function openPortalService\(entry\)/);
  assert.match(source, /function submitPortalSearch\(\)/);
  assert.match(source, /function portalAddress\(url\)/);
  assert.match(source, /class="portal-search"/);
  assert.match(source, /ref="portalSearchInput"/);
  assert.match(source, /@keydown\.enter\.prevent="submitPortalSearch"/);
  assert.match(source, /class="portal-services"/);
  assert.match(source, /v-for="entry in portalServiceMatches"/);
  assert.match(source, /@click="openPortalService\(entry\)"/);
  assert.match(source, /class="portal-links"/);
  assert.match(source, /v-for="item in portalPageMatches"/);
  // Console pages move to the quiet chip row, services become the primary cards.
  assert.match(source, /const DEFAULT_PORTAL_PAGES = \["overview", "docker", "monitor", "history", "system", "navigation"\]/);
  assert.doesNotMatch(source, /portalCards/);
  assert.doesNotMatch(source, /portalLinks/);
  // The portal is the browser default, while the desktop shell keeps its own view.
  assert.match(source, /const activeView = ref\(props\.view \|\| \(props\.native \? "overview" : "home"\)\)/);
  assert.match(source, /key: "home", label: "首页"/);
  // Slash focuses the search box, m still opens the drawer.
  assert.match(source, /event\.key === "\/" \|\| \(event\.key\.toLowerCase\(\) === "k"/);
  assert.match(source, /portalSearchInput\.value\?\.focus\(\)/);
  assert.match(theme, /\.app-shell \.portal-search/);
  assert.match(theme, /\.app-shell \.portal-service:hover/);
  assert.match(theme, /\.app-shell \.portal-services \{/);
});

test("the top right controls stay hidden until the pointer reaches them", () => {
  assert.match(source, /class="quiet-more"/);
  assert.match(theme, /\.topbar\.quiet \.top-actions \{\n  opacity: 0;\n  visibility: hidden;/);
  assert.match(theme, /\.topbar\.quiet:hover \.top-actions,\n:root \.app-shell \.topbar\.quiet:focus-within \.top-actions \{ opacity: 1; visibility: visible; \}/);
  assert.match(theme, /@media \(hover: none\) \{\n  :root \.app-shell \.topbar\.quiet \.top-actions \{ opacity: \.35; visibility: visible; \}/);
});
