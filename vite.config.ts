import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// Keep /compare on the React SPA route while legacy compare.html still exists at repo root.
const forceSpaCompareRoute = (): Plugin => ({
  name: "force-spa-compare-route",
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      if (req.url === "/compare" || req.url?.startsWith("/compare?")) {
        req.url = "/";
      }
      next();
    });
  },
  configurePreviewServer(server) {
    server.middlewares.use((req, _res, next) => {
      if (req.url === "/compare" || req.url?.startsWith("/compare?")) {
        req.url = "/";
      }
      next();
    });
  },
});

export default defineConfig({
  plugins: [react(), forceSpaCompareRoute()],
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
