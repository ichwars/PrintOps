import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StorageLocationSensors } from '../../components/StorageLocationSensors';
import { api } from '../../api/client';

let canWrite = true;
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ hasPermission: (permission: string) => permission === 'inventory:read' || canWrite }) }));
vi.mock('../../api/client', () => ({ api: {
  getStorageHASensorReadings: vi.fn(), getStorageHASensors: vi.fn(), getStorageHAEntities: vi.fn(),
  createStorageHASensor: vi.fn(), updateStorageHASensor: vi.fn(), deleteStorageHASensor: vi.fn(),
} }));

function renderSensors() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><StorageLocationSensors locationId={5} locationName="Dry box" /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks(); canWrite = true;
  vi.mocked(api.getStorageHASensorReadings).mockResolvedValue([{ id: 1, location_id: 5, name: 'Humidity', entity_id: 'sensor.humidity', device_class: 'humidity', unit: '%', value: 42, alerting: false, status: 'fresh', last_checked: null, last_read_at: '2026-10-11T08:00:00' }]);
  vi.mocked(api.getStorageHASensors).mockResolvedValue([]);
  vi.mocked(api.getStorageHAEntities).mockResolvedValue([{ entity_id: 'sensor.humidity', friendly_name: 'Humidity', state: '42', domain: 'sensor', device_class: 'humidity', unit_of_measurement: '%' }]);
});

describe('StorageLocationSensors', () => {
  it('renders value, units, freshness and last successful reading', async () => {
    renderSensors();
    expect(await screen.findByText(/Humidity: 42 %/)).toBeInTheDocument();
    expect(screen.getByText(/Fresh|storageSensors.fresh/)).toBeInTheDocument();
    expect(screen.getByText(/Last reading|storageSensors.lastRead/)).toBeInTheDocument();
  });

  it('renders an unavailable value without showing it as fresh', async () => {
    vi.mocked(api.getStorageHASensorReadings).mockResolvedValue([{ id: 1, location_id: 5, name: 'Humidity', entity_id: 'sensor.humidity', device_class: 'humidity', unit: '%', value: null, alerting: false, status: 'unavailable', last_checked: null, last_read_at: null }]);
    renderSensors();
    expect(await screen.findByText(/Humidity: —/)).toBeInTheDocument();
    expect(screen.getByText(/Unavailable|storageSensors.unavailable/)).toBeInTheDocument();
  });

  it('offers display only for a storage reader', async () => {
    canWrite = false; renderSensors();
    await screen.findByText(/Humidity: 42 %/);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('binds a selected environmental entity to the existing location', async () => {
    const user = userEvent.setup(); renderSensors();
    await user.click(screen.getByRole('button', { name: /^Sensors$|storageSensors.manage/ }));
    await screen.findByRole('dialog');
    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: 'Humidity (%)' }));
    await user.click(screen.getByRole('button', { name: /^Save$|common.save/ }));
    await waitFor(() => expect(api.createStorageHASensor).toHaveBeenCalledWith({ location_id: 5, name: 'Humidity', entity_id: 'sensor.humidity', device_class: 'humidity', unit: '%', alert_above: null, alert_below: null, notify_on_alert: false }));
  });
});
