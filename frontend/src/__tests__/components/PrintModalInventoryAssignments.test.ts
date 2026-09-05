import { describe, expect, it } from 'vitest';
import type { SpoolAssignment } from '../../api/client';
import { groupBuiltInSpoolAssignments } from '../../components/PrintModal/inventoryAssignments';

const cachedAssignment = {
  printer_id: 7,
  ams_id: 0,
  tray_id: 2,
  spool_id: 42,
} as SpoolAssignment;

describe('groupBuiltInSpoolAssignments', () => {
  it('groups active built-in assignments by printer and global tray', () => {
    const grouped = groupBuiltInSpoolAssignments([cachedAssignment], false);

    expect(grouped.get(7)?.get(2)).toBe(cachedAssignment);
  });

  it('ignores cached built-in assignments after Spoolman is enabled', () => {
    const grouped = groupBuiltInSpoolAssignments([cachedAssignment], true);

    expect(grouped.size).toBe(0);
  });
});
