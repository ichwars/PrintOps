import { describe, expect, it } from 'vitest';
import { compareQueueOrder } from '../../utils/queueOrder';

describe('the pending queue uses global positions and SJF priorities', () => {
  it('keeps a pinned job above a model job when its position is lower', () => {
    const jobs = [
      { id: 2, position: 2, printer_id: null, target_model: 'P2S' },
      { id: 1, position: 1, printer_id: 4, target_model: null },
    ];
    expect(jobs.sort((a, b) => compareQueueOrder(a, b)).map(job => job.id)).toEqual([1, 2]);
  });

  it('gives a jumped job priority across printer targets', () => {
    const jobs = [
      { id: 1, position: 1, been_jumped: false, print_time_seconds: 30 },
      { id: 2, position: 2, been_jumped: true, print_time_seconds: 3600 },
    ];
    expect(jobs.sort((a, b) => compareQueueOrder(a, b, true)).map(job => job.id)).toEqual([2, 1]);
  });

  it('keeps unsized jobs last and ties stable', () => {
    const jobs = [
      { id: 4, position: 1, print_time_seconds: null },
      { id: 2, position: 1, print_time_seconds: null },
      { id: 1, position: 2, print_time_seconds: 60 },
    ];
    expect(jobs.sort((a, b) => compareQueueOrder(a, b, true)).map(job => job.id)).toEqual([1, 2, 4]);
  });
});
