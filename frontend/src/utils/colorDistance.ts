const D65_WHITE: readonly [number, number, number] = [0.95047, 1.0, 1.08883];
const LAB_DELTA = 6 / 29;

/**
 * Convert a hex colour to CIE L*a*b* under D65, or null if it is unusable.
 *
 * Alpha is dropped by `normalizeColorForCompare`, deliberately: the alpha a
 * slicer writes for a transparent filament is not a colour the user chose, and
 * counting it would stop a transparent filament matching itself.
 */
function hexToLab(color: string | undefined): [number, number, number] | null {
  const hex = (color || '').replace('#', '').toLowerCase().slice(0, 6);
  if (!/^[0-9a-f]{6}$/.test(hex)) return null;
  if (!hex || hex.length < 6) return null;

  const channels = [0, 2, 4].map((i) => parseInt(hex.substring(i, i + 2), 16) / 255);
  if (channels.some(Number.isNaN)) return null;

  // sRGB gamma -> linear light.
  const [r, g, b] = channels.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));

  const xyz: [number, number, number] = [
    0.4124564 * r + 0.3575761 * g + 0.1804375 * b,
    0.2126729 * r + 0.7151522 * g + 0.072175 * b,
    0.0193339 * r + 0.119192 * g + 0.9503041 * b,
  ];

  const f = (t: number) =>
    t > LAB_DELTA ** 3 ? Math.cbrt(t) : t / (3 * LAB_DELTA * LAB_DELTA) + 4 / 29;
  const [fx, fy, fz] = xyz.map((v, i) => f(v / D65_WHITE[i]));

  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

/**
 * CIEDE2000 colour difference between two L*a*b* triples.
 *
 * Straight transcription of the CIE formulation with kL = kC = kH = 1, kept
 * structurally identical to `perceptual_color_distance` in
 * `backend/app/utils/color_utils.py` so the two can be read side by side. They
 * must agree: the dialog must not promise a spool the scheduler would not pick.
 */
function ciede2000(lab1: [number, number, number], lab2: [number, number, number]): number {
  const [l1, a1, b1] = lab1;
  const [l2, a2, b2] = lab2;
  const rad = (deg: number) => (deg * Math.PI) / 180;

  const c1 = Math.hypot(a1, b1);
  const c2 = Math.hypot(a2, b2);
  const cBar7 = ((c1 + c2) / 2) ** 7;
  const g = 0.5 * (1 - Math.sqrt(cBar7 / (cBar7 + 25 ** 7)));

  const a1p = (1 + g) * a1;
  const a2p = (1 + g) * a2;
  const c1p = Math.hypot(a1p, b1);
  const c2p = Math.hypot(a2p, b2);

  const hue = (ap: number, bp: number) => {
    if (ap === 0 && bp === 0) return 0;
    const deg = (Math.atan2(bp, ap) * 180) / Math.PI;
    return deg < 0 ? deg + 360 : deg;
  };
  const h1p = hue(a1p, b1);
  const h2p = hue(a2p, b2);

  const dlp = l2 - l1;
  const dcp = c2p - c1p;

  const chromaProduct = c1p * c2p;
  let dhp = 0;
  if (chromaProduct !== 0) {
    dhp = h2p - h1p;
    if (dhp > 180) dhp -= 360;
    else if (dhp < -180) dhp += 360;
  }
  const dhpBig = 2 * Math.sqrt(chromaProduct) * Math.sin(rad(dhp) / 2);

  const lBar = (l1 + l2) / 2;
  const cBar = (c1p + c2p) / 2;

  let hBar: number;
  if (chromaProduct === 0) hBar = h1p + h2p;
  else if (Math.abs(h1p - h2p) <= 180) hBar = (h1p + h2p) / 2;
  else if (h1p + h2p < 360) hBar = (h1p + h2p + 360) / 2;
  else hBar = (h1p + h2p - 360) / 2;

  const t =
    1 -
    0.17 * Math.cos(rad(hBar - 30)) +
    0.24 * Math.cos(rad(2 * hBar)) +
    0.32 * Math.cos(rad(3 * hBar + 6)) -
    0.2 * Math.cos(rad(4 * hBar - 63));

  const cBarP7 = cBar ** 7;
  const rc = 2 * Math.sqrt(cBarP7 / (cBarP7 + 25 ** 7));
  const sl = 1 + (0.015 * (lBar - 50) ** 2) / Math.sqrt(20 + (lBar - 50) ** 2);
  const sc = 1 + 0.045 * cBar;
  const sh = 1 + 0.015 * cBar * t;
  const rt = -Math.sin(rad(2 * (30 * Math.exp(-(((hBar - 275) / 25) ** 2))))) * rc;

  const dL = dlp / sl;
  const dC = dcp / sc;
  const dH = dhpBig / sh;
  return Math.sqrt(dL * dL + dC * dC + dH * dH + rt * dC * dH);
}

/**
 * Perceptual distance between two hex colours, or null if either is unusable.
 *
 * Used to rank the candidates `colorsAreSimilar` admits. Eligibility stays the
 * per-channel box that shipped; this only decides which of several eligible
 * spools is closest, so no spool becomes usable or unusable because of it.
 *
 * It ranks by how far apart the colours *look*, not how far apart their numbers
 * are. RGB distance overweights blue badly enough to invert the answer: against
 * a required `#1E4821` green, a purple `#38202F` is the nearer of two eligible
 * spools by RGB and four times the further once measured perceptually.
 *
 * The scale is CIEDE2000 delta-E, where ~1 is a just-noticeable difference —
 * far smaller numbers than the RGB distances this replaced, and not comparable
 * against an RGB threshold.
 */
export function colorDistance(
  color1: string | undefined,
  color2: string | undefined,
): number | null {
  const lab1 = hexToLab(color1);
  const lab2 = hexToLab(color2);
  if (!lab1 || !lab2) return null;
  return ciede2000(lab1, lab2);
}
