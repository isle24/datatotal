import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// Git may check files out with CRLF on Windows; contracts are written against LF.
const readSource = async (url) => (await readFile(url, "utf8")).replace(/\r\n/g, "\n");

const source = await readSource(new URL("../src/App.vue", import.meta.url));
const theme = await readSource(new URL("../src/styles/console-theme.css", import.meta.url));
const portal = await readSource(new URL("../src/components/HomePortalView.vue", import.meta.url));
const palette = await readSource(new URL("../src/components/CommandPalette.vue", import.meta.url));

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
  assert.match(theme, /@media \(max-width: 734px\) \{\n  \/\* Phones: the menu slides over the content and dims it behind a backdrop\. \*\//);
  assert.match(theme, /\.app-shell\.is-portal-mode\.menu-open > \.sidebar/);
  assert.match(theme, /\.app-shell \.sidebar-backdrop\.show \{ opacity: 1; pointer-events: auto; \}/);
});

test("home page is a clean portal launcher with services and search", () => {
  assert.match(source, /const portalServiceMatches = computed/);
  assert.match(source, /const portalPageMatches = computed/);
  assert.match(source, /const portalFirstResult = computed/);
  assert.match(portal, /const searchInput = ref\(null\)/);
  assert.match(source, /async function loadPortalServices\(\)/);
  assert.match(source, /async function openPortalService\(entry\)/);
  assert.match(source, /function submitPortalSearch\(\)/);
  assert.match(source, /function portalAddress\(url\)/);
  assert.match(portal, /class="portal-search"/);
  assert.match(portal, /ref="searchInput"/);
  assert.match(portal, /@keydown\.enter\.prevent/);
  assert.match(portal, /class="portal-services"/);
  assert.match(portal, /v-for="entry in services"/);
  assert.match(source, /@open-service="openPortalService"/);
  assert.match(portal, /class="portal-links"/);
  assert.match(portal, /v-for="item in pages"/);
  // Console pages move to the quiet chip row, services become the primary cards.
  assert.match(source, /const DEFAULT_PORTAL_PAGES = \["overview", "docker", "monitor", "history", "system", "navigation"\]/);
  assert.doesNotMatch(source, /portalCards/);
  assert.doesNotMatch(source, /portalLinks/);
  // The portal is the browser default, while the desktop shell keeps its own view.
  assert.match(source, /const activeView = ref\(props\.view \|\| \(props\.native \? "overview" : "home"\)\)/);
  assert.match(source, /key: "home", label: "首页"/);
  // Slash focuses the search box, m still opens the drawer.
  assert.match(source, /event\.key === "\/"/);
  assert.match(source, /homePortal\.value\?\.focusSearch\(\)/);
  assert.match(theme, /\.app-shell \.portal-search/);
  assert.match(theme, /\.app-shell \.portal-service:hover/);
  assert.match(theme, /\.app-shell \.portal-services \{/);
});

test("the home omits the top bar and provides an accessible command palette", () => {
  assert.match(source, /'is-portal-mode': activeView === 'home'/);
  assert.match(source, /<header v-if="!native && activeView !== 'home'" class="topbar">/);
  assert.match(source, /event\.key\.toLowerCase\(\) === "k" && \(event\.metaKey \|\| event\.ctrlKey\)/);
  assert.match(source, /<CommandPalette/);
  assert.match(palette, /<dialog/);
  assert.match(palette, /\.showModal\(\)/);
  assert.match(palette, /ArrowDown/);
  assert.match(source, /dockerSearch\.value = item\.container\.name/);
});
