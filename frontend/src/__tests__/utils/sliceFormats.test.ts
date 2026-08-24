/**
 * Format boundary for server-side slicing (#92).
 *
 * STEP/STP stay uploadable and previewable but must never be offered to the
 * slicer sidecar, which cannot import them.
 */

import { describe, it, expect } from 'vitest';
import {
  isServerSliceableFilename,
  isServerSliceableFileType,
  isUnsliceableCadFilename,
  isUnsliceableCadFileType,
} from '../../utils/sliceFormats';

describe('isServerSliceableFilename', () => {
  it('accepts model geometry formats the sidecar handles', () => {
    expect(isServerSliceableFilename('bracket.stl')).toBe(true);
    expect(isServerSliceableFilename('Bracket.STL')).toBe(true);
    expect(isServerSliceableFilename('plate.3mf')).toBe(true);
  });

  it('rejects STEP and STP', () => {
    expect(isServerSliceableFilename('flange.step')).toBe(false);
    expect(isServerSliceableFilename('flange.STEP')).toBe(false);
    expect(isServerSliceableFilename('flange.stp')).toBe(false);
    expect(isServerSliceableFilename('flange.Stp')).toBe(false);
  });

  it('rejects already-sliced outputs and unrelated files', () => {
    expect(isServerSliceableFilename('benchy.gcode')).toBe(false);
    expect(isServerSliceableFilename('benchy.gcode.3mf')).toBe(false);
    expect(isServerSliceableFilename('notes.txt')).toBe(false);
    expect(isServerSliceableFilename(null)).toBe(false);
    expect(isServerSliceableFilename(undefined)).toBe(false);
  });
});

describe('isUnsliceableCadFilename', () => {
  it('flags only STEP/STP', () => {
    expect(isUnsliceableCadFilename('flange.step')).toBe(true);
    expect(isUnsliceableCadFilename('flange.STP')).toBe(true);
    expect(isUnsliceableCadFilename('bracket.stl')).toBe(false);
    expect(isUnsliceableCadFilename('')).toBe(false);
  });
});

describe('file_type variants', () => {
  it('mirrors the filename checks', () => {
    expect(isServerSliceableFileType('stl')).toBe(true);
    expect(isServerSliceableFileType('3mf')).toBe(true);
    expect(isServerSliceableFileType('step')).toBe(false);
    expect(isServerSliceableFileType('stp')).toBe(false);
    expect(isUnsliceableCadFileType('step')).toBe(true);
    expect(isUnsliceableCadFileType('STP')).toBe(true);
    expect(isUnsliceableCadFileType('stl')).toBe(false);
  });
});
