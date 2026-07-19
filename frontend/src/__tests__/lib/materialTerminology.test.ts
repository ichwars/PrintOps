import { readdirSync, readFileSync } from 'node:fs';
import { extname, join } from 'node:path';

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name === '__tests__' || entry.name === 'api') return [];
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return ['.ts', '.tsx'].includes(extname(entry.name)) ? [path] : [];
  });
}

describe('visible material terminology', () => {
  it('does not expose legacy small-part terminology in frontend source', () => {
    const files = sourceFiles(join(process.cwd(), 'src'));
    const legacyCopy = /Kleinteil(?:e|en|s)?|small parts?|small-part(?=\s)/i;
    const offenders = files
      .filter((file) => legacyCopy.test(readFileSync(file, 'utf8')))
      .map((file) => file.replace(`${process.cwd()}\\`, ''));

    expect(offenders).toEqual([]);
  });
});
