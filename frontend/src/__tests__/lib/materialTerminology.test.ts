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
  const legacyCopy = /Kleinteil(?:e|en|s)?|small(?:\s+|-)parts?/i;
  const technicalValue = /^(?:small-parts?|\/[^'"\s]*small-parts?(?:\/[^'"\s]*)?|small-part:)/i;
  const stringValues = (source: string) => [...source.matchAll(/(['"])((?:\\.|(?!\1).)*)\1/gs)]
    .map((match) => match[2]);

  it('does not expose legacy small-part terminology in frontend source', () => {
    const files = sourceFiles(join(process.cwd(), 'src'));
    const offenders = files.flatMap((file) => stringValues(readFileSync(file, 'utf8'))
      .filter((value) => legacyCopy.test(value) && !technicalValue.test(value))
      .map((value) => `${file.replace(`${process.cwd()}\\`, '')}: ${value}`));

    expect(offenders).toEqual([]);
  });

  it('does not expose legacy terminology in backend user-message carriers', () => {
    const backend = join(process.cwd(), '..', 'backend', 'app');
    const files = [
      join(backend, 'api', 'routes', 'inventory.py'),
      join(backend, 'api', 'routes', 'small_parts.py'),
      join(backend, 'services', 'small_parts.py'),
      join(backend, 'services', 'stock_reservations.py'),
      join(backend, 'services', 'stock_availability.py'),
    ];
    const offenders = files.flatMap((file) => stringValues(readFileSync(file, 'utf8'))
      .filter((value) => legacyCopy.test(value) && !technicalValue.test(value))
      .map((value) => `${file.replace(`${process.cwd()}\\..\\`, '')}: ${value}`));

    expect(offenders).toEqual([]);
  });
});
