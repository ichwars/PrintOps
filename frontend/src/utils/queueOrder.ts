import type { PrintQueueItem } from '../api/client';

type OrderedItem = Pick<PrintQueueItem, 'id' | 'position'> &
  Partial<Pick<PrintQueueItem, 'been_jumped' | 'print_time_seconds'>>;

export function compareQueueOrder(a: OrderedItem, b: OrderedItem, shortestFirst = false): number {
  if (shortestFirst) {
    const jumped = Number(Boolean(b.been_jumped)) - Number(Boolean(a.been_jumped));
    if (jumped) return jumped;
    const aTime = a.print_time_seconds ?? Infinity;
    const bTime = b.print_time_seconds ?? Infinity;
    if (aTime !== bTime) return aTime - bTime;
  }
  return a.position - b.position || a.id - b.id;
}
