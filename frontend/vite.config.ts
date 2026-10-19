import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: the app calls /api on its own origin and Vite forwards it to FastAPI (no CORS).
// Production: FastAPI serves frontend/dist itself, so /api is the same origin there too.
const API = process.env.VILLA_API ?? "http://127.0.0.1:8040";

export default defineConfig({
  plugins: [react()],
  // three.js (~570 kB) only loads in its own lazy chunk when a 3D view opens; the main bundle stays small.
  build: { chunkSizeWarningLimit: 700 },
  server: { port: 5176, strictPort: true, proxy: { "/api": { target: API, timeout: 300_000, proxyTimeout: 300_000 } } },
});
