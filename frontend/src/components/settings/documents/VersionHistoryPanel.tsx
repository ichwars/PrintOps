import { History } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { DocumentAuditEvent, DocumentConfigurationSummary } from '../../../api/documentManagement';

interface VersionHistoryPanelProps {
  items: DocumentConfigurationSummary[];
  auditEvents: DocumentAuditEvent[];
  loading?: boolean;
}

export function VersionHistoryPanel({ items, auditEvents, loading = false }: VersionHistoryPanelProps) {
  const { t, i18n } = useTranslation();

  return (
    <section className="overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary" aria-labelledby="document-history-heading">
      <div className="flex items-center gap-2 border-b border-bambu-dark-tertiary px-4 py-3">
        <History className="h-4 w-4 text-bambu-green" aria-hidden="true" />
        <h3 id="document-history-heading" className="font-medium text-white">
          {t('settings.documents.history.title', 'Version history')}
        </h3>
      </div>
      {loading ? <p className="p-4 text-sm text-gray-400">{t('common.loading', 'Loading...')}</p> : null}
      {!loading && items.length === 0 ? (
        <p className="p-4 text-sm text-gray-400">{t('settings.documents.history.empty', 'No versions exist for this context yet.')}</p>
      ) : null}
      {items.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="bg-bambu-dark text-xs uppercase text-gray-400">
              <tr>
                <th className="px-4 py-2">{t('settings.documents.history.version', 'Version')}</th>
                <th className="px-4 py-2">{t('settings.documents.history.status', 'Status')}</th>
                <th className="px-4 py-2">{t('settings.documents.history.effectiveFrom', 'Effective from')}</th>
                <th className="px-4 py-2">{t('settings.documents.history.reason', 'Change reason')}</th>
                <th className="px-4 py-2">{t('settings.documents.history.actor', 'Created / published by')}</th>
                <th className="px-4 py-2">{t('settings.documents.history.rules', 'Rule versions')}</th>
                <th className="px-4 py-2">{t('settings.documents.history.publishedAt', 'Published')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-bambu-dark-tertiary">
              {items.map((item) => (
                <tr key={item.id} className="text-gray-200">
                  <td className="px-4 py-3 font-medium">{item.version}</td>
                  <td className="px-4 py-3">{t(`settings.documents.status.${item.status}`, item.status)}</td>
                  <td className="px-4 py-3">{item.effective_from ? new Intl.DateTimeFormat(i18n.language).format(new Date(`${item.effective_from}T00:00:00`)) : '—'}</td>
                  <td className="max-w-md px-4 py-3">{item.change_reason || '—'}</td>
                  <td className="px-4 py-3">{(item.published_by_id ?? item.created_by_id) !== null ? `#${item.published_by_id ?? item.created_by_id}` : '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex max-w-sm flex-wrap gap-1">
                      {Object.entries(item.rule_versions).length
                        ? Object.entries(item.rule_versions).map(([name, version]) => (
                          <span key={name} className="rounded bg-bambu-dark px-2 py-1 text-xs text-gray-300">{name} {version}</span>
                        ))
                        : '—'}
                    </div>
                  </td>
                  <td className="px-4 py-3">{item.published_at ? new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(item.published_at)) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <div className="border-t border-bambu-dark-tertiary px-4 py-3">
        <h4 className="text-sm font-medium text-white">{t('settings.documents.history.auditTitle', 'Audit trail')}</h4>
        {auditEvents.length === 0 ? (
          <p className="mt-2 text-sm text-gray-400">{t('settings.documents.history.auditEmpty', 'No audit events recorded yet.')}</p>
        ) : (
          <ol className="mt-3 space-y-2">
            {auditEvents.map((event) => (
              <li key={event.id} className="grid gap-1 rounded-lg bg-bambu-dark px-3 py-2 text-xs text-gray-300 md:grid-cols-[140px_1fr_auto]">
                <span className="font-medium text-white">{t(`settings.documents.history.actions.${event.action}`, event.action)}</span>
                <span>{event.reason || '—'}</span>
                <span title={`${t('settings.documents.history.correlation', 'Correlation ID')}: ${event.correlation_id}`}>
                  {new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(event.created_at))}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
