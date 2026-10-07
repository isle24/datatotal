<template>
  <dialog ref="dialog" class="modal narrow" :aria-labelledby="titleId" @cancel.prevent="answer(false)">
    <div class="modal-box confirmation-box">
      <h3 :id="titleId">{{ title }}</h3>
      <p class="confirmation-message">{{ message }}</p>
      <div class="edit-actions">
        <button type="button" @click="answer(false)">{{ cancelLabel }}</button>
        <button type="button" :class="danger ? 'danger' : 'primary-button'" @click="answer(true)">{{ confirmLabel }}</button>
      </div>
    </div>
  </dialog>
</template>
<script setup>
import { nextTick, onUnmounted, ref, useId } from "vue";
const dialog = ref(null), message = ref(""), title = ref("确认操作");
const confirmLabel = ref("确认"), cancelLabel = ref("取消"), danger = ref(true);
const titleId = `confirm-${useId()}`;
let resolvePending = null;
function answer(value) { dialog.value?.close(); const resolve = resolvePending; resolvePending = null; resolve?.(value); }
async function ask(text, options = {}) {
  if (resolvePending) return false;
  message.value = text; title.value = options.title || "确认操作";
  confirmLabel.value = options.confirmLabel || "确认"; cancelLabel.value = options.cancelLabel || "取消"; danger.value = options.danger !== false;
  const result = new Promise(resolve => { resolvePending = resolve; });
  await nextTick();
  if (dialog.value?.isConnected) dialog.value.showModal(); else answer(false);
  return result;
}
onUnmounted(() => answer(false));
defineExpose({ ask });
</script>
<style scoped>
.confirmation-box{max-width:520px;display:grid;gap:18px}.confirmation-message{line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere}.confirmation-box .edit-actions{justify-content:flex-end;flex-wrap:wrap}
</style>
