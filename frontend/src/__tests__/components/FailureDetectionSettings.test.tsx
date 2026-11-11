/**
 * Tests for the Failure Detection settings component (#172).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '../utils';
import { FailureDetectionSettings } from '../../components/FailureDetectionSettings';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { SECRET_PLACEHOLDER } from '../../utils/secrets';

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
        expect(await request.json()).toEqual({ url: 'http://obico:3333', token: '' });
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

  it('tests a pending endpoint without saving it first', async () => {
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
        expect(await request.json()).toEqual({ url: 'http://candidate:3333', token: '' });
        return HttpResponse.json({ ok: true, status_code: 200, body: 'ok', error: null });
      }),
    );
    render(<FailureDetectionSettings />);
    const user = userEvent.setup();
    const url = await screen.findByDisplayValue('http://old:3333');
    fireEvent.change(url, { target: { value: 'http://candidate:3333' } });

    await user.click(screen.getByRole('button', { name: /test/i }));

    await waitFor(() => expect(calls[0]).toBe('test'));
  });

  it('blocks a changed URL with a retained token and masks the replacement after saving', async () => {
    let settings = {
      ...baseSettings,
      obico_enabled: true,
      obico_ml_url: 'http://old:3333',
      obico_ml_token: SECRET_PLACEHOLDER,
    };
    const sent = vi.fn();
    server.use(
      http.get('/api/v1/settings/', () => HttpResponse.json(settings)),
      http.put('/api/v1/settings/', async ({ request }) => {
        const update = await request.json() as typeof settings;
        sent(update);
        settings = { ...settings, ...update, obico_ml_token: SECRET_PLACEHOLDER };
        return HttpResponse.json(settings);
      }),
    );
    render(<FailureDetectionSettings />);
    const url = await screen.findByDisplayValue('http://old:3333');
    fireEvent.change(url, { target: { value: 'http://next:3333' } });
    const testButton = screen.getByRole('button', { name: /test/i });
    expect(testButton).toBeDisabled();
    expect(screen.getByText(/re-enter the credential/i)).toBeInTheDocument();
    expect(sent).not.toHaveBeenCalled();

    const token = screen.getByDisplayValue(SECRET_PLACEHOLDER);
    fireEvent.change(token, { target: { value: 'fixture-new-token' } });
    await waitFor(() => expect(sent).toHaveBeenCalledWith(expect.objectContaining({
      obico_ml_url: 'http://next:3333', obico_ml_token: 'fixture-new-token',
    })));
    expect(await screen.findByDisplayValue(SECRET_PLACEHOLDER)).toBeInTheDocument();
  });

  it('reloads a stale printer scope without dropping the edited Obico URL', async () => {
    const original = { ...baseSettings, obico_enabled: true, obico_ml_url: 'http://old:3333', obico_enabled_printers: '[1]' };
    let current = original;
    const saves: Array<{ obico_enabled_printers: string; obico_ml_url: string }> = [];
    server.use(
      http.get('/api/v1/settings/', () => HttpResponse.json(current)),
      http.put('/api/v1/settings/', async ({ request }) => {
        const saved = (await request.json()) as (typeof saves)[number];
        saves.push(saved);
        if (saved.obico_enabled_printers === '[1]') {
          current = { ...original, obico_enabled_printers: '[]' };
          return HttpResponse.json({ detail: 'One or more printer IDs are invalid' }, { status: 400 });
        }
        current = { ...original, ...saved };
        return HttpResponse.json(current);
      }),
    );
    render(<FailureDetectionSettings />);
    const url = await screen.findByDisplayValue('http://old:3333');
    const user = userEvent.setup();
    await user.clear(url);
    await user.type(url, 'http://changed:3333');

    await waitFor(() => expect(saves.at(-1)).toMatchObject({
      obico_enabled_printers: '[]',
      obico_ml_url: 'http://changed:3333',
    }), { timeout: 2500 });
    expect(saves.map(save => save.obico_enabled_printers)).toEqual(['[1]', '[]']);
    expect(screen.queryByText('Save failed')).not.toBeInTheDocument();
  });

  it('shows the configured automatic pause threshold', async () => {
    server.use(
      http.get('/api/v1/settings/', () =>
        HttpResponse.json({ ...baseSettings, obico_enabled: true, obico_ml_url: 'http://obico:3333' }),
      ),
      http.get('/api/v1/obico/status', () =>
        HttpResponse.json({ ...baseStatus, enabled: true, thresholds: { ...baseStatus.thresholds, pause: 1.364 } }),
      ),
    );
    render(<FailureDetectionSettings />);
    expect(await screen.findByText('Automatic pause threshold')).toBeInTheDocument();
    expect(screen.getByText('1.36')).toBeInTheDocument();
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
