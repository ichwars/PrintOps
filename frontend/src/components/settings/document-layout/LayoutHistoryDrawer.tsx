import { useTranslation } from 'react-i18next';
import type { LayoutAuditReceipt, LayoutSummary } from '../../../api/documentLayouts';
import { Modal } from '../../ui/Modal';

export function LayoutHistoryDrawer({ open, versions, audit, canReadAudit, onClose }: { open: boolean; versions: LayoutSummary[]; audit: LayoutAuditReceipt[]; canReadAudit: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  return <Modal open={open} onClose={onClose} title={t('settings.documentLayout.history.title', 'Layout history')} className="max-w-3xl">
    <div className="space-y-3">
      {versions.map((version) => <article key={version.id} className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-3">
        <div className="flex items-center justify-between gap-3">
          <p className="font-medium text-white">{t('settings.documentLayout.history.version', 'Version {{version}}', { version: version.version })}</p>
          <span className="rounded-full bg-bambu-dark-secondary px-2 py-0.5 text-xs text-bambu-gray">{t(`settings.documentLayout.statuses.${version.status}`, version.status)}</span>
        </div>
        <p className="mt-1 text-xs text-bambu-gray">{version.effective_from ? t('settings.documentLayout.history.validFrom', 'Valid from') + ': ' + new Date(version.effective_from).toLocaleString() : new Date(version.updated_at).toLocaleString()}</p>
      </article>)}
      {versions.length === 0 ? <p className="text-sm text-bambu-gray">{t('settings.documentLayout.history.empty', 'No layout versions exist for this scope.')}</p> : null}
      <div className="border-t border-bambu-dark-tertiary pt-3">
        <h3 className="font-medium text-white">Audit</h3>
        {!canReadAudit ? <p className="mt-2 text-sm text-bambu-gray">{t('settings.documentLayout.history.auditRestricted', 'Detailed audit data requires order audit permission.')}</p> : audit.length === 0 ? <p className="mt-2 text-sm text-bambu-gray">No audit events.</p> : <ol className="mt-2 space-y-2">
          {audit.map((entry) => <li key={entry.id} className="rounded bg-bambu-dark p-3 text-sm">
            <p className="font-medium text-white">{entry.event_type}</p>
            <p className="text-xs text-bambu-gray">{new Date(entry.last_seen_at).toLocaleString()}{entry.reason ? ` - ${entry.reason}` : ''}</p>
            {entry.changed_field_paths.length ? <p className="mt-1 break-words text-xs text-bambu-gray">{entry.changed_field_paths.join(', ')}</p> : null}
          </li>)}
        </ol>}
      </div>
    </div>
  </Modal>;
}
