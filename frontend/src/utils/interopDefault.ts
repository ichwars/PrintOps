/**
 * Unwrap a default import that a bundler's CommonJS-to-ESM interop may have
 * wrapped in a module namespace object.
 */
export function resolveInteropDefault<T = unknown>(value: unknown, fallbackKeys: string[] = []): T {
  if (isRenderableType(value)) return value as T;

  if (value !== null && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    if (isRenderableType(obj.default)) return obj.default as T;
    for (const key of fallbackKeys) {
      if (isRenderableType(obj[key])) return obj[key] as T;
    }
  }

  return value as T;
}

function isRenderableType(value: unknown): boolean {
  if (typeof value === 'function' || typeof value === 'string') return true;
  return typeof value === 'object' && value !== null && '$$typeof' in value;
}
