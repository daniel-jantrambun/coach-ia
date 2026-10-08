import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // En dev, l'API FastAPI tourne sur :8000 (uvicorn) ; même origine pour le cookie de session.
    proxy: { "/api": "http://localhost:8000" },
  },
});
