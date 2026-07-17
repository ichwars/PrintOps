import fs from 'node:fs';
import path from 'node:path';
import * as ts from 'typescript';
import { describe, expect, it } from 'vitest';

const sourceRoot = path.resolve(process.cwd(), 'src');
const applicationRoots = ['components', 'pages'];
const specializedTextFieldTypes = new Set([
  'checkbox',
  'color',
  'date',
  'datetime-local',
  'file',
  'number',
  'radio',
  'range',
  'time',
]);

function tsxFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (absolute === path.join(sourceRoot, 'components', 'ui')) return [];
      return tsxFiles(absolute);
    }
    return entry.isFile() && entry.name.endsWith('.tsx') ? [absolute] : [];
  });
}

function literalAttribute(
  node: ts.JsxOpeningLikeElement,
  name: string,
  sourceFile: ts.SourceFile,
): string | undefined {
  const attribute = node.attributes.properties.find(
    (property): property is ts.JsxAttribute =>
      ts.isJsxAttribute(property) && property.name.getText(sourceFile) === name,
  );
  const initializer = attribute?.initializer;
  if (!initializer) return undefined;
  if (ts.isStringLiteral(initializer)) return initializer.text;
  if (
    ts.isJsxExpression(initializer) &&
    initializer.expression &&
    ts.isStringLiteral(initializer.expression)
  ) {
    return initializer.expression.text;
  }
  return undefined;
}

export function directBrowserControls(file: string, source: string): string[] {
  const sourceFile = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const matches: string[] = [];

  function report(node: ts.Node, tag: string): void {
    const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
    matches.push(`${file}:${line + 1} <${tag}>`);
  }

  function visit(node: ts.Node): void {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tagName = node.tagName.getText(sourceFile);
      if (tagName === 'select' || tagName === 'textarea') report(node, tagName);
      if (tagName === 'input' && literalAttribute(node, 'type', sourceFile) !== 'hidden') {
        report(node, 'input');
      }
      if (tagName === 'TextField') {
        const type = literalAttribute(node, 'type', sourceFile);
        if (type && specializedTextFieldTypes.has(type)) report(node, `TextField type=${type}`);
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return matches;
}

describe('application UI migration', () => {
  it('keeps direct browser controls inside the owned UI layer', () => {
    const matches = applicationRoots.flatMap((root) =>
      tsxFiles(path.join(sourceRoot, root)).flatMap((absolute) => {
        const relative = path.relative(sourceRoot, absolute).replaceAll('\\', '/');
        return directBrowserControls(relative, fs.readFileSync(absolute, 'utf8'));
      }),
    );

    expect(matches).toEqual([]);
  });
});
