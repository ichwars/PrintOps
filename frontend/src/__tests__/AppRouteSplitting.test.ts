import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const appSource = fs.readFileSync(path.resolve(process.cwd(), 'src/App.tsx'), 'utf8');

describe('application route splitting', () => {
  it('loads page modules through dynamic imports', () => {
    expect(appSource).not.toMatch(/^import .+ from ['"]\.\/pages\//m);
    expect(appSource).toMatch(/lazy\(\(\) => import\(['"]\.\/pages\/PrintersPage['"]\)/);
    expect(appSource).toMatch(/lazy\(\(\) => import\(['"]\.\/pages\/SettingsPage['"]\)/);
  });

  it('renders a stable fallback while route chunks load', () => {
    expect(appSource).toContain('<Suspense fallback={<RouteFallback />}>');
  });
});
