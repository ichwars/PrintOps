/**
 * Tests for the SettingsPage component.
 */

import { vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { setAuthToken } from '../../api/client';

export const mockSettings = {
  auto_archive: true,
  save_thumbnails: true,
  capture_finish_photo: true,
  default_filament_cost: 25.0,
  currency: 'USD',
  ams_humidity_good: 40,
  ams_humidity_fair: 60,
  ams_temp_good: 30,
  ams_temp_fair: 35,
  time_format: 'system',
  date_format: 'system',
  mqtt_enabled: false,
  mqtt_host: '',
  mqtt_port: 1883,
  spoolman_enabled: false,
  spoolman_url: '',
  ha_enabled: false,
  ha_url: '',
  ha_token: '',
  check_updates: false,
  check_printer_firmware: false,
  show_developer_lan_warning: true,
  show_sponsor_prompts: true,
  bed_cooled_threshold: 35,
  ftp_retry_enabled: true,
  ftp_retry_count: 3,
  ftp_retry_delay: 2,
  ftp_timeout: 30,
};

export function setSettingsTabUrl(tab: string, extraSearch = '') {
  const search = tab === 'general' ? extraSearch : `?tab=${tab}${extraSearch}`;
  window.history.replaceState({}, '', `/settings${search}`);
}

export function resetSettingsPage() {
    // BrowserRouter shares window.location across tests; reset it so a tab
    // switch in one test (e.g. clicking "Printers & Production") doesn't carry into
    // sibling tests that expect to land on the default General tab.
    window.history.replaceState({}, '', '/');
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
    vi.mocked(localStorage.removeItem).mockReset();
    vi.mocked(localStorage.clear).mockReset();
    localStorage.clear();
    setAuthToken(null);
    Element.prototype.scrollIntoView = vi.fn();

    server.use(
      http.get('/api/v1/settings/', () => {
        return HttpResponse.json(mockSettings);
      }),
      http.put('/api/v1/settings/', async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({ ...mockSettings, ...body });
      }),
      http.get('/api/v1/printers/', () => {
        return HttpResponse.json([]);
      }),
      http.get('/api/v1/smart-plugs/', () => {
        return HttpResponse.json([]);
      }),
      http.get('/api/v1/notifications/', () => {
        return HttpResponse.json([]);
      }),
      http.get('/api/v1/api-keys/', () => {
        return HttpResponse.json([]);
      }),
      http.get('/api/v1/mqtt/status', () => {
        return HttpResponse.json({ enabled: false });
      }),
      http.get('/api/v1/virtual-printer/status', () => {
        return HttpResponse.json({ running: false });
      }),
      http.get('/api/v1/auth/status', () => {
        return HttpResponse.json({ auth_enabled: false, requires_setup: false });
      }),
      http.get('/api/v1/external-links/', () => {
        return HttpResponse.json([]);
      })
    );
  }
