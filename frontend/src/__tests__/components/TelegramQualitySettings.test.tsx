import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { vi, it, expect } from 'vitest';
import { render } from '../utils';
import { server } from '../mocks/server';
import { TelegramQualitySettings } from '../../components/TelegramQualitySettings';

vi.mock('../../contexts/AuthContext', () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({ user: { is_admin: true }, authEnabled: true, hasPermission: () => true }),
}));

it('requires explicit actor mapping, saves numeric identities and shows polling conflict', async () => {
  let submitted: unknown;
  server.use(
    http.get('/api/v1/notifications/1/telegram-quality', () => HttpResponse.json({enabled:false, actors:[], status:'disabled'})),
    http.put('/api/v1/notifications/1/telegram-quality', async ({request}) => {
      submitted = await request.json();
      return HttpResponse.json({enabled:true, actors:[{actor_id:42,user_id:7}], status:'webhook_conflict'});
    }),
  );
  render(<TelegramQualitySettings providerId={1} />);
  const input = await screen.findByLabelText('Trusted actors');
  const user = userEvent.setup();
  await user.click(screen.getByLabelText('Enable quality reactions'));
  await user.type(input, '42=7');
  await user.click(screen.getByRole('button', {name:'Save reaction settings'}));
  await waitFor(() => expect(submitted).toEqual({enabled:true, actors:[{actor_id:42,user_id:7}]}));
  expect(await screen.findByText('Webhook active: polling paused')).toBeInTheDocument();
});

it('rejects ambiguous actor IDs locally and keeps the mixed outcome instructions', async () => {
  server.use(http.get('/api/v1/notifications/1/telegram-quality', () => HttpResponse.json({enabled:false, actors:[], status:'disabled'})));
  render(<TelegramQualitySettings providerId={1} />);
  const input = await screen.findByLabelText('Trusted actors');
  await userEvent.type(input, 'not-a-user=7');
  await userEvent.click(screen.getByRole('button', {name:'Save reaction settings'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Telegram ID=PrintOps user ID');
  expect(screen.getByText(/mixed quantities/)).toBeInTheDocument();
});
