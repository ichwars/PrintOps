import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { ScheduledDryingSettings } from '../../components/settings/ScheduledDryingSettings';
import { SettingsPage } from '../../pages/SettingsPage';

const plan = { id: 8, printer_id: 1, ams_id: 0, local_time: '06:30', timezone: 'Europe/Berlin',
  filament: 'PLA', temperature: 45, duration_hours: 4, rotate_tray: false, enabled: false };

function handlers(capabilityReason: string | null = 'offline') {
  server.use(
    http.get('/api/v1/printers/', () => HttpResponse.json([{ id: 1, name: 'P2S', model: 'P2S', is_active: true }])),
    http.get('/api/v1/printers/1/drying/schedules', () => HttpResponse.json({
      schedules: [plan], runs: [], capabilities: [{ ams_id: 0, module_type: 'n3f', max_temperature: 65, reason: capabilityReason }],
    })),
  );
}

async function selectPrinter() {
  fireEvent.click(await screen.findByRole('combobox', { name: 'Printer' }));
  fireEvent.click(await screen.findByRole('option', { name: 'P2S' }));
}

describe('scheduled drying settings', () => {
  it('explains DST and missed-run behavior and cannot enable unavailable hardware', async () => {
    handlers();
    render(<ScheduledDryingSettings />);
    await selectPrinter();
    expect(await screen.findByRole('button', { name: 'Enable' })).toBeDisabled();
    expect(screen.getByText('Europe/Berlin', { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/DST gaps are skipped/)).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Printer unavailable');
  });

  it('saves a timezone-specific plan disabled by default through the real API client', async () => {
    handlers();
    let submitted: unknown;
    server.use(http.post('/api/v1/printers/1/drying/schedules', async ({ request }) => {
      submitted = await request.json();
      return HttpResponse.json({ ...plan, id: 9 }, { status: 201 });
    }));
    render(<ScheduledDryingSettings />);
    await selectPrinter();
    fireEvent.change(screen.getByRole('textbox', { name: /Timezone \(IANA\)/ }), { target: { value: 'Europe/Berlin' } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save plan' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));
    await waitFor(() => expect(submitted).toMatchObject({ timezone: 'Europe/Berlin', local_time: '06:30', enabled: false }));
  });

  it('surfaces the skipped DST occurrence in the run history', async () => {
    handlers(null);
    server.use(http.get('/api/v1/printers/1/drying/schedules', () => HttpResponse.json({ schedules: [plan],
      capabilities: [{ ams_id: 0, module_type: 'n3f', max_temperature: 65, reason: null }],
      runs: [{ id: 3, schedule_id: 8, printer_id: 1, ams_id: 0, occurrence_day: '2026-03-29', status: 'skipped',
        reason: 'dst_gap', active_printer_id: null, due_at: '2026-03-29T01:00:00Z', claimed_at: '2026-03-29T01:00:00Z',
        observed_running_at: null, finished_at: null }],
    })));
    render(<ScheduledDryingSettings />);
    await selectPrinter();
    expect(await screen.findByText(/Skipped/)).toBeInTheDocument();
    expect(screen.getByText('Local time does not exist (DST)')).toBeInTheDocument();
  });

  it('opens its canonical settings tab from search', async () => {
    handlers();
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { value: scrollIntoView, configurable: true });
    render(<SettingsPage />);
    fireEvent.change(await screen.findByPlaceholderText('Search settings…'), { target: { value: 'Scheduled AMS drying' } });
    fireEvent.click(await screen.findByRole('button', { name: /Scheduled AMS drying/ }));
    expect(await screen.findByRole('heading', { name: 'Scheduled AMS drying' })).toBeInTheDocument();
    expect(window.location.search).toContain('tab=warehouse-material');
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
  });

  it('shows an authoritative queue conflict when enabling becomes unsafe', async () => {
    handlers(null);
    server.use(http.put('/api/v1/printers/1/drying/schedules/8', () =>
      HttpResponse.json({ detail: { code: 'queue_conflict' } }, { status: 409 })));
    render(<ScheduledDryingSettings />);
    await selectPrinter();
    const enable = await screen.findByRole('button', { name: 'Enable' });
    expect(enable).toBeEnabled();
    fireEvent.click(enable);
    expect(await screen.findByRole('alert')).toHaveTextContent('Print queue has priority');
  });
});
