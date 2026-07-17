import { cloneElement, isValidElement, useEffect, useId, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Plus, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  ApiError,
  type BusinessProfileOption,
  type CustomerAccount,
  type CustomerAddress,
  type CustomerContact,
  type CustomerCreate,
  type CustomerDetail,
  type CustomerTaxIdentifier,
  type CustomerUpdate,
} from '../../api/client';
import {
  isIsoCountryCode,
  isIsoCurrencyCode,
  normalizeNfkcCasefold,
} from '../../lib/orderMasterDataValidation';
import { normalizeOrderTags } from '../../lib/orderTagNormalization';
import { Button } from '../Button';
import { NumberField , Checkbox, LegacySelect, TextArea, TextField} from '../ui';
import { useModalFocusLifecycle } from '../../hooks/useModalFocusLifecycle';

interface Props {
  customer: CustomerDetail | null;
  profiles: BusinessProfileOption[];
  selectedProfileId: number;
  isSubmitting: boolean;
  onClose: () => void;
  onSubmit: (data: CustomerCreate | CustomerUpdate) => Promise<void>;
  onReloadCurrent: () => Promise<CustomerDetail>;
  onReloadAccepted?: (customer: CustomerDetail) => Promise<void>;
  loadError?: Error | null;
  onRetryLoad?: () => void;
}

type ClientRow<T> = T & { _clientKey: string };
type Draft = Omit<CustomerCreate, 'accounts' | 'contacts' | 'addresses' | 'tax_identifiers'> & {
  accounts: ClientRow<CustomerAccount>[];
  contacts: ClientRow<CustomerContact>[];
  addresses: ClientRow<CustomerAddress>[];
  tax_identifiers: ClientRow<CustomerTaxIdentifier>[];
};
type FieldErrors = Record<string, string>;
type Translate = (key: string, options?: Record<string, unknown>) => string;
const inputClass = 'mt-1 w-full rounded-md border border-bambu-dark-tertiary bg-bambu-dark px-3 py-2 text-sm text-white focus:border-bambu-green focus:outline-none';
const numberInputClass = 'w-full rounded-md border border-bambu-dark-tertiary bg-bambu-dark px-3 py-2 text-sm text-white focus:border-bambu-green focus:outline-none';
const customerKinds = ['company', 'person'] as const;
const customerStatuses = ['active', 'inactive', 'blocked'] as const;
const addressKinds = ['billing', 'delivery', 'other'] as const;
const taxValidationStatuses = ['unchecked', 'valid', 'invalid'] as const;
const topLevelFields = new Set(['kind', 'display_name', 'company_name', 'first_name', 'last_name', 'status', 'preferred_locale', 'notes', 'tags']);
const nestedFields: Record<string, ReadonlySet<string>> = {
  accounts: new Set(['business_profile_id', 'number', 'preferred_currency', 'payment_term_days', 'delivery_terms', 'discount_percent', 'is_active']),
  contacts: new Set(['salutation', 'first_name', 'last_name', 'role', 'email', 'phone', 'is_primary', 'include_on_documents']),
  addresses: new Set(['kind', 'label', 'additional', 'street', 'street_2', 'postal_code', 'city', 'region', 'country_code', 'is_default']),
  tax_identifiers: new Set(['kind', 'value', 'country_code', 'validation_status']),
};

const clean = (value: string) => value.trim() || null;
let clientKeySequence = 0;
const withClientKey = <T,>(item: T, key?: string): ClientRow<T> => ({ ...item, _clientKey: key ?? `new-${++clientKeySequence}` });
const emptyContact = () => withClientKey<CustomerContact>({ salutation: null, first_name: null, last_name: null, role: null, email: null, phone: null, is_primary: false, include_on_documents: false });
const emptyAddress = () => withClientKey<CustomerAddress>({ kind: 'billing', label: null, additional: null, street: '', street_2: null, postal_code: '', city: '', region: null, country_code: 'DE', is_default: false });
const emptyTax = () => withClientKey<CustomerTaxIdentifier>({ kind: 'vat', value: '', country_code: 'DE', validation_status: 'unchecked' });
const fromResponse = <T extends { id: number }>(kind: string, item: T): ClientRow<Omit<T, 'id'>> => {
  const { id, ...value } = item;
  return withClientKey(value, `${kind}-${id}`);
};
const withoutClientKey = <T extends { _clientKey: string }>(item: T): Omit<T, '_clientKey'> => {
  const value = { ...item };
  delete (value as { _clientKey?: string })._clientKey;
  return value;
};

function asDraft(customer: CustomerDetail | null, selectedProfileId: number, profiles: BusinessProfileOption[]): Draft {
  if (!customer) {
    const profile = profiles.find((item) => item.id === selectedProfileId);
    return {
      kind: 'person', display_name: '', company_name: null, first_name: null, last_name: null,
      status: 'active', preferred_locale: profile?.default_locale ?? 'en', notes: null,
      accounts: [withClientKey({ business_profile_id: selectedProfileId, number: null, preferred_currency: profile?.default_currency ?? 'EUR', payment_term_days: 14, delivery_terms: null, discount_percent: '0.00', is_active: true })],
      contacts: [], addresses: [], tax_identifiers: [], tags: [],
    };
  }
  return {
    kind: customer.kind, display_name: customer.display_name, company_name: customer.company_name,
    first_name: customer.first_name, last_name: customer.last_name, status: customer.status,
    preferred_locale: customer.preferred_locale, notes: customer.notes,
    accounts: customer.accounts.map((item) => fromResponse('account', item)),
    contacts: customer.contacts.map((item) => fromResponse('contact', item)),
    addresses: customer.addresses.map((item) => fromResponse('address', item)),
    tax_identifiers: customer.tax_identifiers.map((item) => fromResponse('tax', item)),
    tags: customer.tags,
  };
}

function normalize(draft: Draft): CustomerCreate {
  return {
    ...draft,
    display_name: draft.display_name.trim(),
    company_name: clean(draft.company_name ?? ''), first_name: clean(draft.first_name ?? ''), last_name: clean(draft.last_name ?? ''), notes: clean(draft.notes ?? ''),
    accounts: draft.accounts.map((account) => ({ ...withoutClientKey(account), number: clean(account.number ?? ''), delivery_terms: clean(account.delivery_terms ?? '') })),
    contacts: draft.contacts.map((contact) => ({ ...withoutClientKey(contact), salutation: clean(contact.salutation ?? ''), first_name: clean(contact.first_name ?? ''), last_name: clean(contact.last_name ?? ''), role: clean(contact.role ?? ''), email: clean(contact.email ?? ''), phone: clean(contact.phone ?? '') })),
    addresses: draft.addresses.map((address) => ({ ...withoutClientKey(address), label: clean(address.label ?? ''), additional: clean(address.additional ?? ''), street: address.street.trim(), street_2: clean(address.street_2 ?? ''), postal_code: address.postal_code.trim(), city: address.city.trim(), region: clean(address.region ?? ''), country_code: address.country_code.trim().toUpperCase() })),
    tax_identifiers: draft.tax_identifiers.map((tax) => ({ ...withoutClientKey(tax), kind: tax.kind.trim(), value: tax.value.trim(), country_code: clean(tax.country_code ?? '')?.toUpperCase() ?? null })),
    tags: normalizeOrderTags(draft.tags ?? []),
  };
}

function isKnownFieldPath(path: string): boolean {
  if (topLevelFields.has(path)) return true;
  if (/^tags\.\d+$/.test(path)) return true;
  const match = /^(accounts|contacts|addresses|tax_identifiers)\.(\d+)\.([a-z_]+)$/.exec(path);
  return match !== null && nestedFields[match[1]]?.has(match[3]) === true;
}

function validateCustomer(draft: CustomerCreate, t: Translate): FieldErrors {
  const errors: FieldErrors = {};
  const add = (path: string, message: string) => { if (!errors[path]) errors[path] = message; };
  const text = (path: string, value: string | null | undefined, maximum: number, minimum = 0) => {
    const length = value?.length ?? 0;
    if (minimum > 0 && length < minimum) add(path, t('orderMessages.validation.required'));
    else if (length > maximum) add(path, t('orderMessages.validation.maxCharacters', { count: maximum }));
  };
  const optionalText = (path: string, value: string | null | undefined, maximum: number) => {
    if (value) text(path, value, maximum);
  };

  text('display_name', draft.display_name, 255, 1);
  if (!customerKinds.includes(draft.kind)) add('kind', t('orderMessages.validation.customerKind'));
  if (draft.kind === 'company') text('company_name', draft.company_name, 255, 1);
  else {
    text('first_name', draft.first_name, 120, 1);
    text('last_name', draft.last_name, 120, 1);
  }
  optionalText('company_name', draft.company_name, 255);
  optionalText('first_name', draft.first_name, 120);
  optionalText('last_name', draft.last_name, 120);
  if (!draft.status) add('status', t('orderMessages.validation.required'));
  else if (!customerStatuses.includes(draft.status)) add('status', t('orderMessages.validation.customerStatus'));
  text('preferred_locale', draft.preferred_locale, 16, 2);
  optionalText('notes', draft.notes, 10000);

  if (draft.accounts.length === 0) add('accounts', t('orderMessages.validation.accountRequired'));
  const profileIndexes = new Map<number, number>();
  draft.accounts.forEach((account, index) => {
    const path = (field: string) => `accounts.${index}.${field}`;
    if (!Number.isInteger(account.business_profile_id) || account.business_profile_id <= 0) add(path('business_profile_id'), t('orderMessages.validation.businessProfile'));
    const firstProfile = profileIndexes.get(account.business_profile_id);
    if (firstProfile !== undefined) {
      add(path('business_profile_id'), t('orderMessages.validation.duplicateAccountProfile'));
      add(`accounts.${firstProfile}.business_profile_id`, t('orderMessages.validation.duplicateAccountProfile'));
    } else profileIndexes.set(account.business_profile_id, index);
    optionalText(path('number'), account.number, 50);
    if (!account.preferred_currency) add(path('preferred_currency'), t('orderMessages.validation.required'));
    else if (!isIsoCurrencyCode(account.preferred_currency)) add(path('preferred_currency'), t('orderMessages.validation.currency'));
    if (!Number.isInteger(account.payment_term_days) || (account.payment_term_days ?? 0) < 0 || (account.payment_term_days ?? 0) > 365) add(path('payment_term_days'), t('orderMessages.validation.range', { min: 0, max: 365 }));
    optionalText(path('delivery_terms'), account.delivery_terms, 1000);
    const discount = Number(account.discount_percent);
    if (!Number.isFinite(discount) || discount < 0 || discount > 100) add(path('discount_percent'), t('orderMessages.validation.range', { min: 0, max: 100 }));
    else if (!/^\d+(?:\.\d{1,2})?$/.test(account.discount_percent ?? '')) add(path('discount_percent'), t('orderMessages.validation.twoDecimalPlaces'));
  });

  (draft.contacts ?? []).forEach((contact, index) => {
    const path = (field: string) => `contacts.${index}.${field}`;
    optionalText(path('salutation'), contact.salutation, 32);
    optionalText(path('first_name'), contact.first_name, 120);
    optionalText(path('last_name'), contact.last_name, 120);
    optionalText(path('role'), contact.role, 120);
    optionalText(path('email'), contact.email, 255);
    optionalText(path('phone'), contact.phone, 64);
  });
  const primaryContacts = (draft.contacts ?? []).map((contact, index) => contact.is_primary ? index : -1).filter((index) => index >= 0);
  if (primaryContacts.length > 1) primaryContacts.forEach((index) => add(`contacts.${index}.is_primary`, t('orderUi.singlePrimaryContact')));

  const defaultAddresses = new Map<string, number>();
  (draft.addresses ?? []).forEach((address, index) => {
    const path = (field: string) => `addresses.${index}.${field}`;
    if (!addressKinds.includes(address.kind)) add(path('kind'), t('orderMessages.validation.addressKind'));
    optionalText(path('label'), address.label, 100);
    optionalText(path('additional'), address.additional, 255);
    text(path('street'), address.street, 255, 1);
    optionalText(path('street_2'), address.street_2, 255);
    text(path('postal_code'), address.postal_code, 32, 1);
    text(path('city'), address.city, 120, 1);
    optionalText(path('region'), address.region, 120);
    if (!address.country_code) add(path('country_code'), t('orderMessages.validation.required'));
    else if (!isIsoCountryCode(address.country_code)) add(path('country_code'), t('orderMessages.validation.country'));
    if (address.is_default) {
      const firstDefault = defaultAddresses.get(address.kind);
      if (firstDefault !== undefined) {
        add(path('is_default'), t('orderMessages.validation.duplicateDefaultAddress'));
        add(`addresses.${firstDefault}.is_default`, t('orderMessages.validation.duplicateDefaultAddress'));
      } else defaultAddresses.set(address.kind, index);
    }
  });

  const taxIdentifiers = new Map<string, Map<string, number>>();
  (draft.tax_identifiers ?? []).forEach((tax, index) => {
    const path = (field: string) => `tax_identifiers.${index}.${field}`;
    text(path('kind'), tax.kind, 32, 1);
    text(path('value'), tax.value, 64, 1);
    if (tax.country_code && !isIsoCountryCode(tax.country_code)) add(path('country_code'), t('orderMessages.validation.country'));
    if (!taxValidationStatuses.includes(tax.validation_status ?? 'unchecked')) add(path('validation_status'), t('orderMessages.validation.taxValidationStatus'));
    const normalizedKind = normalizeNfkcCasefold(tax.kind);
    const normalizedValue = normalizeNfkcCasefold(tax.value);
    if (normalizedKind.length > 32) add(path('kind'), t('orderMessages.validation.maxCharacters', { count: 32 }));
    const valuesForKind = taxIdentifiers.get(normalizedKind);
    const firstTax = valuesForKind?.get(normalizedValue);
    if (tax.kind && tax.value && firstTax !== undefined) {
      add(path('value'), t('orderMessages.validation.duplicateTaxIdentifier'));
      add(`tax_identifiers.${firstTax}.value`, t('orderMessages.validation.duplicateTaxIdentifier'));
    } else if (tax.kind && tax.value) {
      const values = valuesForKind ?? new Map<string, number>();
      values.set(normalizedValue, index);
      taxIdentifiers.set(normalizedKind, values);
    }
  });

  if ((draft.tags ?? []).length > 50) add('tags', t('orderMessages.validation.maxTags'));
  (draft.tags ?? []).forEach((tag) => {
    text('tags', tag, 100, 1);
    if (new TextEncoder().encode(normalizeNfkcCasefold(tag)).length > 512) {
      add('tags', t('orderMessages.validation.normalizedTag'));
    }
  });
  return errors;
}

function apiErrors(error: unknown, t: Translate, language: string): { fields: FieldErrors; message: string | null; conflict: boolean } {
  if (!(error instanceof ApiError)) return { fields: {}, message: error instanceof Error ? error.message : null, conflict: false };
  const knownKey = error.code ? ({
    resource_in_use: 'orderUi.operationBlocked',
    version_conflict: 'orderMessages.errors.customer_version_conflict',
    duplicate_business_key: 'orderUi.duplicateRecord',
    not_found: 'orderUiNotFound',
  } as Record<string, string>)[error.code] : undefined;
  if (error.status !== 422) return { fields: {}, message: knownKey ? t(knownKey) : language.startsWith('de') && error.status === 409 ? t('orderMessages.errors.conflict') : error.message, conflict: error.status === 409 };
  const fields: FieldErrors = {};
  const global: string[] = [];
  for (const issue of error.validationErrors ?? []) {
    const parts = issue.loc[0] === 'body' ? issue.loc.slice(1) : issue.loc;
    const path = parts.join('.');
    const fieldPath = /^tags\.\d+$/.test(path) ? 'tags' : path;
    const message = language.startsWith('de') ? t('orderMessages.validation.invalidField') : issue.msg;
    if (fieldPath && isKnownFieldPath(path)) fields[fieldPath] = message;
    else global.push(message);
  }
  return { fields, message: global.join('; ') || (!error.validationErrors?.length ? language.startsWith('de') ? t('orderMessages.validation.failed') : error.message : null), conflict: false };
}

export function CustomerEditorModal({ customer, profiles, selectedProfileId, isSubmitting, onClose, onSubmit, onReloadCurrent, onReloadAccepted, loadError = null, onRetryLoad }: Props) {
  const { t, i18n } = useTranslation();
  const [draft, setDraft] = useState(() => asDraft(customer, selectedProfileId, profiles));
  const [draftVersion, setDraftVersion] = useState(customer?.version);
  const [tags, setTags] = useState(() => (customer?.tags ?? []).join(', '));
  const [error, setError] = useState<unknown>(null);
  const [clientErrors, setClientErrors] = useState<FieldErrors>({});
  const [isReloading, setIsReloading] = useState(false);
  const [reloadError, setReloadError] = useState<unknown>(null);
  const reloadRequest = useRef(0);
  const mounted = useRef(true);
  const mapped = useMemo(() => apiErrors(error, t, i18n.language), [error, i18n.language, t]);
  const loadErrorMessage = useMemo(
    () => loadError ? apiErrors(loadError, t, i18n.language).message ?? loadError.message : null,
    [i18n.language, loadError, t],
  );
  const reloadErrorMessage = useMemo(
    () => reloadError !== null ? apiErrors(reloadError, t, i18n.language).message : null,
    [i18n.language, reloadError, t],
  );
  const errors = { ...mapped.fields, ...clientErrors };
  const editing = customer !== null;
  const initialFocusRef = useRef<HTMLInputElement>(null);
  const pending = isSubmitting || isReloading;
  const { dialogRef, onKeyDown } = useModalFocusLifecycle<HTMLFormElement>({ onClose, canClose: !pending, initialFocusRef });

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      reloadRequest.current += 1;
    };
  }, []);

  const patchAccount = (index: number, patch: Partial<CustomerAccount>) => setDraft((current) => ({ ...current, accounts: current.accounts.map((item, i) => i === index ? { ...item, ...patch } : item) }));
  const patchContact = (index: number, patch: Partial<CustomerContact>) => setDraft((current) => ({ ...current, contacts: (current.contacts ?? []).map((item, i) => i === index ? { ...item, ...patch } : item) }));
  const patchAddress = (index: number, patch: Partial<CustomerAddress>) => setDraft((current) => ({ ...current, addresses: (current.addresses ?? []).map((item, i) => i === index ? { ...item, ...patch } : item) }));
  const patchTax = (index: number, patch: Partial<CustomerTaxIdentifier>) => setDraft((current) => ({ ...current, tax_identifiers: (current.tax_identifiers ?? []).map((item, i) => i === index ? { ...item, ...patch } : item) }));
  const remove = <T,>(values: T[] | undefined, index: number) => (values ?? []).filter((_, i) => i !== index);

  const setPrimaryContact = (index: number, checked: boolean) => setDraft((current) => ({ ...current, contacts: (current.contacts ?? []).map((contact, i) => ({ ...contact, is_primary: i === index ? checked : checked ? false : contact.is_primary })) }));
  const setDefaultAddress = (index: number, checked: boolean) => setDraft((current) => {
    const addresses = current.addresses ?? [];
    const kind = addresses[index].kind;
    return { ...current, addresses: addresses.map((address, i) => ({ ...address, is_default: i === index ? checked : checked && address.kind === kind ? false : address.is_default })) };
  });

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const normalized = normalize({ ...draft, tags: tags.split(',') });
    const validation = validateCustomer(normalized, t);
    setClientErrors(validation);
    if (Object.keys(validation).length) return;
    setError(null);
    try {
      await onSubmit(editing ? { ...normalized, version: draftVersion! } : normalized);
    } catch (submitError) {
      setError(submitError);
    }
  };

  const reload = async () => {
    const request = ++reloadRequest.current;
    setIsReloading(true);
    setReloadError(null);
    try {
      const current = await onReloadCurrent();
      if (!mounted.current || request !== reloadRequest.current) return;
      if (onReloadAccepted) await onReloadAccepted(current);
      if (!mounted.current || request !== reloadRequest.current) return;
      setDraft(asDraft(current, selectedProfileId, profiles));
      setDraftVersion(current.version);
      setTags(current.tags.join(', '));
      setError(null);
      setClientErrors({});
    } catch (currentError) {
      if (mounted.current && request === reloadRequest.current) setReloadError(currentError);
    } finally {
      if (mounted.current && request === reloadRequest.current) setIsReloading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-3" role="presentation">
      <form ref={dialogRef} onKeyDown={onKeyDown} noValidate onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="customer-editor-title" tabIndex={-1} className="flex max-h-[calc(100vh-1.5rem)] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary shadow-xl">
        <header className="flex items-center justify-between border-b border-bambu-dark-tertiary px-5 py-4">
          <h2 id="customer-editor-title" className="text-lg font-semibold text-white">{editing ? t('orders.customerEditor.editTitle') : t('orders.customerEditor.createTitle')}</h2>
          <button type="button" disabled={pending} onClick={onClose} title={t('common.close')} aria-label={t('common.close')} className="rounded p-2 text-bambu-gray hover:bg-bambu-dark hover:text-white disabled:opacity-50"><X className="h-5 w-5" /></button>
        </header>
        <div data-testid="customer-editor-scroll-viewport" className="min-h-0 flex-1 overflow-y-auto">
          <fieldset disabled={pending} className="space-y-6 px-5 py-4">
          {loadErrorMessage && <div role="alert" className="flex items-start gap-2 border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><span className="flex-1">{loadErrorMessage}</span>{onRetryLoad && <Button type="button" size="sm" variant="secondary" onClick={onRetryLoad}>{t('common.retry')}</Button>}</div>}
          {reloadErrorMessage && <div role="alert" className="flex items-start gap-2 border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><span className="flex-1">{reloadErrorMessage}</span><Button type="button" size="sm" variant="secondary" onClick={reload}>{t('common.retry')}</Button></div>}
          {mapped.message && <div role="alert" className={`flex items-start gap-2 border p-3 text-sm ${mapped.conflict ? 'border-amber-500/40 bg-amber-500/10 text-amber-100' : 'border-red-500/40 bg-red-500/10 text-red-200'}`}><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><span className="flex-1">{mapped.message}</span>{mapped.conflict && <Button type="button" size="sm" variant="secondary" onClick={reload}>{t('orders.customerEditor.reload')}</Button>}</div>}

          <Section title={t('orders.customerEditor.identity')}>
            <div className="inline-flex rounded-md border border-bambu-dark-tertiary p-1" aria-label={t('orders.customerEditor.kind')}>
              {(['company', 'person'] as const).map((kind) => <button key={kind} type="button" aria-pressed={draft.kind === kind} onClick={() => setDraft({ ...draft, kind })} className={`rounded px-3 py-1.5 text-sm ${draft.kind === kind ? 'bg-bambu-green text-black' : 'text-bambu-gray hover:text-white'}`}>{t(`orders.customerEditor.${kind}`)}</button>)}
            </div>
            {errors.kind && <span role="alert" className="block text-xs text-red-300">{errors.kind}</span>}
            <div className="grid gap-3 md:grid-cols-2">
              <Field label={t('orders.customerEditor.displayName')} error={errors.display_name}><TextField ref={initialFocusRef} aria-label={t('orders.customerEditor.displayName')} value={draft.display_name} onChange={(e) => setDraft({ ...draft, display_name: e.target.value })} className={inputClass} /></Field>
              {draft.kind === 'company' && <Field label={t('orders.customerEditor.companyName')} error={errors.company_name}><TextField aria-label={t('orders.customerEditor.companyName')} value={draft.company_name ?? ''} onChange={(e) => setDraft({ ...draft, company_name: e.target.value })} className={inputClass} /></Field>}
              <Field label={t('orders.customerEditor.firstName')} error={errors.first_name}><TextField aria-label={t('orders.customerEditor.firstName')} value={draft.first_name ?? ''} onChange={(e) => setDraft({ ...draft, first_name: e.target.value })} className={inputClass} /></Field>
              <Field label={t('orders.customerEditor.lastName')} error={errors.last_name}><TextField aria-label={t('orders.customerEditor.lastName')} value={draft.last_name ?? ''} onChange={(e) => setDraft({ ...draft, last_name: e.target.value })} className={inputClass} /></Field>
            </div>
          </Section>

          <Section title={t('orders.customerEditor.accounts')} action={<Add label={t('orders.customerEditor.addAccount')} onClick={() => { const profile = profiles.find((item) => item.id === selectedProfileId); setDraft({ ...draft, accounts: [...draft.accounts, withClientKey({ business_profile_id: selectedProfileId, number: null, preferred_currency: profile?.default_currency ?? 'EUR', payment_term_days: 14, delivery_terms: null, discount_percent: '0.00', is_active: true })] }); }} />}>
            {draft.accounts.map((account, index) => <Row key={account._clientKey} remove={draft.accounts.length > 1 ? () => setDraft({ ...draft, accounts: remove(draft.accounts, index) }) : undefined} removeLabel={t('orders.customerEditor.removeAccount', { number: index + 1 })}>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Field label={t('orders.customerEditor.accountProfile')} error={errors[`accounts.${index}.business_profile_id`]}><LegacySelect aria-label={`${t('orders.customerEditor.accountProfile')} ${index + 1}`} value={account.business_profile_id} onChange={(e) => { const id = Number(e.target.value); const profile = profiles.find((item) => item.id === id); patchAccount(index, { business_profile_id: id, preferred_currency: profile?.default_currency ?? account.preferred_currency }); }} className={inputClass}>{profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</LegacySelect></Field>
                <Field label={t('orders.customerEditor.customerNumber')} error={errors[`accounts.${index}.number`]}><TextField aria-label={`${t('orders.customerEditor.customerNumber')} ${index + 1}`} value={account.number ?? ''} onChange={(e) => patchAccount(index, { number: e.target.value })} className={inputClass} /></Field>
                <Field label={t('orders.customerEditor.currency')} error={errors[`accounts.${index}.preferred_currency`]}><TextField aria-label={`${t('orders.customerEditor.currency')} ${index + 1}`} value={account.preferred_currency} onChange={(e) => patchAccount(index, { preferred_currency: e.target.value.toUpperCase() })} className={inputClass} /></Field>
                <Field label={t('orders.customerEditor.paymentDays')} error={errors[`accounts.${index}.payment_term_days`]}><NumberField min="0" aria-label={`${t('orders.customerEditor.paymentDays')} ${index + 1}`} value={account.payment_term_days ?? 0} onChange={(e) => patchAccount(index, { payment_term_days: Number(e.target.value) })} containerClassName="mt-1" className={numberInputClass} /></Field>
                <Field label={t('orders.customerEditor.deliveryTerms')} error={errors[`accounts.${index}.delivery_terms`]}><TextField aria-label={`${t('orders.customerEditor.deliveryTerms')} ${index + 1}`} value={account.delivery_terms ?? ''} onChange={(e) => patchAccount(index, { delivery_terms: e.target.value })} className={inputClass} /></Field>
                <Field label={t('orders.customerEditor.discount')} error={errors[`accounts.${index}.discount_percent`]}><NumberField min="0" max="100" step="0.01" aria-label={`${t('orders.customerEditor.discount')} ${index + 1}`} value={account.discount_percent ?? '0.00'} onChange={(e) => patchAccount(index, { discount_percent: e.target.value })} containerClassName="mt-1" className={numberInputClass} /></Field>
                <Check label={`${t('orders.customerEditor.activeAccount')} ${index + 1}`} checked={account.is_active ?? true} onChange={(checked) => patchAccount(index, { is_active: checked })} error={errors[`accounts.${index}.is_active`]} />
              </div>
            </Row>)}
          </Section>

          <Section title={t('orders.customerEditor.contacts')} action={<Add label={t('orders.customerEditor.addContact')} onClick={() => setDraft({ ...draft, contacts: [...(draft.contacts ?? []), emptyContact()] })} />}>
            {draft.contacts.map((contact, index) => <Row key={contact._clientKey} remove={() => setDraft({ ...draft, contacts: remove(draft.contacts, index) })} removeLabel={t('orders.customerEditor.removeContact', { number: index + 1 })}>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Text path={`contacts.${index}.salutation`} label={t('orders.customerEditor.salutation')} number={index} value={contact.salutation} onChange={(value) => patchContact(index, { salutation: value })} errors={errors} />
                <Text path={`contacts.${index}.first_name`} label={t('orders.customerEditor.contactFirstName')} number={index} value={contact.first_name} onChange={(value) => patchContact(index, { first_name: value })} errors={errors} />
                <Text path={`contacts.${index}.last_name`} label={t('orders.customerEditor.contactLastName')} number={index} value={contact.last_name} onChange={(value) => patchContact(index, { last_name: value })} errors={errors} />
                <Text path={`contacts.${index}.role`} label={t('orders.customerEditor.contactRole')} number={index} value={contact.role} onChange={(value) => patchContact(index, { role: value })} errors={errors} />
                <Text path={`contacts.${index}.email`} label={t('orders.customerEditor.contactEmail')} number={index} value={contact.email} onChange={(value) => patchContact(index, { email: value })} errors={errors} type="email" />
                <Text path={`contacts.${index}.phone`} label={t('orders.customerEditor.contactPhone')} number={index} value={contact.phone} onChange={(value) => patchContact(index, { phone: value })} errors={errors} />
                <Check label={`${t('orders.customerEditor.primaryContact')} ${index + 1}`} checked={contact.is_primary ?? false} onChange={(checked) => setPrimaryContact(index, checked)} error={errors[`contacts.${index}.is_primary`]} />
                <Check label={`${t('orders.customerEditor.includeContact')} ${index + 1} ${t('orders.customerEditor.onDocuments')}`} checked={contact.include_on_documents ?? false} onChange={(checked) => patchContact(index, { include_on_documents: checked })} error={errors[`contacts.${index}.include_on_documents`]} />
              </div>
            </Row>)}
          </Section>

          <Section title={t('orders.customerEditor.addresses')} action={<div className="flex flex-wrap justify-end gap-2">
            <Add label={`${t('orders.customerEditor.addAddress')}: ${t('orders.customerEditor.addressKind.billing')}`} onClick={() => setDraft({ ...draft, addresses: [...(draft.addresses ?? []), { ...emptyAddress(), kind: 'billing' }] })} />
            <Add label={`${t('orders.customerEditor.addAddress')}: ${t('orders.customerEditor.addressKind.delivery')}`} onClick={() => setDraft({ ...draft, addresses: [...(draft.addresses ?? []), { ...emptyAddress(), kind: 'delivery' }] })} />
          </div>}>
            {draft.addresses.map((address, index) => <Row key={address._clientKey} remove={() => setDraft({ ...draft, addresses: remove(draft.addresses, index) })} removeLabel={t('orders.customerEditor.removeAddress', { number: index + 1 })}>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Field label={t('orders.customerEditor.addressKindLabel')} error={errors[`addresses.${index}.kind`]}><LegacySelect aria-label={`${t('orders.customerEditor.addressKindLabel')} ${index + 1}`} value={address.kind} onChange={(e) => patchAddress(index, { kind: e.target.value as CustomerAddress['kind'], is_default: false })} className={inputClass}>{(['billing', 'delivery', 'other'] as const).map((kind) => <option key={kind} value={kind}>{t(`orders.customerEditor.addressKind.${kind}`)}</option>)}</LegacySelect></Field>
                <Text path={`addresses.${index}.label`} label={t('orders.customerEditor.addressLabel')} number={index} value={address.label} onChange={(value) => patchAddress(index, { label: value })} errors={errors} />
                <Text path={`addresses.${index}.additional`} label={t('orders.customerEditor.additional')} number={index} value={address.additional} onChange={(value) => patchAddress(index, { additional: value })} errors={errors} />
                <Text path={`addresses.${index}.street`} label={t('orders.customerEditor.street')} number={index} value={address.street} onChange={(value) => patchAddress(index, { street: value })} errors={errors} />
                <Text path={`addresses.${index}.street_2`} label={t('orders.customerEditor.street2')} number={index} value={address.street_2} onChange={(value) => patchAddress(index, { street_2: value })} errors={errors} />
                <Text path={`addresses.${index}.postal_code`} label={t('orders.customerEditor.postalCode')} number={index} value={address.postal_code} onChange={(value) => patchAddress(index, { postal_code: value })} errors={errors} />
                <Text path={`addresses.${index}.city`} label={t('orders.customerEditor.city')} number={index} value={address.city} onChange={(value) => patchAddress(index, { city: value })} errors={errors} />
                <Text path={`addresses.${index}.region`} label={t('orders.customerEditor.region')} number={index} value={address.region} onChange={(value) => patchAddress(index, { region: value })} errors={errors} />
                <Text path={`addresses.${index}.country_code`} label={t('orders.customerEditor.country')} number={index} value={address.country_code} onChange={(value) => patchAddress(index, { country_code: value })} errors={errors} />
                <Check label={`${t('orders.customerEditor.defaultAddress')} ${index + 1}`} checked={address.is_default ?? false} onChange={(checked) => setDefaultAddress(index, checked)} error={errors[`addresses.${index}.is_default`]} />
              </div>
            </Row>)}
          </Section>

          <Section title={t('orders.customerEditor.taxIdentifiers')} action={<Add label={t('orders.customerEditor.addTax')} onClick={() => setDraft({ ...draft, tax_identifiers: [...(draft.tax_identifiers ?? []), emptyTax()] })} />}>
            {draft.tax_identifiers.map((tax, index) => <Row key={tax._clientKey} remove={() => setDraft({ ...draft, tax_identifiers: remove(draft.tax_identifiers, index) })} removeLabel={t('orders.customerEditor.removeTax', { number: index + 1 })}>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Text path={`tax_identifiers.${index}.kind`} label={t('orders.customerEditor.taxKind')} number={index} value={tax.kind} onChange={(value) => patchTax(index, { kind: value })} errors={errors} />
                <Text path={`tax_identifiers.${index}.value`} label={t('orders.customerEditor.taxValue')} number={index} value={tax.value} onChange={(value) => patchTax(index, { value })} errors={errors} />
                <Text path={`tax_identifiers.${index}.country_code`} label={t('orders.customerEditor.taxCountry')} number={index} value={tax.country_code} onChange={(value) => patchTax(index, { country_code: value })} errors={errors} />
                <Field label={t('orders.customerEditor.validationStatus')} error={errors[`tax_identifiers.${index}.validation_status`]}><LegacySelect aria-label={`${t('orders.customerEditor.validationStatus')} ${index + 1}`} value={tax.validation_status ?? 'unchecked'} onChange={(e) => patchTax(index, { validation_status: e.target.value as CustomerTaxIdentifier['validation_status'] })} className={inputClass}>{taxValidationStatuses.map((status) => <option key={status} value={status}>{t(`orderMessages.taxValidationStatus.${status}`)}</option>)}</LegacySelect></Field>
              </div>
            </Row>)}
          </Section>

          <Section title={t('orders.customerEditor.preferences')}>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label={t('common.status')} error={errors.status}><LegacySelect aria-label={t('common.status')} value={draft.status ?? 'active'} onChange={(e) => setDraft({ ...draft, status: e.target.value as Draft['status'] })} className={inputClass}>{(['active', 'inactive', 'blocked'] as const).map((status) => <option key={status} value={status}>{t(`orders.status.${status}`)}</option>)}</LegacySelect></Field>
              <Field label={t('orders.customerEditor.locale')} error={errors.preferred_locale}><TextField aria-label={t('orders.customerEditor.locale')} value={draft.preferred_locale ?? 'en'} onChange={(e) => setDraft({ ...draft, preferred_locale: e.target.value })} className={inputClass} /></Field>
              <Field label={t('orders.customerEditor.tags')} error={errors.tags}><TextField aria-label={t('orders.customerEditor.tags')} value={tags} onChange={(e) => setTags(e.target.value)} className={inputClass} /></Field>
            </div>
            <Field label={t('orders.customerEditor.notes')} error={errors.notes}><TextArea aria-label={t('orders.customerEditor.notes')} value={draft.notes ?? ''} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} rows={3} className={inputClass} /></Field>
          </Section>
          </fieldset>
        </div>
        <footer data-testid="customer-editor-footer" className="flex shrink-0 justify-end gap-3 border-t border-bambu-dark-tertiary bg-bambu-dark-secondary px-5 py-4">
          <Button type="button" variant="secondary" disabled={pending} onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" disabled={pending}>{isSubmitting ? t('common.saving') : t('orders.customerEditor.save')}</Button>
        </footer>
      </form>
    </div>
  );
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return <section className="space-y-3"><div className="flex items-center justify-between gap-3"><h3 className="font-medium text-white">{title}</h3>{action}</div>{children}</section>;
}

function Row({ remove, removeLabel, children }: { remove?: () => void; removeLabel: string; children: React.ReactNode }) {
  return <div className="relative border-t border-bambu-dark-tertiary py-3 first:border-t-0">{remove && <button type="button" onClick={remove} title={removeLabel} aria-label={removeLabel} className="absolute right-0 top-2 rounded p-1.5 text-bambu-gray hover:bg-red-500/10 hover:text-red-300"><Trash2 className="h-4 w-4" /></button>}<div className={remove ? 'pr-9' : ''}>{children}</div></div>;
}

function Add({ label, onClick }: { label: string; onClick: () => void }) {
  return <Button type="button" size="sm" variant="secondary" onClick={onClick}><Plus className="mr-1.5 h-4 w-4" />{label}</Button>;
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  const errorId = useId();
  const control = isValidElement<{ 'aria-describedby'?: string; 'aria-invalid'?: boolean }>(children) && error
    ? cloneElement(children, { 'aria-describedby': errorId, 'aria-invalid': true })
    : children;
  return <label className="block text-sm text-bambu-gray-light">{label}{control}{error && <span id={errorId} role="alert" className="mt-1 block text-xs text-red-300">{error}</span>}</label>;
}

function Text({ path, label, number, value, onChange, errors, type = 'text' }: { path: string; label: string; number: number; value: string | null | undefined; onChange: (value: string) => void; errors: FieldErrors; type?: string }) {
  return <Field label={label} error={errors[path]}><TextField type={type} aria-label={`${label} ${number + 1}`} value={value ?? ''} onChange={(event) => onChange(event.target.value)} className={inputClass} /></Field>;
}

function Check({ label, checked, onChange, error }: { label: string; checked: boolean; onChange: (checked: boolean) => void; error?: string }) {
  const errorId = useId();
  return <label className="flex min-h-10 items-center gap-2 text-sm text-bambu-gray-light"><Checkbox aria-label={label} checked={checked} onChange={(event) => onChange(event.target.checked)} aria-describedby={error ? errorId : undefined} aria-invalid={error ? true : undefined} />{label}{error && <span id={errorId} role="alert" className="text-xs text-red-300">{error}</span>}</label>;
}
