import type { PrintQueueItem } from '../api/client';
import { compareQueueOrder } from './queueOrder';

export type QueuePreviewState = 'checks' | 'manual' | 'scheduled' | 'blocked' | 'dispatching';

// This is a read-only candidate, not a dispatch prediction: printer locks,
// drying ownership, Batch runs, predecessor success and live spool checks
// remain exclusively the scheduler's responsibility. Waiting reasons can be stale.
export function queuePreview(items: PrintQueueItem[], shortestFirst: boolean, now = Date.now()) {
  const ordered = [...items].sort((a, b) => compareQueueOrder(
    { ...a, print_time_seconds: a.scheduler_print_time_seconds },
    { ...b, print_time_seconds: b.scheduler_print_time_seconds }, shortestFirst,
  ));
  const state = (item: PrintQueueItem): QueuePreviewState => {
    if (item.dispatching) return 'dispatching';
    if (item.manual_start) return 'manual';
    if (item.scheduled_time && new Date(item.scheduled_time).getTime() > now) return 'scheduled';
    if (item.waiting_reason || (item.filament_short && !item.skip_filament_check)) return 'blocked';
    return 'checks';
  };
  const item = ordered.find(item => state(item) === 'checks') ?? ordered[0];
  return item ? { item, state: state(item) } : null;
}
