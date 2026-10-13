import { fireEvent, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { expect, it } from 'vitest';
import { SettingsPage } from '../../pages/SettingsPage';
import { server } from '../mocks/server';
import { render } from '../utils';

it('shows the sustained duration only for ambient drying and autosaves its value', async () => {
  const updates: Array<Record<string, unknown>> = [];
  const settings = { ambient_drying_enabled: false, ambient_drying_sustained_minutes: 0 };
  server.use(
    http.get('/api/v1/settings/', () => HttpResponse.json(settings)),
    http.put('/api/v1/settings/', async ({ request }) => {
      const body = await request.json() as Record<string, unknown>;
      updates.push(body);
      return HttpResponse.json({ ...settings, ...body });
    }),
  );
  window.history.replaceState({}, '', '/settings?tab=warehouse-material&sub=filament');
  render(<SettingsPage />);
  await screen.findByText('Ambient drying');
  expect(screen.queryByLabelText('Sustained high humidity (minutes)')).not.toBeInTheDocument();
  const label = screen.getByText('Ambient drying').closest('.flex')!;
  fireEvent.click(label.querySelector('input')!);
  const duration = await screen.findByLabelText('Sustained high humidity (minutes)');
  expect(duration).toHaveValue(0);
  await waitFor(() => expect(updates.at(-1)).toEqual(expect.objectContaining({ ambient_drying_enabled: true })));
  fireEvent.change(duration, { target: { value: '15' } });
  await waitFor(() => expect(updates.at(-1)).toEqual(expect.objectContaining({ ambient_drying_sustained_minutes: 15 })));
  fireEvent.click(label.querySelector('input')!);
  await waitFor(() => expect(screen.queryByLabelText('Sustained high humidity (minutes)')).not.toBeInTheDocument());
  await waitFor(() => expect(updates.at(-1)).toEqual(expect.objectContaining({
    ambient_drying_enabled: false, ambient_drying_sustained_minutes: 15,
  })));
});
