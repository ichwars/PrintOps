import type { InventorySpool } from '../api/client';

export function formatSpoolDryingDetails(spool: InventorySpool): string {
  const parts: string[] = [];
  if (spool.last_dried_temp != null) parts.push(`${spool.last_dried_temp} °C`);
  if (spool.last_dried_hours != null) parts.push(`${Number(spool.last_dried_hours.toFixed(1))} h`);
  return parts.join(' · ');
}
