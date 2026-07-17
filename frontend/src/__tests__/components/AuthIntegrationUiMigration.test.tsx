import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { EmailSettings } from '../../components/EmailSettings';
import { LDAPSettings } from '../../components/LDAPSettings';
import { server } from '../mocks/server';
import { render } from '../utils';

describe('authentication settings shared controls', () => {
  it('renders SMTP security through the custom combobox', async () => {
    server.use(
      http.get('/api/v1/auth/smtp', () => HttpResponse.json(null)),
      http.get('/api/v1/auth/advanced-auth/status', () =>
        HttpResponse.json({
          advanced_auth_enabled: true,
          smtp_configured: false,
          local_login_enabled: true,
          autologin_provider_id: null,
        }),
      ),
    );

    const { container } = render(<EmailSettings />);

    await waitFor(() => expect(screen.getAllByRole('combobox').length).toBeGreaterThan(0));
    expect(container.querySelector('select')).toBeNull();
  });

  it('renders LDAP fields without native selects', async () => {
    const { container } = render(<LDAPSettings />);

    await screen.findByText('LDAP Server Configuration');
    expect(container.querySelectorAll('input').length).toBeGreaterThan(0);
    expect(container.querySelector('select')).toBeNull();
  });
});
