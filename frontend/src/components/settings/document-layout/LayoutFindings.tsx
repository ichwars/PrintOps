import { AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { LayoutFinding } from '../../../api/documentLayouts';
import type { LayoutEditorSection } from './LayoutControlPanel';

function targetSection(path: string | null): LayoutEditorSection {
  const head = path?.split('.')[0];
  if (head === 'asset') return 'assets';
  if (head === 'technical') return 'positions';
  if (head === 'page' || head === 'typography' || head === 'header' || head === 'title' || head === 'positions' || head === 'totals' || head === 'notes' || head === 'footer' || head === 'assets') return head;
  return 'page';
}

export function LayoutFindings({ findings, stale = false, onNavigate }: { findings: LayoutFinding[]; stale?: boolean; onNavigate: (section: LayoutEditorSection) => void }) {
  const { t } = useTranslation();
  return <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4" aria-labelledby="layout-findings-title">
    <h3 id="layout-findings-title" className="font-semibold text-white">{t('settings.documentLayout.findings.title', 'Validation findings')}</h3>
    {stale ? <p className="mt-1 text-xs text-amber-300">{t('settings.documentLayout.findings.stale', 'Findings belong to an older draft and must be refreshed.')}</p> : null}
    {findings.length === 0 ? <p className="mt-2 text-sm text-bambu-gray">{t('settings.documentLayout.findings.none', 'No findings for the latest saved version.')}</p> : <ul className="mt-3 space-y-2">
      {findings.map((finding, index) => {
        const Icon = finding.severity === 'blocker' ? AlertCircle : finding.severity === 'warning' ? AlertTriangle : Info;
        return <li key={`${finding.code}-${finding.field_path ?? index}`} className={`rounded-lg border p-3 ${finding.severity === 'blocker' ? 'border-red-500/40 bg-red-500/10' : finding.severity === 'warning' ? 'border-amber-500/40 bg-amber-500/10' : 'border-bambu-dark-tertiary bg-bambu-dark'}`}>
          <div className="flex gap-2">
            <Icon className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-white">{finding.message}</p>
              {finding.correction_hint ? <p className="mt-1 text-xs text-bambu-gray">{finding.correction_hint}</p> : null}
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-bambu-gray">
                {finding.field_path ? <span>{t('settings.documentLayout.findings.field', 'Field')}: {finding.field_path}</span> : null}
                {finding.external_rule_id ? <span>{t('settings.documentLayout.findings.rule', 'Rule')}: {finding.external_rule_id}</span> : null}
              </div>
            </div>
            {finding.field_path ? <button type="button" className="min-h-11 shrink-0 rounded px-2 text-xs text-bambu-green hover:bg-bambu-green/10" onClick={() => onNavigate(targetSection(finding.field_path))}>{t('settings.documentLayout.findings.goToField', 'Go to field')}</button> : null}
          </div>
        </li>;
      })}
    </ul>}
  </section>;
}
