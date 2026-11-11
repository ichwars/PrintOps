import { beforeEach, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import userEvent from '@testing-library/user-event';
import { AdminTwoFactorReset } from '../../components/settings/AdminTwoFactorReset';
import { render, screen, waitFor } from '../utils';
import { server } from '../mocks/server';

const auth = vi.hoisted(() => ({
  authEnabled: true,
  isAdmin: true,
  hasPermission: () => true,
  user: { id: 1, auth_source: 'local' },
}));

vi.mock('../../contexts/AuthContext', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../contexts/AuthContext')>(),
  useAuth: () => auth,
}));

beforeEach(() => {
  auth.authEnabled = true;
  auth.isAdmin = true;
  auth.user = { id: 1, auth_source: 'local' };
});

it('sends the acting administrator password only after confirmation', async () => {
  const reset = vi.fn(async ({ request }: { request: Request }) => {
    expect(await request.json()).toEqual({ admin_password: 'fixture-passphrase' });
    return HttpResponse.json({ message: 'reset', had_2fa: true });
  });
  server.use(http.delete('/api/v1/auth/2fa/admin/7', reset));
  const user = userEvent.setup();
  render(<AdminTwoFactorReset userId={7} />);
  await user.click(screen.getByRole('button', { name: 'Reset two-factor authentication' }));
  const confirm = screen.getByRole('button', { name: 'Confirm' });
  expect(confirm).toBeDisabled();
  await user.type(screen.getByLabelText('Enter your password'), 'fixture-passphrase');
  await user.click(confirm);
  expect(await screen.findByText('Two-factor authentication was reset.')).toBeInTheDocument();
  expect(reset).toHaveBeenCalledOnce();
});

it('prompts an SSO administrator when the server requires their local password', async () => {
  auth.user.auth_source = 'oidc';
  const submissions: unknown[] = [];
  server.use(http.delete('/api/v1/auth/2fa/admin/7', async ({ request }) => {
    const body = await request.json() as { admin_password: string | null };
    submissions.push(body);
    return body.admin_password
      ? HttpResponse.json({ message: 'reset', had_2fa: false })
      : HttpResponse.json({ detail: 'Admin password required' }, { status: 401 });
  }));
  const user = userEvent.setup();
  render(<AdminTwoFactorReset userId={7} />);
  await user.click(screen.getByRole('button', { name: 'Reset two-factor authentication' }));
  expect(screen.queryByLabelText('Enter your password')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Confirm' }));
  await user.type(await screen.findByLabelText('Enter your password'), 'fixture-sso-passphrase');
  await user.click(screen.getByRole('button', { name: 'Confirm' }));
  await waitFor(() => expect(submissions).toEqual([
    { admin_password: null },
    { admin_password: 'fixture-sso-passphrase' },
  ]));
  expect(await screen.findByText('This user had no active two-factor authentication.')).toBeInTheDocument();
});

it('hides the action from non-admins and in the acting administrator’s own editor', () => {
  const { rerender } = render(<AdminTwoFactorReset userId={1} />);
  expect(screen.queryByRole('button', { name: 'Reset two-factor authentication' })).not.toBeInTheDocument();
  auth.isAdmin = false;
  rerender(<AdminTwoFactorReset userId={7} />);
  expect(screen.queryByRole('button', { name: 'Reset two-factor authentication' })).not.toBeInTheDocument();
});
