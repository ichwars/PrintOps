import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { Minimatch } from 'minimatch';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);

describe('minimatch dependency security', () => {
  it('bounds preprocessing of repeated parent-directory globstars', () => {
    const result = spawnSync(process.execPath, ['-e', `
      const { Minimatch } = require(process.argv[1]);
      const pattern = 'root/' + '*/**/../'.repeat(22) + 'file.3mf';
      const matcher = new Minimatch(pattern, { optimizationLevel: 2 });
      console.log(matcher.match('root/file.3mf'));
    `, require.resolve('minimatch')], { encoding: 'utf8', timeout: 5000 });
    expect(result.error).toBeUndefined();
    expect(result.status, result.stderr).toBe(0);
    expect(result.stdout.trim()).toBe('false');
  }, 10000);

  it('preserves ordinary source glob and exclusion matching', () => {
    const matcher = new Minimatch('src/**/*.{ts,tsx}', { optimizationLevel: 2 });
    expect(matcher.match('src/pages/Settings.tsx')).toBe(true);
    expect(matcher.match('src/api/client.ts')).toBe(true);
    expect(matcher.match('src/pages/Settings.js')).toBe(false);
    expect(matcher.match('node_modules/module/index.ts')).toBe(false);
  });
});
