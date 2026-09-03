import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, ShieldCheck } from 'lucide-react';
import { ApiError } from '../../../api/client/core';
import { lexwareApi, type LexwareConnection, type LexwarePreview, type LexwareResource, type LexwareResourceKind } from '../../../api/client/lexware';
import { useAuth } from '../../../contexts/AuthContext';
import { useToast } from '../../../contexts/ToastContext';
import { Button, Checkbox, Modal } from '../../ui';
import { tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../../ui/tableStyles';
import { LexwareArticleSetup } from './LexwareArticleSetup';
import { articleSetupOptions, emptyArticleSetup } from './lexwareState';
import { LexwareTargetPicker } from './LexwareTargetPicker';
import { LexwarePreviewValue } from './LexwarePreviewValue';
import { lexwareError, useLexwareMessages, type LexwareMessages } from './lexwareMessages';

const allowedFields = {
  contacts: ['identity', 'customer_number', 'addresses', 'contacts', 'tax_identifiers'],
  articles: ['name', 'description', 'sale_price', 'tax_rate'],
};

function fieldName(field: string, text: LexwareMessages) {
  return field === 'contacts' ? text.contactFields : text[field as keyof LexwareMessages] ?? field;
}

interface Props {
  connection: LexwareConnection;
  kind: LexwareResourceKind;
  resources: LexwareResource[];
  onClose: () => void;
  onImported: () => void;
}

export function LexwareImportReview({ connection, kind, resources, onClose, onImported }: Props) {
  const { text } = useLexwareMessages();
  const linkedId = kind === 'contacts' ? resources[0].customer_id : resources[0].article_id;
  const [targetId, setTargetId] = useState<number | null>(linkedId);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const close = () => { if (!busy) onClose(); };
  const previews = useQuery({
    // Reviewed versions are intentionally separate from refreshable snapshot queries.
    queryKey: ['lexware-preview', connection.id, kind, resources.map((row) => row.id), targetId, revision],
    queryFn: async () => {
      const results: LexwarePreview[] = [];
      for (const resource of resources) results.push(await lexwareApi.preview(connection.id, {
        resource_id: resource.id,
        ...(kind === 'contacts' ? { customer_id: targetId } : { article_id: targetId }),
      }));
      return results;
    },
    retry: false, staleTime: Infinity, gcTime: 0, refetchOnWindowFocus: false, refetchOnMount: false,
  });

  return (
    <Modal open onClose={close} closeDisabled={busy} closeOnBackdrop={!busy} closeLabel={text.close} title={text.preview}
      description={resources.length === 1 ? resources[0].name : text.previewHelp} className="max-w-5xl">
    <section aria-label={text.preview} className="space-y-5 text-sm">
      <p className="text-bambu-gray">{text.previewHelp}</p>
      {resources.length === 1 && (linkedId ? <p className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-bambu-dark-tertiary px-4 py-3"><span>{text.linkedTarget}: #{linkedId}</span><span className="inline-flex items-center gap-2 text-xs text-bambu-gray"><ShieldCheck className="h-4 w-4" aria-hidden />{text.readonly}</span></p>
        : <LexwareTargetPicker kind={kind} profileId={connection.business_profile_id} value={targetId} onChange={setTargetId} disabled={busy} />)}
      {previews.isPending && <p role="status">{text.loading}</p>}
      {previews.isError && <div role="alert"><p>{lexwareError(previews.error, text, true)}</p>
        <Button variant="secondary" onClick={() => setRevision(revision + 1)}>{text.refreshPreview}</Button></div>}
      {previews.isSuccess && <PreviewForm key={`${targetId}-${revision}-${previews.data.map((item) => `${item.version_hash}:${item.local_version}`).join(',')}`}
        connection={connection} kind={kind} resources={resources} previews={previews.data} onImported={onImported}
        onBusy={setBusy} onClose={close} onRefresh={() => setRevision(revision + 1)} />}
      {!previews.isSuccess && <Button variant="secondary" onClick={close}>{text.cancel}</Button>}
    </section>
    </Modal>
  );
}

function PreviewForm({ connection, kind, resources, previews, onImported, onBusy, onRefresh, onClose }: {
  connection: LexwareConnection;
  kind: LexwareResourceKind;
  resources: LexwareResource[];
  previews: LexwarePreview[];
  onImported: () => void;
  onBusy: (busy: boolean) => void;
  onRefresh: () => void;
  onClose: () => void;
}) {
  const { text } = useLexwareMessages();
  const { hasPermission } = useAuth();
  const { showToast } = useToast();
  const client = useQueryClient();
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [fields, setFields] = useState<Record<number, string[]>>(() => Object.fromEntries(previews.map((preview) => [
    preview.resource_id, preview.local_version === null ? preview.changes.map((change) => change.field).filter((field) => allowedFields[kind].includes(field)) : [],
  ])));
  const [articleDraft, setArticleDraft] = useState(emptyArticleSetup);
  const [completed, setCompleted] = useState<number[]>([]);
  const [stale, setStale] = useState(false);
  const [unitConfirmed, setUnitConfirmed] = useState(false);
  const newArticle = kind === 'articles' && previews[0].article_id === null;
  const existingArticle = kind === 'articles' && !newArticle;
  const currentUnit = typeof previews[0].current.unit_code === 'string' && previews[0].current.unit_code.trim() ? previews[0].current.unit_code : null;
  const unitConfirmationMissing = existingArticle && (!currentUnit || !unitConfirmed);
  const options = articleSetupOptions(articleDraft);
  const canImport = kind === 'contacts' ? hasPermission('customers:manage') : hasPermission(newArticle ? 'inventory:create' : 'inventory:update');
  const pending = previews.filter((preview) => {
    const resource = resources.find((row) => row.id === preview.resource_id)!;
    const newLink = kind === 'contacts' ? !resource.customer_id && preview.customer_id !== null : !resource.article_id && preview.article_id !== null;
    return !completed.includes(preview.resource_id) && (fields[preview.resource_id]?.length || newLink);
  });
  const linkOnly = pending.length > 0 && pending.every((preview) => fields[preview.resource_id].length === 0);
  const batchLinked = previews.length > 1 && previews.some((preview) => preview.customer_id !== null);
  const archived = resources.some((resource) => resource.archived);
  const requiredMissing = pending.some((preview) => preview.local_version === null && !fields[preview.resource_id].includes(kind === 'contacts' ? 'identity' : 'name'));
  const supportedArticle = kind !== 'articles' || ['PRODUCT', 'SERVICE'].includes(String(previews[0].source.external_type));
  const invalidate = () => Promise.all([
    client.invalidateQueries({ queryKey: ['lexware', 'resources'] }),
    client.invalidateQueries({ queryKey: ['lexware', 'targets'] }),
    client.invalidateQueries({ queryKey: ['customers'] }),
    client.invalidateQueries({ queryKey: ['customer'] }),
    client.invalidateQueries({ queryKey: ['warehouse-articles'] }),
  ]);
  const submit = useMutation({
    mutationFn: async () => {
      onBusy(true);
      try {
        for (const preview of pending) {
          if (!mounted.current) return;
          await lexwareApi.import(connection.id, {
            resource_id: preview.resource_id, version_hash: preview.version_hash, local_version: preview.local_version,
            ...(kind === 'contacts' ? { customer_id: preview.customer_id } : { article_id: preview.article_id }),
            fields: fields[preview.resource_id], ...(newArticle ? { article_options: options } : {}),
            ...(existingArticle ? { confirmed_unit_code: currentUnit } : {}),
          });
          setCompleted((ids) => [...ids, preview.resource_id]);
        }
      } finally { onBusy(false); await invalidate(); }
    },
    onSuccess: () => { if (mounted.current) { showToast(text.imported, 'success'); onImported(); } },
    onError: (error) => { if (error instanceof ApiError && error.status === 409) setStale(true); },
  });

  return (
    <div className="space-y-4">
      {previews.map((preview) => {
        const resource = resources.find((row) => row.id === preview.resource_id)!;
        const changed = preview.changes.filter((change) => allowedFields[kind].includes(change.field));
        const done = completed.includes(preview.resource_id);
        return <article key={preview.resource_id} className="space-y-3" aria-label={resource.name}>
          {previews.length > 1 && <h3 className="border-t border-bambu-dark-tertiary pt-4 font-semibold">{resource.name}</h3>}
          <p className="break-all text-xs text-bambu-gray">{text.sourceNumber}: {resource.number ?? '—'} · {text.externalId}: {resource.external_id}</p>
          {kind === 'articles' && <p className="text-sm">{text.externalType}: {preview.source.external_type === 'PRODUCT' ? text.product : preview.source.external_type === 'SERVICE' ? text.service : text.unknown}</p>}
          {existingArticle && <div className="space-y-3 rounded-lg border border-amber-500/40 p-3">
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              <div><dt className="text-bambu-gray">{text.sourceUnit}</dt><dd><LexwarePreviewValue value={preview.source.unit_name} /></dd></div>
              <div><dt className="text-bambu-gray">{text.currentUnit}</dt><dd><LexwarePreviewValue value={preview.current.unit_code} /></dd></div>
            </dl>
            <Checkbox label={text.confirmUnit} helperText={text.unitBasisHelp} checked={unitConfirmed}
              disabled={!currentUnit || submit.isPending || stale || done || !canImport}
              onCheckedChange={setUnitConfirmed} />
          </div>}
          {done && <p role="status" className="text-bambu-green">{text.imported}</p>}
          {resource.archived && <p className="text-amber-300">{text.archivedWarning}</p>}
          {preview.affected_profiles.length > 1 && <div role="alert" className="rounded-lg bg-amber-500/10 p-3 text-amber-300">
            <p>{text.shared}</p><ul className="list-inside list-disc">{preview.affected_profiles.map((profile) => <li key={profile.id}>{profile.name}</li>)}</ul>
          </div>}
          {preview.warnings.map((warning, index) => <p key={index} className="text-sm text-amber-300">{({
            'Archived Lexware records cannot be imported': text.archivedImport,
            'Changes affect the shared customer identity in every listed business profile': text.shared,
            'Confirm the local article kind and unit; inventory is never imported from Lexware': text.articleHelp,
          } as Record<string, string>)[warning] ?? warning}</p>)}
          <div className="overflow-x-auto rounded-lg border border-bambu-dark-tertiary">
            <table className="w-full min-w-[560px] table-fixed text-left text-sm">
              <thead className={tableHeaderClass}><tr className={tableHeaderRowClass}><th scope="col" className={tableHeaderCellClass + ' w-1/4'}>{text.field}</th><th scope="col" className={tableHeaderCellClass}>{text.original}</th><th scope="col" className={tableHeaderCellClass}>{text.local}</th></tr></thead>
              <tbody>{allowedFields[kind].map((field) => {
                const change = changed.find((item) => item.field === field);
                const checked = fields[preview.resource_id]?.includes(field) ?? false;
                return <tr key={field} className={'border-t border-bambu-dark-tertiary align-top ' + (checked ? 'bg-bambu-green/10' : '')}>
                  <th scope="row" className="break-words px-4 py-3 font-normal">{change ? <Checkbox label={fieldName(field, text)}
                    checked={fields[preview.resource_id]?.includes(field) ?? false} disabled={submit.isPending || stale || done || !canImport || batchLinked}
                    onCheckedChange={(checked) => setFields((previous) => ({ ...previous, [preview.resource_id]: checked ? [...previous[preview.resource_id], field] : previous[preview.resource_id].filter((item) => item !== field) }))} /> : fieldName(field, text)}</th>
                  <td className={'px-4 py-3 ' + (checked ? 'text-bambu-green-light' : 'text-bambu-gray-light')}><LexwarePreviewValue value={preview.source[field]} /></td><td className="px-4 py-3 text-bambu-gray-light"><LexwarePreviewValue value={preview.current?.[field]} /></td>
                </tr>;
              })}</tbody>
            </table>
          </div>
          {changed.length === 0 && <p>{text.noChanges}</p>}
        </article>;
      })}
      {newArticle && <LexwareArticleSetup draft={articleDraft} onChange={setArticleDraft} sourceUnit={previews[0].source.unit_name} sourceType={previews[0].source.external_type} disabled={submit.isPending || stale || !canImport} />}
      {requiredMissing && <p role="alert">{text.requiredIdentity}</p>}
      {!supportedArticle && <p role="alert">{text.unsupportedType}</p>}
      {!canImport && <p role="alert">{text.permissionImport}</p>}
      {batchLinked && <p role="alert">{text.stalePreview}</p>}
      {archived && <p role="alert">{text.archivedImport}</p>}
      {!connection.connected && <p role="alert">{text.reconnectImport}</p>}
      {submit.isError && <div role="alert" className="space-y-2 text-red-300">
        {completed.length > 0 && <p>{text.partial}</p>}<p>{lexwareError(submit.error, text, true)}</p>
      </div>}
      {!pending.length && <p className="text-sm text-bambu-gray">{text.chooseFields}</p>}
      <div className="flex justify-end"><Button variant="ghost" size="sm" disabled={submit.isPending} onClick={onRefresh}><RefreshCw className="h-4 w-4" aria-hidden />{text.refreshPreview}</Button></div>
      <div className="sticky -bottom-6 space-y-3 border-t border-bambu-dark-tertiary bg-bambu-dark-secondary pb-2 pt-4">
        <details className="text-xs leading-relaxed text-bambu-gray"><summary tabIndex={0} className="w-fit cursor-pointer rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green">{text.selectedFieldsOnly}</summary><p className="mt-2 max-w-3xl">{kind === 'contacts' ? text.preserve : text.articleHelp}</p></details>
        <div className="flex flex-wrap justify-between gap-3">
        <Button variant="secondary" disabled={submit.isPending} onClick={onClose}>{text.cancel}</Button>
        <Button disabled={submit.isPending || stale || batchLinked || archived || requiredMissing || unitConfirmationMissing || !supportedArticle || !connection.connected || !canImport || !pending.length || (newArticle && !options)}
          loading={submit.isPending} onClick={() => submit.mutate()}>{submit.isPending ? text.importing : linkOnly ? text.link : text.import}</Button>
        </div>
      </div>
    </div>
  );
}
