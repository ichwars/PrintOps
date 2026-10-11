import { describe, expect, it, vi } from 'vitest';
import { computeHistoryRate, computeDeltaRate } from '../../components/ForecastPanel';
import type { InventorySpool, SpoolUsageRecord } from '../../api/client';

const NOW = Date.parse('2026-09-30T00:00:00Z');
const ago = (days: number) => new Date(NOW - days * 86400000).toISOString();

describe('actual ForecastPanel rate parity vectors used by backend alerts', () => {
  it('uses weighted inter-day history and buckets concurrent prints', () => {
    vi.spyOn(Date, 'now').mockReturnValue(NOW);
    const records = [[40,120],[25,90],[12,200],[3,150]].map(([days, weight_used]) => ({created_at:ago(days),weight_used})) as SpoolUsageRecord[];
    expect(computeHistoryRate(records)?.rate).toBeCloseTo(13.57710201710711, 10);
    expect(computeHistoryRate([{created_at:ago(2),weight_used:30},{created_at:ago(1),weight_used:4},{created_at:ago(1),weight_used:6}] as SpoolUsageRecord[])).toEqual({rate:10,stdDev:0});
    vi.restoreAllMocks();
  });
  it('uses own consumed baseline and oldest spool for delta fallback', () => {
    vi.spyOn(Date, 'now').mockReturnValue(NOW);
    const spools = [{weight_used:700,weight_used_baseline:200,created_at:ago(50)},{weight_used:300,weight_used_baseline:0,created_at:ago(30)}] as InventorySpool[];
    expect(computeDeltaRate(spools)).toBe(16);
    expect(computeDeltaRate([{weight_used:700,weight_used_baseline:700,created_at:ago(50)}] as InventorySpool[])).toBeNull();
    vi.restoreAllMocks();
  });
});
