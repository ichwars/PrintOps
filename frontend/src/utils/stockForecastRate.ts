import { ARCHIVED_RATE_WINDOW_MS } from './forecastStock';
import { parseUTCDate } from './date';
import type { InventorySpool, SpoolUsageRecord } from '../api/client';

/**
 * Compute a time-weighted daily consumption rate and standard deviation.
 *
 * Algorithm:
 *   1. Aggregate all usage events by calendar day (UTC date string), summing
 *      weight_used across all spools in the group that printed on that day.
 *      Day-bucketing fixes two problems: (a) concurrent prints from multiple
 *      spools in the same group no longer produce near-zero inter-event gaps
 *      that inflate per-interval rates; (b) the oldest event's weight is no
 *      longer silently dropped — it contributes to its day bucket.
 *   2. Sort day buckets oldest → newest and compute inter-day g/day rates.
 *      The gap is in whole days (minimum 1) so same-day reprints don't
 *      create a zero-duration interval.
 *   3. Apply exponential age-decay: each observation is weighted by
 *      exp(-λ * age_days) so recent prints dominate. λ = ln(2)/30 gives a
 *      30-day half-life — prints from a month ago count half as much.
 *   4. Compute the weighted mean and weighted variance → std dev.
 *
 * Returns null when there are fewer than 2 distinct days (no gap to measure)
 * — the delta-rate fallback handles that case.
 */
export function computeHistoryRate(records: SpoolUsageRecord[]): { rate: number; stdDev: number } | null {
  if (records.length < 2) return null;

  // Aggregate by UTC calendar day so concurrent multi-spool prints on the
  // same day are summed before rate computation.
  const byDay = new Map<string, number>();
  for (const r of records) {
    const day = r.created_at.slice(0, 10); // "YYYY-MM-DD" UTC — consistent with server timestamps
    byDay.set(day, (byDay.get(day) ?? 0) + r.weight_used);
  }

  if (byDay.size < 2) return null;

  const days = [...byDay.entries()]
    .map(([day, totalG]) => ({ ms: new Date(day).getTime(), totalG }))
    .sort((a, b) => a.ms - b.ms);

  const now = Date.now();
  // λ for 30-day half-life: ln(2)/30
  const lambda = Math.LN2 / 30;

  const observations: { rate: number; weight: number }[] = [];

  for (let i = 1; i < days.length; i++) {
    const elapsedDays = Math.max((days[i].ms - days[i - 1].ms) / 86400000, 1);
    const ageDays = (now - days[i].ms) / 86400000;

    // g/day for this inter-day interval: weight printed on day[i] / gap to previous day
    const intervalRate = days[i].totalG / elapsedDays;
    const w = Math.exp(-lambda * ageDays);

    observations.push({ rate: intervalRate, weight: w });
  }

  if (observations.length === 1) return { rate: observations[0].rate, stdDev: 0 };

  const totalW = observations.reduce((s, o) => s + o.weight, 0);
  if (totalW === 0) return null;

  const mean = observations.reduce((s, o) => s + o.rate * o.weight, 0) / totalW;
  const variance = observations.reduce((s, o) => s + o.weight * (o.rate - mean) ** 2, 0) / totalW;

  return { rate: mean, stdDev: Math.sqrt(variance) };
}

export function computeDeltaRate(
  spools: InventorySpool[],
  firstUses: ReadonlyMap<number, number> = new Map(),
  usedBefore = false,
): number | null {
  const now = Date.now();
  const windowStart = now - ARCHIVED_RATE_WINDOW_MS;
  const spans = spools.flatMap(spool => {
    const consumed = Math.max(0, spool.weight_used - (spool.weight_used_baseline ?? 0));
    if (!consumed) return [];
    const end = Math.min(parseUTCDate(spool.last_used || spool.archived_at)?.getTime() ?? now, now);
    const first = parseUTCDate(spool.first_used_at)?.getTime() ?? firstUses.get(spool.id)
      ?? parseUTCDate(spool.created_at)?.getTime() ?? end;
    return [{ consumed, start: Math.min(first, end), end }];
  });
  if (!spans.length) return null;
  const oldest = spans.reduce((min, span) => Math.min(min, span.start), now);
  const observedFrom = usedBefore ? windowStart : Math.max(windowStart, oldest);
  const days = (now - observedFrom) / 86400000;
  if (days < 1) return null;
  const grams = spans.reduce((total, { consumed, start, end }) => {
    if (end < observedFrom) return total;
    const span = end - start;
    return total + (span < 86400000 ? consumed : consumed * (end - Math.max(start, observedFrom)) / span);
  }, 0);
  return grams / days;
}
