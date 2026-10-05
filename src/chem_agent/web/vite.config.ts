import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

const target = 'http://127.0.0.1:7860'
// Preserve the browser's Host and Origin together. FastAPI enforces their equality.
const proxy = {
  '/api': {
    target,
    changeOrigin: false,
  },
}

export default defineConfig({
  plugins: [vue()],
  base: '/',
  server: { proxy, host: '127.0.0.1', port: 5173, strictPort: true },
  preview: { proxy },
  build: { outDir: 'dist', assetsDir: 'assets', sourcemap: false },
  test: { environment: 'node', include: ['tests/**/*.test.ts'], clearMocks: true },
})
