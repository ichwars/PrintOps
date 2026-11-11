import { afterEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { batched } from '../../api/batch';
import { api, ApiError, setAuthToken } from '../../api/client';
import { server } from '../mocks/server';

afterEach(() => setAuthToken(null));

describe('Batched card reads', () => {
  it('coalesces printer status reads and routes unordered responses by id', async () => {
    const seen: string[] = [];
    server.use(http.get('*/api/v1/bulk/printer-statuses', ({ request }) => {
      seen.push(new URL(request.url).searchParams.get('ids') ?? '');
      return HttpResponse.json([{ id: 2, state: 'IDLE' }, { id: 1, state: 'RUNNING' }]);
    }));
    const result = await Promise.all([api.getPrinterStatus(1), api.getPrinterStatus(2), api.getPrinterStatus(1)]);
    expect(seen).toEqual(['1,2']);
    expect(result.map((status) => [status.id, status.state])).toEqual([
      [1, 'RUNNING'], [2, 'IDLE'], [1, 'RUNNING'],
    ]);
  });

  it('uses the individual route for a single or omitted id', async () => {
    const single = vi.fn(async (id: number) => `single ${id}`);
    const many = vi.fn(async () => new Map([[1, 'bulk 1']]));
    const read = batched(single, many);
    await expect(Promise.all([read(1), read(2)])).resolves.toEqual(['bulk 1', 'single 2']);
    expect(single).toHaveBeenCalledExactlyOnceWith(2);
    await expect(read(3)).resolves.toBe('single 3');
  });

  it('propagates permission failures without retrying each id', async () => {
    const single = vi.fn(async () => 'single');
    const read = batched(single, async () => { throw new ApiError('Denied', 403); });
    const result = await Promise.allSettled([read(1), read(2)]);
    expect(result.every((reply) => reply.status === 'rejected')).toBe(true);
    expect(single).not.toHaveBeenCalled();
  });

  it('does not make a queued request with credentials from a newer session', async () => {
    setAuthToken('first fixture token');
    const single = vi.fn(async (id: number) => id);
    const many = vi.fn(async () => new Map<number, number>());
    const read = batched(single, many);
    const earlier = read(1);
    setAuthToken('second fixture token');
    const later = read(2);

    await expect(earlier).rejects.toMatchObject({ name: 'AbortError' });
    await expect(later).resolves.toBe(2);
    expect(single).toHaveBeenCalledExactlyOnceWith(2);
    expect(many).not.toHaveBeenCalled();
  });
});
