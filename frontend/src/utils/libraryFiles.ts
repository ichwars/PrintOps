import { isServerSliceableFilename } from './sliceFormats';

type LibraryFileClassification = {
  filename: string;
  file_type?: string | null;
};

/** Return whether a library file is already sliced and ready to print. */
export function isSlicedLibraryFile(file: LibraryFileClassification): boolean {
  const fileType = (file.file_type ?? '').toLowerCase();
  if (fileType === 'gcode' || fileType === 'gcode.3mf') {
    return true;
  }

  // Keep filename fallback support for records created before the content-based
  // 3MF classification/backfill introduced for issue #132.
  const filename = file.filename.toLowerCase();
  return filename.endsWith('.gcode') || filename.endsWith('.gcode.3mf');
}

/** Return whether a library file can be sent to the slicer. */
export function isSliceableLibraryFile(file: LibraryFileClassification): boolean {
  return !isSlicedLibraryFile(file) && isServerSliceableFilename(file.filename);
}
