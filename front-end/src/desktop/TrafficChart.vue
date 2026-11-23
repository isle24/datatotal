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
  const style = getComputedStyle(element.value);
  const token = (name) => style.getPropertyValue(name).trim();
  const color = token("--muted");
  const directions = [["下行", "rx", token("--rx-color")], ["上行", "tx", token("--tx-color")]];
  const unit = props.history ? "MiB" : "KiB/s";
  const divisor = props.history ? 1048576 : 1024;
  chart.setOption(
    {
      animation: false,
      color: directions.map(([, , directionColor]) => directionColor),
      grid: { left: 62, right: 24, top: 42, bottom: 30 },
      legend: { top: 0, right: 16, textStyle: { color } },
      tooltip: {
        trigger: "axis",
        confine: true,
        backgroundColor: token("--glass"),
        borderColor: token("--line"),
        textStyle: { color: token("--text"), fontSize: 12 },
        extraCssText: "backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border-radius: 10px; font-variant-numeric: tabular-nums;",
        valueFormatter: (v) => `${Number(v).toFixed(2)} ${unit}`,
      },
      xAxis: {
        type: "time",
        min: props.start ? props.start * 1000 : undefined,
        max: props.end ? props.end * 1000 : undefined,
        axisLabel: { color },
        axisLine: { lineStyle: { color: token("--line") } },
      },
      yAxis: {
        type: "value",
        name: unit,
        min: 0,
        nameTextStyle: { color },
        axisLabel: { color },
        splitLine: { show: false },
      },
      series: directions.map(([name, key, directionColor]) => ({
        name,
        type: "line",
        smooth: true,
        showSymbol: props.points.length < 3,
        symbolSize: 6,
        connectNulls: false,
        lineStyle: { width: 2 },
        areaStyle: {
          opacity: .18,
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: directionColor },
            { offset: 1, color: "transparent" },
          ]),
        },
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
