/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// In Docker, nginx serves the built app and proxies /api to the backend.
// For `npm run dev`, /api is proxied to a backend on the host (default http://localhost:8000).
const devApiTarget = process.env.DEV_API_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { '/api': { target: devApiTarget, changeOrigin: true } },
  },
  build: { sourcemap: false },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    restoreMocks: true,
  },
});
