import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import {
  DryerManagementCard,
  PrinterManagementCard,
} from '../../components/settings/DeviceManagement';

const printer = {
  id: 1,
  name: 'X1 Carbon',
  serial_number: '01S00A000000001',
  ip_address: '192.168.1.40',
  model: 'X1C',
  location: null,
  nozzle_count: 1,
  is_active: true,
  auto_archive: true,
  external_camera_url: null,
  external_camera_type: null,
  external_camera_enabled: false,
  external_camera_snapshot_url: null,
  camera_rotation: 0,
  plate_detection_enabled: false,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
  acquisition_date: '2025-01-15',
  acquisition_value: '1400.00',
  service_years: '5.00',
  annual_hours: '1200.00',
  maintenance_rate: '0.10',
  nominal_power_watts: '350.00',
  residual_value: '1120.00',
  hourly_rate: '0.48',
};

const dryer = {
  id: 7,
  equipment_type: 'dryer' as const,
  name: 'Filament Dryer Pro',
  is_active: true,
  acquisition_date: '2025-02-01',
  acquisition_value: '190.00',
  service_years: '4.00',
  annual_hours: '500.00',
  maintenance_rate: '0.10',
  nominal_power_watts: '250.00',
  residual_value: '142.50',
  hourly_rate: '0.12',
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

function useDeviceHandlers() {
  server.use(
    http.get('/api/v1/printers/', () => HttpResponse.json([printer])),
    http.get('/api/v1/equipment/', () => HttpResponse.json([dryer])),
  );
}

describe('DeviceManagement cards', () => {
  it('renders separate printer and dryer cards with approved accents', async () => {
    useDeviceHandlers();
    const { container } = render(
      <>
        <PrinterManagementCard locale="de" />
        <DryerManagementCard locale="de" />
      </>,
    );

    expect(await screen.findByRole('heading', { name: 'Drucker' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Trockner' })).toBeInTheDocument();
    expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
    expect(screen.getByText('Filament Dryer Pro')).toBeInTheDocument();
    expect(screen.getByText(/1\.120,00\s€/)).toBeInTheDocument();
    expect(screen.getByText(/142,50\s€/)).toBeInTheDocument();

    expect(container.querySelector('[data-device-card="printers"]')).toHaveClass(
      'border-bambu-dark-tertiary',
    );
    expect(container.querySelector('[data-device-accent="printer"]')).toHaveClass(
      'text-bambu-green',
    );
    expect(container.querySelector('[data-device-accent="dryer"]')).toHaveClass(
      'text-cyan-400',
    );
    expect(container.querySelector('.bg-bambu-orange')).toBeNull();
  });

  it('opens and closes both inline add forms without submitting', async () => {
    useDeviceHandlers();
    const user = userEvent.setup();
    render(
      <>
        <PrinterManagementCard locale="de" />
        <DryerManagementCard locale="de" />
      </>,
    );

    await user.click(await screen.findByRole('button', { name: 'Drucker hinzufügen' }));
    expect(screen.getByLabelText('Seriennummer')).toBeInTheDocument();
    await user.click(screen.getAllByRole('button', { name: 'Abbrechen' })[0]);
    expect(screen.queryByLabelText('Seriennummer')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Trockner hinzufügen' }));
    expect(screen.getByLabelText('Bezeichnung')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Abbrechen' }));
    expect(screen.queryByLabelText('Bezeichnung')).not.toBeInTheDocument();
  });
});
