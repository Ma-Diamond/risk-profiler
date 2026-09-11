import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The frontend calls a relative "/api" path everywhere (see API_BASE in
// App.jsx etc.) rather than hardcoding a host — this dev-server proxy
// makes that transparent for local development by forwarding /api/* to
// the local backend, stripping the /api prefix (the backend's own
// routes have no /api prefix, e.g. GET /portfolios not GET /api/portfolios).
// In production, nginx does the equivalent (see deploy notes).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
