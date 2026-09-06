type Translate = (key: string, options?: Record<string, unknown>) => string;

type ArchiveTitle = {
  print_name?: string | null;
  filename: string;
  plate_id?: number | null;
};

export function archiveDisplayName(archive: ArchiveTitle, t: Translate): string {
  const name = archive.print_name || archive.filename;
  const plateId = archive.plate_id;
  if (plateId == null || plateId <= 1) return name;

  const plateLabel = t('printers.plateNumber', { number: plateId });
  const normalizedName = name.toLocaleLowerCase();
  const alreadyIdentified = [`Plate ${plateId}`, plateLabel]
    .some((label) => normalizedName.endsWith(label.toLocaleLowerCase()));
  return alreadyIdentified ? name : `${name} — ${plateLabel}`;
}
