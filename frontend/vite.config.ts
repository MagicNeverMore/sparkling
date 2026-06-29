import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// 开发期前端 5173，API 代理到后端端口（读取 backend/.env 的 SPARKLING_PORT）
export default defineConfig(({ mode }) => {
  const backendEnv = loadEnv(mode, path.resolve(__dirname, '../backend'), 'SPARKLING_')
  const backendPort = backendEnv.SPARKLING_PORT || '8000'

  return {
    build: {
      outDir: '../backend/app/frontend',
      emptyOutDir: true,
    },
    plugins: [
      react(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['favicon.ico'],
        manifest: {
          name: 'Sparkling',
          short_name: 'Sparkling',
          description: '本地优先的碎片想法管理工具',
          theme_color: '#0f172a',
          background_color: '#0f172a',
          display: 'standalone',
          start_url: '/',
          icons: [
            // 占位：图标资源在 Task #9 补齐
          ],
        },
        workbox: {
          runtimeCaching: [
            {
              urlPattern: ({ url }) =>
                url.pathname.startsWith('/api/atoms') ||
                url.pathname.startsWith('/api/graph'),
              handler: 'StaleWhileRevalidate',
              options: { cacheName: 'sparkling-api' },
            },
          ],
        },
      }),
    ],
    server: {
      proxy: {
        '/api': `http://127.0.0.1:${backendPort}`,
        '/ws': { target: `ws://127.0.0.1:${backendPort}`, ws: true },
      },
    },
  }
})
