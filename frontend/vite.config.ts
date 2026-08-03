/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    watch: { usePolling: true, interval: 500 },
    allowedHosts: ['localhost', '127.0.0.1', 'narysai.drone-age.org'],
    proxy: {
      '/api': {
        target: 'http://api:8000',
        changeOrigin: false,
      },
    },
  },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', globals: true },
})
