import { beforeEach, describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import { EncryptionWarningBanner } from '../../components/EncryptionWarningBanner';
import { setAuthToken, type EncryptionStatus } from '../../api/client';
import { render } from '../utils';
import { server } from '../mocks/server';

const STATUS_URL = '/api/v1/auth/encryption-status';

function makeStatus(overrides: Partial<EncryptionStatus> = {}): EncryptionStatus {
  return {
    key_configured: true,
    key_source: 'env',
    legacy_plaintext_rows: { oidc_providers: 0, user_totp: 0 },
    encrypted_rows: { oidc_providers: 1, user_totp: 1 },
    decryption_broken: false,
    migration_error_count: 0,
    ...overrides,
  };
}

describe('EncryptionWarningBanner', () => {
  beforeEach(() => {
    setAuthToken(null);
    server.use(http.get(STATUS_URL, () => HttpResponse.json(makeStatus())));
  });

  it('stays hidden when encryption is healthy', async () => {
    let statusRequests = 0;
    server.use(
      http.get(STATUS_URL, () => {
        statusRequests += 1;
        return HttpResponse.json(makeStatus());
      }),
    );
    render(<EncryptionWarningBanner />);

    await waitFor(() => expect(statusRequests).toBe(1));
    expect(screen.queryByTestId('encryption-warning-banner')).not.toBeInTheDocument();
  });

  it('warns globally when secrets would be stored in plaintext', async () => {
    server.use(
      http.get(STATUS_URL, () =>
        HttpResponse.json(makeStatus({ key_configured: false, key_source: 'none' })),
      ),
    );

    render(<EncryptionWarningBanner />);

    expect(await screen.findByTestId('encryption-warning-banner')).toHaveTextContent(
      /At-rest encryption not configured/i,
    );
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      '/settings?tab=users-security#card-mfa-encryption',
    );
  });

  it('uses critical styling when encrypted records cannot be decrypted', async () => {
    server.use(
      http.get(STATUS_URL, () =>
        HttpResponse.json(
          makeStatus({
            key_configured: false,
            key_source: 'none',
            encrypted_rows: { oidc_providers: 2, user_totp: 1 },
            decryption_broken: true,
          }),
        ),
      ),
    );

    render(<EncryptionWarningBanner />);

    const banner = await screen.findByTestId('encryption-warning-banner');
    expect(banner).toHaveAttribute('role', 'alert');
    expect(banner.className).toContain('red');
    expect(banner).toHaveTextContent(/Encryption key missing/i);
  });

  it('warns when legacy rows or migration failures remain', async () => {
    server.use(
      http.get(STATUS_URL, () =>
        HttpResponse.json(
          makeStatus({
            legacy_plaintext_rows: { oidc_providers: 2, user_totp: 0 },
            migration_error_count: 1,
          }),
        ),
      ),
    );

    render(<EncryptionWarningBanner />);

    const banner = await screen.findByTestId('encryption-warning-banner');
    expect(banner).toHaveTextContent(/2 legacy plaintext row/i);
    expect(banner).toHaveTextContent(/1 legacy row/i);
  });

  it('does not query the privileged endpoint for a viewer', async () => {
    let statusRequests = 0;
    let userRequests = 0;
    setAuthToken('viewer-token');
    server.use(
      http.get('/api/v1/auth/status', () =>
        HttpResponse.json({ auth_enabled: true, requires_setup: false }),
      ),
      http.get('/api/v1/auth/me', () => {
        userRequests += 1;
        return HttpResponse.json({
          id: 2,
          username: 'viewer',
          role: 'user',
          is_active: true,
          is_admin: false,
          groups: [],
          permissions: ['settings:read'],
          created_at: '2026-01-01T00:00:00Z',
        });
      }),
      http.get(STATUS_URL, () => {
        statusRequests += 1;
        return HttpResponse.json(makeStatus({ key_configured: false, key_source: 'none' }));
      }),
    );

    render(<EncryptionWarningBanner />);

    await waitFor(() => expect(userRequests).toBe(1));
    expect(screen.queryByTestId('encryption-warning-banner')).not.toBeInTheDocument();
    expect(statusRequests).toBe(0);
  });
});
