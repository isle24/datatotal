<template>
  <div :class="{ 'dn-workspace': native }">
    <aside v-if="native" class="dn-sidebar">
      <div class="dn-sidebar-title">
        <Server :size="20" />
        <div>
          <strong>{{ profile.name }}</strong
          ><small>NAS 工作区</small>
        </div>
      </div>
      <nav aria-label="NAS 页面">
        <button
          v-for="item in pages"
          :key="item.id"
          :class="{ active: view === item.id }"
          @click="view = item.id"
        >
          <component :is="item.icon" :size="18" /><span>{{ item.name }}</span
          ><ChevronRight v-if="view === item.id" :size="14" />
        </button>
      </nav>
      <button class="dn-web-open" @click="transport.open(profile.url)">
        <ExternalLink :size="16" />在浏览器中打开
      </button>
    </aside>
    <div :class="{ 'dn-main': native }">
      <header v-if="native" class="dn-header">
        <div>
          <span>{{ profile.name }}</span
          ><ChevronRight :size="14" /><strong>{{
            pages.find((p) => p.id === view)?.name
          }}</strong>
        </div>
        <div>
          <span v-if="toast" role="status">{{ toast }}</span
          ><button
            class="ds-icon"
            title="刷新当前页面"
            aria-label="刷新当前页面"
            @click="app?.refresh()"
          >
            <RefreshCw :size="17" /></button
          ><button
            class="ds-icon"
            title="NAS 设置"
            aria-label="NAS 设置"
            @click="view = 'settings'"
          >
            <Settings :size="17" />
          </button>
        </div>
      </header>
      <App
        ref="app"
        :native="native"
        :view="view"
        :theme-mode="theme"
        :target-name="profile.name"
        @view="view = $event"
        @toast="toast = $event"
      >
        <template v-if="native" #overview="state"
          ><NasOverview
            v-bind="state"
            :target-name="profile.name"
            :theme="theme"
        /></template>
      </App>
    </div>
  </div>
</template>
<script setup>
import { provide, onUnmounted, ref } from "vue";
import { invoke, Channel } from "@tauri-apps/api/core";
import { confirm } from "@tauri-apps/plugin-dialog";
import App from "../App.vue";
import NasOverview from "./NasOverview.vue";
import {
  Activity,
  Network,
  History,
  Cpu,
  HardDrive,
  Server,
  ShieldCheck,
  Settings,
  Sparkles,
  Compass,
  ChevronRight,
  ExternalLink,
  RefreshCw,
} from "@lucide/vue";
import "./nas-workspace.css";
import { createNasTransport } from "../api/transport.js";
const props = defineProps({
  profile: Object,
  prompt: Function,
  native: Boolean,
  theme: String,
});
const app = ref(null),
  view = ref("overview"),
  toast = ref("");
const pages = [
  { id: "overview", name: "运行概览", icon: Activity },
  { id: "navigation", name: "服务导航", icon: Compass },
  { id: "interfaces", name: "网络接口", icon: Network },
  { id: "history", name: "流量历史", icon: History },
  { id: "processes", name: "进程与连接", icon: Cpu },
  { id: "system", name: "系统硬件", icon: HardDrive },
  { id: "docker", name: "Docker", icon: Server },
  { id: "monitor", name: "监控中心", icon: ShieldCheck },
  { id: "ai", name: "AI 中心", icon: Sparkles },
  { id: "settings", name: "NAS 设置", icon: Settings },
];
const emit = defineEmits(["expired", "theme"]);
const transport = createNasTransport({
  profile: props.profile,
  invoke,
  Channel,
  confirm: (message) =>
    confirm(message, { title: "NAS 操作确认", kind: "warning" }),
  prompt: props.prompt,
  onAuthenticationRequired: () => emit("expired"),
  onThemeChange: (value) => emit("theme", value),
});
provide("trafficTransport", transport);
onUnmounted(() => transport.dispose());
</script>
