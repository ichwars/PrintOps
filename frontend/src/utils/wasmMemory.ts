/** Lower the declared maximum of OCCT's single, non-shared WASM memory.
 * The native engine cannot bypass this limit with an internal memory.grow.
 * Reject a changed package layout rather than silently leaving it unbounded.
 */
export function capWasmMemory(buffer: ArrayBuffer, maxPages = 4096): Uint8Array {
  const data = new Uint8Array(buffer);
  if (data.length < 8 || new DataView(buffer).getUint32(0, true) !== 0x6d736100) throw new Error('Invalid WASM');
  let offset = 8;
  const read = () => {
    let value = 0;
    for (let shift = 0; shift < 35; shift += 7) {
      if (offset >= data.length) throw new Error('Truncated WASM');
      const byte = data[offset++];
      value += (byte & 127) * 2 ** shift;
      if (!(byte & 128)) return value;
    }
    throw new Error('Invalid WASM integer');
  };
  const encode = (value: number) => {
    const bytes = [];
    do { let byte = value & 127; value = Math.floor(value / 128); if (value) byte |= 128; bytes.push(byte); } while (value);
    return bytes;
  };
  while (offset < data.length) {
    const start = offset;
    const id = data[offset++];
    const length = read();
    const end = offset + length;
    if (end > data.length) throw new Error('Truncated WASM section');
    if (id === 5) {
      const count = read(); const flags = read(); const minimum = read(); const maximum = read();
      if (count !== 1 || flags !== 1 || offset !== end || minimum > maxPages) throw new Error('Unsupported WASM memory layout');
      const section = [1, 1, ...encode(minimum), ...encode(Math.min(maximum, maxPages))];
      const replacement = new Uint8Array([5, ...encode(section.length), ...section]);
      const result = new Uint8Array(start + replacement.length + data.length - end);
      result.set(data.slice(0, start)); result.set(replacement, start); result.set(data.slice(end), start + replacement.length);
      return result;
    }
    offset = end;
  }
  throw new Error('WASM memory section missing');
}
