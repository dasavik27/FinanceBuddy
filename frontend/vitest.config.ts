import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_SUPABASE_URL': JSON.stringify('https://test-project.supabase.co'),
    'import.meta.env.VITE_SUPABASE_ANON_KEY': JSON.stringify('test-anon-key-for-vitest'),
    'import.meta.env.VITE_API_URL': JSON.stringify('/api'),
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    testTimeout: 30000,
    hookTimeout: 30000,
    // threads is much faster than single-fork on Windows and avoids 30s+ UI timeouts
    // under serial coverage runs; keep maxThreads modest to limit memory pressure.
    pool: 'threads',
    poolOptions: {
      threads: { maxThreads: 4, minThreads: 1 },
    },
    env: {
      VITE_SUPABASE_URL: 'https://test-project.supabase.co',
      VITE_SUPABASE_ANON_KEY: 'test-anon-key-for-vitest',
      VITE_API_URL: '/api',
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'text-summary', 'json', 'json-summary', 'html'],
      // Aim near-full app coverage; exclude entry/bootstrap and type-only files.
      thresholds: {
        lines: 90,
        functions: 90,
        statements: 90,
        branches: 90,
      },
      exclude: [
        'node_modules/',
        'src/test/',
        '**/*.d.ts',
        '**/types.ts',
        '**/*.test.{ts,tsx}',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
    },
  },
})

