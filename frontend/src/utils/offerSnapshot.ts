export function snapshotPart(snapshot: Record<string, unknown>, key: 'calculation' | 'revision'): Record<string, unknown> {
  const value = snapshot[key];
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function offerCalculationTitle(calculation: Record<string, unknown>) {
  return String(calculation.title ?? (calculation.id == null ? '—' : `K-${calculation.id}`));
}
