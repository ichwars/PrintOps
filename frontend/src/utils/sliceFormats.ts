/**
 * Which model formats PrintOps can slice server-side.
 *
 * STEP/STP are deliberately excluded: the OrcaSlicer/BambuStudio CLI behind
 * the slicer sidecar cannot import them reliably, so offering the action only
 * produces a job that fails later. Upload, library management and 3D preview
 * of STEP files stay untouched. Mirrors
 * `backend/app/services/slice_formats.py` — see issue #92.
 */

const SLICEABLE_EXTENSIONS = ['.stl', '.3mf'] as const;
const UNSLICEABLE_CAD_EXTENSIONS = ['.step', '.stp'] as const;

/** True when the sidecar can slice this file (model geometry, not G-code). */
export function isServerSliceableFilename(filename: string | null | undefined): boolean {
  const lower = (filename || '').toLowerCase();
  if (lower.endsWith('.gcode') || lower.endsWith('.gcode.3mf')) return false;
  return SLICEABLE_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/** True for CAD formats PrintOps stores but cannot slice server-side. */
export function isUnsliceableCadFilename(filename: string | null | undefined): boolean {
  const lower = (filename || '').toLowerCase();
  return UNSLICEABLE_CAD_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/** Same check keyed off a `file_type` value (`'stl'`, `'step'`, …). */
export function isServerSliceableFileType(fileType: string | null | undefined): boolean {
  const t = (fileType || '').toLowerCase();
  return t === 'stl' || t === '3mf';
}

/** True when a `file_type` value names a CAD format we cannot slice. */
export function isUnsliceableCadFileType(fileType: string | null | undefined): boolean {
  const t = (fileType || '').toLowerCase();
  return t === 'step' || t === 'stp';
}
