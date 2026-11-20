/**
 * Tests for the SettingsPage component.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '../utils';
import { SettingsPage } from '../../pages/SettingsPage';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { setAuthToken } from '../../api/client';

import { resetSettingsPage, setSettingsTabUrl } from './settingsPageFixtures';

describe('WLED permission', () => {
  beforeEach(resetSettingsPage);
  const signInWith = (permissions: string[]) => {
    setAuthToken('test-token');
    server.use(
      http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
      http.get('/api/v1/auth/me', () => HttpResponse.json({ id: 2, username: 'viewer', is_admin: false, is_active: true, role: 'user', groups: [], permissions })),
    );
  };
  const serveWledPrinter = (onPresetRequest: () => void) => server.use(
    http.get('/api/v1/printers/', () => HttpResponse.json([{
      id: 1, name: 'Printer 1', wled_config: {
        enabled: true, base_url: 'http://wled.local', presets: { printing: 3 }, finished_timeout_seconds: 0,
      },
    }])),
    http.post('/api/v1/printers/1/wled/presets', () => {
      onPresetRequest();
      return HttpResponse.json([{ id: 3, name: 'Printing' }]);
    }),
  );

  it.each([true, false])('shows WLED and loads presets when auth enabled=%s with access', async (authEnabled) => {
    if (authEnabled) signInWith(['settings:read', 'settings:update', 'printers:update']);
    let presetRequests = 0;
    serveWledPrinter(() => { presetRequests += 1; });
    setSettingsTabUrl('integrations', '&sub=smart-home');
    render(<SettingsPage />);
    expect(await screen.findByText('1 presets loaded')).toBeInTheDocument();
    expect(document.getElementById('card-wled')).not.toBeNull();
    expect(presetRequests).toBeGreaterThan(0);
  });

  it('hides WLED from navigation and search without printers:update', async () => {
    signInWith(['settings:read', 'settings:update']);
    let presetRequests = 0;
    serveWledPrinter(() => { presetRequests += 1; });
    setSettingsTabUrl('integrations', '&sub=smart-home');
    render(<SettingsPage />);
    await screen.findByText('MQTT Publishing');
    expect(screen.queryByRole('button', { name: 'WLED' })).toBeNull();
    await userEvent.type(screen.getByPlaceholderText(/Search settings/), 'wled');
    expect(screen.queryByText('WLED')).toBeNull();
    expect(document.getElementById('card-wled')).toBeNull();
    expect(presetRequests).toBe(0);
  });

  it('keeps restricted WLED controls out of the Smart Home pane', async () => {
    signInWith(['settings:read', 'settings:update']);
    let presetRequests = 0;
    serveWledPrinter(() => { presetRequests += 1; });
    setSettingsTabUrl('integrations', '&sub=smart-home');
    render(<SettingsPage />);
    await screen.findByText('MQTT Publishing');
    expect(screen.queryByRole('button', { name: 'WLED' })).toBeNull();
    expect(document.getElementById('card-wled')).toBeNull();
    expect(presetRequests).toBe(0);
  });

  it('unmounts WLED when printers:update is revoked during the session', async () => {
    let permissions = ['settings:read', 'settings:update', 'printers:update'];
    signInWith(permissions);
    server.use(http.get('/api/v1/auth/me', () => HttpResponse.json({
      id: 2, username: 'viewer', role: 'user', is_active: true, is_admin: false,
      groups: [], permissions, created_at: '2026-01-01T00:00:00Z',
    })));
    let presetRequests = 0;
    serveWledPrinter(() => { presetRequests += 1; });
    setSettingsTabUrl('integrations', '&sub=smart-home');
    render(<SettingsPage />);
    expect(await screen.findByText('1 presets loaded')).toBeInTheDocument();
    const requestsBeforeRevocation = presetRequests;

    permissions = ['settings:read', 'settings:update'];
    window.dispatchEvent(new CustomEvent('auth:recheck'));
    await waitFor(() => expect(document.getElementById('card-wled')).toBeNull());
    expect(screen.queryByRole('button', { name: 'WLED' })).toBeNull();
    expect(presetRequests).toBe(requestsBeforeRevocation);
  });
});
