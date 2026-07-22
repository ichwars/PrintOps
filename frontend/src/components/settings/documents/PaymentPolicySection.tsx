import { Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { DunningPolicyDraft, PaymentPolicyDraft, PolicyFinding, SourcedValue } from '../../../api/documentManagement';
import { Button, NumberField, Select, Switch, TextArea } from '../../ui';
import { InheritanceField } from './InheritanceField';

interface PaymentPolicySectionProps {
  payment: PaymentPolicyDraft;
  dunning: DunningPolicyDraft;
  effectivePayment?: Record<string, SourcedValue<unknown>>;
  findings: PolicyFinding[];
  disabled: boolean;
  onChange: (path: string, value: unknown) => void;
}

export function PaymentPolicySection({ payment, dunning, effectivePayment = {}, findings, disabled, onChange }: PaymentPolicySectionProps) {
  const { t } = useTranslation();
  const reset = (path: string) => onChange(path, undefined);
  const finding = (path: string) => {
    const key = findings.find((item) => item.field_path === path)?.message_key;
    return key ? t(key, key) : undefined;
  };
  const installmentsTotal = payment.installments.reduce((sum, item) => sum + (Number(item.percent) || 0), 0);
  const stages = [...dunning.stages].sort((left, right) => left.level - right.level);
  const methods = ['bank_transfer', 'cash', 'card', 'direct_debit', 'paypal'];

  return (
    <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4" aria-labelledby="document-payment-policy-heading">
      <h3 id="document-payment-policy-heading" className="font-semibold text-white">{t('settings.documents.payment.title', 'Payment and dunning')}</h3>
      <p className="mt-1 text-sm text-gray-400">{t('settings.documents.payment.description', 'Due dates, discounts, installments, bank assignment and escalation stages.')}</p>
      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <InheritanceField path="payment.payment_term_days" sourced={effectivePayment.payment_term_days as SourcedValue<number> | undefined} onReset={reset}>
          <NumberField label={t('settings.documents.payment.termDays', 'Payment term in days')} value={payment.payment_term_days} min={0} max={3650} disabled={disabled} error={finding('payment.payment_term_days')} onValueChange={(value) => onChange('payment.payment_term_days', Number(value))} />
        </InheritanceField>
        <InheritanceField path="payment.currency" sourced={effectivePayment.currency as SourcedValue<string> | undefined} onReset={reset}>
          <Select label={t('settings.documents.payment.currency', 'Currency')} value={payment.currency} disabled={disabled} options={['EUR', 'CHF', 'USD', 'GBP'].map((value) => ({ value, label: value }))} onValueChange={(value) => onChange('payment.currency', value)} />
        </InheritanceField>
        <InheritanceField path="payment.due_date_basis" sourced={effectivePayment.due_date_basis as SourcedValue<string> | undefined} onReset={reset}>
          <Select label={t('settings.documents.payment.dueBasis', 'Due date based on')} value={payment.due_date_basis} disabled={disabled} options={[
            { value: 'issue_date', label: t('settings.documents.basic.dates.issue', 'Issue date') },
            { value: 'service_date', label: t('settings.documents.basic.dates.service', 'Service date') },
            { value: 'delivery_date', label: t('settings.documents.basic.dates.delivery', 'Delivery date') },
          ]} onValueChange={(value) => onChange('payment.due_date_basis', value)} />
        </InheritanceField>
        <NumberField label={t('settings.documents.payment.bankAccount', 'Bank account ID')} value={payment.bank_account_id ?? ''} min={1} disabled={disabled} onValueChange={(value) => onChange('payment.bank_account_id', value === '' ? null : Number(value))} />
        <NumberField label={t('settings.documents.payment.discountDays', 'Cash discount period')} value={payment.discount_days} min={0} max={3650} suffix={t('common.days', 'days')} disabled={disabled} error={finding('payment.discount_days')} onValueChange={(value) => onChange('payment.discount_days', Number(value))} />
        <NumberField label={t('settings.documents.payment.discountPercent', 'Cash discount')} value={payment.discount_percent} min={0} max={100} step="0.01" suffix="%" disabled={disabled} error={finding('payment.discount_percent')} onValueChange={(value) => onChange('payment.discount_percent', value)} />
        <NumberField label={t('settings.documents.payment.prepayment', 'Advance payment')} value={payment.prepayment_percent} min={0} max={100} step="0.01" suffix="%" disabled={disabled} onValueChange={(value) => onChange('payment.prepayment_percent', value)} />
      </div>
      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {methods.map((method) => (
          <Switch key={method} checked={payment.payment_methods.includes(method)} disabled={disabled} label={t(`settings.documents.payment.methods.${method}`, method)} onCheckedChange={(checked) => onChange('payment.payment_methods', checked ? [...payment.payment_methods, method] : payment.payment_methods.filter((item) => item !== method))} />
        ))}
        <Switch checked={payment.use_term_in_invoice_text} disabled={disabled} label={t('settings.documents.payment.useTermInText', 'Use payment term in invoice text')} onCheckedChange={(checked) => onChange('payment.use_term_in_invoice_text', checked)} />
      </div>

      <div className="mt-5 border-t border-bambu-dark-tertiary pt-4">
        <Switch checked={payment.installment_enabled} disabled={disabled} label={t('settings.documents.payment.installments', 'Installment plan')} onCheckedChange={(checked) => onChange('payment.installment_enabled', checked)} />
        {payment.installment_enabled ? (
          <div className="mt-3 space-y-3">
            {payment.installments.map((installment, index) => (
              <div key={index} className="grid grid-cols-[1fr_1fr_auto] items-end gap-2 rounded-lg bg-bambu-dark p-3">
                <NumberField label={t('settings.documents.payment.installmentPercent', 'Share')} value={installment.percent} min={0.01} max={100} step="0.01" suffix="%" disabled={disabled} onValueChange={(value) => onChange(`payment.installments.${index}.percent`, value)} />
                <NumberField label={t('settings.documents.payment.installmentDue', 'Due after days')} value={installment.due_days} min={0} max={3650} disabled={disabled} onValueChange={(value) => onChange(`payment.installments.${index}.due_days`, Number(value))} />
                <Button type="button" variant="ghost" size="sm" aria-label={t('settings.documents.payment.removeInstallment', 'Remove installment')} disabled={disabled} onClick={() => onChange('payment.installments', payment.installments.filter((_, itemIndex) => itemIndex !== index))}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
            {payment.installments.length > 0 && Math.abs(installmentsTotal - 100) > 0.001 ? <p role="alert" className="text-sm text-amber-300">{t('settings.documents.payment.installmentTotalError', 'Installments must add up to 100%.')}</p> : null}
            <Button type="button" variant="secondary" size="sm" disabled={disabled} onClick={() => onChange('payment.installments', [...payment.installments, { percent: '0', due_days: 0 }])}><Plus className="h-4 w-4" />{t('settings.documents.payment.addInstallment', 'Add installment')}</Button>
          </div>
        ) : null}
      </div>

      <div className="mt-5 border-t border-bambu-dark-tertiary pt-4">
        <Switch checked={dunning.enabled} disabled={disabled} label={t('settings.documents.payment.dunningEnabled', 'Enable dunning')} onCheckedChange={(checked) => onChange('dunning.enabled', checked)} />
        {dunning.enabled ? (
          <div className="mt-3 space-y-3">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <NumberField label={t('settings.documents.payment.interest', 'Annual default interest')} value={dunning.annual_interest_rate} min={0} max={100} step="0.0001" suffix="%" disabled={disabled} onValueChange={(value) => onChange('dunning.annual_interest_rate', value)} />
              <NumberField label={t('settings.documents.payment.flatFee', 'Default fee')} value={dunning.flat_fee} min={0} step="0.01" suffix={payment.currency} disabled={disabled} onValueChange={(value) => onChange('dunning.flat_fee', value)} />
            </div>
            {stages.map((stage, sortedIndex) => {
              const originalIndex = dunning.stages.findIndex((item) => item.level === stage.level);
              return (
                <div key={stage.level} data-testid="dunning-stage" className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-3">
                  <div className="mb-3 flex items-center justify-between"><h4 className="font-medium text-white">{t('settings.documents.payment.stage', { level: stage.level, defaultValue: `Stage ${stage.level}` })}</h4><Button type="button" variant="ghost" size="sm" aria-label={t('settings.documents.payment.removeStage', 'Remove stage')} disabled={disabled} onClick={() => onChange('dunning.stages', stages.filter((_, index) => index !== sortedIndex))}><Trash2 className="h-4 w-4" /></Button></div>
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                    <NumberField label={t('settings.documents.payment.waitDays', 'Wait days')} value={stage.wait_days} min={0} disabled={disabled} onValueChange={(value) => onChange(`dunning.stages.${originalIndex}.wait_days`, Number(value))} />
                    <NumberField label={t('settings.documents.payment.stageFee', 'Stage fee')} value={stage.fee} min={0} step="0.01" suffix={payment.currency} disabled={disabled} onValueChange={(value) => onChange(`dunning.stages.${originalIndex}.fee`, value)} />
                    <NumberField label={t('settings.documents.payment.newDueDays', 'New payment term')} value={stage.new_due_days} min={0} disabled={disabled} onValueChange={(value) => onChange(`dunning.stages.${originalIndex}.new_due_days`, Number(value))} />
                  </div>
                  <div className="mt-3"><TextArea label={t('settings.documents.payment.stageText', 'Dunning text')} value={stage.body} disabled={disabled} onValueChange={(value) => onChange(`dunning.stages.${originalIndex}.body`, value)} /></div>
                  <Switch checked={stage.charge_interest} disabled={disabled} label={t('settings.documents.payment.chargeInterest', 'Charge interest')} onCheckedChange={(checked) => onChange(`dunning.stages.${originalIndex}.charge_interest`, checked)} />
                </div>
              );
            })}
            <Button type="button" variant="secondary" size="sm" disabled={disabled} onClick={() => onChange('dunning.stages', [...stages, { level: stages.length ? Math.max(...stages.map((stage) => stage.level)) + 1 : 1, wait_days: 7, fee: '0', charge_interest: false, new_due_days: 7, body: '', escalation_hint: null }])}><Plus className="h-4 w-4" />{t('settings.documents.payment.addStage', 'Add dunning stage')}</Button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
