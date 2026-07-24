import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Hash, Loader2, Save } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  ApiError,
  api,
  type BusinessProfile,
  type NumberSequence,
  type NumberSequenceKey,
  type NumberSequenceValues,
} from '../../api/client';
import { Button, Checkbox, NumberField, Select, TextField } from '../ui';

interface Props {
  profiles: BusinessProfile[];
  canManage: boolean;
}

interface SequenceDraft {
  prefix: string;
  pattern: string;
  nextValue: string;
  yearly: boolean;
}

interface SequenceDefinition {
  key: NumberSequenceKey;
  germanStem: string;
  germanNoun: string;
  englishName: string;
  defaults: SequenceDraft;
}

const DEFINITIONS: SequenceDefinition[] = [
  { key: 'customer', germanStem: 'Kunden', germanNoun: 'Kundennummernkreis', englishName: 'Customer', defaults: { prefix: 'KD', pattern: '{PREFIX}-{#####}', nextValue: '1', yearly: false } },
  { key: 'offer', germanStem: 'Angebots', germanNoun: 'Angebotsnummernkreis', englishName: 'Offer', defaults: { prefix: 'AG', pattern: '{PREFIX}-{YYYY}-{#####}', nextValue: '1', yearly: true } },
  { key: 'order', germanStem: 'Auftrags', germanNoun: 'Auftragsnummernkreis', englishName: 'Order', defaults: { prefix: 'AU', pattern: '{PREFIX}-{YYYY}-{#####}', nextValue: '1', yearly: true } },
  { key: 'invoice', germanStem: 'Rechnungs', germanNoun: 'Rechnungsnummernkreis', englishName: 'Invoice', defaults: { prefix: 'RE', pattern: '{PREFIX}-{YYYY}-{#####}', nextValue: '1', yearly: true } },
];

function initialDrafts(): Record<NumberSequenceKey, SequenceDraft> {
  return Object.fromEntries(DEFINITIONS.map((definition) => [definition.key, { ...definition.defaults }])) as Record<NumberSequenceKey, SequenceDraft>;
}

function valuesFromDraft(draft: SequenceDraft): NumberSequenceValues {
  return {
    prefix: draft.prefix.trim(),
    pattern: draft.pattern.trim(),
    next_value: Math.max(1, Number.parseInt(draft.nextValue, 10) || 1),
    reset_policy: draft.yearly ? 'yearly' : 'none',
  };
}

export function NumberSequenceSettings({ profiles, canManage }: Props) {
  const { i18n } = useTranslation();
  const german = i18n.language.startsWith('de');
  const queryClient = useQueryClient();
  const [profileId, setProfileId] = useState<number | null>(null);
  const [drafts, setDrafts] = useState(initialDrafts);
  const [error, setError] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<NumberSequenceKey | null>(null);

  useEffect(() => {
    if (profiles.length === 0) {
      setProfileId(null);
      return;
    }
    if (profileId === null || !profiles.some((profile) => profile.id === profileId)) {
      setProfileId((profiles.find((profile) => profile.is_default) ?? profiles[0]).id);
    }
  }, [profileId, profiles]);

  const sequencesQuery = useQuery({
    queryKey: ['business-profile-number-sequences', profileId],
    queryFn: () => api.getNumberSequences(profileId as number),
    enabled: profileId !== null,
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
    setSavedKey(null);
  }, [sequencesQuery.data]);

  const saveMutation = useMutation({
    mutationFn: async ({ definition, existing }: { definition: SequenceDefinition; existing?: NumberSequence }) => {
      if (profileId === null) throw new Error('No business profile selected');
      const values = valuesFromDraft(drafts[definition.key]);
      if (existing) {
        return api.updateNumberSequence(profileId, existing.id, { ...values, version: existing.version });
      }
      return api.createNumberSequence(profileId, { key: definition.key, ...values });
    },
    onSuccess: async (sequence) => {
      setError(null);
      setSavedKey(sequence.key);
      await queryClient.invalidateQueries({ queryKey: ['business-profile-number-sequences', profileId] });
    },
    onError: (caught) => {
      setSavedKey(null);
      setError(caught instanceof ApiError ? caught.message : caught instanceof Error ? caught.message : (german ? 'Nummernkreis konnte nicht gespeichert werden.' : 'Could not save number sequence.'));
    },
  });

  const updateDraft = (key: NumberSequenceKey, patch: Partial<SequenceDraft>) => {
    setSavedKey(null);
    setDrafts((current) => ({ ...current, [key]: { ...current[key], ...patch } }));
  };

  return (
    <section id="card-number-sequences" className="w-full overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary card-shadow" aria-labelledby="number-sequences-heading">
      <div className="flex items-center gap-2 border-b border-bambu-dark-tertiary px-4 py-4">
        <Hash className="h-5 w-5 text-bambu-green" aria-hidden="true" />
        <h2 id="number-sequences-heading" className="text-lg font-semibold text-white">{german ? 'Nummernkreise' : 'Number sequences'}</h2>
      </div>
      <div className="space-y-4 p-4">
        <div className="grid gap-4 md:grid-cols-[minmax(240px,360px)_1fr] md:items-end">
          {profiles.length > 0 ? (
            <Select
              ariaLabel={german ? 'Unternehmensprofil für Nummernkreise' : 'Business profile for number sequences'}
              label={german ? 'Unternehmensprofil für Nummernkreise' : 'Business profile for number sequences'}
              value={profileId ?? profiles[0].id}
              onValueChange={(value) => setProfileId(Number(value))}
              options={profiles.map((profile) => ({ value: profile.id, label: profile.name }))}
            />
          ) : <p className="text-sm text-bambu-gray">{german ? 'Legen Sie zuerst ein Unternehmensprofil an.' : 'Create a business profile first.'}</p>}
          <p className="text-sm text-bambu-gray">
            {german
              ? 'Präfix, Format und nächste laufende Nummer je Dokumenttyp. Erlaubte Platzhalter: {PREFIX}, {YYYY}, {YY} und {####} (4–10 Stellen).'
              : 'Prefix, format, and next counter per document type. Supported placeholders: {PREFIX}, {YYYY}, {YY}, and {####} (4–10 digits).'}
          </p>
        </div>

        {(error || sequencesQuery.error) && (
          <div role="alert" className="flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error ?? (sequencesQuery.error instanceof Error ? sequencesQuery.error.message : (german ? 'Nummernkreise konnten nicht geladen werden.' : 'Could not load number sequences.'))}
          </div>
        )}

        {profileId !== null && sequencesQuery.isPending && (
          <div className="flex items-center gap-2 text-sm text-bambu-gray"><Loader2 className="h-4 w-4 animate-spin" />{german ? 'Nummernkreise werden geladen …' : 'Loading number sequences…'}</div>
        )}

        {profileId !== null && !sequencesQuery.isPending && (
          <div className="grid gap-3 xl:grid-cols-2">
            {DEFINITIONS.map((definition) => {
              const existing = sequencesByKey.get(definition.key);
              const draft = drafts[definition.key];
              const stem = german ? definition.germanStem : definition.englishName;
              const noun = german ? definition.germanNoun : `${definition.englishName} number sequence`;
              const pending = saveMutation.isPending && saveMutation.variables?.definition.key === definition.key;
              return (
                <div key={definition.key} className="space-y-3 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark/35 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="font-medium text-white">{noun}</h3>
                    <span className={`text-xs ${existing ? 'text-bambu-green' : 'text-bambu-gray'}`}>{existing ? (german ? 'Aktiv' : 'Active') : (german ? 'Noch nicht angelegt' : 'Not created')}</span>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <TextField label={german ? `${stem}-Präfix` : `${stem} prefix`} aria-label={german ? `${stem}-Präfix` : `${stem} prefix`} value={draft.prefix} onValueChange={(value) => updateDraft(definition.key, { prefix: value })} disabled={!canManage || pending} />
                    <NumberField label={german ? `Nächste ${stem}nummer` : `Next ${stem.toLowerCase()} number`} aria-label={german ? `Nächste ${stem}nummer` : `Next ${stem.toLowerCase()} number`} min="1" step="1" value={draft.nextValue} onValueChange={(value) => updateDraft(definition.key, { nextValue: value })} disabled={!canManage || pending} />
                  </div>
                  <TextField label={german ? `${stem}-Nummernformat` : `${stem} number format`} aria-label={german ? `${stem}-Nummernformat` : `${stem} number format`} value={draft.pattern} onValueChange={(value) => updateDraft(definition.key, { pattern: value })} disabled={!canManage || pending} />
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <Checkbox checked={draft.yearly} onCheckedChange={(checked) => updateDraft(definition.key, { yearly: checked })} label={german ? `${stem}nummer jährlich zurücksetzen` : `Reset ${stem.toLowerCase()} number yearly`} disabled={!canManage || pending} />
                    {canManage && (
                      <Button type="button" size="sm" onClick={() => saveMutation.mutate({ definition, existing })} loading={pending} disabled={saveMutation.isPending}>
                        {!pending && <Save className="h-4 w-4" />}
                        {existing ? (german ? `${noun} speichern` : `Save ${noun.toLowerCase()}`) : (german ? `${noun} anlegen` : `Create ${noun.toLowerCase()}`)}
                      </Button>
                    )}
                  </div>
                  {savedKey === definition.key && <p role="status" className="text-xs text-bambu-green">{german ? 'Nummernkreis gespeichert.' : 'Number sequence saved.'}</p>}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
