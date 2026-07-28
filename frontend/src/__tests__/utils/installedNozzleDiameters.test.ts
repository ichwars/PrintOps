/**
 * Tests for installedNozzleDiameters helper (#2618).
 *
 * The spool PA-profile picker must fetch K-profiles across every nozzle the
 * printer actually has installed, not just a hardcoded 0.4mm default.
 */

import { describe, it, expect } from 'vitest';

import { installedNozzleDiameters } from '../../utils/amsHelpers';

describe('installedNozzleDiameters', () => {
  it('returns an empty array when status is null or undefined', () => {
    expect(installedNozzleDiameters(null)).toEqual([]);
    expect(installedNozzleDiameters(undefined)).toEqual([]);
  });

  it('returns an empty array when no nozzles are reported', () => {
    expect(installedNozzleDiameters({ nozzles: [] })).toEqual([]);
    expect(installedNozzleDiameters({})).toEqual([]);
  });

  it('skips empty-string and non-positive nozzle defaults', () => {
    expect(
      installedNozzleDiameters({ nozzles: [{ nozzle_diameter: '' }, { nozzle_diameter: '0' }] }),
    ).toEqual([]);
  });

  it('returns the single installed diameter', () => {
    expect(installedNozzleDiameters({ nozzles: [{ nozzle_diameter: '0.4' }] })).toEqual(['0.4']);
  });

  it('returns both diameters on a dual-nozzle printer, in order', () => {
    expect(
      installedNozzleDiameters({ nozzles: [{ nozzle_diameter: '0.4' }, { nozzle_diameter: '0.6' }] }),
    ).toEqual(['0.4', '0.6']);
  });

  it('dedupes repeated diameters', () => {
    expect(
      installedNozzleDiameters({ nozzles: [{ nozzle_diameter: '0.4' }, { nozzle_diameter: '0.4' }] }),
    ).toEqual(['0.4']);
  });

  it('keeps only the valid diameter when one hotend is still an empty default', () => {
    expect(
      installedNozzleDiameters({ nozzles: [{ nozzle_diameter: '0.6' }, { nozzle_diameter: '' }] }),
    ).toEqual(['0.6']);
  });
});
