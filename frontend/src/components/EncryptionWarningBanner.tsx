import { useQuery } from '@tanstack/react-query';
import { ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { api, type EncryptionStatus } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

export function EncryptionWarningBanner() {
  const { t } = useTranslation();
  const { loading, hasPermission } = useAuth();
  const canReadEncryptionStatus = !loading && hasPermission('settings:update');
  const { data } = useQuery<EncryptionStatus>({
    queryKey: ['encryptionStatus'],
    queryFn: () => api.getEncryptionStatus(),
    enabled: canReadEncryptionStatus,
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
    retry: 1,
  });

  if (!data) return null;

  const legacyRows = data.legacy_plaintext_rows.oidc_providers + data.legacy_plaintext_rows.user_totp;
  const encryptedRows = data.encrypted_rows.oidc_providers + data.encrypted_rows.user_totp;
  const isCritical = data.decryption_broken;
  const isUnsafe =
    isCritical ||
    !data.key_configured ||
    legacyRows > 0 ||
    data.migration_error_count > 0;

  if (!isUnsafe) return null;

  const title = isCritical
    ? t('settings.encryption.decryptionBrokenTitle')
    : !data.key_configured
      ? t('settings.encryption.notConfigured')
      : t('settings.encryption.title');

  return (
    <div
      role="alert"
      data-testid="encryption-warning-banner"
      className={
        isCritical
          ? 'border-b border-red-400 bg-red-100 px-4 py-2 text-red-900 dark:border-red-500/50 dark:bg-red-500/20 dark:text-red-100'
          : 'border-b border-amber-300 bg-amber-100 px-4 py-2 text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/20 dark:text-amber-100'
      }
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
        <strong>{title}</strong>
        {isCritical ? (
          <span>{t('settings.encryption.decryptionBrokenError', { count: encryptedRows })}</span>
        ) : !data.key_configured ? (
          <span>{t('settings.encryption.notConfiguredDesc')}</span>
        ) : null}
        {legacyRows > 0 && (
          <span>{t('settings.encryption.legacyRowsWarning', { count: legacyRows })}</span>
        )}
        {data.migration_error_count > 0 && (
          <span>{t('settings.encryption.migrationErrorWarning', { count: data.migration_error_count })}</span>
        )}
        <a
          href="/settings?tab=users-security#card-mfa-encryption"
          className="font-semibold underline underline-offset-2 hover:no-underline"
        >
          {t('settings.tabs.usersSecurity')}
        </a>
      </div>
    </div>
  );
}
