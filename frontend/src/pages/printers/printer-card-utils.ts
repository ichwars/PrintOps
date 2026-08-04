export function formatKValue(k: number | null | undefined): string {
  return (k ?? 0.020).toFixed(3);
}

export function nozzleTypeName(type: string, t: (key: string) => string): string {
  if (!type) return '';
  if (type.includes('hardened')) return t('printers.nozzleHardenedSteel');
  if (type.includes('stainless')) return t('printers.nozzleStainlessSteel');
  if (type.includes('tungsten')) return t('printers.nozzleTungstenCarbide');
  if (type.length >= 4) {
    const material = type.slice(2, 4);
    if (material === '00') return t('printers.nozzleStainlessSteel');
    if (material === '01') return t('printers.nozzleHardenedSteel');
    if (material === '05') return t('printers.nozzleTungstenCarbide');
  }
  if (type === '00') return t('printers.nozzleStainlessSteel');
  if (type === '01') return t('printers.nozzleHardenedSteel');
  if (type === '05') return t('printers.nozzleTungstenCarbide');
  if (type.startsWith('H')) return t('printers.nozzleHardenedSteel');
  return type;
}

export function nozzleFlowName(type: string, t: (key: string) => string): string {
  if (!type) return '';
  if (type.startsWith('HH')) return t('printers.nozzleHighFlow');
  if (type.startsWith('HS')) return t('printers.nozzleStandardFlow');
  return '';
}

export function getEmptySlotKind(
  tray: { tray_type?: string | null; state?: number | null; exists?: boolean | null } | null | undefined,
): 'physical' | 'reset' | null {
  if (tray?.tray_type) return null;
  if (tray?.exists === true) return 'reset';
  if (tray?.exists === false) return 'physical';
  return tray?.state === 9 || tray?.state === 10 ? 'physical' : 'reset';
}
