/**
 * Tests for the external camera URL builder on the settings page (#102).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { SettingsPage } from '../../pages/SettingsPage';
import { server } from '../mocks/server';
import { setAuthToken } from '../../api/client';

const mockSettings = {
  auto_archive: true,
  currency: 'USD',
  time_format: 'system',
  date_format: 'system',
  camera_view_mode: 'window',
};

const mjpegPrinter = {
  id: 7,
  name: 'go2rtc Cam',
  serial_number: 'TEST123',
  ip_address: '192.168.1.100',
  access_code: 'XXXX',
  model: 'P1S',
  location: null,
  nozzle_count: 1,
  is_active: true,
  auto_archive: true,
  external_camera_url: '',
  external_camera_type: 'mjpeg',
  external_camera_enabled: true,
  external_camera_snapshot_url: null,
  camera_rotation: 0,
  plate_detection_enabled: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('external camera URL builder (#102)', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/settings?tab=printers-production');
    localStorage.clear();
    setAuthToken(null);
    Element.prototype.scrollIntoView = vi.fn();

    server.use(
      http.get('/api/v1/settings/', () => HttpResponse.json(mockSettings)),
      http.put('/api/v1/settings/', async ({ request }) =>
        HttpResponse.json({ ...mockSettings, ...(await request.json() as object) }),
      ),
      http.get('/api/v1/smart-plugs/', () => HttpResponse.json([])),
      http.get('/api/v1/notifications/', () => HttpResponse.json([])),
      http.get('/api/v1/api-keys/', () => HttpResponse.json([])),
      http.get('/api/v1/mqtt/status', () => HttpResponse.json({ enabled: false })),
      http.get('/api/v1/virtual-printer/status', () => HttpResponse.json({ running: false })),
      http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: false, requires_setup: false })),
      http.get('/api/v1/external-links/', () => HttpResponse.json([])),
      http.get('/api/v1/equipment/', () => HttpResponse.json([])),
    );
  });

  it('composes a URL from host/port/path and PATCHes it through the same field as manual entry', async () => {
    const user = userEvent.setup();
    let receivedBody: Record<string, unknown> | null = null;
    server.use(
      http.get('/api/v1/printers/', () => HttpResponse.json([mjpegPrinter])),
      http.patch('/api/v1/printers/7', async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...mjpegPrinter, ...receivedBody });
      }),
    );

    render(<SettingsPage />);

    const toggle = await waitFor(() => screen.getByTitle('Build URL from host, port and path'));
    await user.click(toggle);

    await user.type(await screen.findByPlaceholderText('Host or IP'), '192.168.1.61');
    await user.type(screen.getByPlaceholderText('Port'), '1984');
    await user.type(screen.getByPlaceholderText(/e\.g\. \/stream/), '/api/stream.mjpeg');

    await waitFor(
      () => {
        expect(receivedBody).not.toBeNull();
        expect(receivedBody!.external_camera_url).toBe('http://192.168.1.61:1984/api/stream.mjpeg');
      },
      { timeout: 5000 },
    );

    // The composed URL lands in the same free-text field used for manual entry.
    expect(screen.getByPlaceholderText(/Camera URL/i)).toHaveValue('http://192.168.1.61:1984/api/stream.mjpeg');
  }, 15_000);

  it('builds an rtsp:// URL with credentials for RTSP sources', async () => {
    const user = userEvent.setup();
    let receivedBody: Record<string, unknown> | null = null;
    server.use(
      http.get('/api/v1/printers/', () =>
        HttpResponse.json([{ ...mjpegPrinter, external_camera_type: 'rtsp' }]),
      ),
      http.patch('/api/v1/printers/7', async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...mjpegPrinter, ...receivedBody });
      }),
    );

    render(<SettingsPage />);

    await user.click(await waitFor(() => screen.getByTitle('Build URL from host, port and path')));
    await user.type(await screen.findByPlaceholderText('Host or IP'), 'cam.local');
    await user.type(screen.getByPlaceholderText('Username (optional)'), 'admin');
    await user.type(screen.getByPlaceholderText('Password (optional)'), 'secret');

    await waitFor(
      () => {
        expect(receivedBody).not.toBeNull();
        expect(receivedBody!.external_camera_url).toBe('rtsp://admin:secret@cam.local');
      },
      { timeout: 5000 },
    );
  }, 15_000);

  it('does not show the builder toggle for USB cameras', async () => {
    server.use(
      http.get('/api/v1/printers/', () =>
        HttpResponse.json([{ ...mjpegPrinter, external_camera_type: 'usb' }]),
      ),
    );

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Device path/i)).toBeInTheDocument();
    });
    expect(screen.queryByTitle('Build URL from host, port and path')).not.toBeInTheDocument();
  });
});
