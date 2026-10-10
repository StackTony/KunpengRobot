import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5180,
    open: false,
    proxy: {
      // 后端 API (uvicorn :8000); SSE 需关闭缓冲保证流式输出
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // SSE: 响应直通, 不缓冲 (EventSource / llm 打字机依赖)
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache'
              proxyRes.headers['x-accel-buffering'] = 'no'
            }
          })
        },
      },
    },
  },
})
