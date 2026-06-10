import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built assets are served by FastAPI under /static (see app/main.py), so the
// app must reference them from there. In dev (`npm run dev`), API calls are
// proxied to the uvicorn server on :8000 so the same relative fetch() paths
// work without CORS.
const API = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  base: '/static/',
  build: { outDir: 'dist', assetsDir: 'assets', emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      '/incidents': API,
      '/telemetry': API,
      '/traces': API,
      '/github': API,
      '/pipeline': { target: API, ws: false },
    },
  },
})
