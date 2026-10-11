import { beforeEach, describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { PrintersPage } from '../../pages/PrintersPage';
import { server } from '../mocks/server';
import { render } from '../utils';

const idleStatus = {
  connected: true,
  state: 'IDLE',
  awaiting_plate_clear: false,
  progress: 0,
  layer_num: 0,
  total_layers: 0,
  temperatures: { nozzle: 25, bed: 25, chamber: 25 },
  remaining_time: 0,
  filename: null,
  wifi_signal: -50,
  vt_tray: [],
};

async function openJogControls(model: string) {
  const requests: URLSearchParams[] = [];
  server.use(
    http.get('/api/v1/printers/', () => HttpResponse.json([{
      id: 1,
      name: `Test ${model}`,
      ip_address: '192.168.1.100',
      serial_number: '00M09A350100001',
      access_code: '12345678',
      model,
      enabled: true,
      is_active: true,
      nozzle_diameter: 0.4,
      nozzle_type: 'hardened_steel',
      auto_archive: true,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    }])),
    http.get('/api/v1/printers/:id/status', () => HttpResponse.json(idleStatus)),
    http.get('/api/v1/queue/', () => HttpResponse.json([])),
    http.post('/api/v1/printers/:id/bed-jog', ({ request }) => {
      requests.push(new URL(request.url).searchParams);
      return HttpResponse.json({ success: true, message: 'ok' });
    }),
  );

  const user = userEvent.setup();
  render(<PrintersPage />);
  await user.click(await screen.findByTitle('Jog Controls'));
  return { user, requests };
}

describe('PrinterCard Z jog controls', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it.each([
    ['X1C', 'Move plate up', '-10'],
    ['X1C', 'Move plate down', '10'],
    ['A1', 'Move toolhead up', '10'],
    ['A1 Mini', 'Move toolhead down', '-10'],
    ['A2L', 'Move toolhead up', '10'],
    ['N9', 'Move toolhead down', '-10'],
    ['A04', 'Move toolhead up', '10'],
    ['A11', 'Move toolhead down', '-10'],
    ['A12', 'Move toolhead up', '10'],
    ['A1M', 'Move toolhead down', '-10'],
  ])('sends the gap requested by %s / %s without an endstop bypass', async (model, label, distance) => {
    const { user, requests } = await openJogControls(model);
    await user.click(screen.getByRole('button', { name: label }));

    await waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].get('distance')).toBe(distance);
    expect(requests[0].has('force')).toBe(false);
    expect(screen.queryByText('Printer is not homed')).not.toBeInTheDocument();
  });

  it('warns that travel limits are not enforced before a manual move', async () => {
    const { requests } = await openJogControls('X1C');

    expect(screen.getByRole('alert')).toHaveTextContent(/travel limits.*not enforced/i);
    expect(requests).toHaveLength(0);
  });

  it('names the moving toolhead on a bed-slinger', async () => {
    await openJogControls('A1 Mini');

    expect(screen.getByRole('button', { name: 'Move toolhead up' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move toolhead down' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move plate up' })).not.toBeInTheDocument();
  });
});
