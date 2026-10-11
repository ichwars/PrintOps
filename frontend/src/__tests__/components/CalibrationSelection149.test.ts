import { describe, expect, it } from 'vitest';
import { calibrationInput, calibrationKey } from '../../components/spool-form/calibrationSelection';
import type { CalibrationProfile, PrinterWithCalibrations } from '../../components/spool-form/types';

const profile = (size: string, flow?: string): CalibrationProfile => ({
  cali_idx: 5, extruder_id: 0, nozzle_diameter: size, nozzle_id: flow,
  filament_id: 'P1234', setting_id: `P${size}${flow ?? ''}`, name: 'PLA', k_value: 0.02, n_coef: 0,
});
const printers = (calibrations: CalibrationProfile[]) => [
  { printer: { id: 1, model: 'P2S' }, calibrations },
] as PrinterWithCalibrations[];

describe('calibration selection context', () => {
  it('partitions a reused index by diameter and explicit standard/high flow', () => {
    const profiles = [profile('0.4', 'HS00_0.4'), profile('0.4', 'HH00_0.4'), profile('0.6', 'HS00_0.6')];
    expect(new Set(profiles.map(p => calibrationKey(1, p))).size).toBe(3);
    for (const p of profiles) {
      expect(calibrationInput(calibrationKey(1, p), printers(profiles))).toEqual(expect.objectContaining({
        nozzle_diameter: p.nozzle_diameter, nozzle_type: p.nozzle_id!.slice(0, 2), setting_id: p.setting_id,
      }));
    }
  });

  it('accepts a legacy key only when its context is unique', () => {
    expect(calibrationInput('1:5:null', printers([profile('0.4')]))?.nozzle_diameter).toBe('0.4');
    expect(calibrationInput('1:5:null', printers([profile('0.4'), profile('0.6')]))).toBeNull();
    expect(calibrationInput('1:5:0', printers([profile('0.4', 'HS'), profile('0.4', 'HH')]))).toBeNull();
  });

  it('does not guess missing diameter or resolve duplicate rows', () => {
    const missing = { ...profile('0.4'), nozzle_diameter: undefined };
    expect(calibrationInput(calibrationKey(1, missing), printers([missing]))).toBeNull();
    const p = profile('0.4');
    expect(calibrationInput(calibrationKey(1, p), printers([p, p]))).toBeNull();
    expect(calibrationInput(calibrationKey(1, p), printers([]))).toBeNull();
  });
});
