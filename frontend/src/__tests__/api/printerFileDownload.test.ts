import { afterEach, describe, expect, it, vi } from 'vitest';
import { printersFilesMethods } from '../../api/client/printers-files';
import { setAuthToken } from '../../api/client/core';

afterEach(() => {
  vi.unstubAllGlobals();
  setAuthToken(null);
});

describe('printer file download streaming', () => {
  it('writes body chunks to the file stream without calling blob and sends authorization', async () => {
    setAuthToken('test-video-token');
    const received: Uint8Array[] = [];
    const response = new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new Uint8Array([1, 2]));
        controller.enqueue(new Uint8Array([3, 4]));
        controller.close();
      },
    }));
    const blob = vi.spyOn(response, 'blob');
    const fetch = vi.fn().mockResolvedValue(response);
    vi.stubGlobal('fetch', fetch);
    const writable = new WritableStream<Uint8Array>({ write(chunk) { received.push(chunk); } });
    await printersFilesMethods.downloadPrinterFile(1, '/ipcam/video.mp4', writable).promise;
    expect(received.map(chunk => [...chunk])).toEqual([[1, 2], [3, 4]]);
    expect(blob).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledWith(expect.not.stringContaining('token='), expect.objectContaining({
      headers: { Authorization: 'Bearer test-video-token' }, signal: expect.any(AbortSignal),
    }));
  });

  it('cancels the response source and aborts the file stream', async () => {
    const sourceCancelled = vi.fn();
    const destinationAborted = vi.fn();
    let resolveWrite: () => void = () => {};
    const started = new Promise<void>(resolve => { resolveWrite = resolve; });
    const response = new Response(new ReadableStream<Uint8Array>({
      start(controller) { controller.enqueue(new Uint8Array([1, 2])); },
      cancel: sourceCancelled,
    }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    const writable = new WritableStream<Uint8Array>({
      write() { resolveWrite(); }, abort: destinationAborted,
    });
    const operation = printersFilesMethods.downloadPrinterFile(1, '/video.mp4', writable);
    await started;
    operation.cancel();
    await expect(operation.promise).rejects.toHaveProperty('name', 'AbortError');
    expect(sourceCancelled).toHaveBeenCalledOnce();
    expect(destinationAborted).toHaveBeenCalledOnce();
  });

  it('preserves missing-file errors and aborts an unused writable destination', async () => {
    const aborted = vi.fn();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'File not found' }), { status: 404 })));
    const writable = new WritableStream<Uint8Array>({ abort: aborted });
    await expect(printersFilesMethods.downloadPrinterFile(1, '/missing.mp4', writable).promise).rejects.toThrow('File not found');
    expect(aborted).toHaveBeenCalledOnce();
  });
});
