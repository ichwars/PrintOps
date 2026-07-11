import { normalizeNfkcCasefold } from './orderMasterDataValidation';


const pythonWhitespaceCodePoints = new Set([
  0x0085, 0x00A0, 0x1680, 0x2028, 0x2029, 0x202F, 0x205F, 0x3000,
]);

function isPythonWhitespace(codePoint: number): boolean {
  return (codePoint >= 0x0009 && codePoint <= 0x000D)
    || (codePoint >= 0x001C && codePoint <= 0x0020)
    || (codePoint >= 0x2000 && codePoint <= 0x200A)
    || pythonWhitespaceCodePoints.has(codePoint);
}

function stripPythonWhitespace(value: string): string {
  let start = 0;
  let end = value.length;
  while (start < end && isPythonWhitespace(value.charCodeAt(start))) start += 1;
  while (end > start && isPythonWhitespace(value.charCodeAt(end - 1))) end -= 1;
  return value.slice(start, end);
}
function comparePythonStrings(left: string, right: string): number {
  const leftCodePoints = Array.from(left, (character) => character.codePointAt(0)!);
  const rightCodePoints = Array.from(right, (character) => character.codePointAt(0)!);
  const length = Math.min(leftCodePoints.length, rightCodePoints.length);

  for (let index = 0; index < length; index += 1) {
    if (leftCodePoints[index] !== rightCodePoints[index]) {
      return leftCodePoints[index] - rightCodePoints[index];
    }
  }
  return leftCodePoints.length - rightCodePoints.length;
}

export function normalizeOrderTags(tags: readonly string[]): string[] {
  const selectedDisplays = new Map<string, string>();
  for (const rawTag of tags) {
    const display = stripPythonWhitespace(rawTag);
    if (!display) continue;

    const key = normalizeNfkcCasefold(display);
    const selected = selectedDisplays.get(key);
    if (selected === undefined || comparePythonStrings(display, selected) < 0) {
      selectedDisplays.set(key, display);
    }
  }

  return [...selectedDisplays.entries()]
    .sort(([leftKey, leftDisplay], [rightKey, rightDisplay]) => (
      comparePythonStrings(leftKey, rightKey) || comparePythonStrings(leftDisplay, rightDisplay)
    ))
    .map(([, display]) => display);
}
