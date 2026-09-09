<template><App /></template>
<script setup>
import { provide, onUnmounted } from "vue";
import { invoke, Channel } from "@tauri-apps/api/core";
import { confirm } from "@tauri-apps/plugin-dialog";
import App from "../App.vue";
import { createNasTransport } from "../api/transport.js";
const props = defineProps({ profile: Object, prompt: Function });
const emit = defineEmits(["expired"]);
const transport = createNasTransport({ profile: props.profile, invoke, Channel, confirm: (message) => confirm(message, { title: "NAS 操作确认", kind: "warning" }), prompt: props.prompt, onAuthenticationRequired: () => emit("expired") });
provide("trafficTransport", transport);
onUnmounted(() => transport.dispose());
</script>
