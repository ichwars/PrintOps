import { AlertTriangle, CheckCircle2, Clock3, Copy, History, Send, ShieldCheck, Undo2 } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { LayoutDetail, LayoutReadinessReport } from '../../../api/documentLayouts';
import type { AutosaveStatus } from '../../../hooks/useAutosaveDraft';
import { Button } from '../../ui/Button';
import { Modal } from '../../ui/Modal';
import { Checkbox } from '../../ui/Checkbox';
import { DateTimePicker } from '../../ui/DateTimePicker';
import { TextArea } from '../../ui/TextArea';

type DialogKind = 'clone' | 'publish' | 'withdraw' | null;

function Axis({ label, value, state }: { label: string; value: string; state: 'ok' | 'wait' | 'bad' | 'neutral' }) {
  const Icon = state === 'ok' ? CheckCircle2 : state === 'bad' ? AlertTriangle : state === 'wait' ? Clock3 : ShieldCheck;
  return <div className="min-w-[132px] flex-1 rounded-lg bg-bambu-dark px-3 py-2">
    <p className="text-[10px] uppercase tracking-wide text-bambu-gray">{label}</p>
    <p className={`mt-1 flex items-center gap-1.5 text-xs font-medium ${state === 'ok' ? 'text-emerald-300' : state === 'bad' ? 'text-red-300' : state === 'wait' ? 'text-amber-300' : 'text-bambu-gray-light'}`}><Icon className="h-3.5 w-3.5" />{value}</p>
  </div>;
}

export function LayoutLifecycleBar({
  detail,
  confirmedLockVersion,
  autosaveStatus,
  readiness,
  readinessLoading,
  readOnly,
  actionBusy,
  onRetrySave,
  onClone,
  onPublish,
  onWithdraw,
  onOpenHistory,
}: {
  detail: LayoutDetail;
  confirmedLockVersion: number | null;
  autosaveStatus: AutosaveStatus;
  readiness?: LayoutReadinessReport;
  readinessLoading: boolean;
  readOnly: boolean;
  actionBusy: boolean;
  onRetrySave: () => void;
  onClone: (reason: string) => Promise<void>;
  onPublish: (reason: string, effectiveFrom: string | null) => Promise<void>;
  onWithdraw: (reason: string) => Promise<void>;
  onOpenHistory: () => void;
}) {
  const { t } = useTranslation();
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [reason, setReason] = useState('');
  const [scheduled, setScheduled] = useState(false);
  const [effectiveDate, setEffectiveDate] = useState('');
  const [effectiveTime, setEffectiveTime] = useState('09:00');
  const [dialogError, setDialogError] = useState<string | null>(null);
  const current = confirmedLockVersion === detail.summary.lock_version;
  const blockers = readiness?.findings.filter((finding) => finding.severity === 'blocker').length ?? 0;
  const canPublish = !readOnly && detail.summary.status === 'draft' && current && autosaveStatus !== 'saving' && autosaveStatus !== 'pending' && readiness?.ready === true && blockers === 0;
  const invoiceRelevant = detail.summary.scope.document_type?.includes('invoice') ?? false;

  const close = () => { setDialog(null); setReason(''); setScheduled(false); setEffectiveDate(''); setEffectiveTime('09:00'); setDialogError(null); };
  const submit = async () => {
    if (reason.trim().length < 3) {
      setDialogError(t('settings.documentLayout.dialogs.reasonRequired', 'Enter a reason with at least three characters.'));
      return;
    }
    if (dialog === 'publish' && scheduled && (!effectiveDate || new Date(`${effectiveDate}T${effectiveTime}:00`).getTime() <= Date.now())) {
      setDialogError(t('settings.documentLayout.dialogs.dateRequired', 'Choose a future publication date.'));
      return;
    }
    try {
      if (dialog === 'clone') await onClone(reason.trim());
      if (dialog === 'publish') await onPublish(reason.trim(), scheduled ? new Date(`${effectiveDate}T${effectiveTime}:00`).toISOString() : null);
      if (dialog === 'withdraw') await onWithdraw(reason.trim());
      close();
    } catch (cause) {
      setDialogError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const saveValue = autosaveStatus === 'error' ? t('settings.documentLayout.statuses.failed', 'Save failed') : autosaveStatus === 'saving' ? t('settings.documentLayout.statuses.saving', 'Saving...') : autosaveStatus === 'pending' ? t('settings.documentLayout.statuses.pending', 'Changes pending') : t('settings.documentLayout.statuses.saved', 'Saved');
  return <>
    <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-3" aria-labelledby="layout-lifecycle-title">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="layout-lifecycle-title" className="mr-auto font-semibold text-white">{t('settings.documentLayout.lifecycle.title', 'Lifecycle')} <span className="ml-2 rounded-full bg-bambu-dark px-2 py-0.5 text-xs font-normal text-bambu-gray">v{detail.summary.version} - {t(`settings.documentLayout.statuses.${detail.summary.status}`, detail.summary.status)}</span></h2>
        <Button size="sm" variant="ghost" onClick={onOpenHistory}><History className="h-4 w-4" />{t('settings.documentLayout.actions.history', 'History')}</Button>
        {!readOnly ? <Button size="sm" variant="secondary" onClick={() => setDialog('clone')}><Copy className="h-4 w-4" />{t('settings.documentLayout.actions.clone', 'Clone')}</Button> : null}
        {!readOnly && detail.summary.status === 'scheduled' ? <Button size="sm" variant="danger" onClick={() => setDialog('withdraw')}><Undo2 className="h-4 w-4" />{t('settings.documentLayout.actions.withdraw', 'Withdraw')}</Button> : null}
        {!readOnly && detail.summary.status === 'draft' ? <Button size="sm" disabled={!canPublish} title={!canPublish ? t('settings.documentLayout.lifecycle.publishBlocked', 'Publish is blocked until the latest saved version is blocker-free.') : undefined} onClick={() => setDialog('publish')}><Send className="h-4 w-4" />{t('settings.documentLayout.actions.publish', 'Publish')}</Button> : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Axis label={t('settings.documentLayout.lifecycle.autosave', 'Autosave')} value={saveValue} state={autosaveStatus === 'error' ? 'bad' : autosaveStatus === 'pending' || autosaveStatus === 'saving' ? 'wait' : 'ok'} />
        <Axis label={t('settings.documentLayout.lifecycle.preview', 'Preview')} value={current ? t('settings.documentLayout.lifecycle.current', 'Current') : t('settings.documentLayout.lifecycle.updating', 'Updating')} state={current ? 'ok' : 'wait'} />
        <Axis label={t('settings.documentLayout.lifecycle.readiness', 'Readiness')} value={readinessLoading ? t('settings.documentLayout.statuses.checking', 'Checking') : readiness?.ready ? t('settings.documentLayout.statuses.ready', 'Ready') : t('settings.documentLayout.statuses.blocked', 'Blocked')} state={readinessLoading ? 'wait' : readiness?.ready ? 'ok' : 'bad'} />
        <Axis label={t('settings.documentLayout.lifecycle.pdfa', 'PDF/A evidence')} value={detail.validation_status === 'valid' ? 'PDF/A-3u valid' : detail.validation_status === 'invalid' ? 'Invalid' : t('settings.documentLayout.lifecycle.unchecked', 'Unchecked')} state={detail.validation_status === 'valid' ? 'ok' : detail.validation_status === 'invalid' ? 'bad' : 'neutral'} />
        <Axis label={t('settings.documentLayout.lifecycle.einvoice', 'E-invoice')} value={invoiceRelevant ? (readiness?.ready ? 'EN 16931 ready' : t('settings.documentLayout.lifecycle.unchecked', 'Unchecked')) : t('settings.documentLayout.compliance.notApplicable', 'Not applicable')} state={invoiceRelevant ? readiness?.ready ? 'ok' : 'wait' : 'neutral'} />
      </div>
      {autosaveStatus === 'error' ? <button type="button" className="mt-2 text-xs text-red-300 underline" onClick={onRetrySave}>{t('settings.documentLayout.actions.retry', 'Retry')}</button> : null}
    </section>

    <Modal open={dialog !== null} onClose={close} title={dialog === 'clone' ? t('settings.documentLayout.dialogs.cloneTitle', 'Clone layout') : dialog === 'withdraw' ? t('settings.documentLayout.dialogs.withdrawTitle', 'Withdraw publication') : t('settings.documentLayout.dialogs.publishTitle', 'Publish layout')}>
      <div className="space-y-4">
        <TextArea
          label={dialog === 'publish' ? t('settings.documentLayout.dialogs.publishReason', 'Publication reason') : dialog === 'withdraw' ? t('settings.documentLayout.dialogs.withdrawReason', 'Withdrawal reason') : t('settings.documentLayout.dialogs.cloneReason', 'Reason for the new draft')}
          value={reason}
          onValueChange={setReason}
        />
        {dialog === 'publish' ? <>
          <Checkbox checked={scheduled} label={t('settings.documentLayout.dialogs.publishLater', 'Schedule publication')} onCheckedChange={setScheduled} />
          {scheduled ? <DateTimePicker
            dateValue={effectiveDate}
            timeValue={effectiveTime}
            onDateValueChange={setEffectiveDate}
            onTimeValueChange={setEffectiveTime}
            locale="de-DE"
            dateLabel={t('settings.documentLayout.dialogs.effectiveFrom', 'Valid from')}
            timeLabel="Time"
          /> : null}
        </> : null}
        {dialogError ? <p role="alert" className="text-sm text-red-400">{dialogError}</p> : null}
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={close}>{t('settings.documentLayout.actions.cancel', 'Cancel')}</Button><Button loading={actionBusy} onClick={() => void submit()}>{t('settings.documentLayout.actions.confirm', 'Confirm')}</Button></div>
      </div>
    </Modal>
  </>;
}
