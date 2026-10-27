import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Forward /api to Flask so the browser sees one origin (no CORS setup).
    proxy: {
      '/api': 'http://localhost:5000',
    },
  },
})
