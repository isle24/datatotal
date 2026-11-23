<template>
  <component :is="as" class="spotlight-card" @pointermove="move">
    <slot />
  </component>
</template>

<script setup>
defineProps({ as: { type: String, default: "div" } });

function move(event) {
  if (event.pointerType !== "mouse") return;
  const card = event.currentTarget;
  const rect = card.getBoundingClientRect();
  card.style.setProperty("--spot-x", `${event.clientX - rect.left}px`);
  card.style.setProperty("--spot-y", `${event.clientY - rect.top}px`);
}
</script>
