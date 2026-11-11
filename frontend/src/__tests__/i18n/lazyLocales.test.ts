import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import i18n from '../../i18n';

const source = fs.readFileSync(
  path.resolve(process.cwd(), 'src/i18n/index.ts'),
  'utf8',
);

describe('lazy locale loading', () => {
  it('bundles English for startup while loading the other catalogs on demand', () => {
    expect(source.match(/^import .+ from ['"]\.\/locales\/.+$/gm)).toEqual(["import en from './locales/en';"]);
    expect(source).toMatch(/import\(['"]\.\/locales\/de['"]\)/);
    expect(i18n.getResourceBundle('en', 'translation')).toHaveProperty('nav');
  });
});
