import type { SpoolAssignment } from '../../api/client';
import { getGlobalTrayId } from '../../utils/amsHelpers';

export function groupBuiltInSpoolAssignments(
  assignments: SpoolAssignment[] | undefined,
  spoolmanEnabled: boolean,
): Map<number, Map<number, SpoolAssignment>> {
  const grouped = new Map<number, Map<number, SpoolAssignment>>();
  if (spoolmanEnabled || !assignments) return grouped;

  assignments.forEach((assignment) => {
    const globalTrayId = getGlobalTrayId(
      assignment.ams_id,
      assignment.tray_id,
      assignment.ams_id === 255,
    );
    const printerAssignments = grouped.get(assignment.printer_id) ?? new Map();
    printerAssignments.set(globalTrayId, assignment);
    grouped.set(assignment.printer_id, printerAssignments);
  });
  return grouped;
}
