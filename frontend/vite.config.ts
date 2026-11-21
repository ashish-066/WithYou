import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: Number(process.env.PORT) || 3000,
    // Phone testing: `npm run dev:phone` serves on the LAN; a Cloudflare quick
    // tunnel (*.trycloudflare.com) gives the HTTPS a phone needs for the mic
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      '/api': {
        // API_PROXY_TARGET: point at another local API (e.g. a second one on :8002)
        target: process.env.API_PROXY_TARGET || 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
