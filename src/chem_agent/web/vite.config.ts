import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

const webRoot = fileURLToPath(new URL('.', import.meta.url))

const target = 'http://127.0.0.1:7860'
// Preserve the browser's Host and Origin together. FastAPI enforces their equality.
const proxy = {
  '/api': {
    target,
    changeOrigin: false,
  },
}

export default defineConfig({
  // The backend keeps its demonstration index.html. Vite owns a separate entry.
  root: fileURLToPath(new URL('./client', import.meta.url)),
  plugins: [vue()],
  resolve: { alias: { '/src': fileURLToPath(new URL('./src', import.meta.url)) } },
  base: '/',
  server: { proxy, host: '127.0.0.1', port: 5173, strictPort: true, fs: { allow: [webRoot] } },
  preview: { proxy },
  build: { outDir: '../dist', emptyOutDir: true, assetsDir: 'assets', sourcemap: false },
  test: { root: webRoot, environment: 'node', include: ['tests/**/*.test.ts'], clearMocks: true },
})
