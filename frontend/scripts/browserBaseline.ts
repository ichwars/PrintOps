import fs from 'node:fs';
import path from 'node:path';
import { parse, type Node } from 'acorn';
import { RegExpParser, visitRegExpAST } from '@eslint-community/regexpp';
import type { Plugin } from 'vite';

/** Known Safari 16.0–16.3 parse hazards, not a runtime API/polyfill audit. */
export function browserSyntaxErrors(source: string): string[] {
  const errors = new Set<string>();
  const parser = new RegExpParser();
  const nodes: unknown[] = [parse(source, { ecmaVersion: 'latest', sourceType: 'module' })];
  while (nodes.length) {
    const value = nodes.pop();
    if (!value || typeof value !== 'object') continue;
    if (Array.isArray(value)) { nodes.push(...value); continue; }
    const node = value as Node & { regex?: { pattern: string; flags: string } };
    if (node.type === 'StaticBlock') errors.add('class static initialization block');
    if (node.regex) {
      const { pattern, flags } = node.regex;
      const ast = parser.parsePattern(pattern, 0, pattern.length, {
        unicode: flags.includes('u'), unicodeSets: flags.includes('v'),
      });
      visitRegExpAST(ast, {
        onAssertionEnter(assertion) {
          if (assertion.kind === 'lookbehind') errors.add('regexp lookbehind literal');
        },
      });
      if (flags.includes('v')) errors.add('regexp unicode sets flag');
    }
    // Acorn's RegExp value is not executable code; strings/comments are ignored.
    nodes.push(...Object.values(value));
  }
  return [...errors];
}

export function checkBrowserBaseline(directory: string): number {
  let count = 0;
  const errors: string[] = [];
  function scan(current: string) {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const filename = path.join(current, entry.name);
      if (entry.isDirectory()) { scan(filename); continue; }
      if (!/\.(?:js|mjs)$/.test(entry.name)) continue;
      count++;
      try {
        for (const error of browserSyntaxErrors(fs.readFileSync(filename, 'utf8'))) {
          errors.push(`${path.relative(directory, filename)}: ${error}`);
        }
      } catch (error) {
        errors.push(`${path.relative(directory, filename)}: ${String(error)}`);
      }
    }
  }
  scan(directory);
  if (!count) throw new Error('Browser baseline: no JavaScript output found');
  if (errors.length) throw new Error(`Safari 16 syntax baseline failed:\n${errors.join('\n')}`);
  return count;
}

/** Check final disk output, including copied .mjs assets and worker bundles. */
export function browserBaseline(): Plugin {
  let directory = '';
  return {
    name: 'browser-syntax-baseline',
    apply: 'build',
    configResolved(config) { directory = path.resolve(config.root, config.build.outDir); },
    closeBundle() {
      const count = checkBrowserBaseline(directory);
      console.log(`Browser syntax baseline: ${count} JavaScript files passed (Safari 16).`);
    },
  };
}
