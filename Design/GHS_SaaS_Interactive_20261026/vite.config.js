import { defineConfig } from "vite";
export default defineConfig({
  esbuild: { jsx: "automatic" },
  build: {
    rollupOptions: {
      onwarn(warning, warn) {
        if (
          warning.code === "MODULE_LEVEL_DIRECTIVE" &&
          warning.message.includes("use client")
        )
          return;
        warn(warning);
      },
      output: {
        manualChunks(id) {
          if (
            id.includes("/node_modules/echarts/") ||
            id.includes("/node_modules/zrender/")
          )
            return "charts";
          if (
            id.includes("/node_modules/motion/") ||
            id.includes("/node_modules/framer-motion/")
          )
            return "motion";
          if (id.includes("/node_modules/lucide-react/")) return "icons";
        },
      },
    },
  },
});
