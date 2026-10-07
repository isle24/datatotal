import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { compileScript, parse } from "@vue/compiler-sfc";
import * as vue from "vue";
import * as icons from "@lucide/vue";
import * as navigation from "../src/utils/navigation.js";

const source = await readFile(new URL("../src/components/NavigationView.vue", import.meta.url), "utf8");
const { descriptor } = parse(source);
const compiled = compileScript(descriptor, { id: "navigation-editor-test" });
const bindings = { ...vue, ...icons, ...navigation, onMounted() {}, onUnmounted() {} };
const importedNames = Object.keys(compiled.imports);
const component = new Function(...importedNames, compiled.content
  .replace(/^import\s[\s\S]*?from\s+["'][^"']+["'];?\s*/gm, "")
  .replace("export default", "return"))(...importedNames.map((name) => bindings[name]));

function setup(repository = {}) {
  const confirmations = [];
  const state = component.setup({ scope: "Test NAS", repository: {
    list: async () => [],
    confirm: async (message) => { confirmations.push(message); return false; },
    ...repository,
  } }, { expose() {} });
  const dialog = {
    open: false,
    showModal() { this.open = true; },
    close() { this.open = false; },
    getBoundingClientRect: () => ({ left: 20, top: 20, right: 200, bottom: 200 }),
  };
  if (state.editorDialog) state.editorDialog.value = dialog;
  return { state, dialog, confirmations };
}

const entry = { id: "nas-service-1", name: "控制台", url: "http://nas:8080", group: "Docker", notes: "", icon: "", sortOrder: 0, sourceKey: "docker:qb:tcp:8080" };

test("navigation opens a native modal editor while preserving the saved service identity", async () => {
  const { state, dialog } = setup();
  await state.edit(entry);
  assert.equal(dialog.open, true);
  assert.deepEqual({ ...state.editor.value }, entry);
  assert.match(descriptor.template.content, /<dialog[\s\S]*?aria-labelledby=/);
  assert.match(descriptor.template.content, /@cancel\.prevent="cancelEditor"/);
});

test("closing a changed navigation draft opens an inline discard prompt without a system popup", async () => {
  const { state, dialog, confirmations } = setup();
  await state.edit(entry);
  state.editor.value.notes = "尚未保存的备注";
  await state.closeEditor();
  assert.equal(confirmations.length, 0);
  assert.equal(state.discardPrompt?.value, true);
  assert.equal(dialog.open, true);
  assert.equal(state.editor.value.notes, "尚未保存的备注");
});

test("continuing from the discard prompt preserves the draft", async () => {
  const { state, dialog, confirmations } = setup();
  await state.edit(entry);
  state.editor.value.notes = "draft";
  await state.closeEditor();
  assert.equal(typeof state.continueEditing, "function");
  await state.continueEditing();
  assert.equal(state.discardPrompt.value, false);
  assert.equal(state.editor.value.notes, "draft");
  assert.equal(dialog.open, true);
  assert.equal(confirmations.length, 0);
});

test("Escape returns from the discard prompt to editing without closing the dialog", async () => {
  const { state, dialog } = setup();
  await state.edit(entry);
  state.editor.value.notes = "draft";
  assert.equal(typeof state.cancelEditor, "function");
  await state.cancelEditor();
  assert.equal(state.discardPrompt.value, true);
  await state.cancelEditor();
  assert.equal(state.discardPrompt.value, false);
  assert.equal(state.editor.value.notes, "draft");
  assert.equal(dialog.open, true);
});

test("an explicit inline discard closes the native editor and clears the prompt", async () => {
  const discarded = setup();
  await discarded.state.edit(entry);
  discarded.state.editor.value.name = "新名称";
  await discarded.state.closeEditor();
  assert.equal(typeof discarded.state.discardEditor, "function");
  discarded.state.discardEditor();
  assert.equal(discarded.dialog.open, false);
  assert.equal(discarded.state.editor.value, null);
  assert.equal(discarded.state.discardPrompt.value, false);
  assert.equal(discarded.confirmations.length, 0);
});

test("an unchanged navigation draft closes without a discard prompt", async () => {
  const unchanged = setup();
  await unchanged.state.edit(entry);
  await unchanged.state.closeEditor();
  assert.equal(unchanged.dialog.open, false);
  assert.equal(unchanged.confirmations.length, 0);
  assert.equal(unchanged.state.discardPrompt?.value, false);
});

test("saving or processing an icon prevents an accidental editor close", async () => {
  const { state, dialog, confirmations } = setup();
  await state.edit(entry);
  state.iconBusy.value = true;
  await state.closeEditor();
  assert.equal(dialog.open, true);
  state.iconBusy.value = false;
  state.saving.value = true;
  await state.closeEditor();
  assert.equal(dialog.open, true);
  assert.equal(confirmations.length, 0);
});

test("a backdrop click requests a close while clicks within the dialog preserve the editor", async () => {
  const { state, dialog, confirmations } = setup();
  await state.edit(entry);
  state.editor.value.notes = "draft";
  assert.equal(typeof state.dismissBackdrop, "function");
  await state.dismissBackdrop({ target: dialog, currentTarget: dialog, clientX: 40, clientY: 40 });
  assert.equal(confirmations.length, 0);
  assert.equal(state.discardPrompt?.value, false);
  await state.dismissBackdrop({ target: dialog, currentTarget: dialog, clientX: 0, clientY: 0 });
  assert.equal(confirmations.length, 0);
  assert.equal(state.discardPrompt.value, true);
  assert.equal(state.editor.value.notes, "draft");
});

test("the navigation editor contains no stray literal tag separators", () => {
  function textNodes(node) {
    return [node.type === 2 ? node.content.trim() : "", ...(node.children || []).flatMap(textNodes)];
  }
  assert.equal(textNodes(descriptor.template.ast).includes(">"), false);
});

test("saving closes the native editor and retains the NAS source key", async () => {
  let payload;
  const { state, dialog } = setup({ save: async (value) => { payload = value; } });
  await state.edit(entry);
  state.editor.value.name = "New name";
  await state.save();
  assert.equal(payload.id, entry.id);
  assert.equal(payload.sourceKey, entry.sourceKey);
  assert.equal(payload.name, "New name");
  assert.equal(dialog.open, false);
  assert.equal(state.editor.value, null);
});

test("a successful reload clears only an unavailable navigation group", async () => {
  const { state } = setup({ list: async () => [{ ...entry, group: "常用" }] });
  state.group.value = "Docker";
  state.query.value = "控制台";
  await state.load();
  assert.equal(state.group.value, "");
  assert.equal(state.query.value, "控制台");
  state.group.value = "常用";
  await state.load();
  assert.equal(state.group.value, "常用");
});

test("a failed reload retains the current navigation filters and last results", async () => {
  const { state } = setup({ list: async () => { throw new Error("offline"); } });
  state.entries.value = [entry];
  state.group.value = "Docker";
  state.query.value = "控制台";
  await state.load();
  assert.equal(state.group.value, "Docker");
  assert.equal(state.query.value, "控制台");
  assert.equal(state.entries.value[0].id, entry.id);
});

test("navigation can clear both filters after an empty search", () => {
  const { state } = setup();
  state.entries.value = [entry];
  state.group.value = "Docker";
  state.query.value = "不存在";
  assert.equal(state.filtered.value.length, 0);
  assert.equal(typeof state.resetFilters, "function");
  state.resetFilters();
  assert.equal(state.query.value, "");
  assert.equal(state.group.value, "");
  assert.equal(state.filtered.value.length, 1);
  assert.match(descriptor.template.content, /@click="resetFilters"/);
});
