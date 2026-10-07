import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// Git may check files out with CRLF on Windows; contracts are written against LF.
const readSource = async (url) => (await readFile(url, "utf8")).replace(/\r\n/g, "\n");

const source = await readSource(new URL("../src/App.vue", import.meta.url));
const theme = await readSource(new URL("../src/styles/console-theme.css", import.meta.url));

test("the menu is a column on normal pages and only the portal hides it", () => {
  assert.match(source, /const menuOpen = ref\(defaultMenuOpen\(activeView\.value\)\)/);
  assert.match(source, /function defaultMenuOpen\(view\) \{\n  if \(view === "home"\) return false;/);
  assert.match(source, /function toggleMenu\(\)/);
  assert.match(source, /function closeMenu\(\)/);
  assert.match(source, /function handleMenuKeydown\(event\)/);
  assert.match(source, /'menu-open': menuOpen/);
  assert.match(source, /class="icon-button menu-toggle"/);
  assert.match(source, /class="sidebar-tools"/);
  assert.match(source, /@click="navigate\(item\.key\)"/);
  assert.doesNotMatch(source, /@click="setView\(item\.key\)"/);
  // Navigating re-derives the menu state for the target page.
  assert.match(source, /activeView\.value = view;\n  menuOpen\.value = defaultMenuOpen\(view\);/);
  // No pinning anymore: the menu shows itself on every page but the portal.
  assert.doesNotMatch(source, /menuPinned/);
  assert.doesNotMatch(source, /ntl-menu-pinned/);
  assert.match(source, /window\.addEventListener\("keydown", handleMenuKeydown\)/);
});

test("the open menu takes its own column instead of covering the content", () => {
  assert.match(theme, /\.app-shell\.menu-open:not\(\.nas-native-content\) \{ grid-template-columns: 218px minmax\(0, 1fr\); \}/);
  assert.match(theme, /\.app-shell:not\(\.menu-open\) > \.sidebar \{ display: none; \}/);
  assert.match(theme, /:root \.app-shell > \.sidebar \{\n  display: flex;\n  flex-direction: column;\n  position: sticky;/);
  // No overlay on desktop: the backdrop only exists inside the phone media query.
  assert.match(theme, /\.app-shell \.sidebar-backdrop \{ display: none; \}/);
  assert.match(theme, /@media \(max-width: 720px\) \{\n  \/\* Phones: the menu slides over the content and dims it behind a backdrop\. \*\//);
  assert.match(theme, /\.app-shell \.sidebar-backdrop\.show \{ opacity: 1; pointer-events: auto; \}/);
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
