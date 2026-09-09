<template>
  <div ref="element" class="ds-chart" role="img" :aria-label="label"></div>
</template>
<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from "vue";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
]);
const props = defineProps({
  points: { type: Array, default: () => [] },
  dark: Boolean,
  history: Boolean,
  start: Number,
  end: Number,
  label: { type: String, default: "网卡上行与下行趋势" },
});
const element = ref();
let chart, observer;
function draw() {
  if (!chart) return;
  const color = props.dark ? "#aebcb8" : "#62726e";
  const unit = props.history ? "MiB" : "KiB/s";
  const divisor = props.history ? 1048576 : 1024;
  chart.setOption(
    {
      animation: false,
      color: ["#0f9d82", "#d65a7c"],
      grid: { left: 62, right: 24, top: 42, bottom: 30 },
      legend: { top: 0, right: 16, textStyle: { color } },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v) => `${Number(v).toFixed(2)} ${unit}`,
      },
      xAxis: {
        type: "time",
        min: props.start ? props.start * 1000 : undefined,
        max: props.end ? props.end * 1000 : undefined,
        axisLabel: { color },
        axisLine: { lineStyle: { color: props.dark ? "#354740" : "#dce5e1" } },
      },
      yAxis: {
        type: "value",
        name: unit,
        min: 0,
        nameTextStyle: { color },
        axisLabel: { color },
        splitLine: { lineStyle: { color: props.dark ? "#283c34" : "#edf1ef" } },
      },
      series: [
        ["下行", "rx"],
        ["上行", "tx"],
      ].map(([name, key]) => ({
        name,
        type: "line",
        smooth: true,
        showSymbol: props.points.length < 3,
        symbolSize: 6,
        connectNulls: false,
        lineStyle: { width: 2 },
        areaStyle: { opacity: 0.07 },
        data: props.points.map((p) => [
          p.timestamp * 1000,
          p[key] == null ? null : p[key] / divisor,
        ]),
      })),
    },
    { notMerge: true },
  );
}
onMounted(() => {
  chart = echarts.init(element.value);
  observer = new ResizeObserver(() => chart.resize());
  observer.observe(element.value);
  draw();
});
watch(
  () => [props.points, props.dark, props.start, props.end],
  () => nextTick(draw),
);
onUnmounted(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>
