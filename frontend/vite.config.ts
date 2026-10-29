import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  envDir: fileURLToPath(new URL('..', import.meta.url)),
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // Em containers com volume montado do Windows/macOS, eventos de arquivo não chegam.
    watch: process.env.VITE_USE_POLLING === 'true' ? { usePolling: true, interval: 300 } : undefined,
  },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true },
})
