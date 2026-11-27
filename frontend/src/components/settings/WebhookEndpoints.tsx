import { Send } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { SettingsDashboardCard } from './SettingsDashboardCard';

const endpoints = [
  ['GET', '/api/v1/webhook/printer/:id/status', 'getSpecificStatus'],
  ['GET', '/api/v1/webhook/queue', 'queueStatus'],
  ['POST', '/api/v1/webhook/queue/add', 'addToQueue'],
  ['POST', '/api/v1/webhook/printer/:id/start', 'startNext'],
  ['POST', '/api/v1/webhook/printer/:id/stop', 'stopPrint'],
  ['POST', '/api/v1/webhook/printer/:id/cancel', 'cancelPrint'],
] as const;

const methodStyles = {
  GET: 'border-blue-300 bg-blue-100 text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/20 dark:text-blue-300',
  POST: 'border-green-300 bg-green-100 text-green-800 dark:border-green-500/30 dark:bg-green-500/20 dark:text-green-300',
};

export function WebhookEndpoints() {
  const { t } = useTranslation();
  return (
    <SettingsDashboardCard id="card-webhooks" title={t('settings.webhookEndpoints')} icon={Send}>
      <p>{t('settings.webhookApiKeyHint')}</p>
      <ul className="divide-y divide-bambu-dark-tertiary rounded-lg border border-bambu-dark-tertiary">
        {endpoints.map(([method, endpoint, label]) => (
          <li
            key={endpoint}
            className="grid grid-cols-[3.5rem_minmax(0,1fr)] items-start gap-x-3 gap-y-1 px-3 py-2.5 lg:grid-cols-[3.5rem_minmax(0,1.2fr)_minmax(0,1fr)]"
          >
            <span className={`justify-self-start rounded border px-1.5 py-0.5 font-mono text-xs font-semibold ${methodStyles[method]}`}>
              {method}
            </span>
            <code className="wrap-anywhere font-mono text-xs leading-5 text-white">{endpoint}</code>
            <span className="col-start-2 wrap-break-word lg:col-start-3">{t(`settings.webhook.${label}`)}</span>
          </li>
        ))}
      </ul>
    </SettingsDashboardCard>
  );
}
