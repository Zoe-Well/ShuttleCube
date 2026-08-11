import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    proxy: {
      "/api": process.env.SHUTTLECUBE_API_URL ?? "http://localhost:8001",
    },
  },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], css: true },
});
