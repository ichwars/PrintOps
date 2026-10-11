import { afterEach, expect, it, vi } from 'vitest';
import { loadStepPreview } from '../../utils/stepPreview';
vi.mock('../../utils/stepAssets', () => ({ stepWasmUrl: '/assets/occt-test.wasm' }));
class FakeWorker {
  static last: FakeWorker;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  postMessage = vi.fn(); terminate = vi.fn();
  constructor() { FakeWorker.last = this; }
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
function prepare() {
  vi.stubGlobal('Worker', FakeWorker);
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(new Response(
    url.includes('.wasm') ? new Uint8Array([0, 97, 115, 109]) : 'ISO-10303-21; HEADER; ENDSEC; DATA; ENDSEC; END-ISO-10303-21;',
  ))));
}
it('transfers both STEP and WASM buffers and releases its dedicated worker on success', async () => {
  prepare(); const task = loadStepPreview('/part.step', {}, new AbortController().signal);
  await vi.waitFor(() => expect(FakeWorker.last.postMessage).toHaveBeenCalled());
  const [request, transfer] = FakeWorker.last.postMessage.mock.calls[0];
  expect(transfer).toEqual([request.buffer, request.wasmBuffer]);
  FakeWorker.last.onmessage?.({ data: { meshes: [{ positions: new Float32Array([0,0,0,1,0,0,0,1,0]), indices: new Uint32Array([0,1,2]) }] } } as MessageEvent);
  expect((await task)[0].indices).toEqual(new Uint32Array([0,1,2]));
  expect(FakeWorker.last.terminate).toHaveBeenCalledOnce();
});
it('terminates conversion when its preview closes', async () => {
  prepare(); const controller = new AbortController();
  const task = loadStepPreview('/part.step', {}, controller.signal);
  await vi.waitFor(() => expect(FakeWorker.last.postMessage).toHaveBeenCalled());
  controller.abort(); await expect(task).rejects.toMatchObject({ name: 'AbortError' });
  expect(FakeWorker.last.terminate).toHaveBeenCalledOnce();
});
it('terminates conversion after 30 seconds', async () => {
  prepare(); vi.useFakeTimers(); const task = loadStepPreview('/part.step', {}, new AbortController().signal);
  const rejection = expect(task).rejects.toThrow(/timed out/);
  await vi.advanceTimersByTimeAsync(30_000); await rejection;
  expect(FakeWorker.last.terminate).toHaveBeenCalledOnce();
});
it('rejects oversized actual responses before constructing a worker', async () => {
  prepare(); vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('small', { headers: { 'Content-Length': String(32 * 1024 * 1024 + 1) } }))));
  const previous = FakeWorker.last;
  await expect(loadStepPreview('/part.step', {}, new AbortController().signal)).rejects.toThrow(/byte limit/);
  expect(FakeWorker.last).toBe(previous);
});
