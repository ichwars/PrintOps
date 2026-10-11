import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useLocation } from 'react-router';
import { http, HttpResponse } from 'msw';
import App from '../App';
import { server } from './mocks/server';

vi.mock('../pages/InventoryPage', () => ({
  default: function InventoryRouteProbe() {
    const location = useLocation();
    return <output aria-label="Inventory destination">{location.pathname}{location.search}{location.hash}</output>;
  },
}));

describe('legacy inventory links', () => {
  it.each([
    '?focus=used#filters',
    '?location_id=4&spool=12#edit',
  ])('preserves the explicit linked view when redirecting %s', async suffix => {
    window.history.replaceState({}, '', `/inventory${suffix}`);
    server.use(http.get('/api/v1/auth/status', () =>
      HttpResponse.json({ auth_enabled: false, requires_setup: false }),
    ));

    render(<App />);

    expect(await screen.findByLabelText('Inventory destination'))
      .toHaveTextContent(`/warehouse/filament${suffix}`);
    expect(window.location.pathname).toBe('/warehouse/filament');
    expect(window.location.search + window.location.hash).toBe(suffix);
  });
});
