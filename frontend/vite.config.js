import { defineConfig } from "vite";

export default defineConfig({
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      ...Object.fromEntries(
        ["/api", "/docs", "/openapi.json"].map((path) => [
          path,
          {
            target: process.env.TRAM_API_PROXY || "http://127.0.0.1:8000",
            changeOrigin: false,
          },
        ]),
      ),
    },
  },
  preview: { port: 4173, strictPort: true },
  build: { sourcemap: false },
});
