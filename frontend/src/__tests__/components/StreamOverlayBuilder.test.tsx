import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen, render, waitFor } from '@testing-library/react';
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
      fireEvent.change(screen.getByLabelText('Overlay token (optional)'), { target: { value: 'bblt_fixture' } });
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
