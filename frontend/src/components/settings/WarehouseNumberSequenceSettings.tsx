import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Hash, Loader2, Save } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  ApiError,
  api,
  type NumberSequenceValues,
  type WarehouseNumberSequence,
  type WarehouseNumberSequenceKey,
} from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import { Button, Checkbox, NumberField, TextField } from '../ui';
import { SettingsDashboardCard } from './SettingsDashboardCard';

interface SequenceDraft {
  prefix: string;
  pattern: string;
  nextValue: string;
  yearly: boolean;
}

interface SequenceDefinition {
  key: WarehouseNumberSequenceKey;
  defaults: SequenceDraft;
}

const DEFINITIONS: SequenceDefinition[] = [
  { key: 'material', defaults: { prefix: 'MAT', pattern: '{PREFIX}-{#####}', nextValue: '1', yearly: false } },
  { key: 'spool', defaults: { prefix: 'SP', pattern: '{PREFIX}-{#####}', nextValue: '1', yearly: false } },
  { key: 'purchase_order', defaults: { prefix: 'BE', pattern: '{PREFIX}-{YYYY}-{#####}', nextValue: '1', yearly: true } },
  { key: 'goods_receipt', defaults: { prefix: 'WE', pattern: '{PREFIX}-{YYYY}-{#####}', nextValue: '1', yearly: true } },
];

function initialDrafts(): Record<WarehouseNumberSequenceKey, SequenceDraft> {
  return Object.fromEntries(DEFINITIONS.map((definition) => [definition.key, { ...definition.defaults }])) as Record<WarehouseNumberSequenceKey, SequenceDraft>;
}

function valuesFromDraft(draft: SequenceDraft): NumberSequenceValues {
  return {
    prefix: draft.prefix.trim(),
    pattern: draft.pattern.trim(),
    next_value: Math.max(1, Number.parseInt(draft.nextValue, 10) || 1),
    reset_policy: draft.yearly ? 'yearly' : 'none',
  };
}

export function WarehouseNumberSequenceSettings() {
  const { t } = useTranslation();
  const tr = (key: string, values?: { name: string }) => t(`orders.runtimeDevice.${key}`, values);
  const { hasPermission } = useAuth();
  const canManage = hasPermission('inventory:update');
  const queryClient = useQueryClient();
  const [drafts, setDrafts] = useState(initialDrafts);
  const [error, setError] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<WarehouseNumberSequenceKey | null>(null);

  const sequencesQuery = useQuery({
    queryKey: ['warehouse-number-sequences'],
    queryFn: api.getWarehouseNumberSequences,
  });

  const sequencesByKey = useMemo(() => new Map(
    (sequencesQuery.data ?? []).map((sequence) => [sequence.key, sequence]),
  ), [sequencesQuery.data]);

  useEffect(() => {
    if (!sequencesQuery.data) return;
    const next = initialDrafts();
    for (const sequence of sequencesQuery.data) {
      next[sequence.key] = {
        prefix: sequence.prefix,
        pattern: sequence.pattern,
        nextValue: String(sequence.next_value),
        yearly: sequence.reset_policy === 'yearly',
      };
    }
    setDrafts(next);
    setError(null);
  }, [sequencesQuery.data]);

  const saveMutation = useMutation({
    mutationFn: async ({ definition, existing }: { definition: SequenceDefinition; existing?: WarehouseNumberSequence }) => {
      const values = valuesFromDraft(drafts[definition.key]);
      if (existing) {
        return api.updateWarehouseNumberSequence(existing.id, { ...values, version: existing.version });
      }
      return api.createWarehouseNumberSequence({ key: definition.key, ...values });
    },
    onMutate: () => setSavedKey(null),
    onSuccess: async (sequence) => {
      setError(null);
      setSavedKey(sequence.key);
      await queryClient.invalidateQueries({ queryKey: ['warehouse-number-sequences'] });
    },
    onError: (caught) => {
      setError(caught instanceof ApiError ? caught.message : caught instanceof Error ? caught.message : tr('sequenceSaveError'));
    },
  });

  const updateDraft = (key: WarehouseNumberSequenceKey, patch: Partial<SequenceDraft>) => {
    setSavedKey(null);
    setDrafts((current) => ({ ...current, [key]: { ...current[key], ...patch } }));
  };

  return (
    <SettingsDashboardCard id="card-warehouse-number-sequences" title={tr('warehouse.title')} icon={Hash}>
        <p className="text-sm text-table-secondary">
          {tr('warehouse.description')}
        </p>

        {(error || sequencesQuery.error) && (
          <div role="alert" className="flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-800 dark:text-red-200">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error ?? (sequencesQuery.error instanceof Error ? sequencesQuery.error.message : tr('sequenceLoadError'))}
          </div>
        )}

        {sequencesQuery.isPending && (
          <div className="flex items-center gap-2 text-sm text-table-secondary"><Loader2 className="h-4 w-4 animate-spin" />{tr('sequenceLoading')}</div>
        )}

        {!sequencesQuery.isPending && (
          <div className="grid gap-3 xl:grid-cols-2">
            {DEFINITIONS.map((definition) => {
              const existing = sequencesByKey.get(definition.key);
              const draft = drafts[definition.key];
              const textKey = 'warehouse.types.' + definition.key;
              const noun = tr(textKey + '.title');
              const actionName = tr(textKey + '.actionName');
              const pending = saveMutation.isPending && saveMutation.variables?.definition.key === definition.key;
              return (
                <div key={definition.key} className="space-y-3 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark/35 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="font-medium text-white">{noun}</h3>
                    <span className={`text-xs ${existing ? 'text-accent-foreground' : 'text-table-secondary'}`}>{existing ? tr('active') : tr('notCreated')}</span>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <TextField label={tr(textKey + '.prefix')} aria-label={tr(textKey + '.prefix')} value={draft.prefix} onValueChange={(value) => updateDraft(definition.key, { prefix: value })} disabled={!canManage || pending} />
                    <NumberField label={tr(textKey + '.next')} aria-label={tr(textKey + '.next')} min="1" step="1" value={draft.nextValue} onValueChange={(value) => updateDraft(definition.key, { nextValue: value })} disabled={!canManage || pending} />
                  </div>
                  <TextField label={tr(textKey + '.format')} aria-label={tr(textKey + '.format')} value={draft.pattern} onValueChange={(value) => updateDraft(definition.key, { pattern: value })} disabled={!canManage || pending} />
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <Checkbox checked={draft.yearly} onCheckedChange={(checked) => updateDraft(definition.key, { yearly: checked })} label={tr(textKey + '.resetYearly')} disabled={!canManage || pending} />
                    {canManage && (
                      <Button className="text-black!" type="button" size="sm" onClick={() => saveMutation.mutate({ definition, existing })} loading={pending} disabled={saveMutation.isPending}>
                        {!pending && <Save className="h-4 w-4" />}
                        {existing ? tr('saveSequence', { name: actionName }) : tr('createSequence', { name: actionName })}
                      </Button>
                    )}
                  </div>
                  {savedKey === definition.key && <p role="status" className="text-xs text-accent-foreground">{tr('sequenceSaved')}</p>}
                </div>
              );
            })}
          </div>
        )}
    </SettingsDashboardCard>
  );
}
