import { useTranslation } from 'react-i18next';

const labels: Record<string, [string, string]> = {
  kind: ['Type', 'Art'], display_name: ['Display name', 'Anzeigename'], company_name: ['Company', 'Firma'],
  first_name: ['First name', 'Vorname'], last_name: ['Last name', 'Nachname'], additional: ['Address addition', 'Adresszusatz'],
  street: ['Street', 'Straße'], street_2: ['Street addition', 'Straßenzusatz'], postal_code: ['Postal code', 'Postleitzahl'],
  city: ['City', 'Ort'], region: ['Region', 'Region'], country_code: ['Country', 'Land'],
  is_default: ['Default', 'Standard'], salutation: ['Salutation', 'Anrede'], email: ['Email', 'E-Mail'],
  phone: ['Phone', 'Telefon'], role: ['Role', 'Rolle'], is_primary: ['Primary', 'Primär'],
  include_on_documents: ['Include on documents', 'Auf Belegen anzeigen'],
  value: ['Value', 'Wert'], validation_status: ['Validation', 'Prüfung'], label: ['Label', 'Bezeichnung'],
};

const enums: Record<string, [string, string]> = {
  company: ['Company', 'Firma'], person: ['Person', 'Person'], billing: ['Billing address', 'Rechnungsadresse'],
  delivery: ['Delivery address', 'Lieferadresse'], other: ['Other', 'Sonstige'],
  vat: ['VAT ID', 'Umsatzsteuer-ID'], tax_number: ['Tax number', 'Steuernummer'],
  unchecked: ['Unchecked', 'Ungeprüft'], valid: ['Valid', 'Gültig'], invalid: ['Invalid', 'Ungültig'],
};

function Value({ value, language, field }: { value: unknown; language: 0 | 1; field?: string }) {
  if (value === null || value === undefined || value === '' || Array.isArray(value) && value.length === 0) {
    return <span className="text-bambu-gray">—</span>;
  }
  if (Array.isArray(value)) return <ul className="space-y-3">{value.map((item, index) => <li key={index} className="border-l-2 border-bambu-dark-tertiary pl-2"><Value value={item} language={language} /></li>)}</ul>;
  if (typeof value === 'object') {
    const entries = Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== '');
    if (!entries.length) return <span className="text-bambu-gray">—</span>;
    return <dl className="space-y-1">{entries.map(([key, item]) => <div key={key} className="flex flex-wrap items-baseline gap-x-2">
    <dt className="text-xs text-bambu-gray">{labels[key]?.[language] ?? key}</dt><dd className="min-w-0"><Value value={item} language={language} field={key} /></dd>
  </div>)}</dl>;
  }
  if (typeof value === 'boolean') return <span>{language ? value ? 'Ja' : 'Nein' : value ? 'Yes' : 'No'}</span>;
  return <span className="whitespace-pre-wrap break-words">{(field === 'kind' || field === 'validation_status') && enums[String(value)] ? enums[String(value)][language] : String(value)}</span>;
}

function summary(value: unknown): string | null {
  if (!value || typeof value !== 'object') return null;
  if (Array.isArray(value)) {
    const parts = value.map(summary);
    return parts.length && parts.every(Boolean) ? parts.join('\n') : null;
  }
  const item = value as Record<string, unknown>;
  if (typeof item.display_name === 'string') return item.display_name;
  if (typeof item.street === 'string') return [item.street, item.street_2, [item.postal_code, item.city].filter(Boolean).join(' ')].filter(Boolean).join(', ');
  if (item.email || item.phone) return [item.email, item.phone].filter(Boolean).join(' · ');
  if (typeof item.value === 'string') return item.value;
  return null;
}

export function LexwarePreviewValue({ value }: { value: unknown }) {
  const { i18n } = useTranslation();
  const language = i18n.language.startsWith('de') ? 1 : 0;
  const compact = summary(value);
  if (!compact) return <Value value={value} language={language} />;
  return <details className="group">
    <summary tabIndex={0} className="cursor-pointer rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green">
      <span className="whitespace-pre-wrap break-words">{compact}</span>
      <span className="mt-1 block text-xs text-bambu-gray group-open:hidden">{language ? 'Alle Felder anzeigen' : 'Show all fields'}</span>
    </summary>
    <div className="mt-3 border-t border-bambu-dark-tertiary pt-2"><Value value={value} language={language} /></div>
  </details>;
}
