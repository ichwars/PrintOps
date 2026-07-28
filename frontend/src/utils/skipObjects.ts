export function pickObjectIdAt(imageData: ImageData, x: number, y: number): number | null {
  const pixelX = Math.max(0, Math.min(imageData.width - 1, Math.floor(x)));
  const pixelY = Math.max(0, Math.min(imageData.height - 1, Math.floor(y)));
  const offset = (pixelY * imageData.width + pixelX) * 4;
  const red = imageData.data[offset];
  const green = imageData.data[offset + 1];
  const blue = imageData.data[offset + 2];
  const alpha = imageData.data[offset + 3];
  if (!alpha || (red === 0 && green === 0 && blue === 0)) return null;
  return red + (green << 8) + (blue << 16);
}

export function plateClickToMaskPoint(
  bounds: { left: number; top: number; width: number; height: number },
  maskWidth: number,
  maskHeight: number,
  clientX: number,
  clientY: number,
): { x: number; y: number } | null {
  const scale = Math.min(bounds.width / maskWidth, bounds.height / maskHeight);
  if (!(scale > 0)) return null;
  const x = (clientX - bounds.left - (bounds.width - maskWidth * scale) / 2) / scale;
  const y = (clientY - bounds.top - (bounds.height - maskHeight * scale) / 2) / scale;
  if (x < 0 || y < 0 || x >= maskWidth || y >= maskHeight) return null;
  return { x, y };
}
