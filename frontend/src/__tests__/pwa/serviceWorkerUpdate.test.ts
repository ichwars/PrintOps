import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const publicRoot = path.resolve(process.cwd(), 'public');
const sourceRoot = path.resolve(process.cwd(), 'src');

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

  it('reloads once when a deployed lazy chunk is no longer available', () => {
    const source = fs.readFileSync(path.join(sourceRoot, 'main.tsx'), 'utf8');

    expect(source).toContain("window.addEventListener('vite:preloadError'");
    expect(source).toContain('event.preventDefault()');
    expect(source).toContain('sessionStorage');
    expect(source).toContain('window.location.reload()');
  });

  it('precaches every generated locale chunk for offline language switching', () => {
    const workerSource = fs.readFileSync(path.join(publicRoot, 'sw.js'), 'utf8');
    const viteSource = fs.readFileSync(path.resolve(process.cwd(), 'vite.config.ts'), 'utf8');

    expect(viteSource).toContain("fileName: 'locale-assets.json'");
    expect(workerSource).toContain("fetch('/locale-assets.json'");
    expect(workerSource).toContain('cache.addAll(localeAssets)');
  });
});
