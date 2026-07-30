import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// Force Vite to clear its cache to fix the styled_default bug
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    force: true,
  },
  build: {

    // Split the heavy, rarely-changing vendor libraries out of the app chunk so
    // they stay cached across deploys instead of being re-downloaded whenever
    // application code changes. Without this everything landed in one bundle.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
          motion: ['framer-motion'],
          data: ['@tanstack/react-query', 'axios', 'zustand'],
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
