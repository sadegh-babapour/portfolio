import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDirectory = fileURLToPath(new URL('.', import.meta.url))

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/calgary-transit-live/' : '/',
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(rootDirectory, 'index.html'),
        'pdf-viewer': resolve(rootDirectory, 'pdf-viewer.html'),
      },
    },
  },
}))
