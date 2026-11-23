<template><canvas ref="canvas" class="traffic-field-canvas" aria-hidden="true" /></template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from "vue";
import { isPageHidden } from "../api/visibility.js";

const props = defineProps({ rxRate: Number, txRate: Number, theme: String });
const canvas = ref(null);
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let context, resizeObserver, visibilityObserver;
let width = 0, height = 0, frame = 0, lastFrame = 0, phase = 0;
let visible = false;
let rxColor, txColor;

function draw() {
  if (!width || !height) return;
  context.clearRect(0, 0, width, height);
  const rx = Math.min(1, Math.log1p((props.rxRate || 0) / 1024) / 11);
  const tx = Math.min(1, Math.log1p((props.txRate || 0) / 1024) / 11);
  const waves = [
    { color: rxColor, strength: rx, base: .61, speed: 1, opacity: .52 },
    { color: rxColor, strength: rx, base: .69, speed: 1.3, opacity: .23 },
    { color: txColor, strength: tx, base: .77, speed: -.85, opacity: .44 },
  ];
  for (const [index, wave] of waves.entries()) {
    const amplitude = height * (.04 + wave.strength * .14);
    context.beginPath();
    for (let step = 0; step <= 72; step++) {
      const position = step / 72;
      const envelope = Math.sin(position * Math.PI);
      const ripple = Math.sin(position * 14 + index + phase * wave.speed) + .25 * Math.cos(position * 9 - phase);
      const y = height * wave.base + ripple * amplitude * envelope;
      if (step === 0) context.moveTo(0, y);
      else context.lineTo(position * width, y);
    }
    context.strokeStyle = wave.color;
    context.globalAlpha = wave.opacity;
    context.lineWidth = index === 1 ? 1 : 1.5;
    context.stroke();
  }
}
function tick(time) {
  if (time - lastFrame >= 32) {
    phase += .045;
    draw();
    lastFrame = time;
  }
  frame = requestAnimationFrame(tick);
}
function updateAnimation() {
  cancelAnimationFrame(frame);
  if (visible && !isPageHidden()) {
    draw();
    if (!reducedMotion.matches) frame = requestAnimationFrame(tick);
  }
}
function readColors() {
  const style = getComputedStyle(canvas.value);
  rxColor = style.getPropertyValue("--rx-color").trim();
  txColor = style.getPropertyValue("--tx-color").trim();
  if (visible && !isPageHidden()) draw();
}

onMounted(() => {
  context = canvas.value.getContext("2d");
  if (!context) return;
  readColors();
  resizeObserver = new ResizeObserver(([entry]) => {
    ({ width, height } = entry.contentRect);
    const scale = Math.min(devicePixelRatio, 1.5);
    canvas.value.width = Math.round(width * scale);
    canvas.value.height = Math.round(height * scale);
    context.setTransform(scale, 0, 0, scale, 0, 0);
    if (visible && !isPageHidden()) draw();
  });
  resizeObserver.observe(canvas.value);
  visibilityObserver = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    updateAnimation();
  });
  visibilityObserver.observe(canvas.value);
  reducedMotion.addEventListener("change", updateAnimation);
  document.addEventListener("visibilitychange", updateAnimation);
});
watch(() => props.theme, readColors, { flush: "post" });
watch(() => [props.rxRate, props.txRate], () => {
  if (visible && !isPageHidden() && reducedMotion.matches) draw();
});
onUnmounted(() => {
  cancelAnimationFrame(frame);
  resizeObserver?.disconnect();
  visibilityObserver?.disconnect();
  reducedMotion.removeEventListener("change", updateAnimation);
  document.removeEventListener("visibilitychange", updateAnimation);
});
</script>

<style scoped>
.traffic-field-canvas { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
</style>
