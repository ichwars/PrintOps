import { useTranslation } from 'react-i18next';

interface PreviewLabels {
  fields: Record<string, string>;
  enums: Record<string, string>;
  yes: string;
  no: string;
  showAll: string;
}

function Value({ value, labels, field }: { value: unknown; labels: PreviewLabels; field?: string }) {
  if (value === null || value === undefined || value === '' || Array.isArray(value) && value.length === 0) {
    return <span className="text-bambu-gray">—</span>;
  }
  if (Array.isArray(value)) return <ul className="space-y-3">{value.map((item, index) => <li key={index} className="border-l-2 border-bambu-dark-tertiary pl-2"><Value value={item} labels={labels} /></li>)}</ul>;
  if (typeof value === 'object') {
    const entries = Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== '');
    if (!entries.length) return <span className="text-bambu-gray">—</span>;
    return <dl className="space-y-1">{entries.map(([key, item]) => <div key={key} className="flex flex-wrap items-baseline gap-x-2">
    <dt className="text-xs text-bambu-gray">{labels.fields[key] ?? key}</dt><dd className="min-w-0"><Value value={item} labels={labels} field={key} /></dd>
  </div>)}</dl>;
  }
  if (typeof value === 'boolean') return <span>{value ? labels.yes : labels.no}</span>;
  return <span className="whitespace-pre-wrap break-words">{(field === 'kind' || field === 'validation_status') && labels.enums[String(value)] ? labels.enums[String(value)] : String(value)}</span>;
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
  const { t } = useTranslation();
  const labels = t('orders.runtimeDomain.lexwarePreview', { returnObjects: true }) as unknown as PreviewLabels;
  const compact = summary(value);
  if (!compact) return <Value value={value} labels={labels} />;
  return <details className="group">
    <summary tabIndex={0} className="cursor-pointer rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green">
      <span className="whitespace-pre-wrap break-words">{compact}</span>
      <span className="mt-1 block text-xs text-bambu-gray group-open:hidden">{labels.showAll}</span>
    </summary>
    <div className="mt-3 border-t border-bambu-dark-tertiary pt-2"><Value value={value} labels={labels} /></div>
  </details>;
}
