import { request } from './core';

interface ArchiveMergeMember {
  id: number;
  print_name: string | null;
  filename: string;
  created_at: string;
  run_count: number;
}

interface ArchiveMergeGroup {
  survivor: ArchiveMergeMember;
  merged: ArchiveMergeMember[];
  skipped: 'busy' | null;
}

interface ArchiveMergeSelection {
  survivor_id: number;
  merged_ids: number[];
}

export const archiveMergeApi = {
  count: () => request<{ groups: number }>('/archives/merge-count'),
  preview: () => request<{ groups: ArchiveMergeGroup[] }>('/archives/merge-preview'),
  merge: (groups: ArchiveMergeSelection[]) => request<{
    merged: ArchiveMergeSelection[];
    skipped: { survivor_id: number; reason: string }[];
  }>('/archives/merge', { method: 'POST', body: JSON.stringify({ groups }) }),
};
