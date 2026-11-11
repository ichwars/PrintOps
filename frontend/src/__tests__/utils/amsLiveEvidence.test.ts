import {describe, expect, it} from 'vitest';
import {amsHasLoadedTray, getAmsLabel, isAmsHtUnit, trayForSlot} from '../../utils/amsHelpers';

it('keeps a sparse regular AMS report in its actual slot', () => {
  const trays = [{id: 3, state: 7}];
  expect(trayForSlot(trays, 0)).toBeUndefined();
  expect(trayForSlot(trays, 3)).toBe(trays[0]);
  expect(getAmsLabel(0)).toBe('AMS-A');
  expect(getAmsLabel(128)).toBe('HT-A');
  expect(getAmsLabel(6)).toBe('AMS Lite');
  expect(isAmsHtUnit(0)).toBe(false);
});

it('uses positional fallback only when firmware ids cannot distinguish trays', () => {
  const trays = [{id: 0, state: 1}, {id: 0, state: 2}];
  expect(trayForSlot(trays, 1)).toBe(trays[1]);
});

describe('safe drying rotation', () => {
  const ams = {id: 1, tray: [{id: 2, state: 7}]};
  it('recognizes the loaded tray even with another firmware state code', () => {
    expect(amsHasLoadedTray(ams, 6, null)).toBe(true);
  });
  it('recognizes an inactive nozzle feed and keeps another AMS independent', () => {
    expect(amsHasLoadedTray(ams, 0, {'1': {ams_id: 1, has_filament: true}})).toBe(true);
    expect(amsHasLoadedTray(ams, 0, {'1': {ams_id: 0, has_filament: true}})).toBe(false);
  });
});
