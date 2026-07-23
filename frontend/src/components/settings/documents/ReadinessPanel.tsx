import { AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../../../api/client';
import type { ReadinessFinding, ReadinessReport } from '../../../api/documentManagement';
import { Button } from '../../ui';
import { readinessFindingText } from './readinessMessages';

interface ReadinessPanelProps {
  report?: ReadinessReport | null;
  error?: unknown;
  loading?: boolean;
  onReload?: () => void;
}

function focusFinding(finding: ReadinessFinding) {
  const escaped = finding.field_path.replaceAll('\\', '\\\\').replaceAll('"', '\\"');
  const target = document.querySelector<HTMLElement>(`[data-field-path="${escaped}"]`);
  target?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
  target?.querySelector<HTMLElement>('input,select,textarea,button,[role="combobox"]')?.focus();
}

export function ReadinessPanel({ report, error, loading = false, onReload }: ReadinessPanelProps) {
  const { t, i18n } = useTranslation();
  if (loading) {
    return <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4 text-sm text-gray-400">{t('settings.documents.readiness.loading', 'Checking readiness...')}</section>;
  }
  if (error) {
    const apiError = error instanceof ApiError ? error : null;
    const ruleId = typeof apiError?.detail?.rule_id === 'string' ? apiError.detail.rule_id : null;
    const correlationId = typeof apiError?.detail?.correlation_id === 'string' ? apiError.detail.correlation_id : null;
    const versionConflict = apiError?.status === 409 && apiError.code === 'version_conflict';
    return (
      <section role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-100">
        <h3 className="font-semibold">{versionConflict ? t('settings.documents.readiness.versionConflict', 'The draft was changed elsewhere') : t('settings.documents.readiness.checkFailed', 'Compliance check failed')}</h3>
        {ruleId ? <p className="mt-2">{t('settings.documents.readiness.ruleId', 'Rule ID')}: <code>{ruleId}</code></p> : null}
        {correlationId ? <p>{t('settings.documents.readiness.correlationId', 'Correlation ID')}: <code>{correlationId}</code></p> : null}
        {!ruleId && !correlationId ? <p className="mt-2">{apiError?.message ?? t('settings.documents.readiness.unknownError', 'Unknown validation error')}</p> : null}
        {versionConflict && onReload ? <Button className="mt-3" variant="secondary" onClick={onReload}><RefreshCw className="h-4 w-4" />{t('settings.documents.readiness.reloadCompare', 'Reload and compare')}</Button> : null}
      </section>
    );
  }
  if (!report) return null;

  const findings = report.findings
    .map((finding, index) => ({ finding, index }))
    .sort((left, right) => Number(left.finding.severity !== 'blocker') - Number(right.finding.severity !== 'blocker') || left.index - right.index);

  return (
    <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4" aria-labelledby="document-readiness-heading">
      <div className="flex items-center gap-2">
        {report.status === 'ready'
          ? <CheckCircle2 className="h-5 w-5 text-bambu-green" />
          : <AlertTriangle className={`h-5 w-5 ${report.status === 'blocked' ? 'text-red-400' : 'text-amber-300'}`} />}
        <h3 id="document-readiness-heading" className="font-semibold text-white">
          {t('settings.documents.readiness.title', 'Publication readiness')}: {t(`settings.documents.readiness.${report.status}`, report.status)}
        </h3>
      </div>
      {findings.length ? (
        <ol className="mt-3 space-y-2">
          {findings.map(({ finding, index }) => {
            const fallbackTitle = t(finding.message_key, t(`settings.documents.readiness.findings.${finding.code}`, finding.code.replaceAll('_', ' ')));
            const localized = readinessFindingText(i18n.resolvedLanguage ?? i18n.language, finding.code, fallbackTitle, finding.correction);
            return (
              <li key={`${finding.field_path}-${finding.code}-${index}`}>
                <button type="button" className="w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-3 text-left hover:border-bambu-green/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green" onClick={() => focusFinding(finding)}>
                  <span className={finding.severity === 'blocker' ? 'text-red-300' : 'text-amber-200'}>{localized.title}</span>
                  <span className="mt-1 block text-xs text-gray-400">{localized.correction}</span>
                  {finding.rule_id ? <span className="mt-1 block font-mono text-xs text-gray-500">{finding.rule_id}</span> : null}
                </button>
              </li>
            );
          })}
        </ol>
      ) : <p className="mt-2 text-sm text-gray-400">{t('settings.documents.readiness.noFindings', 'No blocking findings.')}</p>}
    </section>
  );
}
