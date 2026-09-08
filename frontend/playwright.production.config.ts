import path from 'node:path';
import { tmpdir } from 'node:os';
import base from './playwright.config';

// Exercise an already-built preview. Never rebuild ../static as a side effect
// of a production smoke test (it may contain the developer's own changes).
export default {
  ...base,
  webServer: undefined,
  testMatch: 'touch-actions.spec.ts',
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || path.join(tmpdir(), 'printops-production-tests'),
  use: { ...base.use, baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:4184' },
};
