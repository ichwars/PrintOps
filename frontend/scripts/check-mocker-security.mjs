import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { createServer } from 'vite';
import { interceptorPlugin } from '@vitest/mocker/node';

// Exercise the installed plugin's actual WebSocket registration handler and
// load hook, with Vite's real fs policy. All canaries belong to this test.
for (const target of ['allowed.js', '.env', '../outside.js']) {
  test(`redirect mocks respect server.fs: ${target}`, async () => {
    const directory = await mkdtemp(join(tmpdir(), 'printops-mocker-'));
    const root = join(directory, 'root');
    let server;
    try {
      await mkdir(root);
      const canary = 'export const canary = "owned-security-fixture";';
      for (const file of ['allowed.js', '.env', '../outside.js']) {
        await writeFile(join(root, file), canary);
      }
      server = await createServer({
        configFile: false, root, logLevel: 'silent',
        server: { middlewareMode: true, ws: false, fs: { strict: true, allow: [root], deny: ['.env'] } },
      });
      const handlers = new Map();
      const plugin = interceptorPlugin();
      plugin.configureServer({
        config: server.config,
        ws: { on: (event, handler) => handlers.set(event, handler), send() {} },
      });
      const register = handlers.get('vitest:interceptor:register');
      assert.equal(typeof register, 'function');
      // An opaque URL retains dot segments, unlike normalized http/file URLs.
      const event = { type: 'redirect', raw: './mock.js', id: '/mock.js', url: '/mock.js', redirect: `fixture:${target}` };
      if (target === 'allowed.js') {
        await register(event);
        assert.equal(await plugin.load.handler('/mock.js'), canary);
      } else {
        await register(event);
        assert.equal(await plugin.load.handler('/mock.js'), undefined, 'blocked redirect must never be registered or read');
      }
    } finally {
      await server?.close();
      await rm(directory, { recursive: true, force: true });
    }
  });
}
