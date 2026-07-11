import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  ApiError,
  type BusinessProfile,
  type BusinessProfileAddress,
  type BusinessProfileBankAccount,
  type BusinessProfileCreate,
  type BusinessProfileTaxIdentifier,
  type BusinessProfileUpdate,
} from '../../api/client';
import { Button } from '../Button';

type ProfileDraft = BusinessProfileCreate;

interface MappedValidationErrors {
  fields: Record<string, string>;
  global: string[];
}

const inputClass = 'w-full rounded-md border border-bambu-dark-tertiary bg-bambu-dark px-3 py-2 text-white focus:border-bambu-green focus:outline-none';
const countryOptions = ['DE', 'US', 'GB'];
const currencyOptions = ['EUR', 'USD', 'GBP'];
const topLevelFields = [
  'name', 'legal_name', 'trading_name', 'country_code', 'default_currency',
  'timezone', 'default_locale', 'billing_mode', 'is_active',
];
const addressFields = ['street', 'postal_code', 'city', 'country_code', 'is_default'];
const taxFields = ['kind', 'value', 'is_primary'];
const bankFields = ['label', 'account_holder', 'bank_name', 'country_code', 'currency', 'iban', 'bic', 'account_number', 'routing_number', 'is_default'];

function emptyAddress(countryCode = 'DE'): BusinessProfileAddress {
  return { kind: 'registered', street: '', postal_code: '', city: '', country_code: countryCode, is_default: true };
}

function emptyTaxId(countryCode = 'DE'): BusinessProfileTaxIdentifier {
  return { kind: 'vat', value: '', country_code: countryCode, is_primary: false };
}

function emptyBankAccount(countryCode = 'DE', currency = 'EUR'): BusinessProfileBankAccount {
  return {
    label: '', account_holder: '', bank_name: null, country_code: countryCode, currency,
    iban: null, bic: null, account_number: null, routing_number: null, is_default: false,
  };
}

function asDraft(profile: BusinessProfile | null): ProfileDraft {
  if (!profile) {
    return {
      name: '', legal_name: '', trading_name: '', country_code: 'DE', default_currency: 'EUR',
      timezone: 'Europe/Berlin', default_locale: 'en', billing_mode: 'hybrid', is_active: true,
      is_default: false, addresses: [emptyAddress()], tax_identifiers: [], bank_accounts: [],
    };
  }
  return {
    name: profile.name,
    legal_name: profile.legal_name,
    trading_name: profile.trading_name,
    country_code: profile.country_code,
    default_currency: profile.default_currency,
    timezone: profile.timezone,
    default_locale: profile.default_locale,
    billing_mode: profile.billing_mode,
    is_active: profile.is_active,
    is_default: profile.is_default,
    addresses: profile.addresses.map((address) => ({
      kind: address.kind, label: address.label, additional: address.additional, street: address.street,
      street_2: address.street_2, postal_code: address.postal_code, city: address.city, region: address.region,
      country_code: address.country_code, is_default: address.is_default,
    })),
    tax_identifiers: profile.tax_identifiers.map((identifier) => ({
      kind: identifier.kind, value: identifier.value, country_code: identifier.country_code,
      is_primary: identifier.is_primary, valid_from: identifier.valid_from, valid_until: identifier.valid_until,
    })),
    bank_accounts: profile.bank_accounts.map((account) => ({
      label: account.label, account_holder: account.account_holder, bank_name: account.bank_name,
      country_code: account.country_code, currency: account.currency, iban: account.iban, bic: account.bic,
      account_number: account.account_number, routing_number: account.routing_number, is_default: account.is_default,
    })),
  };
}

function knownFieldPaths(draft: ProfileDraft): Set<string> {
  const paths = new Set(topLevelFields);
  const addNested = (aggregate: string, count: number, fields: string[]) => {
    for (let index = 0; index < count; index += 1) {
      paths.add(`${aggregate}.${index}`);
      fields.forEach((field) => paths.add(`${aggregate}.${index}.${field}`));
    }
  };
  addNested('addresses', draft.addresses.length, addressFields);
  addNested('tax_identifiers', draft.tax_identifiers?.length ?? 0, taxFields);
  addNested('bank_accounts', draft.bank_accounts?.length ?? 0, bankFields);
  return paths;
}

function mapApiValidationErrors(error: unknown, knownPaths: Set<string>): MappedValidationErrors {
  const mapped: MappedValidationErrors = { fields: {}, global: [] };
  if (!(error instanceof ApiError) || error.status !== 422) return mapped;
  if (!error.validationErrors?.length) {
    mapped.global.push(error.message);
    return mapped;
  }

  error.validationErrors.forEach((issue) => {
    const loc = issue.loc[0] === 'body' ? issue.loc.slice(1) : issue.loc;
    const path = loc.map(String).join('.');
    const message = issue.msg || error.message;
    if (path && knownPaths.has(path)) {
      mapped.fields[path] = mapped.fields[path] ? `${mapped.fields[path]}; ${message}` : message;
    } else {
      mapped.global.push(message);
    }
  });
  return mapped;
}

function FieldError({ message }: { message?: string }) {
  return message ? <span className="mt-1 block text-xs text-red-300">{message}</span> : null;
}

interface Props {
  profile: BusinessProfile | null;
  isSubmitting: boolean;
  onClose: () => void;
  onSubmit: (data: BusinessProfileCreate | BusinessProfileUpdate) => Promise<void>;
}

export function BusinessProfileEditorModal({ profile, isSubmitting, onClose, onSubmit }: Props) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<ProfileDraft>(() => asDraft(profile));
  const [error, setError] = useState<unknown>(null);
  const editing = profile !== null;
  const validation = useMemo(() => mapApiValidationErrors(error, knownFieldPaths(draft)), [draft, error]);
  const updateAddress = (index: number, patch: Partial<BusinessProfileAddress>) => setDraft((current) => ({
    ...current,
    addresses: current.addresses.map((address, addressIndex) => addressIndex === index ? { ...address, ...patch } : address),
  }));
  const updateTaxId = (index: number, patch: Partial<BusinessProfileTaxIdentifier>) => setDraft((current) => ({
    ...current,
    tax_identifiers: (current.tax_identifiers ?? []).map((identifier, identifierIndex) => identifierIndex === index ? { ...identifier, ...patch } : identifier),
  }));
  const updateBankAccount = (index: number, patch: Partial<BusinessProfileBankAccount>) => setDraft((current) => ({
    ...current,
    bank_accounts: (current.bank_accounts ?? []).map((account, accountIndex) => accountIndex === index ? { ...account, ...patch } : account),
  }));
  const setAddressDefault = (index: number, checked: boolean) => setDraft((current) => {
    const selected = current.addresses[index];
    return {
      ...current,
      addresses: current.addresses.map((address, addressIndex) => ({
        ...address,
        is_default: addressIndex === index ? checked : checked && address.kind === selected.kind ? false : address.is_default,
      })),
    };
  });
  const setPrimaryTaxId = (index: number, checked: boolean) => setDraft((current) => {
    const identifiers = current.tax_identifiers ?? [];
    const selected = identifiers[index];
    return {
      ...current,
      tax_identifiers: identifiers.map((identifier, identifierIndex) => ({
        ...identifier,
        is_primary: identifierIndex === index
          ? checked
          : checked && identifier.kind === selected.kind ? false : identifier.is_primary,
      })),
    };
  });
  const setDefaultBankAccount = (index: number, checked: boolean) => setDraft((current) => {
    const accounts = current.bank_accounts ?? [];
    const selected = accounts[index];
    return {
      ...current,
      bank_accounts: accounts.map((account, accountIndex) => ({
        ...account,
        is_default: accountIndex === index ? checked : checked && account.currency === selected.currency ? false : account.is_default,
      })),
    };
  });

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      await onSubmit(editing ? { ...draft, version: profile.version } : draft);
    } catch (submitError) {
      setError(submitError);
    }
  };
  const numberedLabel = (base: string, index: number) => index === 0 ? base : `${base} ${index + 1}`;
  const genericError = error instanceof ApiError && error.status === 422
    ? validation.global.join('; ') || null
    : error instanceof Error ? error.message : null;

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !isSubmitting) onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isSubmitting, onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3" role="presentation">
      <form onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="business-profile-editor-title" className="flex max-h-[calc(100vh-1.5rem)] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary shadow-xl">
        <div className="border-b border-bambu-dark-tertiary px-5 py-4">
          <h2 id="business-profile-editor-title" className="text-lg font-semibold text-white">
            {editing ? t('orders.businessProfile.editTitle') : t('orders.businessProfile.createTitle')}
          </h2>
        </div>
        <div data-testid="business-profile-editor-scroll-viewport" className="min-h-0 flex-1 overflow-y-auto">
          <fieldset disabled={isSubmitting} className="space-y-6 px-5 py-4">
          {genericError && (
            <div role="alert" className={`flex gap-2 border p-3 text-sm ${error instanceof ApiError && error.status === 409 ? 'border-amber-500/40 bg-amber-500/10 text-amber-100' : 'border-red-500/40 bg-red-500/10 text-red-200'}`}>
              <AlertTriangle className="h-4 w-4 shrink-0" />{genericError}
            </div>
          )}

          <fieldset className="space-y-3">
            <legend className="font-medium text-white">{t('orders.businessProfile.identity')}</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.profileName')}
                <input required aria-label={t('orders.businessProfile.profileName')} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className={inputClass} />
                <FieldError message={validation.fields.name} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.legalName')}
                <input required aria-label={t('orders.businessProfile.legalName')} value={draft.legal_name} onChange={(event) => setDraft({ ...draft, legal_name: event.target.value })} className={inputClass} />
                <FieldError message={validation.fields.legal_name} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.tradingName')}
                <input aria-label={t('orders.businessProfile.tradingName')} value={draft.trading_name ?? ''} onChange={(event) => setDraft({ ...draft, trading_name: event.target.value || null })} className={inputClass} />
                <FieldError message={validation.fields.trading_name} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.profileCountry')}
                <select aria-label={t('orders.businessProfile.profileCountry')} value={draft.country_code} onChange={(event) => setDraft({ ...draft, country_code: event.target.value })} className={inputClass}>
                  {countryOptions.map((country) => <option key={country} value={country}>{country}</option>)}
                </select>
                <FieldError message={validation.fields.country_code} />
              </label>
            </div>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="font-medium text-white">{t('orders.businessProfile.address')}</legend>
            {draft.addresses.map((address, index) => (
              <div key={index} className="grid gap-3 border-b border-bambu-dark-tertiary pb-4 sm:grid-cols-2">
                <FieldError message={validation.fields[`addresses.${index}`]} />
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orders.businessProfile.street'), index)}
                  <input required aria-label={numberedLabel(t('orders.businessProfile.street'), index)} value={address.street} onChange={(event) => updateAddress(index, { street: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`addresses.${index}.street`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orders.businessProfile.city'), index)}
                  <input required aria-label={numberedLabel(t('orders.businessProfile.city'), index)} value={address.city} onChange={(event) => updateAddress(index, { city: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`addresses.${index}.city`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orders.businessProfile.postalCode'), index)}
                  <input required aria-label={numberedLabel(t('orders.businessProfile.postalCode'), index)} value={address.postal_code} onChange={(event) => updateAddress(index, { postal_code: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`addresses.${index}.postal_code`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orders.businessProfile.country'), index)}
                  <select aria-label={numberedLabel(t('orders.businessProfile.country'), index)} value={address.country_code} onChange={(event) => updateAddress(index, { country_code: event.target.value })} className={inputClass}>
                    {countryOptions.map((country) => <option key={country} value={country}>{country}</option>)}
                  </select>
                  <FieldError message={validation.fields[`addresses.${index}.country_code`]} />
                </label>
                <label className="inline-flex items-center gap-2 text-sm text-bambu-gray-light">
                  <input type="checkbox" aria-label={t('orders.businessProfile.defaultAddress', { number: index + 1 })} checked={address.is_default ?? false} onChange={(event) => setAddressDefault(index, event.target.checked)} />
                  {t('orders.businessProfile.defaultAddress', { number: index + 1 })}
                  <FieldError message={validation.fields[`addresses.${index}.is_default`]} />
                </label>
                {(address.kind !== 'registered' || draft.addresses.filter((item) => item.kind === 'registered').length > 1) && (
                  <button type="button" onClick={() => setDraft({ ...draft, addresses: draft.addresses.filter((_, addressIndex) => addressIndex !== index) })} title={t('orders.businessProfile.removeAddress', { number: index + 1 })} aria-label={t('orders.businessProfile.removeAddress', { number: index + 1 })} className="justify-self-start text-red-300">
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            ))}
            <button type="button" onClick={() => setDraft({ ...draft, addresses: [...draft.addresses, { ...emptyAddress(draft.country_code), kind: 'billing', is_default: false }] })} className="inline-flex items-center gap-1 text-sm text-bambu-green">
              <Plus className="h-4 w-4" />{t('orders.businessProfile.addAddress')}
            </button>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="font-medium text-white">{t('orders.businessProfile.taxAndBank')}</legend>
            {(draft.tax_identifiers ?? []).map((identifier, index) => (
              <div key={index} className="grid gap-3 sm:grid-cols-[1fr_2fr_auto]">
                <FieldError message={validation.fields[`tax_identifiers.${index}`]} />
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.taxIdKind')}
                  <input aria-label={`${t('orders.businessProfile.taxIdKind')} ${index + 1}`} value={identifier.kind} onChange={(event) => updateTaxId(index, { kind: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`tax_identifiers.${index}.kind`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.taxIdValue')}
                  <input required aria-label={`${t('orders.businessProfile.taxIdValue')} ${index + 1}`} value={identifier.value} onChange={(event) => updateTaxId(index, { value: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`tax_identifiers.${index}.value`]} />
                </label>
                <label className="inline-flex items-center gap-2 text-sm text-bambu-gray-light">
                  <input type="checkbox" aria-label={t('orders.businessProfile.primaryTaxId', { number: index + 1 })} checked={identifier.is_primary ?? false} onChange={(event) => setPrimaryTaxId(index, event.target.checked)} />
                  {t('orders.businessProfile.primaryTaxId', { number: index + 1 })}
                  <FieldError message={validation.fields[`tax_identifiers.${index}.is_primary`]} />
                </label>
                <button type="button" onClick={() => setDraft({ ...draft, tax_identifiers: (draft.tax_identifiers ?? []).filter((_, itemIndex) => itemIndex !== index) })} title={t('orders.businessProfile.removeTaxId', { number: index + 1 })} aria-label={t('orders.businessProfile.removeTaxId', { number: index + 1 })} className="self-end p-2 text-red-300">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button type="button" onClick={() => setDraft({ ...draft, tax_identifiers: [...(draft.tax_identifiers ?? []), emptyTaxId(draft.country_code)] })} className="inline-flex items-center gap-1 text-sm text-bambu-green">
              <Plus className="h-4 w-4" />{t('orders.businessProfile.addTaxId')}
            </button>

            {(draft.bank_accounts ?? []).map((account, index) => (
              <div key={index} className="grid gap-3 border-t border-bambu-dark-tertiary pt-3 sm:grid-cols-2">
                <FieldError message={validation.fields[`bank_accounts.${index}`]} />
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.bankAccountLabel')}
                  <input required aria-label={`${t('orders.businessProfile.bankAccountLabel')} ${index + 1}`} value={account.label} onChange={(event) => updateBankAccount(index, { label: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.label`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.accountHolder')}
                  <input required aria-label={`${t('orders.businessProfile.accountHolder')} ${index + 1}`} value={account.account_holder} onChange={(event) => updateBankAccount(index, { account_holder: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.account_holder`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.bankName')}
                  <input aria-label={`${t('orders.businessProfile.bankName')} ${index + 1}`} value={account.bank_name ?? ''} onChange={(event) => updateBankAccount(index, { bank_name: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.bank_name`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.bankCountry')}
                  <select aria-label={`${t('orders.businessProfile.bankCountry')} ${index + 1}`} value={account.country_code ?? ''} onChange={(event) => updateBankAccount(index, { country_code: event.target.value || null })} className={inputClass}>
                    <option value="">-</option>
                    {countryOptions.map((country) => <option key={country} value={country}>{country}</option>)}
                  </select>
                  <FieldError message={validation.fields[`bank_accounts.${index}.country_code`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.bankCurrency')}
                  <select required aria-label={`${t('orders.businessProfile.bankCurrency')} ${index + 1}`} value={account.currency} onChange={(event) => updateBankAccount(index, { currency: event.target.value })} className={inputClass}>
                    {currencyOptions.map((currency) => <option key={currency} value={currency}>{currency}</option>)}
                  </select>
                  <FieldError message={validation.fields[`bank_accounts.${index}.currency`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.iban')}
                  <input aria-label={`${t('orders.businessProfile.iban')} ${index + 1}`} value={account.iban ?? ''} onChange={(event) => updateBankAccount(index, { iban: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.iban`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.bic')}
                  <input aria-label={`${t('orders.businessProfile.bic')} ${index + 1}`} value={account.bic ?? ''} onChange={(event) => updateBankAccount(index, { bic: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.bic`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.accountNumber')}
                  <input aria-label={`${t('orders.businessProfile.accountNumber')} ${index + 1}`} value={account.account_number ?? ''} onChange={(event) => updateBankAccount(index, { account_number: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.account_number`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.routingNumber')}
                  <input aria-label={`${t('orders.businessProfile.routingNumber')} ${index + 1}`} value={account.routing_number ?? ''} onChange={(event) => updateBankAccount(index, { routing_number: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.routing_number`]} />
                </label>
                <label className="inline-flex items-center gap-2 text-sm text-bambu-gray-light">
                  <input type="checkbox" aria-label={t('orders.businessProfile.defaultBankAccount', { number: index + 1 })} checked={account.is_default ?? false} onChange={(event) => setDefaultBankAccount(index, event.target.checked)} />
                  {t('orders.businessProfile.defaultBankAccount', { number: index + 1 })}
                  <FieldError message={validation.fields[`bank_accounts.${index}.is_default`]} />
                </label>
                <button type="button" onClick={() => setDraft({ ...draft, bank_accounts: (draft.bank_accounts ?? []).filter((_, itemIndex) => itemIndex !== index) })} title={t('orders.businessProfile.removeBankAccount', { number: index + 1 })} aria-label={t('orders.businessProfile.removeBankAccount', { number: index + 1 })} className="justify-self-start p-2 text-red-300">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button type="button" onClick={() => setDraft({ ...draft, bank_accounts: [...(draft.bank_accounts ?? []), emptyBankAccount(draft.country_code, draft.default_currency)] })} className="inline-flex items-center gap-1 text-sm text-bambu-green">
              <Plus className="h-4 w-4" />{t('orders.businessProfile.addBankAccount')}
            </button>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="font-medium text-white">{t('orders.businessProfile.localeSection')}</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.billingMode')}
                <select aria-label={t('orders.businessProfile.billingMode')} value={draft.billing_mode} onChange={(event) => setDraft({ ...draft, billing_mode: event.target.value as ProfileDraft['billing_mode'] })} className={inputClass}>
                  <option value="internal">internal</option><option value="external">external</option><option value="hybrid">hybrid</option>
                </select>
                <FieldError message={validation.fields.billing_mode} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.currency')}
                <select aria-label={t('orders.businessProfile.currency')} value={draft.default_currency} onChange={(event) => setDraft({ ...draft, default_currency: event.target.value })} className={inputClass}>
                  {currencyOptions.map((currency) => <option key={currency} value={currency}>{currency}</option>)}
                </select>
                <FieldError message={validation.fields.default_currency} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.locale')}
                <select aria-label={t('orders.businessProfile.locale')} value={draft.default_locale} onChange={(event) => setDraft({ ...draft, default_locale: event.target.value })} className={inputClass}>
                  <option value="en">English</option><option value="de">Deutsch</option>
                </select>
                <FieldError message={validation.fields.default_locale} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.timezone')}
                <select aria-label={t('orders.businessProfile.timezone')} value={draft.timezone} onChange={(event) => setDraft({ ...draft, timezone: event.target.value })} className={inputClass}>
                  <option value="Europe/Berlin">Europe/Berlin</option><option value="America/New_York">America/New_York</option>
                </select>
                <FieldError message={validation.fields.timezone} />
              </label>
            </div>
            <label className="inline-flex items-center gap-2 text-sm text-bambu-gray-light">
              <input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })} />
              {t('orders.businessProfile.active')}
              <FieldError message={validation.fields.is_active} />
            </label>
          </fieldset>
          </fieldset>
        </div>
        <div className="flex shrink-0 justify-end gap-3 border-t border-bambu-dark-tertiary bg-bambu-dark-secondary px-5 py-4">
          <Button type="button" variant="secondary" onClick={onClose} disabled={isSubmitting}>{t('common.cancel')}</Button>
          <Button type="submit" disabled={isSubmitting} aria-label={t('orders.businessProfile.save')}>{isSubmitting ? t('common.saving') : t('orders.businessProfile.save')}</Button>
        </div>
      </form>
    </div>
  );
}
