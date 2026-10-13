import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { render } from '../utils';
import { setAuthToken } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { StreamOverlayBuilder } from '../../components/settings/StreamOverlayBuilder';
import { buildOverlayUrl, parseOverlayConfig } from '../../utils/streamOverlay';

describe('overlay share links', () => {
  it('omits every default while preserving the explicit streaming token', () => {
    expect(buildOverlayUrl('https://printops.example', 7, parseOverlayConfig(new URLSearchParams()), 'bblt_a b'))
      .toBe('https://printops.example/overlay/7?token=bblt_a+b');
  });
  it('keeps login credentials out of share links', () => {
    expect(buildOverlayUrl('https://printops.example', 7, parseOverlayConfig(new URLSearchParams()), 'eyJhbGciOi.JWTPayload.signature'))
      .toBe('https://printops.example/overlay/7');
  });
  it('canonicalizes independent fields and option order with token last', () => {
    const config = parseOverlayConfig(new URLSearchParams('show=temperatures,model,printer,progress&fps=25&camera=0&size=large&artwork=landscape'));
    expect(buildOverlayUrl('https://printops.example', 7, config, 'bblt_x'))
      .toBe('https://printops.example/overlay/7?show=progress%2Cprinter%2Cmodel%2Ctemperatures&size=large&fps=25&camera=false&artwork=landscape&token=bblt_x');
  });
  it('keeps an empty field selection empty and rejects invalid enum options', () => {
    expect(buildOverlayUrl('https://printops.example', 7, parseOverlayConfig(new URLSearchParams('show=&size=invalid&fps=NaN&artwork=invalid'))))
      .toBe('https://printops.example/overlay/7?show=');
  });
  it('never subscribes before an explicit preview click and hides preview on editing', async () => {
    server.use(http.get('/api/v1/printers', () => HttpResponse.json([{ id: 7, name: 'Studio printer' }])));
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><StreamOverlayBuilder /></QueryClientProvider>);
    await screen.findByText('Studio printer');
    expect(screen.queryByTitle('Stream Overlay')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show preview' }));
    expect(screen.getByTitle('Stream Overlay')).toHaveAttribute('src', 'http://localhost:3000/overlay/7');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Model' }));
    expect(screen.queryByTitle('Stream Overlay')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Overlay URL' })).toHaveValue('http://localhost:3000/overlay/7?show=progress%2Clayers%2Ceta%2Cfilename%2Cstatus%2Cmodel');
  });
  it('copies the canonical share URL without starting a preview', async () => {
    const secure = Object.getOwnPropertyDescriptor(window, 'isSecureContext');
    const clipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
    const writeText = vi.fn().mockResolvedValue(undefined);
    const submitted: string[] = [];
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true });
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    try {
      server.use(http.get('/api/v1/printers', () => HttpResponse.json([{ id: 7, name: 'Studio printer' }])));
      render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><form onSubmit={event => { event.preventDefault(); submitted.push('submitted'); }}><StreamOverlayBuilder /></form></QueryClientProvider>);
      await screen.findByText('Studio printer');
      fireEvent.change(screen.getByLabelText(/Overlay token/), { target: { value: 'bblt_fixture' } });
      fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
      await waitFor(() => expect(writeText).toHaveBeenCalledWith('http://localhost:3000/overlay/7?token=bblt_fixture'));
      expect(screen.queryByTitle('Stream Overlay')).not.toBeInTheDocument();
      expect(submitted).toEqual([]);
    } finally {
      if (secure) Object.defineProperty(window, 'isSecureContext', secure);
      else Reflect.deleteProperty(window, 'isSecureContext');
      if (clipboard) Object.defineProperty(navigator, 'clipboard', clipboard);
      else Reflect.deleteProperty(navigator, 'clipboard');
    }
  });

});

// Real AuthProvider state, with only the HTTP backend fixture replaced.
function signedIn(scope: number[] | null) {
  setAuthToken('fixture-session');
  server.use(
    http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('/api/v1/auth/me', () => HttpResponse.json({ id: 4, username: 'viewer', is_admin: false, is_active: true, permissions: ['printers:read', 'camera:view'], allowed_printer_ids: scope })),
    http.get('/api/v1/printers', () => HttpResponse.json([{ id: 2, name: 'Private printer' }, { id: 7, name: 'Allowed studio' }])),
  );
}

describe('authenticated sharing boundaries', () => {
  it('offers only allowed printers and defaults to the first authorized printer', async () => {
    signedIn([7]);
    render(<StreamOverlayBuilder />);
    await screen.findByText('Allowed studio');
    fireEvent.click(screen.getByRole('combobox', { name: 'Printer' }));
    expect(screen.getAllByRole('option')).toHaveLength(1);
    expect(screen.queryByText('Private printer')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('option', { name: 'Allowed studio' }));
    fireEvent.change(screen.getByLabelText(/Overlay token/), { target: { value: 'bblt_fixture' } });
    expect(screen.getByRole('textbox', { name: 'Overlay URL' })).toHaveValue('http://localhost:3000/overlay/7?token=bblt_fixture');
  });
  it('offers no printer or share action for a deny-all scope', async () => {
    signedIn([]);
    render(<><StreamOverlayBuilder /><ScopeReady /></>);
    await screen.findByText('scope:[]');
    await waitFor(() => expect(screen.queryByText('Private printer')).not.toBeInTheDocument());
    expect(screen.getByRole('textbox', { name: 'Overlay URL' })).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Show preview' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Copy' })).not.toBeInTheDocument();
  });
  it('requires an Overlay token for share/copy/preview even with a live login', async () => {
    signedIn(null);
    render(<StreamOverlayBuilder />);
    await screen.findByText('Private printer');
    expect(screen.getByRole('button', { name: 'Show preview' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Copy' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Overlay URL' })).toHaveValue('');
    fireEvent.change(screen.getByLabelText(/Overlay token/), { target: { value: 'bblt_fixture' } });
    expect(screen.getByRole('button', { name: 'Copy' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Show preview' }));
    expect(screen.getByTitle('Stream Overlay')).toHaveAttribute('src', 'http://localhost:3000/overlay/2?token=bblt_fixture');
    fireEvent.change(screen.getByLabelText(/Overlay token/), { target: { value: '' } });
    expect(screen.queryByTitle('Stream Overlay')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show preview' })).toBeDisabled();
  });
});

function ScopeReady() {
  const { user } = useAuth();
  return <output>{user ? `scope:${JSON.stringify(user.allowed_printer_ids)}` : 'loading scope'}</output>;
}
