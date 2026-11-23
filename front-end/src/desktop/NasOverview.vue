<template>
  <div class="dn-overview">
    <TrafficOverviewHero :wan="summary.wan" :theme="theme" :target-name="targetName" :status="status" :fresh="fresh" :updated="updated" :format-bytes="formatBytes" :ai-loading="aiLoading" :analyze="analyze" :open-connections="openConnections" />
    <div class="dn-stat-grid">
      <SpotlightCard as="button" type="button" class="dn-stat" @click="openConnections({ scope: 'wan' })">
        <span><Network :size="18" />公网连接</span
        ><strong>{{ connections.wan || 0 }}<small>条</small></strong
        ><small>总连接 {{ connections.total || 0 }} · {{ connectionSource }}</small>
      </SpotlightCard>
      <SpotlightCard as="button" type="button" class="dn-stat" @click="navigate('docker')">
        <span><Container :size="18" />Docker 容器</span
        ><strong
          >{{ overview?.containerStatus?.containerCount ?? "—"
          }}<small>个</small></strong
        ><small
          >{{ overview?.containerStatus?.enabled ? "已接入" : "未接入" }} ·
          {{ overview?.containerStatus?.count || 0 }} 个端口</small
        >
      </SpotlightCard>
    </div>
    <section class="dn-chart-section">
      <div class="dn-section-title">
        <h3>公网实时趋势</h3>
        <span :class="['dn-live', { stale: !fresh }]"
          ><i></i>{{ fresh ? "正在采集" : "等待数据" }}</span
        >
      </div>
      <TrafficChart :points="points" :dark="theme === 'dark'" label="公网实时上下行速率" />
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
import {
  Network,
  Container,
  ArrowUpRight,
  Bell,
  ShieldCheck,
} from "@lucide/vue";
import TrafficChart from "./TrafficChart.vue";
import TrafficOverviewHero from "../components/TrafficOverviewHero.vue";
import SpotlightCard from "../components/SpotlightCard.vue";
defineProps({
  summary: Object,
  overview: Object,
  connections: Object,
  connectionSource: String,
  fresh: Boolean,
  updated: String,
  status: String,
  points: Array,
  aiLoading: Boolean,
  formatBytes: Function,
  openConnections: Function,
  navigate: Function,
  analyze: Function,
  targetName: String,
  theme: String,
});
function bytes(value) {
  if (!Number.isFinite(value)) return "—";
  const n = Math.min(4, Math.floor(Math.log2(Math.max(1, value)) / 10));
  return `${(value / 1024 ** n).toFixed(n ? 1 : 0)} ${["B", "KiB", "MiB", "GiB", "TiB"][n]}`;
}
</script>
