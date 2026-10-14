import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  // Desktop packaging copies only public files referenced by the emitted bundle.
  build: { copyPublicDir: mode !== 'desktop' },
  plugins: [
    react(), tailwindcss(),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/classifier-api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
        timeout: 0,
        proxyTimeout: 0,
      },
      '/rag-api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
    },
  },
}))
