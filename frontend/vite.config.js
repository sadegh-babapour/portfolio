import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { transitApiBaseForMode } from './src/apiConfig.js'

const rootDirectory = fileURLToPath(new URL('.', import.meta.url))

// Records which API a built bundle targets, so a deployment can check it
// (ops/check_frontend_bundle.py) instead of trusting whatever dist/ holds.
function transitApiTargetManifest(mode, apiBase) {
  return {
    name: 'bizqlab-transit-api-target',
    apply: 'build',
    generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'transit-api-target.json',
        source: `${JSON.stringify({ mode, api_base: apiBase })}\n`,
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ command, mode, isPreview }) => {
  // Serving an existing dist/ (vite preview) embeds nothing, so it needs no target.
  if (isPreview) {
    return { base: '/', plugins: [react()] }
  }
  // Every build and dev server needs an explicit, valid target for its mode; a
  // missing or invalid one stops here with a clear error (src/apiConfig.js).
  const env = loadEnv(mode, rootDirectory, 'VITE_')
  const apiBase = transitApiBaseForMode(mode, env.VITE_TRANSIT_API_BASE_URL)
  return {
    base: command === 'build' ? '/calgary-transit-live/' : '/',
    plugins: [react(), transitApiTargetManifest(mode, apiBase)],
    define: {
      'import.meta.env.VITE_TRANSIT_API_BASE_URL': JSON.stringify(apiBase),
    },
    build: {
      rollupOptions: {
        input: {
          main: resolve(rootDirectory, 'index.html'),
          'pdf-viewer': resolve(rootDirectory, 'pdf-viewer.html'),
        },
      },
    },
  }
})
