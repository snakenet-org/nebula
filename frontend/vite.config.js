// @ai-purpose: Vite build config for the Nebula Vault SPA.
// @ai-context: Builds the Vue 3 + Tailwind frontend into ../public, which the FastAPI backend serves
//   as static files (see main.py). In `vite dev`, /api is proxied to the local Nebula API on :8000
//   so the SPA talks to the real backend during development. `@` resolves to `src/` (see
//   jsconfig.json's matching `paths` entry) — required by shadcn-vue's copied `ui/*` components,
//   which all import shared code via `@/lib/utils`/`@/components/ui/*`.
// @version: 1.1.0
// @author: Marc Fiedler <marc@snakenet.org>
// @date: 2026-08-06
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  // Emit the production build into the backend's public/ folder (served by FastAPI).
  build: {
    outDir: '../public',
    emptyOutDir: true,
  },
  // Dev-only: proxy same-origin API calls to the local Nebula backend on :8000.
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
});
