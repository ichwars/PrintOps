import occtimportjs from 'occt-import-js';
import { capWasmMemory } from '../utils/wasmMemory';
import type { StepMesh } from '../utils/stepPreview';

// This worker has connect-src/worker-src 'none'. Both inputs arrive by transfer.
self.onmessage = async (event: MessageEvent<{ buffer: ArrayBuffer; wasmBuffer: ArrayBuffer }>) => {
  try {
    const { buffer, wasmBuffer } = event.data;
    if (buffer.byteLength > 32 * 1024 * 1024 || wasmBuffer.byteLength > 8 * 1024 * 1024) throw new Error('STEP byte limit exceeded');
    const importer = await occtimportjs({ wasmBinary: capWasmMemory(wasmBuffer) });
    const result = importer.ReadStepFile(new Uint8Array(buffer), {
      linearUnit: 'millimeter', linearDeflectionType: 'bounding_box_ratio', linearDeflection: 0.005, angularDeflection: 0.5,
    });
    if (!result.success || !result.meshes.length || result.meshes.length > 100) throw new Error('STEP contains no supported meshes');
    let triangles = 0; let bytes = 0;
    const meshes: StepMesh[] = result.meshes.map(mesh => {
      triangles += mesh.index.array.length / 3;
      bytes += 4 * (mesh.attributes.position.array.length + mesh.index.array.length + (mesh.attributes.normal?.array.length ?? 0));
      if (triangles > 1_000_000 || bytes > 96 * 1024 * 1024) throw new Error('STEP geometry limit exceeded');
      return { positions: new Float32Array(mesh.attributes.position.array), indices: new Uint32Array(mesh.index.array),
        normals: mesh.attributes.normal ? new Float32Array(mesh.attributes.normal.array) : undefined, color: mesh.color };
    });
    const transfer: ArrayBuffer[] = meshes.flatMap(mesh => [mesh.positions.buffer as ArrayBuffer, mesh.indices.buffer as ArrayBuffer,
      ...(mesh.normals ? [mesh.normals.buffer as ArrayBuffer] : [])]);
    self.postMessage({ meshes }, { transfer });
  } catch { self.postMessage({ error: 'STEP conversion failed or exceeded its limits' }); }
};
