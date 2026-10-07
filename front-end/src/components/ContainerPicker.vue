<template>
  <div class="container-picker">
    <details ref="picker" @toggle="opened = $event.target.open" @keydown.esc.prevent="closePicker">
      <summary class="container-picker-trigger">
        <Server :size="18" /><span>{{ summary }}</span><ChevronDown :size="16" />
      </summary>
      <div class="container-picker-panel">
        <div class="container-picker-search">
          <Search :size="16" /><input v-model="query" type="search" :aria-label="multiple ? '搜索可选容器' : '搜索容器'" placeholder="搜索容器名称或镜像" />
          <button type="button" aria-label="刷新容器列表" :disabled="loading" @click="$emit('refresh')"><RefreshCw :size="16" /></button>
        </div>
        <p v-if="error" class="settings-feedback error" role="alert">{{ error }} <button type="button" :disabled="loading" @click="$emit('refresh')">重新获取</button></p>
        <div v-if="loading" class="container-picker-loading" role="status"><span v-for="n in 3" :key="n" aria-hidden="true"></span>正在读取 Docker 容器…</div>
        <template v-else>
          <div v-if="multiple && visible.length" class="container-picker-actions">
            <button type="button" @click="selectVisible">{{ query ? '选择搜索结果' : '选择全部列表容器' }}</button>
            <button type="button" :disabled="!modelValue.length" @click="$emit('update:modelValue', [])">清除选择</button>
          </div>
          <div class="container-picker-options" :role="multiple ? 'group' : 'radiogroup'" aria-label="可选 Docker 容器">
            <label v-for="container in visible" :key="container.id || container.name" class="container-picker-option" :class="{ selected: selected(container) }">
              <input :type="multiple ? 'checkbox' : 'radio'" :name="inputName" :checked="selected(container)" @change="choose(container)" />
              <span><strong>{{ container.name || container.id }}</strong><small>{{ container.image || container.composeService || 'Docker 容器' }}</small></span>
              <em>{{ container.state === 'running' ? '运行中' : container.state === 'restarting' ? '重启中' : '当前可见' }}</em>
            </label>
          </div>
          <div v-if="!visible.length" class="container-picker-empty">
            <span>{{ query ? '没有匹配的容器' : '尚未发现可选容器，请检查 Docker 自动发现是否开启' }}</span>
            <button v-if="query" type="button" @click="query = ''">清空搜索</button>
            <button v-else type="button" @click="$emit('refresh')">重新获取容器</button>
          </div>
          <button v-if="multiple" class="container-picker-done" type="button" @click="closePicker">完成选择 · {{ modelValue.length }} 个容器</button>
        </template>
      </div>
    </details>
    <div v-if="modelValue.length" class="container-picker-selection">
      <span v-for="(target, index) in modelValue" :key="`${target.containerName}-${target.containerId}-${index}`" :class="{ unavailable: !available(target) }">
        {{ target.containerName || target.composeService || '已保存容器' }}<small v-if="!available(target)">暂时不可见</small>
        <button type="button" :aria-label="`移除 ${target.containerName || target.composeService || '容器'}`" @click="remove(index)"><X :size="13" /></button>
      </span>
    </div>
    <p class="field-hint">{{ multiple ? '可直接勾选多个容器；暂时不可见的已选容器仍会保留。' : '从列表选择容器，名称和更新后的身份由系统匹配。' }}</p>
  </div>
</template>

<script setup>
import { computed, ref, useId, watch } from "vue";
import { Server, ChevronDown, Search, RefreshCw, X } from "@lucide/vue";
import { addVisibleTargets, containerTarget, matchesContainerTarget, toggleContainerTarget } from "../utils/container-selection.js";
const props = defineProps({ modelValue: { type: Array, default: () => [] }, containers: { type: Array, default: () => [] }, multiple: Boolean, loading: Boolean, error: { type: String, default: "" } });
const emit = defineEmits(["update:modelValue", "refresh"]);
const query = ref("");
const opened = ref(false);
const picker = ref(null);
const inputName = `container-picker-${useId()}`;
const visible = computed(() => props.containers.filter(c => !c.manualOnly && (!query.value.trim() || `${c.name || ''} ${c.image || ''} ${c.composeService || ''}`.toLowerCase().includes(query.value.trim().toLowerCase()))));
const summary = computed(() => !props.modelValue.length ? (props.multiple ? "点击选择多个容器" : "点击选择容器") : props.multiple ? `已选择 ${props.modelValue.length} 个容器` : props.modelValue[0].containerName || props.modelValue[0].composeService || "已保存容器");
const selected = c => props.modelValue.some(t => matchesContainerTarget(t, c));
const available = t => props.containers.some(c => !c.manualOnly && matchesContainerTarget(t, c));
function closePicker() { if (picker.value) { picker.value.open = false; picker.value.querySelector('summary')?.focus(); } }
function choose(container) { emit("update:modelValue", props.multiple ? toggleContainerTarget(props.modelValue, container) : [containerTarget(container)]); if (!props.multiple) closePicker(); }
function selectVisible() { emit("update:modelValue", addVisibleTargets(props.modelValue, visible.value)); }
function remove(index) { emit("update:modelValue", props.modelValue.filter((_, i) => i !== index)); }
watch(() => props.multiple, () => { query.value = ""; });
</script>

<style scoped>
.container-picker{display:grid;gap:10px}.container-picker-trigger{display:flex;align-items:center;gap:10px;min-height:44px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;cursor:pointer;list-style:none;background:var(--panel)}.container-picker-trigger::-webkit-details-marker{display:none}.container-picker-trigger span{flex:1}.container-picker-trigger:focus-visible{outline:2px solid var(--blue);outline-offset:3px}.container-picker-panel{margin-top:8px;padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}.container-picker-search{display:flex;align-items:center;gap:8px}.container-picker-search input{min-width:0;flex:1}.container-picker-search button{flex:0 0 38px;padding:0}.container-picker-options{display:grid;gap:4px;max-height:260px;overflow:auto;margin-top:10px}.container-picker-option{display:flex;align-items:center;gap:10px;padding:10px;border-radius:6px;cursor:pointer}.container-picker-option:hover,.container-picker-option.selected{background:var(--panel-soft)}.container-picker-option input{width:17px;min-height:17px;height:17px;flex:0 0 17px;accent-color:var(--blue)}.container-picker-option span{display:grid;gap:3px;min-width:0;flex:1}.container-picker-option strong{font-size:13px;overflow-wrap:anywhere}.container-picker-option small{color:var(--muted);font-size:12px;overflow-wrap:anywhere}.container-picker-option em{font-size:11px;font-style:normal;color:var(--muted);flex:0 0 auto}.container-picker-actions{display:flex;justify-content:space-between;gap:8px;margin-top:10px}.container-picker-actions button{font-size:12px;min-height:32px}.container-picker-selection{display:flex;flex-wrap:wrap;gap:7px}.container-picker-selection>span{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);padding:4px 5px 4px 9px;border-radius:6px;font-size:12px;overflow-wrap:anywhere}.container-picker-selection small{color:var(--muted)}.container-picker-selection button{min-height:26px;width:26px;padding:0;border:0;background:transparent}.container-picker-empty{display:grid;justify-items:start;gap:10px;padding:18px 8px;color:var(--muted)}.container-picker-loading{display:grid;gap:8px;padding:12px 0;color:var(--muted);font-size:12px}.container-picker-loading span{height:35px;border-radius:6px;background:var(--panel-soft)}.container-picker-done{margin-top:12px;width:100%}
</style>
