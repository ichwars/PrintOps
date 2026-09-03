import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { lexwareDocumentsApi } from '../api/client/lexware-documents';
import { Button } from '../components/Button';
import { LexwareDocumentDetail } from '../components/lexware-documents/LexwareDocumentDetail';
import { displayMoney, documentCodeLabel, useLexwareDocumentLabels } from '../components/lexware-documents/labels';
import { Select, TextField } from '../components/ui';
import { useAuth } from '../contexts/AuthContext';

const types = ['invoice', 'creditnote', 'quotation', 'orderconfirmation', 'salesinvoice', 'salescreditnote', 'purchaseinvoice', 'purchasecreditnote', 'downpaymentinvoice', 'deliverynote'];

export default function LexwareDocumentsPage() {
  const labels = useLexwareDocumentLabels();
  const { hasPermission } = useAuth();
  const canRead = hasPermission('commercial_documents:read');
  const canFinance = hasPermission('payments:read');
  const canLink = canFinance && hasPermission('commercial_documents:draft');
  const [search, setSearch] = useState('');
  const [voucherType, setVoucherType] = useState('');
  const [profile, setProfile] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const filters = { search, voucher_type: voucherType, business_profile_id: profile ? Number(profile) : undefined, offset, limit: 25 };
  const profiles = useQuery({ queryKey: ['business-profile-options'], queryFn: () => api.getBusinessProfileOptions(), enabled: canRead });
  const listing = useQuery({ queryKey: ['lexware-documents', 'list', filters, canFinance], queryFn: () => lexwareDocumentsApi.list(filters), enabled: canRead });
  const finance = useQuery({ queryKey: ['lexware-finance', profile], queryFn: () => lexwareDocumentsApi.finance({ business_profile_id: filters.business_profile_id }), enabled: canRead && canFinance });
  const detail = useQuery({ queryKey: ['lexware-documents', 'detail', selected, canFinance], queryFn: () => lexwareDocumentsApi.detail(selected!), enabled: canRead && selected !== null });
  function resetFilter(action: () => void) { action(); setOffset(0); setSelected(null); }
  async function reload() { await Promise.all([listing.refetch(), ...(canFinance ? [finance.refetch()] : []), ...(selected !== null ? [detail.refetch()] : [])]); }
  if (!canRead) return <p className="p-6">{labels.denied}</p>;
  return <div className="p-4 md:p-6 space-y-6 text-white">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-2xl font-semibold">{labels.title}</h1><p className="mt-1 text-bambu-gray-light">{labels.description}</p></div>
      <Button variant="secondary" onClick={() => void reload()} loading={listing.isFetching}><RefreshCw size={16} />{labels.refresh}</Button>
    </div>
    <Select
      className="max-w-sm"
      label={labels.profile}
      value={profile}
      options={[
        { value: '', label: labels.allProfiles },
        ...(profiles.data ?? []).map(item => ({ value: String(item.id), label: item.name })),
      ]}
      onValueChange={value => resetFilter(() => setProfile(value))}
    />
    {canFinance && <section className="rounded-xl border border-bambu-gray/30 bg-bambu-dark-secondary p-5 space-y-3" aria-label={labels.financeTitle}>
      <h2 className="font-semibold text-lg">{labels.financeTitle}</h2><p className="text-sm text-bambu-gray-light">{labels.financeNote}</p>
      {finance.isLoading && <p role="status">{labels.loading}</p>}
      {finance.isError && <p role="alert">{labels.error} <Button variant="ghost" onClick={() => void finance.refetch()}>{labels.retry}</Button></p>}
      {finance.data && <>
        {finance.data.totals.map(total => <div key={total.currency} className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg bg-bambu-dark p-4"><p>{labels.receivables}</p><p className="text-2xl">{total.receivables} {total.currency}</p><p className="text-sm text-amber-300">{labels.overdue}: {total.overdue_receivables} {total.currency}</p></div>
          <div className="rounded-lg bg-bambu-dark p-4"><p>{labels.payables}</p><p className="text-2xl">{total.payables} {total.currency}</p><p className="text-sm text-amber-300">{labels.overdue}: {total.overdue_payables} {total.currency}</p></div>
        </div>)}
        <p className="text-sm">{labels.linked}: {finance.data.linked_count} · {labels.unknownCount}: {finance.data.unknown_count} · {labels.excluded}: {finance.data.excluded_count}</p>
        <p className="text-sm text-bambu-gray-light">{labels.credits}</p>
        {finance.data.stale_connection_count > 0 && <p className="text-amber-300" role="status">{labels.stale}</p>}
      </>}
    </section>}
    <div className="flex flex-wrap items-end gap-3">
      <TextField aria-label={labels.search} className="min-w-48" placeholder={labels.search} value={search} onValueChange={value => resetFilter(() => setSearch(value))} />
      <Select
        className="w-full sm:w-64"
        ariaLabel={labels.type}
        value={voucherType}
        options={[
          { value: '', label: labels.allTypes },
          ...types.map(type => ({ value: type, label: documentCodeLabel(labels, 'type', type) })),
        ]}
        onValueChange={value => resetFilter(() => setVoucherType(value))}
      />
    </div>
    {listing.isLoading && <p role="status">{labels.loading}</p>}
    {listing.isError && <p role="alert">{labels.error} <Button variant="ghost" onClick={() => void listing.refetch()}>{labels.retry}</Button></p>}
    {listing.data?.items.length === 0 && <p className="rounded-lg bg-bambu-dark-secondary p-6">{labels.empty}</p>}
    {!!listing.data?.items.length && <div className="overflow-x-auto rounded-xl border border-bambu-gray/30"><table className="w-full text-left text-sm">
      <thead className="bg-bambu-dark-secondary"><tr>{[labels.number, labels.type, labels.contact, labels.date, labels.status, ...(canFinance ? [labels.open] : []), labels.details].map(label => <th className="p-3" key={label}>{label}</th>)}</tr></thead>
      <tbody>{listing.data.items.map(document => <tr className="border-t border-bambu-gray/20" key={document.id}>
        <td className="p-3">{document.voucher_number || '—'}<small className="block text-bambu-gray-light">Lexware · {document.company_name}</small>{document.local_document_id && <small>PrintOps #{document.local_document_id}</small>}</td>
        <td className="p-3">{documentCodeLabel(labels, 'type', document.voucher_type)}{!document.supported && <small className="block text-amber-300">{labels.unsupported}</small>}</td>
        <td className="p-3">{document.contact_name || '—'}</td><td className="p-3 whitespace-nowrap">{document.voucher_date || '—'}</td>
        <td className="p-3">{documentCodeLabel(labels, 'status', document.voucher_status)}{document.archived && <small className="block">{labels.archived}</small>}{!document.connection_enabled && <small className="block text-amber-300">{labels.stale}</small>}{!document.in_latest_sync && <small className="block text-amber-300">{labels.missing}</small>}</td>
        {canFinance && <td className="p-3 whitespace-nowrap">{document.finance?.payment_state === 'not_applicable' ? labels.notApplicable : displayMoney(document.finance?.open_amount, document.finance?.currency || '', labels.unknown)}</td>}
        <td className="p-3"><Button variant="secondary" size="sm" onClick={() => setSelected(document.id)}>{labels.details}</Button></td>
      </tr>)}</tbody>
    </table></div>}
    {listing.data && <div className="flex gap-3 items-center"><Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>{labels.previous}</Button><span>{labels.count}: {listing.data.total}</span><Button variant="secondary" disabled={offset + 25 >= listing.data.total} onClick={() => setOffset(offset + 25)}>{labels.next}</Button></div>}
    {selected !== null && detail.isLoading && <p role="status">{labels.loading}</p>}
    {selected !== null && detail.isError && <p role="alert">{labels.error} <Button variant="ghost" onClick={() => void detail.refetch()}>{labels.retry}</Button></p>}
    {selected !== null && detail.data && <LexwareDocumentDetail key={detail.data.id} document={detail.data} canFinance={canFinance} canLink={canLink} onClose={() => setSelected(null)} />}
  </div>;
}
