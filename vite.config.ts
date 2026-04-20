import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8766",
        changeOrigin: true,
        ws: false,
        configure: (proxy) => {
          proxy.on("error", (err) => {
            console.error("proxy /api error:", err.message);
          });
        },
      },
      "/project.json": {
        target: "http://127.0.0.1:8766",
        changeOrigin: true,
        ws: false,
      },
      "/source_index.json": {
        target: "http://127.0.0.1:8766",
        changeOrigin: true,
        ws: false,
      },
      "/annotations": {
        target: "http://127.0.0.1:8766",
        changeOrigin: true,
        ws: false,
      },
      "/audio": {
        target: "http://127.0.0.1:8766",
        changeOrigin: true,
        ws: false,
      },
    },
  },
  test: {
    exclude: [
      '**/node_modules/**',
      'src/__tests__/apiRegression*.test.ts',  // live integration tests — run with: npx vitest run --config vitest.integration.ts
    ],
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
