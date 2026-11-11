import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader } from '../Card';

const endpoints = [
  ['GET', '/api/v1/webhook/printer/:id/status', 'getSpecificStatus'],
  ['GET', '/api/v1/webhook/queue', 'queueStatus'],
  ['POST', '/api/v1/webhook/queue/add', 'addToQueue'],
  ['POST', '/api/v1/webhook/printer/:id/start', 'startNext'],
  ['POST', '/api/v1/webhook/printer/:id/stop', 'stopPrint'],
  ['POST', '/api/v1/webhook/printer/:id/cancel', 'cancelPrint'],
] as const;

export function WebhookEndpoints() {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <h3 className="text-base font-semibold text-white" id="card-webhooks">{t('settings.webhookEndpoints')}</h3>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-bambu-gray">{t('settings.webhookApiKeyHint')}</p>
        <ul className="space-y-2 font-mono text-xs">
          {endpoints.map(([method, endpoint, label]) => (
            <li key={endpoint} className="rounded bg-bambu-dark p-2">
              <span className={method === 'GET' ? 'text-blue-700 dark:text-blue-400' : 'text-green-700 dark:text-green-400'}>
                {method}
              </span>{' '}
              <span className="text-white">{endpoint}</span>{' '}
              <span className="text-bambu-gray">{t(`settings.webhook.${label}`)}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
