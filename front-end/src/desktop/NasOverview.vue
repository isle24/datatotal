<template>
  <div class="dn-overview">
    <div class="dn-overview-title">
      <div>
        <span class="dn-caption">{{ targetName }}</span>
        <h2>网络运行概览</h2>
        <p>{{ updated }} · {{ connectionSource }}</p>
      </div>
      <button class="ds-button" @click="analyze">
        <Sparkles :size="16" />AI 分析
      </button>
    </div>
    <div class="dn-stat-grid">
      <button
        class="dn-stat"
        @click="openConnections({ scope: 'wan', direction: 'rx' })"
      >
        <span><ArrowDown class="dn-rx" :size="18" />公网下行</span
        ><strong>{{ bytes(summary.wan?.rxBps) }}<small>/s</small></strong
        ><small>累计 {{ bytes(summary.wan?.rxBytes) }}</small>
      </button>
      <button
        class="dn-stat"
        @click="openConnections({ scope: 'wan', direction: 'tx' })"
      >
        <span><ArrowUp class="dn-tx" :size="18" />公网上行</span
        ><strong>{{ bytes(summary.wan?.txBps) }}<small>/s</small></strong
        ><small>累计 {{ bytes(summary.wan?.txBytes) }}</small>
      </button>
      <button class="dn-stat" @click="openConnections({ scope: 'wan' })">
        <span><Network :size="18" />公网连接</span
        ><strong>{{ connections.wan || 0 }}<small>条</small></strong
        ><small>总连接 {{ connections.total || 0 }}</small>
      </button>
      <button class="dn-stat" @click="navigate('docker')">
        <span><Container :size="18" />Docker 容器</span
        ><strong
          >{{ overview?.containerStatus?.containerCount ?? "—"
          }}<small>个</small></strong
        ><small
          >{{ overview?.containerStatus?.enabled ? "已接入" : "未接入" }} ·
          {{ overview?.containerStatus?.count || 0 }} 个端口</small
        >
      </button>
    </div>
    <section class="dn-chart-section">
      <div class="dn-section-title">
        <h3>公网实时趋势</h3>
        <span :class="['dn-live', { stale: !fresh }]"
          ><i></i>{{ fresh ? "正在采集" : "等待数据" }}</span
        >
      </div>
      <TrafficChart :points="points" :dark="dark" label="公网实时上下行速率" />
    </section>
    <div class="dn-bottom-grid">
      <section>
        <div class="dn-section-title">
          <h3>网络接口</h3>
          <button
            class="ds-icon"
            title="查看网卡"
            aria-label="查看网卡"
            @click="navigate('interfaces')"
          >
            <ArrowUpRight :size="18" />
          </button>
        </div>
        <div class="dn-network-row">
          <Network :size="26" />
          <div>
            <strong>{{ summary.interfaces?.up || 0 }} 个活跃接口</strong>
            <p>
              {{
                (overview?.captureInterfaces || []).join(" · ") ||
                "等待接口信息"
              }}
            </p>
          </div>
        </div>
        <div class="dn-lan">
          <span
            >内网下行
            <b class="dn-rx">{{ bytes(summary.lan?.rxBps) }}/s</b></span
          ><span
            >内网上行
            <b class="dn-tx">{{ bytes(summary.lan?.txBps) }}/s</b></span
          >
        </div>
      </section>
      <section>
        <div class="dn-section-title">
          <h3>最近告警</h3>
          <button
            class="ds-icon"
            title="监控中心"
            aria-label="监控中心"
            @click="navigate('monitor')"
          >
            <ArrowUpRight :size="18" />
          </button>
        </div>
        <div
          v-for="alert in (overview?.alerts || []).slice(0, 3)"
          :key="alert.id"
          class="dn-alert"
        >
          <Bell :size="16" /><span>{{ alert.message }}</span>
        </div>
        <p v-if="!overview?.alerts?.length" class="dn-no-alert">
          <ShieldCheck :size="25" />暂无告警
        </p>
      </section>
    </div>
  </div>
</template>
<script setup>
import { ref, watch, computed } from "vue";
import {
  ArrowDown,
  ArrowUp,
  Network,
  Container,
  Sparkles,
  ArrowUpRight,
  Bell,
  ShieldCheck,
} from "@lucide/vue";
import TrafficChart from "./TrafficChart.vue";
const props = defineProps({
  summary: Object,
  overview: Object,
  connections: Object,
  connectionSource: String,
  fresh: Boolean,
  updated: String,
  openConnections: Function,
  navigate: Function,
  analyze: Function,
  targetName: String,
  theme: String,
});
const points = ref([]);
const dark = computed(() => props.theme === "dark");
watch(
  () => props.overview,
  () => {
    if (props.fresh)
      points.value = [
        ...points.value,
        {
          timestamp: Date.now() / 1000,
          rx: props.summary.wan?.rxBps || 0,
          tx: props.summary.wan?.txBps || 0,
        },
      ].slice(-60);
  },
  { immediate: true },
);
function bytes(value) {
  if (!Number.isFinite(value)) return "—";
  const n = Math.min(4, Math.floor(Math.log2(Math.max(1, value)) / 10));
  return `${(value / 1024 ** n).toFixed(n ? 1 : 0)} ${["B", "KiB", "MiB", "GiB", "TiB"][n]}`;
}
</script>
