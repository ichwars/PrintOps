import { isServerSliceableFilename, isServerSliceableFileType } from './sliceFormats';
import { isSliceableFilename, isSliceableFileType, type SlicerType } from './slicer';

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

  if (fileType === '3mf') return false;

  // Keep filename fallback support for records without a recognized type.
  const filename = file.filename.toLowerCase();
  return filename.endsWith('.gcode') || filename.endsWith('.gcode.3mf');
}

/** Return whether a library file can be sent to the slicer. */
export function isSliceableLibraryFile(file: LibraryFileClassification): boolean {
  return !isSlicedLibraryFile(file)
    && (isServerSliceableFileType(file.file_type) || isServerSliceableFilename(file.filename));
}

export function isDesktopSliceableLibraryFile(file: LibraryFileClassification, slicer: SlicerType): boolean {
  return !isSlicedLibraryFile(file)
    && (isSliceableFileType(file.file_type, slicer) || isSliceableFilename(file.filename, slicer));
}
