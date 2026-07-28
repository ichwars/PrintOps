/**
 * Regression test for the PA-profile picker's nozzle blindness (#2618).
 *
 * Given two K-profiles for the same filament but different nozzle sizes, the
 * picker must offer both and label them by nozzle diameter.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';

import i18n from '../../../i18n';
import { PAProfileSection } from '../../../components/spool-form/PAProfileSection';
import { defaultFormData } from '../../../components/spool-form/types';
import type { PrinterWithCalibrations } from '../../../components/spool-form/types';

const printers = [
  {
    printer: { id: 1, name: 'H2D', connected: true },
    calibrations: [
      { cali_idx: 10, filament_id: 'GFN05', setting_id: '', name: 'PAHT-CF', k_value: 0.042, n_coef: 0, extruder_id: 0, nozzle_diameter: '0.4' },
      { cali_idx: 11, filament_id: 'GFN05', setting_id: '', name: 'PAHT-CF', k_value: 0.028, n_coef: 0, extruder_id: 1, nozzle_diameter: '0.6' },
    ],
  },
] as unknown as PrinterWithCalibrations[];

describe('PAProfileSection nozzle-specific profiles (#2618)', () => {
  it('renders both nozzle profiles for one filament, each with a nozzle badge', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <PAProfileSection
          formData={{ ...defaultFormData, material: 'PAHT-CF', slicer_filament: 'GFN05' }}
          updateField={vi.fn()}
          printersWithCalibrations={printers}
          selectedProfiles={new Set()}
          setSelectedProfiles={vi.fn()}
          expandedPrinters={new Set(['1'])}
          setExpandedPrinters={vi.fn()}
        />
      </I18nextProvider>,
    );

    expect(screen.getByText('K=0.042')).toBeInTheDocument();
    expect(screen.getByText('K=0.028')).toBeInTheDocument();
    expect(screen.getByText('0.4mm')).toBeInTheDocument();
    expect(screen.getByText('0.6mm')).toBeInTheDocument();
  });
});
