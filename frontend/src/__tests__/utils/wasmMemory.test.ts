import { expect, it } from 'vitest';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { capWasmMemory } from '../../utils/wasmMemory';
const require = createRequire(import.meta.url);
const path = require.resolve('occt-import-js/dist/occt-import-js.wasm');
const wasm = readFileSync(path);
function bytes() { return wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength); }
it('caps the real native OCCT memory, including direct memory.grow calls', async () => {
  const occt = require('occt-import-js');
  let memory: WebAssembly.Memory | undefined;
  const importer = await occt({
    wasmBinary: capWasmMemory(bytes()),
    instantiateWasm: (imports: WebAssembly.Imports, receive: (instance: WebAssembly.Instance, module: WebAssembly.Module) => void) => {
      const module = new WebAssembly.Module(capWasmMemory(bytes()));
      const instance = new WebAssembly.Instance(module, imports);
      memory = Object.values(instance.exports).find(value => value instanceof WebAssembly.Memory) as WebAssembly.Memory;
      receive(instance, module); return instance.exports;
    },
  });
  const cube = readFileSync('src/__tests__/fixtures/occt-cube.step');
  const result = importer.ReadStepFile(cube, null);
  expect(result.success).toBe(true);
  expect(result.meshes[0].index.array.length).toBeGreaterThan(0);
  expect(memory).toBeInstanceOf(WebAssembly.Memory);
  const initialPages = memory!.buffer.byteLength / 65536;
  expect(initialPages).toBeGreaterThanOrEqual(457);
  expect(initialPages).toBeLessThan(4096);
  memory!.grow(4096 - initialPages);
  expect(memory!.buffer.byteLength).toBe(256 * 1024 * 1024);
  expect(() => memory!.grow(1)).toThrow(RangeError);
});
it('rejects unexpected memory layouts instead of dropping the native cap', () => {
  const data = new Uint8Array([0,97,115,109,1,0,0,0,5,3,1,0,1]);
  expect(() => capWasmMemory(data.buffer)).toThrow();
});
