import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api, type APIKey } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { Toggle } from './Toggle';

export function AppNotificationKeyToggle({ apiKey }: { apiKey: APIKey }) {
  const { t } = useTranslation();
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: (enabled: boolean) => api.updateAPIKey(apiKey.id, { can_send_notifications: enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['api-keys'] }),
  });
  if (!isAdmin) return null;
  return <div className="mt-3 border-t border-bambu-dark-tertiary pt-3">
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm text-white">{t('appNotifications.label')}</span>
      <Toggle ariaLabel={t('appNotifications.label')} checked={apiKey.can_send_notifications ?? false}
        disabled={update.isPending} onChange={(enabled) => update.mutate(enabled)} />
    </div>
    {update.error && <p role="alert" className="mt-1 text-xs text-red-500">{update.error.message}</p>}
  </div>;
}
