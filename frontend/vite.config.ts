import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/matches": "http://127.0.0.1:8000",
      "/predictions": "http://127.0.0.1:8000",
      "/opportunities": "http://127.0.0.1:8000",
      "/odds": "http://127.0.0.1:8000",
      "/backtests": "http://127.0.0.1:8000",
      "/models": "http://127.0.0.1:8000",
      "/analytics": "http://127.0.0.1:8000",
      "/quality": "http://127.0.0.1:8000",
      "/data": "http://127.0.0.1:8000",
      "/fixtures": "http://127.0.0.1:8000",
      "/competitions": "http://127.0.0.1:8000",
      "/dashboard": "http://127.0.0.1:8000",
      "/analysis": "http://127.0.0.1:8000",
    },
  },
});
