import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const publicRoot = path.resolve(process.cwd(), 'public');

describe('service worker update contract', () => {
  it('checks the worker script without the HTTP cache', () => {
    const source = fs.readFileSync(path.join(publicRoot, 'sw-register.js'), 'utf8');

    expect(source).toContain(
      "navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' })",
    );
  });

  it('uses the current cache generation for runtime and static assets', () => {
    const source = fs.readFileSync(path.join(publicRoot, 'sw.js'), 'utf8');

    expect(source).toContain("const CACHE_NAME = 'printops-v3';");
    expect(source).toContain("const STATIC_CACHE = 'printops-static-v3';");
  });
});
