import { useEffect } from 'react';
import { act, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { useAuth } from '../../contexts/AuthContext';
import { setAuthToken, type UserResponse } from '../../api/client';
import { PrintersPage } from '../../pages/PrintersPage';

let login: ReturnType<typeof useAuth>['loginWithToken'];
function LoginProbe() {
  const auth = useAuth();
  useEffect(() => { login = auth.loginWithToken; }, [auth]);
  return <output data-testid="auth-ready">{String(!auth.loading)}</output>;
}
const account = (sub: string, permissions = ['queue:read_own', 'printers:read']) => ({
  id: 17, sub, username: sub, is_admin: false, permissions,
}) as UserResponse;
afterEach(() => setAuthToken(null));

it.each([['printers:read'], ['printers:read', 'queue:read_own']])('isolates prior owner name/count on same-ID account replacement (%j)', async (...permissions) => {
  let rows = [{ id: 1, position: 1, printer_id: 1, status: 'pending', archive_name: 'Owner A private job' }];
  let denied = false;
  server.use(
    http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('/api/v1/printers/', () => HttpResponse.json([{ id: 1, name: 'Queue fixture', model: 'X1C', serial_number: 'queue-fixture', enabled: true }])),
    http.get('/api/v1/printers/1/status', () => HttpResponse.json({ connected: true, state: 'IDLE', ams: [], vt_tray: [], temperatures: {} })),
    http.get('/api/v1/queue/', ({ request }) => {
      if (new URL(request.url).searchParams.get('status') !== 'pending') return HttpResponse.json([]);
      return denied ? new HttpResponse(null, { status: 403 }) : HttpResponse.json(rows);
    }),
  );
  render(<><LoginProbe /><PrintersPage /></>);
  await waitFor(() => expect(screen.getByTestId('auth-ready')).toHaveTextContent('true'));
  act(() => login('session-A', account('owner-A')));
  await screen.findByText('Owner A private job');
  expect(screen.getByTitle('1 print in queue')).toBeInTheDocument();
  // Replacement uses the same SQLite numeric ID, a different public subject and token.
  denied = true;
  act(() => login('session-B', account('owner-B', permissions)));
  expect(screen.queryByText('Owner A private job')).not.toBeInTheDocument();
  expect(screen.queryByTitle('1 print in queue')).not.toBeInTheDocument();
  rows = [{ ...rows[0], archive_name: 'Owner B job' }];
  denied = false;
  act(() => login('session-B-allowed', account('owner-B')));
  expect(await screen.findByText('Owner B job')).toBeInTheDocument();
  expect(screen.queryByText('Owner A private job')).not.toBeInTheDocument();
});
