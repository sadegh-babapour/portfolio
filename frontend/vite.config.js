// frontend/vite.config.js
// Replace the generated one with this after npm create vite
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// export default defineConfig({
//   plugins: [react()],
//   build: {
//     outDir: 'dist',
//     emptyOutDir: true,
//   },
//   base: '/map/',  // served at /map/ by FastAPI
// })

export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true },
  base: '/map/',
  server: {
    proxy: {
      '/api': 'http://localhost:8086'  // your local NiceGUI port
    }
  }
})