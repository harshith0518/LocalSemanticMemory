import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/assets/",
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: {
    outDir: "../src/jarvis/web",
    emptyOutDir: true,
    sourcemap: false,
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        entryFileNames: "app.js",
        chunkFileNames: "[name]-[hash].js",
        assetFileNames: ({ names }) =>
          names?.some((name) => name.endsWith(".css"))
            ? "app.css"
            : "[name]-[hash][extname]",
      },
    },
  },
});
