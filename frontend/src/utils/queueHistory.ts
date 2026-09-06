type QueueHistoryItem = { id: number; status: string };
type QueueRemovalResult = { deleted: boolean };

const HISTORY_STATUSES = new Set(['completed', 'failed', 'skipped', 'cancelled']);

export async function clearQueueHistory(
  items: QueueHistoryItem[],
  remove: (id: number) => Promise<QueueRemovalResult>,
): Promise<{ cleared: number; kept: number }> {
  let cleared = 0;
  let kept = 0;
  for (const item of items) {
    if (!HISTORY_STATUSES.has(item.status)) continue;
    const result = await remove(item.id);
    if (result.deleted) cleared += 1;
    else kept += 1;
  }
  return { cleared, kept };
}
