import { readPreviewResponse } from './previewBytes';

export interface StepMesh {
  positions: Float32Array;
  normals?: Float32Array;
  indices: Uint32Array;
  color?: [number, number, number];
}
export const STEP_MAX_BYTES = 32 * 1024 * 1024;
export const STEP_MAX_TRIANGLES = 1_000_000;
export const STEP_MAX_MESHES = 100;
export const STEP_MAX_GEOMETRY_BYTES = 96 * 1024 * 1024;

export function validateStepMeshes(meshes: StepMesh[]): void {
  if (!Array.isArray(meshes) || meshes.length === 0 || meshes.length > STEP_MAX_MESHES) throw new Error('STEP mesh limit exceeded');
  let triangles = 0; let bytes = 0;
  for (const mesh of meshes) {
    if (!(mesh.positions instanceof Float32Array) || !(mesh.indices instanceof Uint32Array)
      || mesh.positions.length % 3 || mesh.indices.length % 3) throw new Error('Invalid STEP geometry');
    triangles += mesh.indices.length / 3;
    bytes += mesh.positions.byteLength + mesh.indices.byteLength + (mesh.normals?.byteLength ?? 0);
    if (triangles > STEP_MAX_TRIANGLES || bytes > STEP_MAX_GEOMETRY_BYTES) throw new Error('STEP geometry limit exceeded');
    if (mesh.normals && (!(mesh.normals instanceof Float32Array) || mesh.normals.length !== mesh.positions.length)) throw new Error('Invalid STEP normals');
    if (mesh.positions.some(value => !Number.isFinite(value)) || mesh.normals?.some(value => !Number.isFinite(value))
      || mesh.indices.some(value => value >= mesh.positions.length / 3)) throw new Error('Invalid STEP geometry');
  }
}

export async function loadStepPreview(url: string, headers: HeadersInit, signal: AbortSignal): Promise<StepMesh[]> {
  const controller = new AbortController();
  let worker: Worker | undefined;
  let rejectWorker: ((error: Error) => void) | undefined;
  const cancel = () => { controller.abort(signal.reason); rejectWorker?.(new DOMException('Preview closed', 'AbortError')); };
  signal.addEventListener('abort', cancel, { once: true });
  if (signal.aborted) cancel();
  const timeout = setTimeout(() => {
    controller.abort(new Error('STEP conversion timed out'));
    rejectWorker?.(new Error('STEP conversion timed out'));
  }, 30_000);
  try {
    const buffer = await readPreviewResponse(await fetch(url, { headers, signal: controller.signal }), STEP_MAX_BYTES);
    if (!new TextDecoder().decode(buffer.slice(0, 4096)).includes('ISO-10303-21;')) throw new Error('Invalid STEP file');
    const { stepWasmUrl } = await import('./stepAssets');
    controller.signal.throwIfAborted();
    const wasmBuffer = await readPreviewResponse(await fetch(stepWasmUrl, { signal: controller.signal }), 8 * 1024 * 1024);
    controller.signal.throwIfAborted();
    worker = new Worker(new URL('../workers/stepPreview.worker.ts', import.meta.url), { type: 'module' });
    return await new Promise<StepMesh[]>((resolve, reject) => {
      rejectWorker = reject;
      worker!.onerror = () => reject(new Error('STEP conversion failed'));
      worker!.onmessage = (event: MessageEvent<{ meshes?: StepMesh[]; error?: string }>) => {
        try {
          if (event.data.error || !event.data.meshes) throw new Error(event.data.error || 'STEP contains no meshes');
          validateStepMeshes(event.data.meshes); resolve(event.data.meshes);
        } catch (error) { reject(error); }
      };
      worker!.postMessage({ buffer, wasmBuffer }, [buffer, wasmBuffer]);
    });
  } finally {
    clearTimeout(timeout); signal.removeEventListener('abort', cancel); controller.abort(); worker?.terminate();
  }
}
