import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // Output to sibling static/ directory for FastAPI to serve
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    // Proxy API requests to FastAPI backend during development
    proxy: {
      '/api': {
        target: 'http://localhost:9876',
        changeOrigin: true,
      },
      '/feedback': {
        target: 'http://localhost:9876',
        changeOrigin: true,
      },
      '/more': {
        target: 'http://localhost:9876',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:9876',
        changeOrigin: true,
      },
    },
  },
})
