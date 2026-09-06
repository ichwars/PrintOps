import { describe, expect, it } from 'vitest';

import { isSliceableLibraryFile, isSlicedLibraryFile } from '../../utils/libraryFiles';

describe('isSlicedLibraryFile', () => {
  it('prefers a content-detected sliced type over a plain 3MF filename', () => {
    expect(
      isSlicedLibraryFile({ filename: 'Labyrinth - Plate 3.3mf', file_type: 'gcode.3mf' })
    ).toBe(true);
  });

  it('does not treat a source 3MF as sliced', () => {
    expect(isSlicedLibraryFile({ filename: 'model.3mf', file_type: '3mf' })).toBe(false);
  });

  it('recognizes raw G-code by its detected type', () => {
    expect(isSlicedLibraryFile({ filename: 'print.data', file_type: 'gcode' })).toBe(true);
  });

  it('keeps the legacy filename fallback for stale records', () => {
    expect(isSlicedLibraryFile({ filename: 'benchy.gcode.3mf', file_type: '3mf' })).toBe(true);
    expect(isSlicedLibraryFile({ filename: 'benchy.gcode' })).toBe(true);
  });
});

describe('isSliceableLibraryFile', () => {
  it('allows source models but excludes content-detected sliced 3MF files', () => {
    expect(isSliceableLibraryFile({ filename: 'model.3mf', file_type: '3mf' })).toBe(true);
    expect(
      isSliceableLibraryFile({ filename: 'Labyrinth - Plate 3.3mf', file_type: 'gcode.3mf' })
    ).toBe(false);
  });

  it('keeps unsupported CAD files out of the slicer', () => {
    expect(isSliceableLibraryFile({ filename: 'model.step', file_type: 'step' })).toBe(false);
  });
});
