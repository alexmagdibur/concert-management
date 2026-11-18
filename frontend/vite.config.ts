import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxy = {
    '/api': {
      target: env.API_TARGET || 'http://127.0.0.1:8000',
      rewrite: (path: string) => path.replace(/^\/api(?=\/|$)/, ''),
    },
  }
  return {
    plugins: [react(), tailwindcss()],
    cacheDir: '.vite-cache',
    server: { host: '127.0.0.1', strictPort: true, proxy },
    preview: { host: '127.0.0.1', strictPort: true, proxy },
  }
})
