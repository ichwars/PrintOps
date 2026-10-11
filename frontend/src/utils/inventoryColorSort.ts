import type { InventorySpool } from '../api/client';

type SpoolColor = Pick<InventorySpool, 'id' | 'rgba' | 'extra_colors'>;
type ColorGroup = 'neutral' | 'brown' | 'chromatic' | 'transparent' | 'multicolor' | 'missing';
type Color = { hex: string; hue: number; saturation: number; lightness: number; alpha: number };
const groupOrder: Record<ColorGroup, number> = {
  neutral: 0, brown: 1, chromatic: 2, transparent: 3, multicolor: 4, missing: 5,
};

function parseColor(value: string | null | undefined): Color | null {
  const hex = value?.trim().replace(/^#/, '').toLowerCase();
  if (!hex || !/^(?:[\da-f]{6}|[\da-f]{8})$/.test(hex)) return null;
  const [red, green, blue] = [0, 2, 4].map(offset => parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const max = Math.max(red, green, blue), min = Math.min(red, green, blue);
  const delta = max - min, lightness = (max + min) / 2;
  const saturation = delta === 0 ? 0 : delta / (1 - Math.abs(2 * lightness - 1));
  let hue = 0;
  if (delta !== 0) {
    if (max === red) hue = (green - blue) / delta;
    else if (max === green) hue = (blue - red) / delta + 2;
    else hue = (red - green) / delta + 4;
    hue = (hue * 60 + 360) % 360;
  }
  return { hex: hex.length === 6 ? `${hex}ff` : hex, hue, saturation, lightness,
    alpha: hex.length === 8 ? parseInt(hex.slice(6), 16) : 255 };
}

function displayedColors(spool: SpoolColor): Color[] {
  // The shared swatch paints extra stops instead of the base RGBA when present.
  const stops = (spool.extra_colors ?? '').split(',').map(parseColor).filter((color): color is Color => color !== null);
  const colors = stops.length ? stops : [parseColor(spool.rgba)].filter((color): color is Color => color !== null);
  return [...new Map(colors.map(color => [color.hex, color])).values()];
}

function classify(colors: Color[]): ColorGroup {
  if (!colors.length) return 'missing';
  if (colors.every(color => color.alpha === 0)) return 'transparent';
  if (colors.length > 1) return 'multicolor';
  const color = colors[0];
  if (color.alpha < 255) return 'transparent';
  if (color.saturation < 0.15 || color.lightness < 0.15 || color.lightness > 0.85) return 'neutral';
  if (color.hue >= 15 && color.hue < 70 && color.lightness < (color.hue < 45 ? 0.45 : 0.4)) return 'brown';
  return 'chromatic';
}

export function classifyInventoryColor(spool: SpoolColor): ColorGroup {
  return classify(displayedColors(spool));
}

function sortKey(spool: SpoolColor): Array<string | number> {
  const colors = displayedColors(spool), group = classify(colors), first = colors[0];
  return [groupOrder[group],
    group === 'chromatic' || group === 'transparent' ? first?.hue ?? 0 : 0,
    group === 'neutral' || group === 'brown' || group === 'chromatic' ? first?.lightness ?? 0 : 0,
    first?.alpha ?? 0, colors.map(color => color.hex).sort().join(','), spool.id];
}

/** Ascending: neutrals dark→light, brown, hue spectrum, transparency, multi, missing.
 *  Spool ID breaks equal-color ties independently of backend response order. */
export function compareInventoryColors(left: SpoolColor, right: SpoolColor): number {
  const a = sortKey(left), b = sortKey(right);
  for (let index = 0; index < a.length; index++) {
    if (a[index] < b[index]) return -1;
    if (a[index] > b[index]) return 1;
  }
  return 0;
}
