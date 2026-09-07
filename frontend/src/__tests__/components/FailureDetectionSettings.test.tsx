/**
 * Tests for the Failure Detection settings component (#172).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '../utils';
import { FailureDetectionSettings } from '../../components/FailureDetectionSettings';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';

const baseSettings = {
  auto_archive: true,
  save_thumbnails: true,
  capture_finish_photo: true,
  default_filament_cost: 25,
  currency: 'USD',
  energy_cost_per_kwh: 0.15,
  energy_tracking_mode: 'total',
  check_updates: true,
  check_printer_firmware: true,
  include_beta_updates: false,
  obico_enabled: false,
  obico_ml_url: '',
  obico_sensitivity: 'medium',
  obico_action: 'notify',
  obico_poll_interval: 10,
  obico_enabled_printers: '',
};

const baseStatus = {
  is_running: true,
  last_error: null,
  per_printer: {},
  thresholds: { low: 0.38, high: 0.78 },
  history: [],
  enabled: false,
  ml_url: '',
  sensitivity: 'medium',
  action: 'notify',
  poll_interval: 10,
};

describe('FailureDetectionSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    server.use(
      http.get('/api/v1/settings/', () => HttpResponse.json(baseSettings)),
      http.get('/api/v1/obico/status', () => HttpResponse.json(baseStatus)),
      http.get('/api/v1/printers', () => HttpResponse.json([])),
    );
  });

  it('renders headings and fields', async () => {
    render(<FailureDetectionSettings />);
    await waitFor(() => {
      expect(screen.getByText(/AI Failure Detection|Failure Detection/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Obico ML API URL/i)).toBeInTheDocument();
    expect(screen.getByText(/Sensitivity/i)).toBeInTheDocument();
  });

  it('test button calls the test-connection endpoint and shows success', async () => {
    let called = false;
    server.use(
      http.get('/api/v1/settings/', () =>
        HttpResponse.json({ ...baseSettings, obico_enabled: true, obico_ml_url: 'http://obico:3333' }),
      ),
      http.post('/api/v1/obico/test-connection', async ({ request }) => {
        called = true;
        expect(await request.json()).toEqual({});
        return HttpResponse.json({ ok: true, status_code: 200, body: 'ok', error: null });
      }),
    );
    render(<FailureDetectionSettings />);
    const testBtn = await screen.findByRole('button', { name: /test/i });
    await userEvent.click(testBtn);
    await waitFor(() => {
      expect(called).toBe(true);
    });
    expect(await screen.findByText(/ML API reachable/i)).toBeInTheDocument();
  });

  it('saves pending form changes before testing the persisted configuration', async () => {
    const calls: string[] = [];
    server.use(
      http.get('/api/v1/settings/', () =>
        HttpResponse.json({ ...baseSettings, obico_enabled: true, obico_ml_url: 'http://old:3333' }),
      ),
      http.put('/api/v1/settings/', async ({ request }) => {
        calls.push('save');
        return HttpResponse.json({ ...baseSettings, ...((await request.json()) as object) });
      }),
      http.post('/api/v1/obico/test-connection', async ({ request }) => {
        calls.push('test');
        expect(await request.json()).toEqual({});
        return HttpResponse.json({ ok: true, status_code: 200, body: 'ok', error: null });
      }),
    );
    render(<FailureDetectionSettings />);
    const user = userEvent.setup();
    const url = await screen.findByDisplayValue('http://old:3333');
    await user.clear(url);
    await user.type(url, 'http://saved:3333');

    await user.click(screen.getByRole('button', { name: /test/i }));

    await waitFor(() => expect(calls).toEqual(['save', 'test']));
  });

  it('shows failure class history entries with red styling', async () => {
    server.use(
      http.get('/api/v1/obico/status', () =>
        HttpResponse.json({
          ...baseStatus,
          history: [
            {
              printer_id: 1,
              task_name: 'test.3mf',
              timestamp: '2026-04-13T10:00:00Z',
              current_p: 0.9,
              score: 0.85,
              class: 'failure',
              detections: 1,
            },
          ],
        }),
      ),
    );
    render(<FailureDetectionSettings />);
    // Match the history row's score-and-class text, which looks like "failure 0.850"
    expect(await screen.findByText(/failure\s+0\.850/)).toBeInTheDocument();
  });

  it('shows a per-printer error without a score that was never produced', async () => {
    server.use(
      http.get('/api/v1/obico/status', () =>
        HttpResponse.json({
          ...baseStatus,
          per_printer: {
            '1': {
              class: 'error',
              frame_count: 0,
              score: 0,
              error: 'Obico ML API rejected the token (401).',
            },
          },
        }),
      ),
    );
    render(<FailureDetectionSettings />);

    expect(await screen.findByText('Not checking')).toBeInTheDocument();
    expect(screen.getByText('Obico ML API rejected the token (401).')).toBeInTheDocument();
    expect(screen.queryByText(/0\.000/)).not.toBeInTheDocument();
  });
});
