import { reactive } from "vue";
import { check } from "@tauri-apps/plugin-updater";
import { updateController } from "./update-controller.js";
export const updateState = reactive({
  phase: "idle",
  version: "",
  notes: "",
  error: "",
  downloaded: 0,
  total: 0,
});
export const updates = updateController(updateState, check);
