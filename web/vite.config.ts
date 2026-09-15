import path from "path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:18889",
        changeOrigin: true,
        // Chat and IR analysis use SSE; do not let the proxy buffer the stream.
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes, req) => {
            const url = req.url || "";
            if (url.includes("/api/agent") || url.includes("/analyze") || url.includes("/explain-selection") || url.includes("/speaking")) {
              proxyRes.headers["cache-control"] = "no-cache";
              proxyRes.headers["x-accel-buffering"] = "no";
            }
          });
        },
      },
    },
  },
});
