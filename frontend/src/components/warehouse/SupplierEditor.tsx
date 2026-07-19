import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Trash2 } from 'lucide-react';

import { ApiError } from '../../api/client';
import type { Supplier, SupplierInput } from '../../api/procurement';
import { Button, Checkbox, Modal, NumberField, TextArea, TextField } from '../ui';

interface SupplierEditorProps {
  supplier: Supplier | null;
  onClose: () => void;
  onSubmit: (input: SupplierInput) => Promise<void>;
  onDelete?: () => Promise<void>;
  canDelete: boolean;
}

interface SupplierDraft {
  name: string;
  contact_name: string;
  email: string;
  phone: string;
  website: string;
  address_line1: string;
  address_line2: string;
  postal_code: string;
  city: string;
  country_code: string;
  customer_number: string;
  payment_terms: string;
  default_lead_time_days: string;
  internal_notes: string;
  is_active: boolean;
}

const emptyDraft = (): SupplierDraft => ({
  name: '', contact_name: '', email: '', phone: '', website: '', address_line1: '', address_line2: '',
  postal_code: '', city: '', country_code: '', customer_number: '', payment_terms: '',
  default_lead_time_days: '0', internal_notes: '', is_active: true,
});

const asDraft = (supplier: Supplier | null): SupplierDraft => {
  if (!supplier) return emptyDraft();
  return {
    ...supplier,
    contact_name: supplier.contact_name ?? '', email: supplier.email ?? '', phone: supplier.phone ?? '',
    website: supplier.website ?? '', address_line1: supplier.address_line1 ?? '', address_line2: supplier.address_line2 ?? '',
    postal_code: supplier.postal_code ?? '', city: supplier.city ?? '', country_code: supplier.country_code ?? '',
    customer_number: supplier.customer_number ?? '', payment_terms: supplier.payment_terms ?? '',
    internal_notes: supplier.internal_notes ?? '', default_lead_time_days: String(supplier.default_lead_time_days),
  };
};

const nullable = (value: string) => value.trim() || null;

function asInput(draft: SupplierDraft): SupplierInput {
  return {
    name: draft.name.trim(),
    contact_name: nullable(draft.contact_name), email: nullable(draft.email), phone: nullable(draft.phone),
    website: nullable(draft.website), address_line1: nullable(draft.address_line1), address_line2: nullable(draft.address_line2),
    postal_code: nullable(draft.postal_code), city: nullable(draft.city),
    country_code: nullable(draft.country_code)?.toUpperCase() ?? null,
    customer_number: nullable(draft.customer_number), payment_terms: nullable(draft.payment_terms),
    default_lead_time_days: Math.max(0, Number.parseInt(draft.default_lead_time_days, 10) || 0),
    internal_notes: nullable(draft.internal_notes), is_active: draft.is_active,
  };
}

export function SupplierEditor({ supplier, onClose, onSubmit, onDelete, canDelete }: SupplierEditorProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<SupplierDraft>(() => asDraft(supplier));
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const editing = supplier !== null;

  useEffect(() => {
    setDraft(asDraft(supplier));
    setActionError(null);
  }, [supplier]);

  const update = <K extends keyof SupplierDraft>(key: K, value: SupplierDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const submit = async () => {
    const input = asInput(draft);
    if (!input.name) {
      setActionError(t('suppliers.validation.nameRequired'));
      return;
    }
    setSubmitting(true);
    setActionError(null);
    try {
      await onSubmit(input);
      onClose();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : t('suppliers.errors.save'));
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async () => {
    if (!onDelete) return;
    setSubmitting(true);
    setActionError(null);
    try {
      await onDelete();
      onClose();
    } catch (error) {
      setActionError(error instanceof ApiError || error instanceof Error ? error.message : t('suppliers.errors.delete'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open
      onClose={() => { if (!submitting) onClose(); }}
      closeDisabled={submitting}
      closeLabel={t('common.close')}
      title={editing ? t('suppliers.editTitle') : t('suppliers.createTitle')}
      className="max-w-3xl"
    >
      <div className="space-y-8">
        {actionError ? <p role="alert" className="rounded-lg border border-red-500/50 bg-red-950/30 px-3 py-2 text-sm text-red-300">{actionError}</p> : null}

        <section className="space-y-4">
          <h3 className="text-base font-semibold text-white">{t('suppliers.sections.masterData')}</h3>
          <div className="grid gap-4 md:grid-cols-2">
            <TextField label={t('suppliers.fields.name')} required value={draft.name} onValueChange={(value) => update('name', value)} disabled={submitting} />
            <TextField label={t('suppliers.fields.customerNumber')} value={draft.customer_number} onValueChange={(value) => update('customer_number', value)} disabled={submitting} />
          </div>
          <Checkbox checked={draft.is_active} onCheckedChange={(value) => update('is_active', value)} label={t('suppliers.fields.active')} disabled={submitting} />
        </section>

        <section className="space-y-4">
          <h3 className="text-base font-semibold text-white">{t('suppliers.sections.contactAddress')}</h3>
          <div className="grid gap-4 md:grid-cols-2">
            <TextField label={t('suppliers.fields.contactName')} value={draft.contact_name} onValueChange={(value) => update('contact_name', value)} disabled={submitting} />
            <TextField type="email" label={t('suppliers.fields.email')} value={draft.email} onValueChange={(value) => update('email', value)} disabled={submitting} />
            <TextField type="tel" label={t('suppliers.fields.phone')} value={draft.phone} onValueChange={(value) => update('phone', value)} disabled={submitting} />
            <TextField type="url" label={t('suppliers.fields.website')} value={draft.website} onValueChange={(value) => update('website', value)} disabled={submitting} />
            <TextField label={t('suppliers.fields.addressLine1')} value={draft.address_line1} onValueChange={(value) => update('address_line1', value)} disabled={submitting} />
            <TextField label={t('suppliers.fields.addressLine2')} value={draft.address_line2} onValueChange={(value) => update('address_line2', value)} disabled={submitting} />
            <TextField label={t('suppliers.fields.postalCode')} value={draft.postal_code} onValueChange={(value) => update('postal_code', value)} disabled={submitting} />
            <TextField label={t('suppliers.fields.city')} value={draft.city} onValueChange={(value) => update('city', value)} disabled={submitting} />
            <TextField label={t('suppliers.fields.countryCode')} maxLength={2} value={draft.country_code} onValueChange={(value) => update('country_code', value)} disabled={submitting} />
          </div>
        </section>

        <section className="space-y-4">
          <h3 className="text-base font-semibold text-white">{t('suppliers.sections.procurement')}</h3>
          <div className="grid gap-4 md:grid-cols-2">
            <TextField label={t('suppliers.fields.paymentTerms')} value={draft.payment_terms} onValueChange={(value) => update('payment_terms', value)} disabled={submitting} />
            <NumberField label={t('suppliers.fields.defaultLeadTime')} min={0} max={3650} value={draft.default_lead_time_days} onValueChange={(value) => update('default_lead_time_days', value)} disabled={submitting} />
          </div>
        </section>

        <section className="space-y-4">
          <h3 className="text-base font-semibold text-white">{t('suppliers.sections.internalNotes')}</h3>
          <TextArea label={t('suppliers.fields.internalNotes')} value={draft.internal_notes} onValueChange={(value) => update('internal_notes', value)} disabled={submitting} />
        </section>

        <div className="flex flex-col-reverse gap-3 border-t border-bambu-dark-tertiary pt-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            {editing && canDelete && onDelete ? <Button type="button" variant="danger" onClick={remove} disabled={submitting}><Trash2 aria-hidden="true" className="h-4 w-4" />{t('suppliers.actions.delete')}</Button> : null}
          </div>
          <div className="flex flex-col-reverse gap-3 sm:flex-row">
            <Button type="button" variant="secondary" onClick={onClose} disabled={submitting}>{t('common.cancel')}</Button>
            <Button type="button" onClick={submit} loading={submitting}>{t('suppliers.actions.save')}</Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
