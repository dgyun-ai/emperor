import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fixA2uiCssModules, fixA2uiCssModulesEsbuildPlugin } from "./vite-plugins/fixA2uiCssModules";

export default defineConfig({
  plugins: [react(), fixA2uiCssModules()],
  build: {
    outDir: "../src/dashboard/static",
    emptyOutDir: true,
  },
  optimizeDeps: {
    esbuildOptions: {
      plugins: [fixA2uiCssModulesEsbuildPlugin()],
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:9119",
    },
  },
});
