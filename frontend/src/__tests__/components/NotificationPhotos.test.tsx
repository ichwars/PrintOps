import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { NotificationProviderCard } from '../../components/NotificationProviderCard';
import { AddNotificationModal } from '../../components/AddNotificationModal';
import type { NotificationProvider } from '../../api/client';

function buildProvider(overrides: Partial<NotificationProvider> = {}): NotificationProvider {
  return {
    id: 1,
    name: 'Test Provider',
    provider_type: 'ntfy',
    enabled: true,
    config: { server: 'https://ntfy.sh', topic: 'printops' },
    on_print_start: false,
    on_print_complete: false,
    on_print_failed: false,
    on_print_stopped: false,
    on_print_progress: false,
    on_print_missing_spool_assignment: false,
    on_printer_offline: false,
    on_printer_error: false,
    on_ai_failure_detection: false,
    on_filament_low: false,
    on_maintenance_due: false,
    on_ams_humidity_high: false,
    on_ams_temperature_high: false,
    on_ams_ht_humidity_high: false,
    on_ams_ht_temperature_high: false,
    on_plate_not_empty: false,
    on_bed_cooled: false,
    on_first_layer_complete: false,
    on_queue_job_added: false,
    on_queue_job_assigned: false,
    on_queue_job_started: false,
    on_queue_job_waiting: false,
    on_queue_job_skipped: false,
    on_queue_job_failed: false,
    on_queue_completed: false,
    on_stock_reorder_alert: false,
    on_stock_break_alert: false,
    quiet_hours_enabled: false,
    quiet_hours_start: null,
    quiet_hours_end: null,
    daily_digest_enabled: false,
    daily_digest_time: null,
    printer_id: null,
    last_success: null,
    last_error: null,
    last_error_at: null,
    created_at: '2026-04-25T00:00:00Z',
    updated_at: '2026-04-25T00:00:00Z',
    ...overrides,
  };
}


describe('notification camera photo preference', () => {
  it('preserves legacy photos and persists opt-out from the card', async () => {
    let captured: unknown;
    server.use(http.patch('*/api/v1/notifications/1', async ({ request }) => {
      captured = await request.json();
      return HttpResponse.json({ ...buildProvider(), attach_photo: false });
    }));
    const user = userEvent.setup();
    render(<NotificationProviderCard provider={buildProvider()} onEdit={vi.fn()} />);
    await user.click(await screen.findByText(/event settings/i));
    const toggle = await screen.findByRole('switch', { name: 'Attach camera photo' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    await user.click(toggle);
    await waitFor(() => expect(captured).toEqual({ attach_photo: false }));
  });
  it('saves the photo preference with existing provider settings', async () => {
    let captured: unknown;
    server.use(http.patch('*/api/v1/notifications/1', async ({ request }) => {
      captured = await request.json();
      return HttpResponse.json(buildProvider());
    }));
    const user = userEvent.setup();
    render(<AddNotificationModal provider={buildProvider()} onClose={vi.fn()} />);
    const toggle = await screen.findByRole('switch', { name: 'Attach camera photo' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    await user.click(toggle);
    await user.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(captured).toMatchObject({ attach_photo: false, config: { topic: 'printops' } }));
  });
});
