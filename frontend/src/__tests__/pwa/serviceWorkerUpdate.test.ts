import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
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

    expect(source).toContain("const CACHE_NAME = 'printops-v4';");
    expect(source).toContain("const STATIC_CACHE = 'printops-static-v3';");
  });

  it('serves versioned assets from cache, and keeps HTML errors out of that cache', async () => {
    const source = fs.readFileSync(path.join(publicRoot, 'sw.js'), 'utf8');
    const origin = 'http://localhost';
    const contents = new Map<string, Response>();
    const routes = new Map<string, (event: unknown) => void>();
    let networkRequests = 0;
    const url = (request: Request | string) => typeof request === 'string' ? new URL(request, origin).href : request.url;
    const cache = {
      match: async (request: Request | string) => contents.get(url(request))?.clone(),
      put: async (request: Request | string, response: Response) => { contents.set(url(request), response); },
    };
    vm.runInNewContext(source, {
      URL,
      Response,
      caches: { match: cache.match, open: async () => cache },
      self: {
        location: { origin },
        addEventListener: (type: string, handler: (event: unknown) => void) => routes.set(type, handler),
      },
      fetch: async (request: Request) => {
        networkRequests++;
        return request.url.includes('OldPage')
          ? new Response('<html>stale module</html>', { headers: { 'content-type': 'text/html' } })
          : new Response('export default 42;', { headers: { 'content-type': 'text/javascript' } });
      },
    });

    async function requestAsset(pathname: string, headers?: HeadersInit) {
      let response: Promise<Response> | undefined;
      let completion: Promise<void> | undefined;
      routes.get('fetch')!({
        request: new Request(new URL(pathname, origin), { headers }),
        respondWith: (value: Promise<Response>) => { response = value; },
        waitUntil: (value: Promise<void>) => { completion = value; },
      });
      await completion;
      return response;
    }

    const current = '/assets/QueuePage-A1b2C3d4.js';
    const missing = '/assets/OldPage-B2c3D4e5.js';
    expect(await (await requestAsset(current))?.text()).toBe('export default 42;');
    expect(await (await requestAsset(current))?.text()).toBe('export default 42;');
    expect(await (await requestAsset(missing))?.text()).toBe('<html>stale module</html>');
    expect(await (await requestAsset(missing))?.text()).toBe('<html>stale module</html>');
    expect(networkRequests).toBe(3);
    expect(await requestAsset('/health')).toBeUndefined();
    expect(await requestAsset(current, { Range: 'bytes=0-4' })).toBeUndefined();
  });

  it('precaches every generated locale chunk for offline language switching', () => {
    const workerSource = fs.readFileSync(path.join(publicRoot, 'sw.js'), 'utf8');
    const viteSource = fs.readFileSync(path.resolve(process.cwd(), 'vite.config.ts'), 'utf8');

    expect(viteSource).toContain("fileName: 'locale-assets.json'");
    expect(workerSource).toContain("fetch('/locale-assets.json'");
    expect(workerSource).toContain('cache.addAll(localeAssets)');
  });
});
