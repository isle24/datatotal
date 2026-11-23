<template>
  <section class="view portal" aria-label="首页">
    <div class="portal-tools">
      <slot name="tools" />
    </div>
    <div class="portal-inner">
      <div class="portal-brand">
        <span class="portal-mark"><Activity :size="34" aria-hidden="true" /></span>
        <h2>NAS Traffic Lens</h2>
        <button class="portal-status" type="button" title="进入概览" @click="emit('navigate', 'overview')">
          <span :class="['live-dot', { pending: !fresh }]" aria-hidden="true"></span>
          {{ status }}
        </button>
      </div>

      <div class="portal-search">
        <Search :size="18" aria-hidden="true" />
        <input
          ref="searchInput"
          v-model="query"
          type="search"
          autocomplete="off"
          spellcheck="false"
          placeholder="搜索服务或页面，回车直达"
          aria-label="搜索服务或页面"
          @keydown.enter.prevent="emit('submit')"
          @keydown.esc="query = ''"
        />
        <kbd v-if="!searching">/</kbd>
        <button v-else class="portal-search-clear" type="button" aria-label="清除搜索" @click="query = ''; focusSearch()"><X :size="15" /></button>
      </div>

      <p v-if="error" class="portal-empty" role="status">{{ error }}</p>
      <div v-if="services.length" class="portal-services">
        <SpotlightCard v-for="entry in services" :key="entry.id" as="button" class="portal-service" type="button" :title="entry.url" @click="emit('open-service', entry)">
          <span class="portal-service-logo">
            <img v-if="entry.icon" :src="entry.icon" alt="" loading="lazy" />
            <Globe v-else :size="21" aria-hidden="true" />
          </span>
          <strong>{{ entry.name }}</strong>
          <small>{{ entry.notes || address(entry.url) }}</small>
        </SpotlightCard>
      </div>
      <div v-else-if="loading" class="portal-services" aria-hidden="true">
        <span v-for="index in 4" :key="index" class="skeleton skeleton-service"></span>
      </div>
      <p v-else-if="searching && !pages.length" class="portal-empty" role="status">没有匹配的服务或页面</p>
      <button v-else-if="!searching && !error" class="portal-add" type="button" @click="emit('navigate', 'navigation')"><Plus :size="16" />添加常用服务</button>

      <nav v-if="pages.length" class="portal-links" aria-label="快捷入口">
        <button v-for="item in pages" :key="item.key" type="button" @click="emit('navigate', item.key)">{{ item.label }}</button>
      </nav>
      <div class="portal-hint">
        <span>按 <kbd>/</kbd> 搜索 ·</span>
        <button type="button" :aria-expanded="menuOpen" @click="emit('toggle-menu')"><kbd>m</kbd> 打开全部页面</button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";
import { Activity, Globe, Plus, Search, X } from "@lucide/vue";
import SpotlightCard from "./SpotlightCard.vue";

defineProps({ status: String, fresh: Boolean, services: Array, pages: Array, error: String, loading: Boolean, searching: Boolean, address: Function, menuOpen: Boolean });
const emit = defineEmits(["navigate", "submit", "open-service", "toggle-menu"]);
const query = defineModel("query", { type: String, required: true });
const searchInput = ref(null);
function focusSearch() { searchInput.value?.focus(); }
defineExpose({ focusSearch });
</script>
