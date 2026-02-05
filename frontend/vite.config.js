import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api/planner': {
        target: 'http://localhost:8011',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/planner/, '') 
      },
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
     
      '/chart_api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },

      
    }
  }
})