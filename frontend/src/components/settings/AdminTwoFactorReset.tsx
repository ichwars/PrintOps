import { useId, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ApiError, api } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import { useToast } from '../../contexts/ToastContext';
import { Button } from '../Button';
import { TextField } from '../ui';

export function AdminTwoFactorReset({ userId }: { userId: number }) {
  const { t } = useTranslation();
  const { authEnabled, hasPermission, isAdmin, user } = useAuth();
  const { showToast } = useToast();
  const passwordId = useId();
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState('');
  const [passwordRequested, setPasswordRequested] = useState(false);
  const needsPassword = passwordRequested || !['ldap', 'oidc'].includes(user?.auth_source ?? '');

  const reset = useMutation({
    mutationFn: () => api.admin2FADisable(userId, needsPassword ? password : null),
    onSuccess: ({ had_2fa }) => {
      setConfirming(false);
      setPassword('');
      showToast(t(had_2fa ? 'users.form.twoFactorResetDone' : 'users.form.twoFactorResetNone'), had_2fa ? 'success' : 'info');
    },
    onError: (error: Error) => {
      setPassword('');
      if (!needsPassword && error instanceof ApiError && error.status === 401 && error.message === 'Admin password required') {
        setPasswordRequested(true);
        return;
      }
      showToast(error.message, 'error');
    },
  });

  if (!authEnabled || !isAdmin || !user || user.id === userId || !hasPermission('users:update')) return null;

  return (
    <div className="mt-5 space-y-3 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary/50 p-3">
      {confirming ? (
        <>
          <p className="text-sm text-bambu-gray">{t('users.form.twoFactorResetHint')}</p>
          {needsPassword && (
            <div className="space-y-1">
              <label htmlFor={passwordId} className="text-sm font-medium text-white">{t('settings.twoFa.passwordPlaceholder')}</label>
              <TextField
                id={passwordId}
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={reset.isPending}
              />
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="danger"
              disabled={reset.isPending || (needsPassword && !password)}
              onClick={() => reset.mutate()}
            >
              {t('common.confirm')}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={reset.isPending}
              onClick={() => {
                setConfirming(false);
                setPassword('');
              }}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </>
      ) : (
        <Button type="button" size="sm" variant="secondary" onClick={() => setConfirming(true)}>
          {t('users.form.twoFactorReset')}
        </Button>
      )}
    </div>
  );
}
