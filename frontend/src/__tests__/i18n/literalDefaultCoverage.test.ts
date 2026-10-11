import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';
import en from '../../i18n/locales/en';
import nl from '../../i18n/locales/nl';

const sourceDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

function valueAt(catalog: object, key: string): unknown {
  return key.split('.').reduce<unknown>((value, part) => (
    value !== null && typeof value === 'object' ? (value as Record<string, unknown>)[part] : undefined
  ), catalog);
}

function sourceFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name === '__tests__' || entry.name === 'i18n') return [];
    const file = path.join(directory, entry.name);
    return entry.isDirectory() ? sourceFiles(file) : /\.tsx?$/.test(file) ? [file] : [];
  });
}

function translatorNames(source: ts.SourceFile): Set<string> {
  const names = new Set(['t']);
  const visit = (node: ts.Node) => {
    if (ts.isVariableDeclaration(node) && node.initializer && ts.isCallExpression(node.initializer)) {
      const expression = node.initializer.expression;
      const method = ts.isIdentifier(expression) ? expression.text
        : ts.isPropertyAccessExpression(expression) ? expression.name.text : '';
      if (method === 'useTranslation' && ts.isObjectBindingPattern(node.name)) {
        for (const binding of node.name.elements) {
          const property = binding.propertyName?.getText(source) ?? binding.name.getText(source);
          if (property.replace(/^['"]|['"]$/g, '') === 't' && ts.isIdentifier(binding.name)) {
            names.add(binding.name.text);
          }
        }
      }
      if (method === 'getFixedT' && ts.isIdentifier(node.name)) names.add(node.name.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return names;
}

describe('literal translation keys', () => {
  it('has English and Dutch entries for every literal runtime translation key', () => {
    const missing: string[] = [];
    for (const file of sourceFiles(sourceDir)) {
      const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
      const translators = translatorNames(source);
      const visit = (node: ts.Node) => {
        if (ts.isCallExpression(node)
          && ((ts.isIdentifier(node.expression) && translators.has(node.expression.text))
            || (ts.isPropertyAccessExpression(node.expression) && node.expression.name.text === 't'))) {
          const [key, ...options] = node.arguments;
          const returnsObject = options.some((option) => ts.isObjectLiteralExpression(option)
            && option.properties.some((property) => (
              ts.isPropertyAssignment(property)
              && property.name.getText(source).replace(/^['"]|['"]$/g, '') === 'returnObjects'
              && property.initializer.kind === ts.SyntaxKind.TrueKeyword
            )));
          if (key && ts.isStringLiteralLike(key)) {
            for (const [locale, catalog] of Object.entries({ en, nl })) {
              const value = valueAt(catalog, key.text);
              if (!(returnsObject && value !== null && typeof value === 'object')
                && typeof value !== 'string'
                && typeof valueAt(catalog, `${key.text}_one`) !== 'string') {
                const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
                missing.push(`${path.relative(sourceDir, file)}:${line} ${locale}: ${key.text}`);
              }
            }
          }
        }
        ts.forEachChild(node, visit);
      };
      visit(source);
    }
    expect(missing).toEqual([]);
  });

  it('includes aliased hook translators and fixed-language translators in the audit', () => {
    const source = ts.createSourceFile('aliases.tsx', `
      const { t: translateInterface } = useTranslation();
      const { t: tr } = reactI18next.useTranslation();
      const fixedLabel = i18n.getFixedT('nl');
    `, ts.ScriptTarget.Latest, true);
    expect([...translatorNames(source)])
      .toEqual(['t', 'translateInterface', 'tr', 'fixedLabel']);
  });

  it('preserves ordered column-label arrays consumed by commerce pages', () => {
    const arrays = (value: unknown, prefix = ''): Map<string, string[]> => {
      if (Array.isArray(value)) return new Map([[prefix, value]]);
      const result = new Map<string, string[]>();
      if (value && typeof value === 'object') {
        for (const [key, child] of Object.entries(value)) {
          for (const [arrayPath, entries] of arrays(child, prefix ? `${prefix}.${key}` : key)) {
            result.set(arrayPath, entries);
          }
        }
      }
      return result;
    };
    const reference = arrays(en.orders.runtimeDomain);
    const dutch = arrays(nl.orders.runtimeDomain);
    expect(reference.size).toBeGreaterThan(0);
    expect([...dutch.keys()]).toEqual([...reference.keys()]);
    for (const [key, labels] of reference) {
      expect(dutch.get(key)).toHaveLength(labels.length);
      expect(dutch.get(key)?.every((label) => typeof label === 'string')).toBe(true);
    }
    expect(nl.orders.runtimeDomain.orderPage.page.overview.columns)
      .toEqual(['Onderdeel', 'Status', 'Volgende stap']);
  });
});
