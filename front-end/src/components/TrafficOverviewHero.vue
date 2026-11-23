<template>
  <section class="traffic-hero" aria-label="公网流量">
    <TrafficFieldCanvas :rx-rate="wan?.rxBps" :tx-rate="wan?.txBps" :theme="theme" />
    <div class="traffic-hero-copy">
      <p class="traffic-hero-status">
        <span :class="['live-dot', { pending: !fresh }]" aria-hidden="true"></span>
        {{ [targetName, status, updated !== "-" ? updated : ""].filter(Boolean).join(" · ") }}
      </p>
      <h3>公网流量总览</h3>
      <p class="traffic-hero-meta"><span>当前公网总速率</span><strong>{{ wan ? formatBytes((wan.rxBps || 0) + (wan.txBps || 0)) + "/s" : "—" }}</strong></p>
      <button class="board-ai-button" type="button" :disabled="aiLoading" @click="analyze()"><Sparkles :size="16" />{{ aiLoading ? "分析中" : "AI 分析" }}</button>
    </div>
    <div class="traffic-hero-rates">
      <SpotlightCard
        v-for="metric in directions" :key="metric.key" as="button" type="button"
        class="traffic-rate" :class="`traffic-rate-${metric.key}`"
        :title="`查看${metric.label}连接`"
        @click="openConnections({ scope: 'wan', direction: metric.key })"
      >
        <span class="traffic-rate-label"><component :is="metric.icon" :size="17" />{{ metric.label }}速率<ArrowUpRight :size="15" class="traffic-rate-link" /></span>
        <strong>{{ wan ? formatBytes(wan[`${metric.key}Bps`]) + "/s" : "—" }}</strong>
        <span class="traffic-rate-total">采集累计 <b>{{ wan ? formatBytes(wan[`${metric.key}Bytes`]) : "—" }}</b></span>
      </SpotlightCard>
    </div>
  </section>
</template>

<script setup>
import { ArrowDownLeft, ArrowUpRight, Sparkles } from "@lucide/vue";
import SpotlightCard from "./SpotlightCard.vue";
import TrafficFieldCanvas from "./TrafficFieldCanvas.vue";

defineProps({ wan: Object, theme: String, targetName: String, status: String, updated: String, fresh: Boolean, aiLoading: Boolean, analyze: Function, openConnections: Function, formatBytes: Function });
const directions = [
  { key: "rx", label: "公网下行", icon: ArrowDownLeft },
  { key: "tx", label: "公网上行", icon: ArrowUpRight },
];
</script>
