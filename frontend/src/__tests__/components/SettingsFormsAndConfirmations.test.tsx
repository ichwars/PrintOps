import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { render } from '../utils';
import { EmailSettings } from '../../components/EmailSettings';
import { LDAPSettings } from '../../components/LDAPSettings';
import { ShoppingListClearButton } from '../../components/ShoppingListClearButton';
import { TwoFactorSettings } from '../../components/TwoFactorSettings';
import { FirmwareUpdateModal } from '../../pages/printers/FirmwareUpdateModal';
import type { FirmwareUpdateInfo, Printer } from '../../api/client';

describe('Settings form actions', () => {
  it('tests the edited SMTP values without saving the form', async () => {
    const testSmtp = vi.fn();
    server.use(
      http.get('/api/v1/auth/smtp', () => HttpResponse.json({
        smtp_host: 'smtp.saved.invalid',
        smtp_port: 587,
        smtp_security: 'starttls',
        smtp_auth_enabled: true,
        smtp_username: 'sender',
        smtp_from_email: 'sender@example.invalid',
      })),
      http.get('/api/v1/auth/advanced-auth/status', () => HttpResponse.json({ smtp_configured: true })),
      http.post('/api/v1/auth/smtp/test', async ({ request }) => {
        testSmtp(await request.json());
        return HttpResponse.json({ success: true, message: 'Test sent' });
      }),
    );
    const user = userEvent.setup();
    render(<EmailSettings />);
    const host = await screen.findByDisplayValue('smtp.saved.invalid');
    await user.clear(host);
    await user.type(host, 'smtp.edited.invalid');
    await user.type(screen.getByPlaceholderText('test@example.com'), 'probe@example.invalid');
    await user.click(screen.getByRole('button', { name: /send test email/i }));

    await waitFor(() => expect(testSmtp).toHaveBeenCalledWith(expect.objectContaining({
      test_recipient: 'probe@example.invalid',
      smtp: expect.objectContaining({ smtp_host: 'smtp.edited.invalid', smtp_password: '' }),
    })));
  });

  it('tests the LDAP server URL currently in the form', async () => {
    const testLdap = vi.fn();
    server.use(
      http.get('/api/v1/settings/', () => HttpResponse.json({ ldap_server_url: 'ldap://saved.invalid' })),
      http.get('/api/v1/auth/ldap/status', () => HttpResponse.json({ ldap_enabled: false })),
      http.post('/api/v1/auth/ldap/test', async ({ request }) => {
        testLdap(await request.json());
        return HttpResponse.json({ success: true, message: 'LDAP tested' });
      }),
    );
    const user = userEvent.setup();
    render(<LDAPSettings />);
    const address = await screen.findByDisplayValue('ldap://saved.invalid');
    await user.clear(address);
    await user.type(address, 'ldap://edited.invalid');
    await user.click(screen.getByRole('button', { name: /test connection/i }));

    await waitFor(() => expect(testLdap).toHaveBeenCalledWith(expect.objectContaining({
      ldap_server_url: 'ldap://edited.invalid', ldap_bind_password: '',
    })));
  });
});

describe('Confirmations', () => {
  it('asks before clearing the shopping list', async () => {
    const clear = vi.fn();
    server.use(http.delete('/api/v1/inventory/shopping-list', () => {
      clear();
      return HttpResponse.json({ deleted: 2 });
    }));
    const user = userEvent.setup();
    render(<ShoppingListClearButton />);
    const button = screen.getByRole('button', { name: 'Clear all' });
    await user.click(button);
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    expect(clear).not.toHaveBeenCalled();
    await user.click(button);
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Clear all' }));
    await waitFor(() => expect(clear).toHaveBeenCalledTimes(1));
  });

  it('asks before unlinking the selected SSO provider', async () => {
    const unlink = vi.fn();
    server.use(
      http.get('/api/v1/auth/2fa/status', () => HttpResponse.json({ totp_enabled: false, email_otp_enabled: false })),
      http.get('/api/v1/auth/oidc/links', () => HttpResponse.json([
        { id: 12, provider_id: 5, provider_name: 'Fixture SSO' },
      ])),
      http.delete('/api/v1/auth/oidc/links/:providerId', ({ params }) => {
        unlink(params.providerId);
        return HttpResponse.json({ message: 'unlinked' });
      }),
    );
    const user = userEvent.setup();
    render(<TwoFactorSettings />);
    const button = await screen.findByRole('button', { name: 'Unlink sign-in account' });
    await user.click(button);
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Remove the sign-in link for Fixture SSO?')).toBeInTheDocument();
    expect(unlink).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole('button', { name: 'Unlink sign-in account' }));
    await waitFor(() => expect(unlink).toHaveBeenCalledWith('5'));
  });
});

it('offers firmware upload only after the printer becomes idle', async () => {
  const prepare = vi.fn();
  server.use(http.get('/api/v1/firmware/updates/11/prepare', () => {
    prepare();
    return HttpResponse.json({ can_proceed: true, errors: [] });
  }));
  const printer = { id: 11, name: 'Fixture Printer', model: 'X1C' } as Printer;
  const firmwareInfo = {
    printer_id: 11,
    printer_name: printer.name,
    current_version: '01.00.00.00',
    latest_version: '02.00.00.00',
    update_available: true,
  } as FirmwareUpdateInfo;
  const onClose = vi.fn();
  const { rerender } = render(
    <FirmwareUpdateModal printer={printer} firmwareInfo={firmwareInfo} printerState="RUNNING" onClose={onClose} />,
  );
  expect(await screen.findByText('Firmware can only be uploaded while the printer is idle.')).toBeInTheDocument();
  expect(prepare).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: /upload firmware/i })).not.toBeInTheDocument();

  rerender(<FirmwareUpdateModal printer={printer} firmwareInfo={firmwareInfo} printerState="IDLE" onClose={onClose} />);
  expect(await screen.findByRole('button', { name: /upload firmware/i })).toBeEnabled();
  expect(prepare).toHaveBeenCalledTimes(1);
});
