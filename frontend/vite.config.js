import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

import { validateApiBaseUrl } from './src/utils/apiConfig.js'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Vite inlines VITE_* at build time, so a bundle built with a missing or
  // malformed API base URL can only fail once it reaches a browser. Validate it
  // here and let a bad value throw, which aborts the build before any bundle is
  // produced — the mistake surfaces in CI or at deploy time, not as a broken
  // page. The same validateApiBaseUrl the runtime resolver uses enforces the
  // rules, so the build guard and the app cannot disagree on what is valid.
  //
  // Only `mode === 'production'` (i.e. `npm run build`) is gated, and only there
  // is https required. `npm run dev` and vitest run in other modes and keep the
  // localhost HTTP fallback.
  if (mode === 'production') {
    // import.meta.dirname rather than process.cwd(): this resolves against the
    // frontend directory regardless of where the command was invoked, and keeps
    // the config free of Node globals that ESLint does not expect here.
    const env = loadEnv(mode, import.meta.dirname, '')
    validateApiBaseUrl(env.VITE_API_BASE_URL, { requireHttps: true })
  }

  return {
    plugins: [react()],
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/test/setup.js',
    },
  }
})
