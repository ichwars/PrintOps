import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    environmentOptions: {
      jsdom: {
        url: 'http://localhost:3000',
      },
    },
    setupFiles: ['./src/__tests__/setup.ts'],
    // Node 26 enables its own experimental Web Storage implementation in
    // workers. Tests use jsdom's browser storage instead, so disable Node's
    // copy to avoid one warning per worker and two competing storage owners.
    execArgv: ['--no-experimental-webstorage'],
    // Large-core developer machines otherwise spawn enough jsdom workers to
    // exhaust memory and turn healthy tests into timeouts or spawn failures.
    maxWorkers: 4,
    testTimeout: 10000,
    include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
    exclude: ['node_modules', 'dist'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/**/*.spec.{ts,tsx}',
        'src/__tests__/**',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
      thresholds: {
        statements: 46,
        branches: 41,
        functions: 37,
        lines: 46,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
