// frontend/vite.config.ts
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  html: {
    cspNonce: "__CSP_NONCE__",
  },
  build: {
    outDir: "../src/weatherbot/web/static",
    emptyOutDir: true,
    sourcemap: false,
    license: {
      fileName: "licenses.json",
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        headers: {
          Origin: "http://127.0.0.1:8765",
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: false,
    restoreMocks: true,
  },
});
