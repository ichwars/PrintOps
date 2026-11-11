import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { FilamentProfileDefaults } from '../../components/FilamentProfileDefaults';
import { render } from '../utils';
import { server } from '../mocks/server';

describe('product profile defaults', () => {
  it('copies the configured spool into a product default', async () => {
    let saved: unknown;
    server.use(
      http.get('/api/v1/inventory/profile-defaults/', () => HttpResponse.json([])),
      http.get('/api/v1/inventory/spools', () => HttpResponse.json([
        { id: 7, brand: 'Bambu Lab', material: 'PLA', subtype: 'Silk+', color_name: 'Silver', slicer_filament: 'GFA06' },
      ])),
      http.get('/api/v1/inventory/spools/7/filament-presets', () => HttpResponse.json([])),
      http.get('/api/v1/inventory/spools/7/k-profiles', () => HttpResponse.json([{ printer_id: 5, k_value: 0.02 }])),
      http.put('/api/v1/inventory/profile-defaults/', async ({ request }) => {
        saved = await request.json();
        return HttpResponse.json({ id: 1, ...saved as object });
      }),
    );
    render(<FilamentProfileDefaults spoolman={false} />);
    const picker = await screen.findByRole('combobox', { name: 'Choose a configured spool' });
    await waitFor(() => expect(picker).toBeEnabled());
    fireEvent.click(picker);
    await userEvent.click(await screen.findByRole('option', { name: 'Bambu Lab PLA Silk+ Silver (#7)' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save as product default' }));
    await waitFor(() => expect(saved).toMatchObject({
      material: 'PLA', subtype: 'Silk+', color_name: '', slicer_filament: 'GFA06',
      k_profiles: [{ printer_id: 5, k_value: 0.02 }],
    }));
  });
});
