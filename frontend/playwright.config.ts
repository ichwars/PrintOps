import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';

const frontendDir = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(frontendDir, '..');
const backendPort = '8010';
const bundledPython = path.join(repositoryRoot, '.venv', 'Scripts', 'python.exe');
const python = process.env.PYTHON || (existsSync(bundledPython) ? '"' + bundledPython + '"' : 'python3');
const useRealBackend = process.env.PLAYWRIGHT_REAL_BACKEND === '1';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  outputDir: 'test-results/playwright',
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    serviceWorkers: 'block',
  },
  webServer: [
    ...(useRealBackend ? [{
      command: python + ' -m uvicorn backend.app.main:app --host 127.0.0.1 --port ' + backendPort,
      cwd: repositoryRoot,
      url: 'http://127.0.0.1:' + backendPort + '/api/v1/auth/status',
      timeout: 120_000,
      reuseExistingServer: true,
      env: {
        ...process.env,
        DATA_DIR: path.join(repositoryRoot, '.playwright-data'),
      },
    }] : []),
    {
      command: 'npm run build && ' + python + ' e2e/spa_server.py --directory ../static --port 4173',
      cwd: frontendDir,
      url: 'http://127.0.0.1:4173',
      timeout: 120_000,
      reuseExistingServer: true,
      env: {
        ...process.env,
        BACKEND_PORT: backendPort,
      },
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
