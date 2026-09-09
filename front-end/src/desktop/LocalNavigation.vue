<template><NavigationView :repository="repository" scope="本机" /></template>
<script setup>
import { invoke } from "@tauri-apps/api/core";
import { confirm } from "@tauri-apps/plugin-dialog";
import NavigationView from "../components/NavigationView.vue";
const repository = {
  list: () => invoke("local_navigation"),
  save: (entry) => invoke("save_navigation", { entry }),
  remove: (id) => invoke("delete_navigation", { id }),
  open: (url) => invoke("open_external", { url }),
  confirm: (message) => confirm(message, { title: "导航", kind: "warning" }),
};
</script>
