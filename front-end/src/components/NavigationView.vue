<template>
  <section class="nav-hub">
    <div class="nav-toolbar">
      <div class="nav-summary">
        <Compass :size="25" />
        <div>
          <h3>服务导航</h3>
          <p>
            {{ unavailable ? "待更新 NAS" : `${entries.length} 个服务` }} ·
            {{ scope }}
          </p>
        </div>
      </div>
      <div class="nav-tools">
        <label class="nav-search"
          ><Search :size="17" /><input
            v-model="query"
            type="search"
            aria-label="搜索服务"
            placeholder="搜索名称、地址、备注"
        /></label>
        <select v-model="group" aria-label="筛选导航分组">
          <option value="">全部分组</option>
          <option v-for="name in groups" :key="name">{{ name }}</option>
        </select>
        <button
          type="button"
          title="刷新导航"
          aria-label="刷新导航"
          :disabled="busy"
          @click="load"
        >
          <RefreshCw :size="17" />
        </button>
        <button
          type="button"
          class="nav-primary"
          :disabled="unavailable || busy"
          @click="edit()"
        >
          <Plus :size="17" />添加服务
        </button>
      </div>
    </div>
    <div v-if="unavailable" class="nav-upgrade" role="status">
      <Server :size="32" />
      <h3>需要更新 NAS 服务端</h3>
      <p>{{ error }}</p>
      <button @click="load" :disabled="busy">
        <RefreshCw :size="16" />更新后重试
      </button>
    </div>
    <div v-else-if="error" class="nav-error" role="alert">{{ error }}</div>
    <div v-if="busy && !entries.length" class="nav-empty">正在加载服务…</div>
    <div v-else-if="!error && !filtered.length" class="nav-empty">
      <Compass :size="40" />
      <h3>{{ query || group ? "没有匹配的服务" : "暂无服务" }}</h3>
      <button v-if="!query && !group" @click="edit()">
        <Plus :size="17" />添加服务
      </button>
    </div>
    <section v-for="section in sections" :key="section.name" class="nav-group">
      <h4>
        {{ section.name }}<span>{{ section.items.length }}</span>
      </h4>
      <div class="nav-grid">
        <article
          v-for="entry in section.items"
          :key="entry.id"
          class="nav-card"
        >
          <button class="nav-launch" :title="entry.url" @click="open(entry)">
            <span class="nav-logo"
              ><img
                v-if="entry.icon"
                :src="entry.icon"
                alt=""
                loading="lazy" /><Globe v-else :size="26" /></span
            ><span class="nav-copy"
              ><strong>{{ entry.name }}</strong
              ><small>{{
                entry.notes || displayAddress(entry.url)
              }}</small></span
            ><ArrowUpRight :size="18" class="nav-launch-arrow" />
          </button>
          <div class="nav-card-footer">
            <span
              ><Container v-if="entry.sourceKey" :size="13" /><Link2
                v-else
                :size="13"
              />{{ displayAddress(entry.url) }}</span
            ><button
              :title="`编辑 ${entry.name}`"
              :aria-label="`编辑 ${entry.name}`"
              @click="edit(entry)"
            >
              <Pencil :size="14" />
            </button>
          </div>
        </article>
      </div>
    </section>
    <div
      v-if="editor"
      class="nav-backdrop"
      @click.self="closeEditor"
      @keydown.esc="closeEditor"
    >
      <form class="nav-editor" @submit.prevent="save">
        <div class="nav-editor-title">
          <h3>{{ editor.id ? "编辑服务" : "添加服务" }}</h3>
          <button
            type="button"
            title="关闭"
            aria-label="关闭编辑"
            :disabled="saving"
            @click="closeEditor"
          >
            <X :size="18" />
          </button>
        </div>
        <div class="nav-icon-editor">
          <span class="nav-logo"
            ><img v-if="editor.icon" :src="editor.icon" alt="服务图标" /><Globe
              v-else
              :size="30" /></span
          ><label class="nav-upload"
            ><ImagePlus :size="16" />上传图标<input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              :disabled="iconBusy"
              @change="upload" /></label
          ><button
            v-if="editor.icon"
            type="button"
            title="清除图标"
            aria-label="清除图标"
            @click="editor.icon = ''"
          >
            <Trash2 :size="16" />
          </button>
        </div>
        <div class="nav-fields">
          <label
            >名称<input
              v-model="editor.name"
              required
              maxlength="120"
              autofocus /></label
          ><label
            >分组<input
              v-model="editor.group"
              maxlength="60"
              list="navigation-groups" /><datalist id="navigation-groups">
              <option v-for="name in groups" :value="name" /></datalist
          ></label>
          <label class="nav-wide"
            >地址<input
              v-model="editor.url"
              type="url"
              required
              maxlength="2048"
              placeholder="http://192.168.1.10:8080"
          /></label>
          <label class="nav-wide"
            >备注<textarea
              v-model="editor.notes"
              rows="2"
              maxlength="500"
            ></textarea></label
          ><label
            >排序<input
              v-model.number="editor.sortOrder"
              type="number"
              min="-10000"
              max="10000"
          /></label>
        </div>
        <p v-if="editorError" class="nav-error" role="alert">
          {{ editorError }}
        </p>
        <div class="nav-editor-actions">
          <button
            v-if="editor.id"
            type="button"
            class="nav-delete"
            :disabled="saving"
            @click="remove"
          >
            <Trash2 :size="16" />删除</button
          ><span></span
          ><button type="button" :disabled="saving" @click="closeEditor">
            取消</button
          ><button class="nav-primary" :disabled="saving || iconBusy">
            <Save :size="16" />{{ saving ? "保存中…" : "保存" }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  Compass,
  Search,
  Plus,
  RefreshCw,
  Globe,
  ArrowUpRight,
  Pencil,
  Container,
  Link2,
  X,
  ImagePlus,
  Trash2,
  Save,
  Server,
} from "@lucide/vue";
import { safeNavigationUrl, navigationIcon } from "../utils/navigation.js";
const props = defineProps({
  repository: { type: Object, required: true },
  scope: { type: String, default: "此 NAS" },
});
const entries = ref([]),
  query = ref(""),
  group = ref(""),
  busy = ref(false),
  error = ref("");
const unavailable = ref(false);
const editor = ref(null),
  editorError = ref(""),
  saving = ref(false),
  iconBusy = ref(false);
let disposed = false;
const groups = computed(() =>
  [...new Set(entries.value.map((e) => e.group || "常用"))].sort(),
);
const filtered = computed(() =>
  entries.value.filter(
    (e) =>
      (!group.value || (e.group || "常用") === group.value) &&
      `${e.name} ${e.url} ${e.notes} ${e.group}`
        .toLowerCase()
        .includes(query.value.toLowerCase().trim()),
  ),
);
const sections = computed(() =>
  [...new Set(filtered.value.map((e) => e.group || "常用"))].map((name) => ({
    name,
    items: filtered.value.filter((e) => (e.group || "常用") === name),
  })),
);
function displayAddress(url) {
  try {
    const u = new URL(url);
    return `${u.host}${u.pathname === "/" ? "" : u.pathname}`;
  } catch {
    return url;
  }
}
async function load() {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  unavailable.value = false;
  try {
    const data = await props.repository.list();
    if (!disposed) entries.value = data;
  } catch (e) {
    if (!disposed) {
      error.value = e.message || String(e);
      unavailable.value = e.code === "NAVIGATION_UNAVAILABLE";
    }
  } finally {
    busy.value = false;
  }
}
function edit(entry) {
  editorError.value = "";
  editor.value = entry
    ? { ...entry }
    : {
        name: "",
        url: "",
        icon: "",
        group: group.value || "常用",
        notes: "",
        sortOrder: 0,
        sourceKey: "",
      };
}
function closeEditor() {
  if (!saving.value) editor.value = null;
}
async function open(entry) {
  const url = safeNavigationUrl(entry.url);
  if (!url) {
    error.value = "服务地址无效，请编辑后重试";
    return;
  }
  try {
    await props.repository.open(url);
  } catch (e) {
    error.value = e.message || String(e);
  }
}
async function upload(event) {
  const target = editor.value;
  const file = event.target.files?.[0];
  if (!file) return;
  iconBusy.value = true;
  try {
    const icon = await navigationIcon(file);
    if (editor.value === target) editor.value.icon = icon;
  } catch (e) {
    editorError.value = e.message || String(e);
  } finally {
    iconBusy.value = false;
    event.target.value = "";
  }
}
async function save() {
  if (saving.value) return;
  const url = safeNavigationUrl(editor.value.url);
  if (!url) {
    editorError.value = "请输入不含账号密码的 HTTP/HTTPS 地址";
    return;
  }
  saving.value = true;
  editorError.value = "";
  try {
    await props.repository.save({ ...editor.value, url });
    editor.value = null;
    await load();
  } catch (e) {
    editorError.value = e.message || String(e);
  } finally {
    saving.value = false;
  }
}
async function remove() {
  if (!(await props.repository.confirm(`删除导航服务“${editor.value.name}”？`)))
    return;
  saving.value = true;
  try {
    await props.repository.remove(editor.value.id);
    editor.value = null;
    await load();
  } catch (e) {
    editorError.value = e.message || String(e);
  } finally {
    saving.value = false;
  }
}
onMounted(load);
onUnmounted(() => {
  disposed = true;
});
</script>

<style scoped>
.nav-upgrade {
  display: flex;
  align-items: center;
  flex-direction: column;
  justify-content: center;
  min-height: 300px;
  gap: 16px;
  text-align: center;
  color: var(--nav-muted);
}
.nav-upgrade h3 {
  margin: 0;
  color: var(--nav-text);
  font-size: 18px;
}
.nav-upgrade p {
  max-width: 460px;
  line-height: 1.8;
  margin: 0 0 8px;
  font-size: 13px;
}
.nav-hub {
  --nav-bg: var(--ds-bg, var(--bg));
  --nav-panel: var(--ds-surface, var(--panel));
  --nav-line: var(--ds-line, var(--line));
  --nav-text: var(--ds-text, var(--text));
  --nav-muted: var(--ds-muted, var(--muted));
  --nav-accent: var(--ds-accent, var(--blue));
  color: var(--nav-text);
  min-width: 0;
}
.nav-toolbar,
.nav-tools,
.nav-summary,
.nav-editor-title,
.nav-icon-editor,
.nav-editor-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.nav-toolbar {
  justify-content: space-between;
  flex-wrap: wrap;
  margin: 4px 0 30px;
}
.nav-summary {
  gap: 14px;
}
.nav-summary > svg {
  color: var(--nav-accent);
}
.nav-summary h3,
.nav-editor h3 {
  font-size: 20px;
  margin: 0;
}
.nav-summary p {
  margin: 4px 0 0;
  color: var(--nav-muted);
  font-size: 12px;
}
.nav-tools {
  flex-wrap: wrap;
}
.nav-tools select {
  width: auto;
  max-width: 150px;
}
.nav-search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--nav-panel);
  border: 1px solid var(--nav-line);
  border-radius: 6px;
  padding: 0 10px;
}
.nav-search input {
  border: 0;
  background: transparent;
  max-width: 240px;
  min-width: 120px;
  outline: 0;
}
.nav-hub button {
  background: var(--nav-panel);
  color: var(--nav-text);
  font-weight: 500;
}
.nav-hub .nav-primary {
  background: var(--nav-accent);
  color: #fff;
  border-color: transparent;
}
.nav-hub input,
.nav-hub select,
.nav-hub textarea {
  color: var(--nav-text);
  background: var(--nav-panel);
}
.nav-group {
  margin: 0 0 32px;
}
.nav-group h4 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 13px;
}
.nav-group h4 span {
  color: var(--nav-muted);
  font-size: 12px;
  font-weight: 400;
}
.nav-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr));
  gap: 16px;
}
.nav-card {
  background: var(--nav-panel);
  border: 1px solid var(--nav-line);
  border-radius: 8px;
  min-width: 0;
  overflow: hidden;
  box-shadow: 0 2px 4px #00000003;
  transition:
    box-shadow 0.15s,
    border-color 0.15s;
}
.nav-card:hover {
  border-color: var(--nav-accent);
  box-shadow: 0 4px 14px #00000009;
}
.nav-card .nav-launch {
  display: flex;
  text-align: left;
  width: 100%;
  padding: 22px 18px;
  border: 0;
  border-radius: 0;
  gap: 14px;
  min-height: 100px;
}
.nav-logo {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  flex: 0 0 48px;
  background: var(--nav-bg);
  color: var(--nav-accent);
  border-radius: 8px;
}
.nav-logo img {
  width: 38px;
  height: 38px;
  object-fit: contain;
}
.nav-copy {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.nav-copy strong {
  font-size: 15px;
  overflow-wrap: anywhere;
}
.nav-copy small {
  font-size: 12px;
  color: var(--nav-muted);
  font-weight: 400;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.nav-launch-arrow {
  flex-shrink: 0;
  color: var(--nav-muted);
}
.nav-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid var(--nav-line);
  padding: 6px 12px 6px 18px;
  gap: 10px;
}
.nav-card-footer > span {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--nav-muted);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.nav-card-footer svg {
  flex-shrink: 0;
}
.nav-card-footer button {
  border: 0;
  width: 30px;
  min-height: 30px;
  padding: 0;
  flex: 0 0 30px;
}
.nav-empty {
  display: flex;
  align-items: center;
  flex-direction: column;
  justify-content: center;
  min-height: 280px;
  color: var(--nav-muted);
  gap: 15px;
}
.nav-empty h3 {
  margin: 0;
  font-size: 17px;
}
.nav-error {
  color: #d44646;
  font-size: 13px;
  padding: 12px 0;
  overflow-wrap: anywhere;
}
.nav-backdrop {
  position: fixed;
  inset: 0;
  background: #0006;
  z-index: 110;
  display: grid;
  place-items: center;
  padding: 24px;
}
.nav-editor {
  width: min(560px, 100%);
  max-height: 90vh;
  overflow-y: auto;
  background: var(--nav-panel);
  border: 1px solid var(--nav-line);
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 24px 100px #0003;
}
.nav-editor-title {
  justify-content: space-between;
  margin-bottom: 22px;
}
.nav-editor-title button {
  width: 32px;
  min-height: 32px;
  padding: 0;
}
.nav-icon-editor {
  margin-bottom: 24px;
}
.nav-upload {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  font-size: 13px;
}
.nav-upload input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
  width: 100%;
}
.nav-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
.nav-fields label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
  min-width: 0;
}
.nav-fields input,
.nav-fields textarea {
  width: 100%;
  max-width: none;
  border: 1px solid var(--nav-line);
  padding: 8px;
  border-radius: 5px;
}
.nav-wide {
  grid-column: span 2;
}
.nav-editor-actions {
  margin-top: 24px;
}
.nav-editor-actions > span {
  flex: 1;
}
.nav-hub .nav-delete {
  color: #d44646;
  border-color: transparent;
}
.nav-editor-actions button {
  padding: 0 12px;
}
@media (max-width: 650px) {
  .nav-toolbar {
    gap: 20px;
  }
  .nav-tools {
    width: 100%;
  }
  .nav-search {
    flex: 1;
  }
  .nav-search input {
    width: 100%;
  }
  .nav-tools select {
    max-width: 120px;
  }
  .nav-backdrop {
    padding: 12px;
  }
  .nav-editor {
    padding: 18px;
  }
  .nav-grid {
    gap: 12px;
  }
  .nav-card .nav-launch {
    padding: 18px;
  }
}
</style>
