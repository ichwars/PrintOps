import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from '../../../api/client';
import { fetchPrinterCalibrations } from '../../../components/spool-form/utils';
import { installedNozzleDiameters } from '../../../utils/amsHelpers';

vi.mock('../../../api/client', () => ({
  api: {
    getKProfiles: vi.fn(),
  },
}));

describe('installedNozzleDiameters', () => {
  it('returns unique positive reported nozzle diameters', () => {
    expect(
      installedNozzleDiameters({
        nozzles: [
          { nozzle_diameter: '0.4' },
          { nozzle_diameter: '' },
          { nozzle_diameter: '0' },
          { nozzle_diameter: '0.6' },
          { nozzle_diameter: '0.4' },
        ],
      }),
    ).toEqual(['0.4', '0.6']);
  });
});

describe('fetchPrinterCalibrations', () => {
  beforeEach(() => {
    vi.mocked(api.getKProfiles).mockReset();
  });

  it('fetches and merges K-profiles for every installed nozzle diameter', async () => {
    vi.mocked(api.getKProfiles)
      .mockResolvedValueOnce({
        profiles: [
          {
            slot_id: 1,
            filament_id: 'GFA00',
            setting_id: 'GFSA00_01',
            name: 'ASA 0.4',
            k_value: '0.020000',
            n_coef: '1.400000',
            extruder_id: 0,
            nozzle_diameter: '0.4',
          },
        ],
      })
      .mockResolvedValueOnce({
        profiles: [
          {
            slot_id: 2,
            filament_id: 'GFA00',
            setting_id: 'GFSA00_02',
            name: 'ASA 0.6',
            k_value: '0.030000',
            n_coef: '1.400000',
            extruder_id: 1,
            nozzle_diameter: '0.6',
          },
        ],
      });

    const result = await fetchPrinterCalibrations(7, {
      nozzles: [{ nozzle_diameter: '0.4' }, { nozzle_diameter: '0.6' }],
    });

    expect(api.getKProfiles).toHaveBeenCalledWith(7, '0.4');
    expect(api.getKProfiles).toHaveBeenCalledWith(7, '0.6');
    expect(result.map((profile) => profile.nozzle_diameter)).toEqual(['0.4', '0.6']);
  });

  it('falls back to 0.4 when no nozzle hardware has been reported', async () => {
    vi.mocked(api.getKProfiles).mockResolvedValueOnce({ profiles: [] });

    await fetchPrinterCalibrations(9, { nozzles: [{ nozzle_diameter: '' }] });

    expect(api.getKProfiles).toHaveBeenCalledTimes(1);
    expect(api.getKProfiles).toHaveBeenCalledWith(9, '0.4');
  });
});
