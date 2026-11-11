export const CAMERA_WALL_SIZE_KEY = 'camWallTileSize';
export const CAMERA_WALL_SIZES = ['S', 'M', 'L', 'XL'] as const;

const GRID_COLUMNS = [
  'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5',
  'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4',
  'grid-cols-1 lg:grid-cols-2',
  'grid-cols-1',
];

export function cameraWallGrid(size: number): string {
  return GRID_COLUMNS[size - 1] ?? GRID_COLUMNS[1];
}

export function readCameraWallSize(requested?: string | null): number {
  const fromUrl = CAMERA_WALL_SIZES.findIndex((size) => size.toLowerCase() === requested?.toLowerCase());
  if (fromUrl >= 0) return fromUrl + 1;
  try {
    const saved = Number(localStorage.getItem(CAMERA_WALL_SIZE_KEY));
    if (Number.isInteger(saved) && saved >= 1 && saved <= CAMERA_WALL_SIZES.length) return saved;
  } catch { /* Storage may be unavailable. */ }
  return 2;
}
