import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

declare const process: { env: Record<string, string | undefined> };

export function resolveParseApiTarget(env: Record<string, string | undefined> = process.env): string {
  const port = (env.PARSE_API_PORT ?? env.PARSE_PORT ?? "8766").trim() || "8766";
  return `http://127.0.0.1:${port}`;
}

const parseApiTarget = resolveParseApiTarget();

export default defineConfig({
  define: {
    __PARSE_API_TARGET__: JSON.stringify(parseApiTarget),
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: parseApiTarget,
        changeOrigin: true,
        ws: false,
        configure: (proxy) => {
          proxy.on("error", (err) => {
            console.error("proxy /api error:", err.message);
          });
        },
      },
      "/project.json": {
        target: parseApiTarget,
        changeOrigin: true,
        ws: false,
      },
      "/source_index.json": {
        target: parseApiTarget,
        changeOrigin: true,
        ws: false,
      },
      "/annotations": {
        target: parseApiTarget,
        changeOrigin: true,
        ws: false,
      },
      "/audio": {
        target: parseApiTarget,
        changeOrigin: true,
        ws: false,
      },
      "/peaks": {
        target: parseApiTarget,
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
