import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EncryptionWarningBanner } from '../../components/EncryptionWarningBanner';

const mocks = vi.hoisted(() => ({
  useAuth: vi.fn(),
  useQuery: vi.fn(),
}));

vi.mock('@tanstack/react-query', () => ({ useQuery: mocks.useQuery }));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: mocks.useAuth }));
vi.mock('../../api/client', () => ({ api: { getEncryptionStatus: vi.fn() } }));

describe('EncryptionWarningBanner cached data isolation', () => {
  beforeEach(() => {
    mocks.useAuth.mockReturnValue({
      loading: false,
      hasPermission: () => false,
    });
    mocks.useQuery.mockReturnValue({
      data: {
        key_configured: false,
        key_source: 'none',
        legacy_plaintext_rows: { oidc_providers: 1, user_totp: 0 },
        encrypted_rows: { oidc_providers: 0, user_totp: 0 },
        decryption_broken: false,
        migration_error_count: 0,
      },
    });
  });

  it('does not render cached privileged status for a viewer', () => {
    render(<EncryptionWarningBanner />);

    expect(screen.queryByTestId('encryption-warning-banner')).not.toBeInTheDocument();
    expect(mocks.useQuery).toHaveBeenCalledWith(expect.objectContaining({ enabled: false }));
  });
});
