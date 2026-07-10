import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Loader2, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import { Button } from '../components/Button';
import { Card, CardContent, CardHeader } from '../components/Card';

export function OrdersCustomersPage() {
  const { t } = useTranslation();
  const profilesQuery = useQuery({
    queryKey: ['business-profile-options'],
    queryFn: () => api.getBusinessProfileOptions(),
  });
  const activeProfiles = profilesQuery.data?.filter((profile) => profile.is_active) ?? [];
  const selectedProfile = activeProfiles.find((profile) => profile.is_default) ?? activeProfiles[0];
  const customersQuery = useQuery({
    queryKey: ['customers', 'list', selectedProfile?.id],
    queryFn: () => api.getCustomers({ businessProfileId: selectedProfile!.id, limit: 50, offset: 0 }),
    enabled: selectedProfile !== undefined,
  });

  return (
    <div className="p-4 md:p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <Users className="w-7 h-7 text-bambu-green" />
          {t('orders.customers.title')}
        </h1>
        <p className="text-bambu-gray mt-1">{t('orders.customers.subtitle')}</p>
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold text-white">
            {selectedProfile?.name ?? t('orders.customers.businessProfile')}
          </h2>
        </CardHeader>
        <CardContent>
          {profilesQuery.isPending ? (
            <div className="flex items-center gap-2 text-sm text-bambu-gray">
              <Loader2 className="w-4 h-4 animate-spin" />
              {t('orders.businessProfile.loading')}
            </div>
          ) : profilesQuery.isError ? (
            <div className="flex flex-wrap items-center gap-3 text-sm text-red-300">
              <AlertTriangle className="w-4 h-4" />
              <span>{t('orders.businessProfile.error')}</span>
              <Button size="sm" variant="secondary" onClick={() => profilesQuery.refetch()}>
                {t('common.retry')}
              </Button>
            </div>
          ) : selectedProfile === undefined ? (
            <p className="text-sm text-bambu-gray">{t('orders.customers.noBusinessProfile')}</p>
          ) : customersQuery.isPending ? (
            <div className="flex items-center gap-2 text-sm text-bambu-gray">
              <Loader2 className="w-4 h-4 animate-spin" />
              {t('orders.customers.loading')}
            </div>
          ) : customersQuery.isError ? (
            <div className="flex flex-wrap items-center gap-3 text-sm text-red-300">
              <AlertTriangle className="w-4 h-4" />
              <span>{t('orders.customers.error')}</span>
              <Button size="sm" variant="secondary" onClick={() => customersQuery.refetch()}>
                {t('common.retry')}
              </Button>
            </div>
          ) : customersQuery.data.items.length === 0 ? (
            <p className="text-sm text-bambu-gray">{t('orders.customers.empty')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-bambu-gray">
                  <tr>
                    <th className="pb-2 pr-4 font-medium">{t('orders.customers.customer')}</th>
                    <th className="pb-2 pr-4 font-medium">{t('common.status')}</th>
                    <th className="pb-2 pr-4 font-medium">{t('orders.customers.discount')}</th>
                  </tr>
                </thead>
                <tbody>
                  {customersQuery.data.items.map((customer) => (
                    <tr key={customer.id} className="border-t border-bambu-dark-tertiary text-white">
                      <td className="py-3 pr-4">
                        <p>{customer.display_name}</p>
                        <p className="text-xs text-bambu-gray">{customer.account_number}</p>
                      </td>
                      <td className="py-3 pr-4 capitalize">{t(`orders.status.${customer.status}`)}</td>
                      <td className="py-3 pr-4">{customer.discount_percent}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
