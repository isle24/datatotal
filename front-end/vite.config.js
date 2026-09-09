import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ mode }) => ({
  base: mode === "desktop" ? "./" : "/",
  plugins: [vue()],
  build: {
    outDir: mode === "desktop" ? "dist-desktop" : "dist",
    rollupOptions: mode === "desktop" ? { input: "desktop.html" } : undefined,
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8088",
    },
  },
}));
