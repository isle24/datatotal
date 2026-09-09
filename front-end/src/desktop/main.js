import { createApp } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { setDesktopHidden } from "../api/visibility.js";
import DesktopShell from "./DesktopShell.vue";
import "../styles.css";
import "./desktop.css";
createApp(DesktopShell).mount("#app");
listen("desktop-visibility", ({ payload }) => setDesktopHidden(!payload));
document.addEventListener(
  "click",
  (event) => {
    const anchor = event.target.closest?.("a");
    if (!anchor || anchor.getAttribute("href")?.startsWith("#")) return;
    event.preventDefault();
    const url = new URL(anchor.href);
    if (["http:", "https:"].includes(url.protocol))
      invoke("open_external", { url: url.href }).catch(console.warn);
  },
  true,
);
