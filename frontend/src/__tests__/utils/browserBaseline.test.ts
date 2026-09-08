import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { browserSyntaxErrors, checkBrowserBaseline } from '../../../scripts/browserBaseline';

describe('production browser syntax baseline', () => {
  it.each(['/(?<=prefix)value/u', '/(?<!prefix)value/u'])('rejects lookbehind: %s', (source) => {
    expect(browserSyntaxErrors(source)).toContain('regexp lookbehind literal');
  });

  it('rejects class static initialization blocks and unicode sets', () => {
    expect(browserSyntaxErrors('class Example { static { this.ready = true; } }'))
      .toContain('class static initialization block');
    expect(browserSyntaxErrors('/[a&&b]/v')).toContain('regexp unicode sets flag');
  });

  it('does not confuse strings, comments, escaped patterns, named groups or lookahead with hazards', () => {
    expect(browserSyntaxErrors([
      'const note = "(?<= static {";', '// (?<! static {',
      '/\\(\\?<=/;', '/(?<name>value)/u;', '/(?=value)(?!other)/;',
      'class Example { static value = 1; static method() {} }',
    ].join('\n'))).toEqual([]);
  });

  const directories: string[] = [];
  afterEach(() => {
    for (const directory of directories.splice(0)) fs.rmSync(directory, { recursive: true, force: true });
  });
  function output() {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'printops-baseline-test-'));
    directories.push(directory);
    fs.mkdirSync(path.join(directory, 'assets'));
    return directory;
  }

  it('checks nested chunks AND raw .mjs assets in the selected output directory', () => {
    const directory = output();
    fs.writeFileSync(path.join(directory, 'assets', 'page.js'), 'export const value = 1;');
    fs.writeFileSync(path.join(directory, 'assets', 'worker.mjs'), 'class Worker { static {} }');
    expect(() => checkBrowserBaseline(directory)).toThrow(/worker.mjs.*static initialization/);
    fs.writeFileSync(path.join(directory, 'assets', 'worker.mjs'), 'export const value = 2;');
    expect(checkBrowserBaseline(directory)).toBe(2);
  });

  it('fails closed on missing/empty output and malformed JavaScript', () => {
    const directory = output();
    expect(() => checkBrowserBaseline(path.join(directory, 'missing'))).toThrow();
    expect(() => checkBrowserBaseline(directory)).toThrow('no JavaScript output');
    fs.writeFileSync(path.join(directory, 'broken.js'), 'export const =');
    expect(() => checkBrowserBaseline(directory)).toThrow(/broken.js.*SyntaxError/);
  });
});
