/** Read actual response bytes within a limit, even when Content-Length is absent. */
export async function readPreviewResponse(response: Response, maxBytes: number): Promise<ArrayBuffer> {
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const length = Number(response.headers.get('Content-Length'));
  if (length > maxBytes) { await response.body?.cancel(); throw new Error('Preview exceeds byte limit'); }
  if (!response.body) return new ArrayBuffer(0);
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) { await reader.cancel(); throw new Error('Preview exceeds byte limit'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const data = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.byteLength; }
  return data.buffer;
}

/** Use raster magic bytes rather than the extension or a supplied MIME type. */
export function rasterImageMime(buffer: ArrayBuffer): string {
  const data = new Uint8Array(buffer);
  const view = new DataView(buffer);
  const fourcc = (offset: number) => String.fromCharCode(...data.slice(offset, offset + 4));
  const dimensions = (width: number, height: number, mime: string) => {
    if (width <= 0 || height <= 0 || width * height > 25_000_000) throw new Error('Image exceeds pixel limit');
    return mime;
  };
  if (data.length >= 24 && [137,80,78,71,13,10,26,10].every((value, index) => data[index] === value) && fourcc(12) === 'IHDR') {
    return dimensions(view.getUint32(16), view.getUint32(20), 'image/png');
  }
  if (data[0] === 255 && data[1] === 216) {
    let offset = 2;
    while (offset + 4 <= data.length) {
      if (data[offset++] !== 255) break;
      while (data[offset] === 255) offset++;
      const marker = data[offset++];
      if (marker === 0xda || marker === 0xd9) break;
      if (offset + 2 > data.length) break;
      const length = view.getUint16(offset);
      if (length < 2 || offset + length > data.length) break;
      if ([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker) && length >= 8) {
        return dimensions(view.getUint16(offset + 5), view.getUint16(offset + 3), 'image/jpeg');
      }
      offset += length;
    }
    throw new Error('Invalid JPEG dimensions');
  }
  if (data.length >= 10 && String.fromCharCode(...data.slice(0, 6)).match(/^GIF8[79]a$/)) {
    return dimensions(view.getUint16(6, true), view.getUint16(8, true), 'image/gif');
  }
  if (data.length >= 30 && fourcc(0) === 'RIFF' && fourcc(8) === 'WEBP') {
    const uint24 = (offset: number) => data[offset] + data[offset + 1] * 256 + data[offset + 2] * 65536;
    if (fourcc(12) === 'VP8X') return dimensions(uint24(24) + 1, uint24(27) + 1, 'image/webp');
    if (fourcc(12) === 'VP8 ') return dimensions(view.getUint16(26, true) & 16383, view.getUint16(28, true) & 16383, 'image/webp');
    if (fourcc(12) === 'VP8L' && data[20] === 0x2f) {
      const bits = view.getUint32(21, true);
      return dimensions((bits & 16383) + 1, ((bits >>> 14) & 16383) + 1, 'image/webp');
    }
  }
  if (data.length >= 26 && data[0] === 66 && data[1] === 77) {
    if (view.getUint32(14, true) === 12) return dimensions(view.getUint16(18, true), view.getUint16(20, true), 'image/bmp');
    return dimensions(view.getInt32(18, true), Math.abs(view.getInt32(22, true)), 'image/bmp');
  }
  throw new Error('Unsupported raster image');
}
