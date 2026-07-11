import { AlertTriangle, Pencil, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ApiError, type BusinessProfileOption, type CustomerDetail } from '../../api/client';
import { Button } from '../Button';
import { useModalFocusLifecycle } from '../../hooks/useModalFocusLifecycle';

interface Props {
  customer: CustomerDetail;
  profiles: BusinessProfileOption[];
  selectedProfileId: number;
  canManage: boolean;
  onClose: () => void;
  onEdit: () => void;
  onDelete: () => void;
  loadError?: Error | null;
  onRetryLoad?: () => void;
}

const value = (input: string | number | null | undefined) => input === null || input === undefined || input === '' ? '-' : String(input);

export function CustomerDetailsModal({ customer, profiles, selectedProfileId, canManage, onClose, onEdit, onDelete, loadError = null, onRetryLoad }: Props) {
  const { t, i18n } = useTranslation();
  const profileName = (id: number) => profiles.find((profile) => profile.id === id)?.name ?? `#${id}`;
  const accounts = [...customer.accounts].sort((a, b) => Number(b.business_profile_id === selectedProfileId) - Number(a.business_profile_id === selectedProfileId));
  const date = (input: string) => new Intl.DateTimeFormat(i18n.language, { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(input));
  const loadErrorMessage = loadError instanceof ApiError && loadError.code === 'not_found'
    ? t('orderUiNotFound')
    : loadError?.message;

  const { dialogRef, onKeyDown } = useModalFocusLifecycle<HTMLElement>({ onClose });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3" role="presentation">
      <section ref={dialogRef} onKeyDown={onKeyDown} role="dialog" aria-modal="true" aria-labelledby="customer-details-title" className="flex max-h-[calc(100vh-1.5rem)] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary shadow-xl">
        <header className="flex items-start justify-between gap-4 border-b border-bambu-dark-tertiary px-5 py-4">
          <div>
            <h2 id="customer-details-title" className="text-lg font-semibold text-white">{t('orders.customerDetails.title')}</h2>
            <p className="text-sm text-bambu-gray">{customer.display_name}</p>
          </div>
          <div className="flex items-center gap-2">
            {canManage && <Button size="sm" onClick={onEdit}><Pencil className="mr-2 h-4 w-4" />{t('orders.customers.editCustomer')}</Button>}
            {canManage && <Button size="sm" variant="danger" onClick={onDelete}><Trash2 className="mr-2 h-4 w-4" />{t('orders.customers.deleteCustomer')}</Button>}
            <button type="button" onClick={onClose} title={t('common.close')} aria-label={t('common.close')} className="rounded p-2 text-bambu-gray hover:bg-bambu-dark hover:text-white"><X className="h-5 w-5" /></button>
          </div>
        </header>
        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-4 text-sm">
          {loadErrorMessage && <div role="alert" className="flex items-start gap-2 border border-amber-500/40 bg-amber-500/10 p-3 text-amber-100"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><span className="flex-1">{loadErrorMessage}</span>{onRetryLoad && <Button size="sm" variant="secondary" onClick={onRetryLoad}>{t('common.retry')}</Button>}</div>}
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Info label={t('orders.customerEditor.kind')} text={t(`orders.customerEditor.${customer.kind}`)} />
            <Info label={t('common.status')} text={t(`orders.status.${customer.status}`)} />
            <Info label={t('orders.customerEditor.locale')} text={customer.preferred_locale} />
            <Info label={t('orders.customerEditor.displayName')} text={customer.display_name} />
            {customer.company_name && <Info label={t('orders.customerEditor.companyName')} text={customer.company_name} />}
            {customer.first_name && <Info label={t('orders.customerEditor.firstName')} text={customer.first_name} />}
            {customer.last_name && <Info label={t('orders.customerEditor.lastName')} text={customer.last_name} />}
          </section>

          <Aggregate title={t('orders.customerEditor.accounts')} empty={accounts.length === 0}>
            {accounts.map((account) => <div key={account.id} className="border-t border-bambu-dark-tertiary py-3 first:border-0">
              <strong className="text-white">{profileName(account.business_profile_id)}</strong>
              <p className="mt-1 text-bambu-gray">{value(account.number)} · {account.preferred_currency} · {t('orders.customerDetails.paymentDays', { count: account.payment_term_days })} · {value(account.delivery_terms)} · {account.discount_percent}% · {account.is_active ? t('orders.status.active') : t('orders.status.inactive')}</p>
            </div>)}
          </Aggregate>

          <Aggregate title={t('orders.customerEditor.contacts')} empty={customer.contacts.length === 0}>
            {customer.contacts.map((contact) => <div key={contact.id} className="border-t border-bambu-dark-tertiary py-3 first:border-0">
              <strong className="text-white">{[contact.salutation, contact.first_name, contact.last_name].filter(Boolean).join(' ') || '-'}</strong>
              <p className="text-bambu-gray"><span>{value(contact.role)}</span> · <span>{value(contact.email)}</span> · <span>{value(contact.phone)}</span></p>
              <p className="text-xs text-bambu-gray">{contact.is_primary ? t('orders.customerEditor.primaryContact') : ''}{contact.is_primary && contact.include_on_documents ? ' · ' : ''}{contact.include_on_documents ? t('orders.customerEditor.includeDocuments') : ''}</p>
            </div>)}
          </Aggregate>

          <Aggregate title={t('orders.customerEditor.addresses')} empty={customer.addresses.length === 0}>
            <div className="grid gap-4 sm:grid-cols-2">
              {customer.addresses.map((address) => <address key={address.id} className="not-italic text-bambu-gray">
                <strong className="text-white">{t(`orders.customerEditor.addressKind.${address.kind}`)}{address.label ? ` · ${address.label}` : ''}</strong>
                {address.additional && <span className="block">{address.additional}</span>}
                <span className="block">{address.street}</span>{address.street_2 && <span className="block">{address.street_2}</span>}
                <span className="block">{address.postal_code} {address.city}{address.region ? `, ${address.region}` : ''}</span>
                <span className="block">{address.country_code}{address.is_default ? ` · ${t('orders.customerEditor.defaultAddress')}` : ''}</span>
              </address>)}
            </div>
          </Aggregate>

          <Aggregate title={t('orders.customerEditor.taxIdentifiers')} empty={customer.tax_identifiers.length === 0}>
            {customer.tax_identifiers.map((tax) => <p key={tax.id} className="border-t border-bambu-dark-tertiary py-3 text-bambu-gray first:border-0"><strong className="text-white">{tax.kind}</strong> · <span>{tax.value}</span> · {value(tax.country_code)} · {t(`orderMessages.taxValidationStatus.${tax.validation_status}`)}</p>)}
          </Aggregate>

          <Aggregate title={t('orders.customerEditor.tags')} empty={customer.tags.length === 0}>
            <div className="flex flex-wrap gap-2">{customer.tags.map((tag) => <span key={tag} className="rounded bg-bambu-dark px-2 py-1 text-xs text-bambu-gray-light">{tag}</span>)}</div>
          </Aggregate>

          {customer.notes && <Aggregate title={t('orders.customerEditor.notes')}><p className="whitespace-pre-wrap text-bambu-gray-light">{customer.notes}</p></Aggregate>}
          <footer className="flex flex-wrap gap-4 border-t border-bambu-dark-tertiary pt-4 text-xs text-bambu-gray">
            <span>{t('orders.customerDetails.created', { date: date(customer.created_at) })}</span>
            <span>{t('orders.customerDetails.updated', { date: date(customer.updated_at) })}</span>
          </footer>
        </div>
      </section>
    </div>
  );
}

function Info({ label, text }: { label: string; text: string }) {
  return <div><span className="block text-xs text-bambu-gray">{label}</span><span className="text-white">{text}</span></div>;
}

function Aggregate({ title, empty = false, children }: { title: string; empty?: boolean; children?: React.ReactNode }) {
  return <section><h3 className="mb-2 font-medium text-white">{title}</h3>{empty ? <p className="text-bambu-gray">-</p> : children}</section>;
}
