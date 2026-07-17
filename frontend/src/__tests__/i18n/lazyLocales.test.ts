import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const source = fs.readFileSync(
  path.resolve(process.cwd(), 'src/i18n/index.ts'),
  'utf8',
);

describe('lazy locale loading', () => {
  it('keeps translation catalogs out of the initial bundle', () => {
    expect(source).not.toMatch(/^import .+ from ['"]\.\/locales\//m);
    expect(source).toMatch(/import\(['"]\.\/locales\/en['"]\)/);
    expect(source).toMatch(/import\(['"]\.\/locales\/de['"]\)/);
  });
});
