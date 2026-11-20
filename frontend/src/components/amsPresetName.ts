// Known filament material types
export const MATERIAL_TYPES = ['PLA', 'PETG', 'PCTG', 'ABS', 'ASA', 'TPU', 'PC', 'PA', 'NYLON', 'PVA', 'HIPS', 'PP', 'PET'];

// Extract filament type from preset name by finding known material type
export function parsePresetName(name: string): { material: string; brand: string; variant: string } {
  // Remove printer/nozzle suffix first
  const withoutSuffix = name.replace(/@.+$/, '').trim();
  const upperName = withoutSuffix.toUpperCase();

  // Handle "X Support for Y" pattern: the filament type is Y, not X.
  // e.g. "PLA Support for PETG PETG Basic" → material is PETG
  const supportMatch = upperName.match(/\bSUPPORT\s+FOR\s+/);
  if (supportMatch) {
    const afterSupport = upperName.slice(supportMatch.index! + supportMatch[0].length);
    for (const mat of MATERIAL_TYPES) {
      const regex = new RegExp(`\\b${mat}\\b`);
      if (regex.test(afterSupport)) {
        const brand = withoutSuffix.slice(0, supportMatch.index).trim();
        return { material: mat, brand, variant: 'Support' };
      }
    }
  }

  // Try to find a known material type in the name
  for (const mat of MATERIAL_TYPES) {
    // Use word boundary to match whole words only
    const regex = new RegExp(`\\b${mat}\\b`, 'i');
    if (regex.test(upperName)) {
      // Found material, extract brand (everything before material) and variant (after)
      const parts = withoutSuffix.split(regex);
      const brand = parts[0]?.trim() || '';
      const variant = parts[1]?.trim() || '';
      return { material: mat, brand, variant };
    }
  }

  // Fallback: assume first word is brand, second is material
  const parts = withoutSuffix.split(/\s+/);
  if (parts.length >= 2) {
    return { material: parts[1], brand: parts[0], variant: parts.slice(2).join(' ') };
  }

  return { material: withoutSuffix, brand: '', variant: '' };
}

// Check if a preset is a user preset (not built-in)
export function isUserPreset(settingId: string): boolean {
  // Built-in presets have specific patterns, user presets are UUIDs
  return !settingId.startsWith('GF') && !settingId.startsWith('P1');
}
