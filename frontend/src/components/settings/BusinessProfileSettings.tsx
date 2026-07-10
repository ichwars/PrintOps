import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Building2, Loader2, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../../api/client';
import { Card, CardContent, CardHeader } from '../Card';
import { Button } from '../Button';

export function BusinessProfileSettings() {
  const { t } = useTranslation();
  const profilesQuery = useQuery({
    queryKey: ['business-profiles', false],
    queryFn: () => api.getBusinessProfiles(),
  });

  return (
    <Card id="card-business-profile">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Building2 className="w-5 h-5 text-bambu-green" />
          <h2 className="text-lg font-semibold text-white">{t('orders.businessProfile.title')}</h2>
        </div>
      </CardHeader>
      <CardContent>
        {profilesQuery.isPending && (
          <div className="flex items-center gap-2 text-sm text-bambu-gray">
            <Loader2 className="w-4 h-4 animate-spin" />
            {t('orders.businessProfile.loading')}
          </div>
        )}

        {profilesQuery.isError && (
          <div className="flex flex-wrap items-center gap-3 text-sm text-red-300">
            <AlertTriangle className="w-4 h-4" />
            <span>{t('orders.businessProfile.error')}</span>
            <Button size="sm" variant="secondary" onClick={() => profilesQuery.refetch()}>
              <RefreshCw className="w-4 h-4" />
              {t('common.retry')}
            </Button>
          </div>
        )}

        {profilesQuery.isSuccess && profilesQuery.data.length === 0 && (
          <p className="text-sm text-bambu-gray">{t('orders.businessProfile.empty')}</p>
        )}

        {profilesQuery.isSuccess && profilesQuery.data.length > 0 && (
          <ul className="divide-y divide-bambu-dark-tertiary">
            {profilesQuery.data.map((profile) => (
              <li key={profile.id} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <p className="truncate font-medium text-white">{profile.name}</p>
                  <p className="truncate text-sm text-bambu-gray">
                    {profile.legal_name} · {profile.country_code} · {profile.default_currency}
                  </p>
                </div>
                {profile.is_default && (
                  <span className="shrink-0 text-xs text-bambu-green">{t('orders.default')}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
