import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/ui/",
  build: {
    outDir: "../src/mcp_stack/gateway/static",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8090",
      "/health": "http://127.0.0.1:8090",
      "/ready": "http://127.0.0.1:8090",
      "/ui/login": "http://127.0.0.1:8090",
      "/mcp": "http://127.0.0.1:8090",
      "/profiles": "http://127.0.0.1:8090",
      "/servers": "http://127.0.0.1:8090",
    },
  },
});
