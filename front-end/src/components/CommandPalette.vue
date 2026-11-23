<template>
  <dialog ref="dialog" class="command-palette glass-surface" aria-label="全局搜索" @close="query = ''" @click.self="dismissBackdrop">
    <div class="command-head">
      <Search :size="19" aria-hidden="true" />
      <input
        v-model="query"
        type="text"
        role="combobox"
        aria-label="搜索页面、服务或 Docker 容器"
        aria-autocomplete="list"
        :aria-controls="listId"
        :aria-expanded="true"
        :aria-activedescendant="results[active] ? `${listId}-${active}` : undefined"
        placeholder="搜索页面、服务或容器…"
        autocomplete="off"
        spellcheck="false"
        autofocus
        @keydown="move"
      />
      <button type="button" class="command-close" aria-label="关闭搜索" @click="dialog.close()">Esc</button>
    </div>
    <div :id="listId" class="command-results" role="listbox" aria-label="搜索结果">
      <button
        v-for="(item, index) in results" :id="`${listId}-${index}`" :key="item.id"
        type="button" role="option" tabindex="-1" :aria-selected="index === active"
        @pointermove="active = index" @click="select(item)"
      >
        <component :is="item.icon" :size="17" aria-hidden="true" />
        <span><strong>{{ item.label }}</strong><small v-if="item.detail">{{ item.detail }}</small></span>
        <small>{{ item.kind }}</small>
      </button>
    </div>
    <p v-if="!results.length" class="command-status" role="status">{{ busy ? "正在读取搜索数据…" : "没有匹配结果" }}</p>
  </dialog>
</template>

<script setup>
import { computed, nextTick, ref, useId, watch } from "vue";
import { Search } from "@lucide/vue";

const props = defineProps({ items: { type: Array, required: true }, busy: Boolean });
const emit = defineEmits(["select"]);
const listId = `commands-${useId()}`;
const dialog = ref(null);
const query = ref("");
const active = ref(0);
const results = computed(() => {
  const keyword = query.value.trim().toLowerCase();
  return props.items.filter(item => `${item.label} ${item.detail || ""} ${item.searchText || ""} ${item.kind}`.toLowerCase().includes(keyword)).slice(0, 40);
});
watch(query, () => { active.value = 0; });

function open() {
  if (dialog.value.open) return;
  query.value = "";
  active.value = 0;
  dialog.value.showModal();
}
function select(item) {
  dialog.value.close();
  emit("select", item);
}
function move(event) {
  if (event.isComposing || !results.value.length) return;
  if (event.key === "Enter") {
    event.preventDefault();
    select(results.value[active.value] || results.value[0]);
  } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const delta = event.key === "ArrowDown" ? 1 : -1;
    active.value = (active.value + delta + results.value.length) % results.value.length;
    nextTick(() => document.getElementById(`${listId}-${active.value}`)?.scrollIntoView({ block: "nearest" }));
  }
}
function dismissBackdrop(event) {
  const bounds = dialog.value.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.value.close();
}
defineExpose({ open });
</script>

<style scoped>
.command-palette {
  width: min(580px, calc(100% - 32px));
  max-height: 75dvh;
  margin: min(15vh, 108px) auto auto;
  padding: 0;
  overflow: hidden;
  color: var(--text);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-float);
}
.command-palette::backdrop { background: rgb(7 8 11 / .46); }
.command-head { display: flex; align-items: center; gap: 12px; padding: 12px 15px; border-bottom: 1px solid var(--line); color: var(--muted); }
.command-head input, .app-shell .command-head input {
  flex: 1; min-width: 0; padding: 0; border: 0; outline: 0;
  color: var(--text); background: transparent; font-size: 1rem;
}
.command-palette:has(input:focus-visible) { border-color: var(--accent); }
.command-head .command-close { padding: 0 8px; min-height: 28px; color: var(--muted); font-size: .75rem; }
.command-results { max-height: min(53dvh, 408px); overflow-y: auto; }
.command-results:not(:empty) { padding: 6px; }
.command-results button, .app-shell .command-results button {
  width: 100%; justify-content: flex-start; gap: 11px; min-height: 43px; padding: 8px 10px;
  border: 1px solid transparent; border-radius: var(--radius-md); text-align: left; background: transparent;
}
.command-results button[aria-selected="true"] { background: var(--accent-soft); color: var(--text); }
.command-results button > span { flex: 1; display: grid; min-width: 0; }
.command-results button svg, .command-results button > small { flex-shrink: 0; }
.command-results strong, .command-results small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.command-results small { color: var(--muted); font-size: .75rem; font-weight: 400; }
.command-status { padding: 17px; text-align: center; color: var(--muted); }
</style>
