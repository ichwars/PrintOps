import { fireEvent, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { expect, it } from 'vitest';
import { SettingsPage } from '../../pages/SettingsPage';
import { server } from '../mocks/server';
import { render } from '../utils';

it('persists explicit keep-warm opt-in and duration through the shared settings autosave', async () => {
  const updates: Array<Record<string, unknown>> = [];
  const settings = {
    preheat_enabled: true,
    require_plate_clear: true,
    queue_keep_bed_warm: false,
    queue_keep_warm_max_minutes: 10,
  };
  server.use(
    http.get('/api/v1/settings/', () => HttpResponse.json(settings)),
    http.put('/api/v1/settings/', async ({ request }) => {
      const body = await request.json() as Record<string, unknown>;
      updates.push(body);
      return HttpResponse.json({ ...settings, ...body });
    }),
  );
  window.history.replaceState({}, '', '/settings?tab=printers-production&sub=print-process');
  render(<SettingsPage />);
  const toggle = await screen.findByRole('switch', { name: 'Keep the bed warm between compatible jobs' });
  expect(toggle).not.toBeChecked();
  fireEvent.click(toggle);
  await waitFor(() => {
    expect(updates).toEqual([expect.objectContaining({
      queue_keep_bed_warm: true,
      queue_keep_warm_max_minutes: 10,
    })]);
  });
  fireEvent.change(screen.getByLabelText('Maximum warm hold (minutes)'), { target: { value: '15' } });
  await waitFor(() => {
    expect(updates.at(-1)).toEqual(expect.objectContaining({
      queue_keep_bed_warm: true,
      queue_keep_warm_max_minutes: 15,
    }));
  });
});
