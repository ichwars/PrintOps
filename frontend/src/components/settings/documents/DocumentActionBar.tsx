import { CheckCircle2, Copy, Rocket, Save, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { ConfigurationStatus, ReadinessStatus } from '../../../api/documentManagement';
import { Button, TextField } from '../../ui';

interface DocumentActionBarProps {
  canManage: boolean;
  hasConfiguration: boolean;
  status: ConfigurationStatus | null;
  readiness: ReadinessStatus | null;
  dirty: boolean;
  policyDirty: boolean;
  changeReason: string;
  pendingAction: string | null;
  onChangeReason: (value: string) => void;
  onCreate: () => void;
  onSave: () => void;
  onCheck: () => void;
  onPublish: () => void;
  onClone: () => void;
  onWithdraw: () => void;
}

export function DocumentActionBar({
  canManage,
  hasConfiguration,
  status,
  readiness,
  dirty,
  policyDirty,
  changeReason,
  pendingAction,
  onChangeReason,
  onCreate,
  onSave,
  onCheck,
  onPublish,
  onClone,
  onWithdraw,
}: DocumentActionBarProps) {
  const { t } = useTranslation();
  const reasonValid = changeReason.trim().length >= 3;
  const busy = pendingAction !== null;

  return (
    <div className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(260px,1fr)_auto] lg:items-end">
        <TextField
          value={changeReason}
          label={t('settings.documents.changeReason', 'Change reason')}
          helperText={t('settings.documents.changeReasonHint', 'Required for saved and published changes (at least 3 characters).')}
          disabled={!canManage || busy}
          onValueChange={onChangeReason}
        />
        <div className="flex flex-wrap gap-2">
          {!hasConfiguration ? (
            <Button onClick={onCreate} disabled={!canManage || busy} loading={pendingAction === 'create'}>
              {t('settings.documents.actions.create', 'Create draft')}
            </Button>
          ) : (
            <>
              <Button variant="secondary" onClick={onCheck} disabled={busy} loading={pendingAction === 'check'}>
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                {t('settings.documents.actions.check', 'Check readiness')}
              </Button>
              <Button onClick={onSave} disabled={!canManage || status !== 'draft' || !dirty || !reasonValid || busy} loading={pendingAction === 'save'}>
                <Save className="h-4 w-4" aria-hidden="true" />
                {t('settings.documents.actions.save', 'Save draft')}
              </Button>
              {status === 'draft' ? (
                <Button onClick={onPublish} disabled={!canManage || policyDirty || !reasonValid || readiness === 'blocked' || busy}>
                  <Rocket className="h-4 w-4" aria-hidden="true" />
                  {t('settings.documents.actions.publish', 'Publish')}
                </Button>
              ) : null}
              {status === 'scheduled' ? (
                <Button variant="secondary" onClick={onWithdraw} disabled={!canManage || !reasonValid || busy} loading={pendingAction === 'withdraw'}>
                  <Undo2 className="h-4 w-4" aria-hidden="true" />
                  {t('settings.documents.actions.withdraw', 'Withdraw schedule')}
                </Button>
              ) : null}
              {status === 'active' || status === 'superseded' ? (
                <Button variant="secondary" onClick={onClone} disabled={!canManage || busy} loading={pendingAction === 'clone'}>
                  <Copy className="h-4 w-4" aria-hidden="true" />
                  {t('settings.documents.actions.clone', 'Create new version')}
                </Button>
              ) : null}
            </>
          )}
        </div>
      </div>
      {!canManage ? (
        <p className="mt-3 text-xs text-amber-200">{t('settings.documents.readOnlyHint', 'You have read-only access. Editing actions are disabled.')}</p>
      ) : null}
    </div>
  );
}
