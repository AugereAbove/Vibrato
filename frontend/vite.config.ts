import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const backend = process.env.VIBRATO_API ?? 'http://127.0.0.1:8765'
const proxy = { '/api': { target: backend, changeOrigin: false } }

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 1200,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
    restoreMocks: true,
  },
})
