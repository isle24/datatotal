<template>
  <section class="ds-settings-section ds-updater">
    <div class="ds-section-title">
      <h2><Download :size="19" />客户端更新</h2>
      <span class="ds-muted">v{{ version }}</span>
    </div>
    <label class="ds-setting-row"
      ><span><strong>启动时检查更新</strong></span
      ><input
        type="checkbox"
        :checked="automatic"
        @change="$emit('automatic', $event.target.checked)"
    /></label>
    <div class="ds-update-status" role="status">
      <strong>{{ status }}</strong
      ><span v-if="updateState.version">v{{ updateState.version }}</span>
    </div>
    <p v-if="updateState.error" class="ds-error">
      更新失败：{{ updateState.error }}
    </p>
    <p v-if="updateState.notes" class="ds-update-notes">
      {{ updateState.notes }}
    </p>
    <progress
      v-if="updateState.phase === 'downloading'"
      :value="updateState.total ? updateState.downloaded : undefined"
      :max="updateState.total || 1"
    ></progress>
    <div class="ds-actions">
      <button class="ds-button" :disabled="busy" @click="updates.check()">
        <RefreshCw :size="16" />检查更新</button
      ><button
        v-if="updateState.phase === 'available'"
        class="ds-button ds-primary"
        @click="install"
      >
        <Download :size="16" />下载并安装</button
      ><button
        v-if="updateState.phase === 'installed'"
        class="ds-button ds-primary"
        @click="relaunch"
      >
        <RotateCw :size="16" />重启客户端</button
      ><button
        class="ds-button"
        @click="
          invoke('open_external', {
            url: 'https://github.com/isle24/datatotal/releases?q=desktop-v',
          })
        "
      >
        <ExternalLink :size="16" />版本下载
      </button>
    </div>
  </section>
</template>
<script setup>
import { computed } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { confirm } from "@tauri-apps/plugin-dialog";
import { relaunch } from "@tauri-apps/plugin-process";
import { Download, RefreshCw, RotateCw, ExternalLink } from "@lucide/vue";
import { updates, updateState } from "./updater.js";
defineProps({ version: String, automatic: Boolean });
defineEmits(["automatic"]);
const busy = computed(() =>
  ["checking", "downloading", "installing", "installed"].includes(
    updateState.phase,
  ),
);
const status = computed(
  () =>
    ({
      idle: "尚未检查",
      checking: "正在检查 GitHub Releases…",
      current: "已是最新版本",
      available: "发现新版本",
      downloading: `正在下载 ${Math.round(updateState.downloaded / 1024 / 1024)} MB`,
      installing: "正在安装…",
      installed: "安装完成，重启后生效",
      error: "暂时无法检查更新",
    })[updateState.phase],
);
async function install() {
  if (
    await confirm(
      `安装 Traffic Lens ${updateState.version}？安装将关闭或重启客户端，请先保存正在编辑的内容。`,
      { title: "安装更新", kind: "info" },
    )
  )
    await updates.install();
}
</script>
<style scoped>
.ds-updater h2 {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ds-update-status {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px 0;
  font-size: 14px;
}
.ds-update-status span {
  font-size: 12px;
  color: var(--ds-accent);
}
.ds-update-notes {
  white-space: pre-wrap;
  color: var(--ds-muted);
  font-size: 13px;
  max-height: 220px;
  overflow: auto;
}
.ds-updater progress {
  width: 100%;
  margin-bottom: 18px;
  accent-color: var(--ds-accent);
}
</style>
