import { describe, expect, it, vi } from 'vitest';

import { clearQueueHistory } from '../../utils/queueHistory';

describe('clearQueueHistory', () => {
  it('processes history sequentially and reports templates retained for open batches', async () => {
    const remove = vi.fn(async (id: number) => ({ deleted: id !== 2 }));

    const result = await clearQueueHistory(
      [
        { id: 1, status: 'failed' },
        { id: 2, status: 'cancelled' },
        { id: 3, status: 'pending' },
      ],
      remove,
    );

    expect(remove.mock.calls).toEqual([[1], [2]]);
    expect(result).toEqual({ cleared: 1, kept: 1 });
  });
});
