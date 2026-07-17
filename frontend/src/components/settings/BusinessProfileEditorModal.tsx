import { useMemo, useRef, useState } from 'react';
import { AlertTriangle, Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  ApiError,
  api,
  type BusinessProfile,
  type BusinessProfileAddress,
  type BusinessProfileBankAccount,
  type BusinessProfileCreate,
  type BusinessProfileTaxIdentifier,
  type BusinessProfileUpdate,
} from '../../api/client';
import { Button, Checkbox, DatePicker, IconButton, Modal, Select, TextField } from '../ui';
import { orderMasterDataCountryCodes, orderMasterDataCurrencyCodes } from '../../lib/orderMasterDataValidation';

type ProfileDraft = BusinessProfileCreate;

interface MappedValidationErrors {
  fields: Record<string, string>;
  global: string[];
}
type Translate = (key: string, options?: Record<string, unknown>) => string;

const inputClass = 'h-10 w-full rounded-md border border-bambu-dark-tertiary bg-bambu-dark px-3 py-2 text-white focus:border-bambu-green focus:outline-none';
const topLevelFields = [
  'name', 'legal_name', 'trading_name', 'country_code', 'default_currency',
  'timezone', 'default_locale', 'billing_mode', 'tax_mode', 'default_tax_rate',
  'cash_accounting', 'input_tax_deductible', 'show_offer_qr', 'paypal_me_url', 'is_active',
];
const addressFields = ['kind', 'label', 'additional', 'street', 'street_2', 'postal_code', 'city', 'region', 'country_code', 'is_default'];
const taxFields = ['kind', 'value', 'country_code', 'is_primary', 'valid_from', 'valid_until'];
const bankFields = ['label', 'account_holder', 'bank_name', 'country_code', 'currency', 'iban', 'bic', 'account_number', 'routing_number', 'is_default'];
const addressKinds = ['registered', 'billing', 'shipping', 'other'] as const;
const taxIdentifierKinds = ['vat', 'tax', 'other'] as const;
const supportedLocales = [
  ['de', 'Deutsch'], ['en', 'English'], ['es', 'Español'], ['fr', 'Français'], ['it', 'Italiano'],
  ['ja', '日本語'], ['ko', '한국어'], ['pt-BR', 'Português (Brasil)'], ['tr', 'Türkçe'],
  ['zh-CN', '简体中文'], ['zh-TW', '繁體中文'],
] as const;
const countryOptions = orderMasterDataCountryCodes;
const currencyOptions = orderMasterDataCurrencyCodes;

function systemTimezones(): string[] {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  try {
    const values = Intl.supportedValuesOf?.('timeZone');
    if (values?.length) return Array.from(new Set([timezone, ...values])).sort();
  } catch {
    // Older browsers can still submit an IANA timezone through the text input.
  }
  return Array.from(new Set([timezone, 'UTC'])).filter(Boolean).sort();
}

const timezoneOptions = systemTimezones();

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
      tax_mode: 'standard', default_tax_rate: '19.00', cash_accounting: false,
      input_tax_deductible: true, show_offer_qr: false, paypal_me_url: null,
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
    tax_mode: profile.tax_mode, default_tax_rate: profile.default_tax_rate,
    cash_accounting: profile.cash_accounting, input_tax_deductible: profile.input_tax_deductible,
    show_offer_qr: profile.show_offer_qr, paypal_me_url: profile.paypal_me_url,
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

function localizedApiMessage(error: unknown, t: Translate, language: string): string | null {
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : null;
  const knownKey = error.code ? ({
    resource_in_use: 'orderUi.operationBlocked',
    version_conflict: 'orderMessages.errors.business_profile_version_conflict',
    duplicate_business_key: 'orderUi.duplicateRecord',
    not_found: 'orderUiNotFound',
  } as Record<string, string>)[error.code] : undefined;
  if (knownKey) return t(knownKey);
  if (language.startsWith('de') && error.status === 409) return t('orderMessages.errors.conflict');
  if (language.startsWith('de') && error.status === 422) return t('orderMessages.validation.failed');
  return error.message;
}

function mapApiValidationErrors(error: unknown, knownPaths: Set<string>, t: Translate, language: string): MappedValidationErrors {
  const mapped: MappedValidationErrors = { fields: {}, global: [] };
  if (!(error instanceof ApiError) || error.status !== 422) return mapped;
  if (!error.validationErrors?.length) {
    mapped.global.push(localizedApiMessage(error, t, language) ?? t('orderMessages.validation.failed'));
    return mapped;
  }

  error.validationErrors.forEach((issue) => {
    const loc = issue.loc[0] === 'body' ? issue.loc.slice(1) : issue.loc;
    const path = loc.map(String).join('.');
    const message = language.startsWith('de') ? t('orderMessages.validation.invalidField') : issue.msg || error.message;
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
  onSubmit: (data: BusinessProfileCreate | BusinessProfileUpdate, logoFile?: File | null, removeLogo?: boolean) => Promise<void>;
}

export function BusinessProfileEditorModal({ profile, isSubmitting, onClose, onSubmit }: Props) {
  const { t, i18n } = useTranslation();
  const [draft, setDraft] = useState<ProfileDraft>(() => asDraft(profile));
  const [error, setError] = useState<unknown>(null);
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [removeLogo, setRemoveLogo] = useState(false);
  const editing = profile !== null;
  const initialFocusRef = useRef<HTMLInputElement>(null);
  const localeOptions = useMemo(() => {
    const current = draft.default_locale ?? 'en';
    return supportedLocales.some(([value]) => value === current)
      ? supportedLocales
      : [[current, current], ...supportedLocales] as const;
  }, [draft.default_locale]);
  const german = i18n.language.startsWith('de');
  const tradingNameHelp = german
    ? 'Optional. Im Geschäftsverkehr verwendeter Name, falls er vom rechtlichen Namen abweicht.'
    : 'Optional. Name used in business if it differs from the legal name.';
  const taxKindLabels: Record<(typeof taxIdentifierKinds)[number], string> = german
    ? { vat: 'Umsatzsteuer-Identifikationsnummer', tax: 'Steuernummer', other: 'Sonstige Steuer-ID' }
    : { vat: 'VAT identification number', tax: 'Tax number', other: 'Other tax ID' };
  const validation = useMemo(() => mapApiValidationErrors(error, knownFieldPaths(draft), t, i18n.language), [draft, error, i18n.language, t]);
  const updateAddress = (index: number, patch: Partial<BusinessProfileAddress>) => setDraft((current) => ({
    ...current,
    addresses: current.addresses.map((address, addressIndex) => addressIndex === index ? { ...address, ...patch } : address),
  }));
  const changeAddressKind = (index: number, kind: BusinessProfileAddress['kind']) => setDraft((current) => {
    const selected = current.addresses[index];
    return {
      ...current,
      addresses: current.addresses.map((address, addressIndex) => {
        if (addressIndex === index) return { ...address, kind };
        if (selected.is_default && address.kind === kind) return { ...address, is_default: false };
        return address;
      }),
    };
  });
  const updateTaxId = (index: number, patch: Partial<BusinessProfileTaxIdentifier>) => setDraft((current) => ({
    ...current,
    tax_identifiers: (current.tax_identifiers ?? []).map((identifier, identifierIndex) => identifierIndex === index ? { ...identifier, ...patch } : identifier),
  }));
  const updateBankAccount = (index: number, patch: Partial<BusinessProfileBankAccount>) => setDraft((current) => ({
    ...current,
    bank_accounts: (current.bank_accounts ?? []).map((account, accountIndex) => accountIndex === index ? { ...account, ...patch } : account),
  }));
  const changeTaxKind = (index: number, kind: string) => setDraft((current) => {
    const identifiers = current.tax_identifiers ?? [];
    const selected = identifiers[index];
    return {
      ...current,
      tax_identifiers: identifiers.map((identifier, identifierIndex) => {
        if (identifierIndex === index) return { ...identifier, kind };
        if (selected.is_primary && identifier.kind === kind) return { ...identifier, is_primary: false };
        return identifier;
      }),
    };
  });
  const changeBankCurrency = (index: number, currency: string) => setDraft((current) => {
    const accounts = current.bank_accounts ?? [];
    const selected = accounts[index];
    return {
      ...current,
      bank_accounts: accounts.map((account, accountIndex) => {
        if (accountIndex === index) return { ...account, currency };
        if (selected.is_default && account.currency === currency) return { ...account, is_default: false };
        return account;
      }),
    };
  });
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
      await onSubmit(editing ? { ...draft, version: profile.version } : draft, logoFile, removeLogo);
    } catch (submitError) {
      setError(submitError);
    }
  };
  const numberedLabel = (base: string, index: number) => index === 0 ? base : `${base} ${index + 1}`;
  const genericError = error instanceof ApiError && error.status === 422
    ? validation.global.join('; ') || null
    : localizedApiMessage(error, t, i18n.language);

  return (
    <Modal
      open
      onClose={() => { if (!isSubmitting) onClose(); }}
      closeOnBackdrop={!isSubmitting}
      closeDisabled={isSubmitting}
      closeLabel={t('common.close', 'Close')}
      title={editing ? t('orders.businessProfile.editTitle') : t('orders.businessProfile.createTitle')}
      initialFocusRef={initialFocusRef}
      className="max-w-3xl"
    >
      <form onSubmit={submit}>
        <div data-testid="business-profile-editor-scroll-viewport" className="min-h-0">
          <fieldset disabled={isSubmitting} className="space-y-6">
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
                <TextField ref={initialFocusRef} required aria-label={t('orders.businessProfile.profileName')} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className={inputClass} />
                <FieldError message={validation.fields.name} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.legalName')}
                <TextField required aria-label={t('orders.businessProfile.legalName')} value={draft.legal_name} onChange={(event) => setDraft({ ...draft, legal_name: event.target.value })} className={inputClass} />
                <FieldError message={validation.fields.legal_name} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.tradingName')}
                <TextField aria-label={t('orders.businessProfile.tradingName')} value={draft.trading_name ?? ''} onChange={(event) => setDraft({ ...draft, trading_name: event.target.value || null })} className={inputClass} />
                <span className="mt-1 block text-xs text-bambu-gray">{tradingNameHelp}</span>
                <FieldError message={validation.fields.trading_name} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.profileCountry')}
                <Select ariaLabel={t('orders.businessProfile.profileCountry')} value={draft.country_code} onValueChange={(value) => setDraft({ ...draft, country_code: value })} options={countryOptions.map((country) => ({ value: country, label: country }))} />
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
                  {numberedLabel(t('orderMessages.addressKind'), index)}
                  <Select ariaLabel={numberedLabel(t('orderMessages.addressKind'), index)} value={address.kind} onValueChange={(value) => changeAddressKind(index, value as BusinessProfileAddress['kind'])} disabled={address.kind === 'registered' && draft.addresses.filter((item) => item.kind === 'registered').length === 1} options={addressKinds.map((kind) => ({ value: kind, label: t(`orderMessages.addressKinds.${kind}`) }))} />
                  <FieldError message={validation.fields[`addresses.${index}.kind`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orderMessages.addressLabel'), index)}
                  <TextField aria-label={numberedLabel(t('orderMessages.addressLabel'), index)} value={address.label ?? ''} onChange={(event) => updateAddress(index, { label: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`addresses.${index}.label`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orderMessages.additional'), index)}
                  <TextField aria-label={numberedLabel(t('orderMessages.additional'), index)} value={address.additional ?? ''} onChange={(event) => updateAddress(index, { additional: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`addresses.${index}.additional`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orders.businessProfile.street'), index)}
                  <TextField required aria-label={numberedLabel(t('orders.businessProfile.street'), index)} value={address.street} onChange={(event) => updateAddress(index, { street: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`addresses.${index}.street`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orderMessages.street2'), index)}
                  <TextField aria-label={numberedLabel(t('orderMessages.street2'), index)} value={address.street_2 ?? ''} onChange={(event) => updateAddress(index, { street_2: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`addresses.${index}.street_2`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orders.businessProfile.city'), index)}
                  <TextField required aria-label={numberedLabel(t('orders.businessProfile.city'), index)} value={address.city} onChange={(event) => updateAddress(index, { city: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`addresses.${index}.city`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orders.businessProfile.postalCode'), index)}
                  <TextField required aria-label={numberedLabel(t('orders.businessProfile.postalCode'), index)} value={address.postal_code} onChange={(event) => updateAddress(index, { postal_code: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`addresses.${index}.postal_code`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orders.businessProfile.country'), index)}
                  <Select ariaLabel={numberedLabel(t('orders.businessProfile.country'), index)} value={address.country_code} onValueChange={(value) => updateAddress(index, { country_code: value })} options={countryOptions.map((country) => ({ value: country, label: country }))} />
                  <FieldError message={validation.fields[`addresses.${index}.country_code`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {numberedLabel(t('orderMessages.region'), index)}
                  <TextField aria-label={numberedLabel(t('orderMessages.region'), index)} value={address.region ?? ''} onChange={(event) => updateAddress(index, { region: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`addresses.${index}.region`]} />
                </label>
                <label className="inline-flex min-h-10 items-center gap-2 self-end text-sm text-bambu-gray-light">
                  <Checkbox ariaLabel={t('orders.businessProfile.defaultAddress', { number: index + 1 })} checked={address.is_default ?? false} onChange={(event) => setAddressDefault(index, event.target.checked)} />
                  {t('orders.businessProfile.defaultAddress', { number: index + 1 })}
                  <FieldError message={validation.fields[`addresses.${index}.is_default`]} />
                </label>
                {(address.kind !== 'registered' || draft.addresses.filter((item) => item.kind === 'registered').length > 1) && (
                  <IconButton label={t('orders.businessProfile.removeAddress', { number: index + 1 })} icon={Trash2} onClick={() => setDraft({ ...draft, addresses: draft.addresses.filter((_, addressIndex) => addressIndex !== index) })} size="sm" className="justify-self-start text-red-300" />
                )}
              </div>
            ))}
            <Button type="button" variant="ghost" size="sm" onClick={() => setDraft({ ...draft, addresses: [...draft.addresses, { ...emptyAddress(draft.country_code), kind: 'other', is_default: false }] })} className="text-bambu-green">
              <Plus className="h-4 w-4" />{t('orders.businessProfile.addAddress')}
            </Button>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="font-medium text-white">{german ? 'Dokumentdarstellung' : 'Document appearance'}</legend>
            <div className="rounded-lg border border-bambu-dark-tertiary p-3">
              <div className="flex flex-wrap items-center gap-3">
                {(logoFile || (profile?.logo_version && !removeLogo)) ? (
                  <img className="h-16 w-24 rounded border border-bambu-dark-tertiary object-contain" alt={german ? 'Logovorschau' : 'Logo preview'} src={logoFile ? URL.createObjectURL(logoFile) : api.getBusinessProfileLogoUrl(profile!.id, profile!.logo_version!)} />
                ) : <div className="flex h-16 w-24 items-center justify-center rounded border border-bambu-dark-tertiary text-xs text-bambu-gray">{german ? 'Kein Logo' : 'No logo'}</div>}
                <label className="text-sm text-bambu-gray-light">
                  {german ? 'Logo hochladen' : 'Upload logo'}
                  <input type="file" accept="image/png,image/jpeg" aria-label={german ? 'Logo hochladen' : 'Upload logo'} onChange={(event) => { setLogoFile(event.target.files?.[0] ?? null); setRemoveLogo(false); }} className="mt-1 block text-sm" />
                </label>
                {(logoFile || (profile?.logo_version && !removeLogo)) && <Button type="button" variant="ghost" size="sm" onClick={() => { setLogoFile(null); setRemoveLogo(true); }} className="text-red-300">{german ? 'Logo entfernen' : 'Remove logo'}</Button>}
              </div>
              <label className="mt-3 inline-flex min-h-10 items-center gap-2 text-sm text-bambu-gray-light">
                <Checkbox checked={draft.show_offer_qr ?? false} onChange={(event) => setDraft({ ...draft, show_offer_qr: event.target.checked })} />
                {german ? 'QR-Code zum Online-Angebot auf PDFs anzeigen' : 'Show online-offer QR code on PDFs'}
              </label>
              <p className="text-xs text-bambu-gray">{german ? 'Erfordert eine von außen erreichbare PrintOps-URL. Die PDF-Ausgabe folgt mit der Dokumentfunktion.' : 'Requires a publicly reachable PrintOps URL. PDF output follows with document support.'}</p>
            </div>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="font-medium text-white">{german ? 'Steuerangaben' : 'Tax settings'}</legend>
            <p className="text-xs text-bambu-gray">{german ? 'Diese Angaben steuern die spätere Dokumentlogik und ersetzen keine steuerliche Prüfung.' : 'These settings control future document logic and do not replace professional tax advice.'}</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm text-bambu-gray-light">{german ? 'Steuermodus' : 'Tax mode'}
                <Select ariaLabel={german ? 'Steuermodus' : 'Tax mode'} value={draft.tax_mode ?? 'standard'} onValueChange={(taxMode) => setDraft({ ...draft, tax_mode: taxMode as 'standard' | 'exempt' | 'none', ...(taxMode === 'standard' ? {} : { default_tax_rate: '0.00', input_tax_deductible: false }) })} options={[
                  { value: 'standard', label: german ? 'Reguläre Umsatzsteuer' : 'Standard VAT' },
                  { value: 'exempt', label: german && draft.country_code === 'DE' ? 'Kleinunternehmerregelung §19 UStG' : (german ? 'Steuerbefreit' : 'Tax exempt') },
                  { value: 'none', label: german ? 'Keine Umsatzsteuer' : 'No VAT' },
                ]} />
              </label>
              <label className="text-sm text-bambu-gray-light">{german ? 'Standard-MwSt. %' : 'Default VAT %'}
                <TextField type="number" min="0" max="100" step="0.01" disabled={draft.tax_mode !== 'standard'} aria-label={german ? 'Standard-MwSt. %' : 'Default VAT %'} value={draft.default_tax_rate ?? '0.00'} onChange={(event) => setDraft({ ...draft, default_tax_rate: event.target.value })} className={inputClass} />
              </label>
              <Checkbox checked={draft.cash_accounting ?? false} onCheckedChange={(checked) => setDraft({ ...draft, cash_accounting: checked })} label={german ? 'Ist-Versteuerung' : 'Cash accounting'} />
              <Checkbox disabled={draft.tax_mode !== 'standard'} checked={draft.input_tax_deductible ?? false} onCheckedChange={(checked) => setDraft({ ...draft, input_tax_deductible: checked })} label={german ? 'Vorsteuerabzug aktiv' : 'Input tax deductible'} />
            </div>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="font-medium text-white">{t('orders.businessProfile.taxAndBank')}</legend>
            <label className="block text-sm text-bambu-gray-light">PayPal.Me
              <TextField type="url" aria-label="PayPal.Me" placeholder="https://paypal.me/deinname" value={draft.paypal_me_url ?? ''} onChange={(event) => setDraft({ ...draft, paypal_me_url: event.target.value || null })} className={inputClass} />
              <FieldError message={validation.fields.paypal_me_url} />
            </label>
            {(draft.tax_identifiers ?? []).map((identifier, index) => (
              <div key={index} className="grid gap-3 sm:grid-cols-[1fr_2fr_auto]">
                <FieldError message={validation.fields[`tax_identifiers.${index}`]} />
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.taxIdKind')}
                  <Select ariaLabel={`${t('orders.businessProfile.taxIdKind')} ${index + 1}`} value={identifier.kind} onValueChange={(value) => changeTaxKind(index, value)} options={[
                    ...(!taxIdentifierKinds.includes(identifier.kind as (typeof taxIdentifierKinds)[number]) ? [{ value: identifier.kind, label: identifier.kind }] : []),
                    ...taxIdentifierKinds.map((kind) => ({ value: kind, label: taxKindLabels[kind] })),
                  ]} />
                  <FieldError message={validation.fields[`tax_identifiers.${index}.kind`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.taxIdValue')}
                  <TextField required aria-label={`${t('orders.businessProfile.taxIdValue')} ${index + 1}`} value={identifier.value} onChange={(event) => updateTaxId(index, { value: event.target.value })} className={inputClass} />
                  {identifier.kind === 'vat' && (
                    <span className="mt-1 block text-xs text-bambu-gray">
                      {german ? 'Für Deutschland die Umsatzsteuer-ID einschließlich DE-Präfix eingeben, z. B. DE123456789.' : 'For Germany, enter the VAT ID including the DE prefix, e.g. DE123456789.'}
                    </span>
                  )}
                  <FieldError message={validation.fields[`tax_identifiers.${index}.value`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orderMessages.taxCountry')}
                  <Select ariaLabel={`${t('orderMessages.taxCountry')} ${index + 1}`} value={identifier.country_code ?? ''} onValueChange={(value) => updateTaxId(index, { country_code: value || null })} options={[{ value: '', label: '-' }, ...countryOptions.map((country) => ({ value: country, label: country }))]} />
                  <FieldError message={validation.fields[`tax_identifiers.${index}.country_code`]} />
                </label>
                {identifier.kind === 'other' && <>
                  <label className="text-sm text-bambu-gray-light">
                    {t('orderMessages.validFrom')}
                    <DatePicker locale={i18n.language} ariaLabel={`${t('orderMessages.validFrom')} ${index + 1}`} value={identifier.valid_from ?? ''} onValueChange={(value) => updateTaxId(index, { valid_from: value || null })} />
                    <FieldError message={validation.fields[`tax_identifiers.${index}.valid_from`]} />
                  </label>
                  <label className="text-sm text-bambu-gray-light">
                    {t('orderMessages.validUntil')}
                    <DatePicker locale={i18n.language} ariaLabel={`${t('orderMessages.validUntil')} ${index + 1}`} value={identifier.valid_until ?? ''} onValueChange={(value) => updateTaxId(index, { valid_until: value || null })} />
                    <FieldError message={validation.fields[`tax_identifiers.${index}.valid_until`]} />
                  </label>
                </>}
                <label className="inline-flex min-h-10 items-center gap-2 self-end text-sm text-bambu-gray-light">
                  <Checkbox ariaLabel={t('orders.businessProfile.primaryTaxId', { number: index + 1 })} checked={identifier.is_primary ?? false} onChange={(event) => setPrimaryTaxId(index, event.target.checked)} />
                  {t('orders.businessProfile.primaryTaxId', { number: index + 1 })}
                  <FieldError message={validation.fields[`tax_identifiers.${index}.is_primary`]} />
                </label>
                <IconButton label={t('orders.businessProfile.removeTaxId', { number: index + 1 })} icon={Trash2} onClick={() => setDraft({ ...draft, tax_identifiers: (draft.tax_identifiers ?? []).filter((_, itemIndex) => itemIndex !== index) })} size="sm" className="self-end text-red-300" />
              </div>
            ))}
            <Button type="button" variant="ghost" size="sm" onClick={() => setDraft({ ...draft, tax_identifiers: [...(draft.tax_identifiers ?? []), emptyTaxId(draft.country_code)] })} className="text-bambu-green">
              <Plus className="h-4 w-4" />{t('orders.businessProfile.addTaxId')}
            </Button>

            {(draft.bank_accounts ?? []).map((account, index) => (
              <div key={index} className="grid gap-3 border-t border-bambu-dark-tertiary pt-3 sm:grid-cols-2">
                <FieldError message={validation.fields[`bank_accounts.${index}`]} />
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.bankAccountLabel')}
                  <TextField required aria-label={`${t('orders.businessProfile.bankAccountLabel')} ${index + 1}`} value={account.label} onChange={(event) => updateBankAccount(index, { label: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.label`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.accountHolder')}
                  <TextField required aria-label={`${t('orders.businessProfile.accountHolder')} ${index + 1}`} value={account.account_holder} onChange={(event) => updateBankAccount(index, { account_holder: event.target.value })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.account_holder`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.bankName')}
                  <TextField aria-label={`${t('orders.businessProfile.bankName')} ${index + 1}`} value={account.bank_name ?? ''} onChange={(event) => updateBankAccount(index, { bank_name: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.bank_name`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.bankCountry')}
                  <Select ariaLabel={`${t('orders.businessProfile.bankCountry')} ${index + 1}`} value={account.country_code ?? ''} onValueChange={(value) => updateBankAccount(index, { country_code: value || null })} options={[{ value: '', label: '-' }, ...countryOptions.map((country) => ({ value: country, label: country }))]} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.country_code`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.bankCurrency')}
                  <Select required ariaLabel={`${t('orders.businessProfile.bankCurrency')} ${index + 1}`} value={account.currency} onValueChange={(value) => changeBankCurrency(index, value)} options={currencyOptions.map((currency) => ({ value: currency, label: currency }))} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.currency`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.iban')}
                  <TextField aria-label={`${t('orders.businessProfile.iban')} ${index + 1}`} value={account.iban ?? ''} onChange={(event) => updateBankAccount(index, { iban: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.iban`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.bic')}
                  <TextField aria-label={`${t('orders.businessProfile.bic')} ${index + 1}`} value={account.bic ?? ''} onChange={(event) => updateBankAccount(index, { bic: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.bic`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.accountNumber')}
                  <TextField aria-label={`${t('orders.businessProfile.accountNumber')} ${index + 1}`} value={account.account_number ?? ''} onChange={(event) => updateBankAccount(index, { account_number: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.account_number`]} />
                </label>
                <label className="text-sm text-bambu-gray-light">
                  {t('orders.businessProfile.routingNumber')}
                  <TextField aria-label={`${t('orders.businessProfile.routingNumber')} ${index + 1}`} value={account.routing_number ?? ''} onChange={(event) => updateBankAccount(index, { routing_number: event.target.value || null })} className={inputClass} />
                  <FieldError message={validation.fields[`bank_accounts.${index}.routing_number`]} />
                </label>
                <label className="inline-flex min-h-10 items-center gap-2 self-end text-sm text-bambu-gray-light">
                  <Checkbox ariaLabel={t('orders.businessProfile.defaultBankAccount', { number: index + 1 })} checked={account.is_default ?? false} onChange={(event) => setDefaultBankAccount(index, event.target.checked)} />
                  {t('orders.businessProfile.defaultBankAccount', { number: index + 1 })}
                  <FieldError message={validation.fields[`bank_accounts.${index}.is_default`]} />
                </label>
                <IconButton label={t('orders.businessProfile.removeBankAccount', { number: index + 1 })} icon={Trash2} onClick={() => setDraft({ ...draft, bank_accounts: (draft.bank_accounts ?? []).filter((_, itemIndex) => itemIndex !== index) })} size="sm" className="justify-self-start text-red-300" />
              </div>
            ))}
            <Button type="button" variant="ghost" size="sm" onClick={() => setDraft({ ...draft, bank_accounts: [...(draft.bank_accounts ?? []), emptyBankAccount(draft.country_code, draft.default_currency)] })} className="text-bambu-green">
              <Plus className="h-4 w-4" />{t('orders.businessProfile.addBankAccount')}
            </Button>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="font-medium text-white">{t('orders.businessProfile.localeSection')}</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.billingMode')}
                <Select ariaLabel={t('orders.businessProfile.billingMode')} value={draft.billing_mode} onValueChange={(value) => setDraft({ ...draft, billing_mode: value as ProfileDraft['billing_mode'] })} options={[
                  { value: 'internal', label: t('orderUi.billingModes.internal') },
                  { value: 'external', label: t('orderUi.billingModes.external') },
                  { value: 'hybrid', label: t('orderUi.billingModes.hybrid') },
                ]} />
                <FieldError message={validation.fields.billing_mode} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.currency')}
                <Select ariaLabel={t('orders.businessProfile.currency')} value={draft.default_currency} onValueChange={(value) => setDraft({ ...draft, default_currency: value })} options={currencyOptions.map((currency) => ({ value: currency, label: currency }))} />
                <FieldError message={validation.fields.default_currency} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.locale')}
                <Select ariaLabel={t('orders.businessProfile.locale')} value={draft.default_locale} onValueChange={(value) => setDraft({ ...draft, default_locale: value })} options={localeOptions.map(([value, label]) => ({ value, label }))} />
                <FieldError message={validation.fields.default_locale} />
              </label>
              <label className="text-sm text-bambu-gray-light">
                {t('orders.businessProfile.timezone')}
                <TextField list="business-profile-timezones" aria-label={t('orders.businessProfile.timezone')} value={draft.timezone} onChange={(event) => setDraft({ ...draft, timezone: event.target.value })} className={inputClass} />
                <datalist id="business-profile-timezones">{timezoneOptions.map((timezone) => <option key={timezone} value={timezone} />)}</datalist>
                <FieldError message={validation.fields.timezone} />
              </label>
            </div>
            <label className="inline-flex min-h-10 items-center gap-2 text-sm text-bambu-gray-light">
              <Checkbox checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })} />
              {t('orders.businessProfile.active')}
              <FieldError message={validation.fields.is_active} />
            </label>
          </fieldset>
          </fieldset>
        </div>
        <div className="mt-6 flex justify-end gap-3 border-t border-bambu-dark-tertiary pt-4">
          <Button type="button" variant="secondary" onClick={onClose} disabled={isSubmitting}>{t('common.cancel')}</Button>
          <Button type="submit" disabled={isSubmitting} aria-label={t('orders.businessProfile.save')}>{isSubmitting ? t('common.saving') : t('orders.businessProfile.save')}</Button>
        </div>
      </form>
    </Modal>
  );
}
