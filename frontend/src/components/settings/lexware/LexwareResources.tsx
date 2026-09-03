import { useEffect, useRef, useState } from 'react';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { ArrowRight, Archive, ExternalLink, Link2, Search, ShieldCheck } from 'lucide-react';
import { lexwareApi, type LexwareConnection, type LexwareResource, type LexwareResourceKind } from '../../../api/client/lexware';
import { useAuth } from '../../../contexts/AuthContext';
import { Button, Checkbox, Select, TextField } from '../../ui';
import { tableHeaderActionCellClass, tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../../ui/tableStyles';
import { LexwareImportReview } from './LexwareImportReview';
import { formatLexwareDate, lexwareError, useLexwareMessages } from './lexwareMessages';

function useResources(connection: LexwareConnection, kind: LexwareResourceKind, enabled: boolean) {
  const resources = useQuery({
    queryKey: ['lexware', 'resources', connection.id, kind],
    queryFn: () => lexwareApi.resources(connection.id, kind),
    enabled, retry: false, refetchOnWindowFocus: false,
  });
  const lastSuccess = useRef(connection.last_success_at);
  const { refetch } = resources;
  useEffect(() => {
    if (lastSuccess.current !== connection.last_success_at) {
      lastSuccess.current = connection.last_success_at;
      if (enabled) void refetch();
    }
  }, [connection.last_success_at, enabled, refetch]);
  return resources;
}

export function LexwareResources({ connection }: { connection: LexwareConnection }) {
  const { hasPermission } = useAuth();
  const { text } = useLexwareMessages();
  const canReadContacts = hasPermission('customers:read');
  const canReadArticles = hasPermission('inventory:read');
  const [chosenKind, setChosenKind] = useState<LexwareResourceKind>('contacts');
  const kind = chosenKind === 'contacts' && canReadContacts ? 'contacts' : canReadArticles ? 'articles' : 'contacts';
  const contacts = useResources(connection, 'contacts', canReadContacts);
  const articles = useResources(connection, 'articles', canReadArticles);
  if (!canReadArticles && !canReadContacts) return <p className="text-sm text-bambu-gray">{text.resourcePermission}</p>;
  return <div className="min-w-0 space-y-5">
    <div role="group" aria-label={text.title} className="flex gap-6 border-b border-bambu-dark-tertiary">
      {([{ value: 'contacts', allowed: canReadContacts, query: contacts }, { value: 'articles', allowed: canReadArticles, query: articles }] as const)
        .filter((tab) => tab.allowed).map((tab) => <button key={tab.value} type="button" aria-label={text[tab.value]} aria-pressed={kind === tab.value}
          className={'inline-flex items-center gap-2 border-b-2 px-2 pb-3 pt-1 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green ' + (kind === tab.value ? 'border-bambu-green font-semibold text-white' : 'border-transparent text-bambu-gray hover:text-white')}
          onClick={() => setChosenKind(tab.value)}>{text[tab.value]}<span aria-hidden className="font-normal tabular-nums text-bambu-gray">{tab.query.data?.length ?? '—'}</span></button>)}
    </div>
    <ResourceList key={kind} connection={connection} kind={kind} resources={kind === 'contacts' ? contacts : articles} />
  </div>;
}

function ResourceList({ connection, kind, resources }: { connection: LexwareConnection; kind: LexwareResourceKind; resources: UseQueryResult<LexwareResource[], Error> }) {
  const { hasPermission } = useAuth();
  const { text, locale } = useLexwareMessages();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<number[]>([]);
  const [review, setReview] = useState<LexwareResource[] | null>(null);
  const canCreateCustomers = kind === 'contacts' && hasPermission('customers:manage');
  const rows = resources.data ?? [];
  const isLinked = (row: LexwareResource) => kind === 'contacts' ? row.customer_id !== null : row.article_id !== null;
  const selectable = (row: LexwareResource) => !row.archived && !isLinked(row);
  const selection = rows.filter((row) => selected.includes(row.id) && selectable(row));
  const filtered = rows.filter((row) => (
    (row.name + ' ' + (row.number ?? '') + ' ' + row.external_id).toLocaleLowerCase(locale).includes(search.toLocaleLowerCase(locale))
    && (filter === 'all' || filter === 'archived' && row.archived || filter === 'linked' && isLinked(row) || filter === 'new' && selectable(row))
  ));
  const pageOffset = Math.min(offset, Math.max(0, Math.ceil(filtered.length / 25) - 1) * 25);
  const page = filtered.slice(pageOffset, pageOffset + 25);
  const pageSelectable = page.filter(selectable).map((row) => row.id);
  const pageSelected = pageSelectable.filter((id) => selected.includes(id));

  return <>
    <section className="min-w-0 space-y-4" aria-label={kind === 'contacts' ? text.contacts : text.articles}>
      <div className="flex flex-wrap items-end gap-3">
        <div className="relative w-full sm:max-w-xs">
          <Search className="pointer-events-none absolute bottom-3 left-3 h-4 w-4 text-bambu-gray" aria-hidden />
          <TextField type="search" label={text.search} value={search} className="pl-9" onValueChange={(value) => { setSearch(value); setOffset(0); }} />
        </div>
        <div className="w-full sm:w-56"><Select label={text.filter} value={filter} options={[
          { value: 'all', label: text.all }, { value: 'new', label: text.new }, { value: 'linked', label: text.linked }, { value: 'archived', label: text.archived },
        ]} onValueChange={(value) => { setFilter(value); setOffset(0); }} /></div>
      </div>
      {resources.isPending && <p role="status" className="py-8 text-center text-sm text-bambu-gray">{text.loading}</p>}
      {resources.isError && <div role="alert" className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm"><p>{lexwareError(resources.error, text)}</p><p className="text-bambu-gray">{text.stale}</p>
        <Button variant="secondary" size="sm" onClick={() => void resources.refetch()}>{text.retry}</Button></div>}
      {resources.isSuccess && rows.length === 0 && <p className="rounded-lg border border-dashed border-bambu-dark-tertiary px-4 py-10 text-center text-sm text-bambu-gray">{text.noResources}</p>}
      {rows.length > 0 && filtered.length === 0 && <p className="py-10 text-center text-sm text-bambu-gray">{text.noMatches}</p>}
      {page.length > 0 && <div className="overflow-x-auto rounded-lg border border-bambu-dark-tertiary">
        <table className="w-full min-w-[680px] text-left text-sm">
          <thead className={tableHeaderClass}><tr className={tableHeaderRowClass}>
            {canCreateCustomers && <th scope="col" className="w-12 px-4 py-1"><Checkbox ariaLabel={text.selectPage} disabled={!pageSelectable.length}
              checked={pageSelectable.length > 0 && pageSelected.length === pageSelectable.length} indeterminate={pageSelected.length > 0 && pageSelected.length < pageSelectable.length}
              onCheckedChange={(checked) => setSelected((ids) => checked ? [...new Set([...ids, ...pageSelectable])] : ids.filter((id) => !pageSelectable.includes(id)))} /></th>}
            <th scope="col" className={tableHeaderCellClass + ' w-40 whitespace-nowrap'}>{text.sourceNumber}</th>
            <th scope="col" className={tableHeaderCellClass}>{text.recordName}</th>
            <th scope="col" className={tableHeaderCellClass + ' w-[30%]'}>{text.filter}</th>
            <th scope="col" className={tableHeaderActionCellClass + ' w-36'}>{text.actions}</th>
          </tr></thead>
          <tbody>{page.map((row) => <tr key={row.id} className={'border-b border-bambu-dark-tertiary/60 transition-colors last:border-b-0 ' + (selection.some((item) => item.id === row.id) ? 'bg-bambu-green/10' : 'hover:bg-bambu-dark-tertiary/20')}>
            {canCreateCustomers && <td className="px-4 py-3"><Checkbox ariaLabel={text.select + ': ' + row.name} disabled={!selectable(row)} checked={selection.some((item) => item.id === row.id)}
              onCheckedChange={(checked) => setSelected((ids) => checked ? [...new Set([...ids, row.id])] : ids.filter((id) => id !== row.id))} /></td>}
            <td className="px-4 py-4 tabular-nums text-bambu-gray-light">{row.number || '—'}</td>
            <td className="max-w-sm px-4 py-4"><p className="break-words font-medium text-white">{row.name}</p>
              <p className="mt-1 text-xs text-bambu-gray" title={text.externalId + ': ' + row.external_id}>{text.updated}: {formatLexwareDate(row.updated_at, locale, text.never)}</p></td>
            <td className="px-4 py-4">{row.archived ? <span className="inline-flex items-center gap-1.5 text-bambu-gray"><Archive className="h-4 w-4" aria-hidden />{text.archived}</span>
              : isLinked(row) ? <span className="inline-flex items-center gap-1.5 text-bambu-gray-light"><Link2 className="h-4 w-4" aria-hidden />{text.linked}</span>
                : <span className="inline-flex rounded bg-sky-500/10 px-2 py-1 text-xs font-medium text-sky-300">{text.new}</span>}</td>
            <td className="px-4 py-4 text-right"><button type="button" aria-label={text.review + ': ' + row.name} aria-haspopup="dialog"
              className="inline-flex min-h-10 items-center justify-end gap-2 rounded px-1 font-medium text-bambu-green hover:text-bambu-green-light focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green"
              onClick={() => setReview([row])}>{text.previewAction}<ExternalLink className="h-3.5 w-3.5" aria-hidden /></button></td>
          </tr>)}</tbody>
        </table>
      </div>}
      {canCreateCustomers && rows.length > 0 && <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-bambu-dark-tertiary px-4 py-3">
        <div className="flex items-center gap-3 text-sm"><span className="tabular-nums">{selection.length} {text.selected}</span>
          {selection.length > 0 && <Button size="sm" variant="ghost" onClick={() => setSelected([])}>{text.clearSelection}</Button>}</div>
        <p className="flex items-center gap-2 text-xs text-bambu-gray" title={text.batchHelp}><ShieldCheck className="h-4 w-4" aria-hidden />{text.approvalNote}</p>
        <Button disabled={!selection.length} aria-haspopup="dialog" onClick={() => setReview(selection)}>{text.reviewSelected} ({selection.length})<ArrowRight className="h-4 w-4" aria-hidden /></Button>
      </div>}
      {filtered.length > 25 && <div className="flex items-center justify-end gap-3 text-sm text-bambu-gray">
        <span className="tabular-nums">{pageOffset + 1}–{Math.min(pageOffset + 25, filtered.length)} / {filtered.length}</span>
        <Button variant="secondary" size="sm" disabled={!pageOffset} onClick={() => setOffset(Math.max(0, pageOffset - 25))}>{text.previous}</Button>
        <Button variant="secondary" size="sm" disabled={pageOffset + 25 >= filtered.length} onClick={() => setOffset(pageOffset + 25)}>{text.next}</Button>
      </div>}
    </section>
    {review && <LexwareImportReview connection={connection} kind={kind} resources={review}
      onClose={() => setReview(null)} onImported={() => { setReview(null); setSelected([]); }} />}
  </>;
}
