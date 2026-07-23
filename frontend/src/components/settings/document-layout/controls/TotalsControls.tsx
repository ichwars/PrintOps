import { useTranslation } from 'react-i18next';
import type { TotalsRules } from '../../../../api/documentLayouts';
import { BooleanField, SelectField, type LayoutSectionProps } from './shared';

export function TotalsControls(props: LayoutSectionProps<TotalsRules>) {
  const { t } = useTranslation();
  return <div className="grid gap-3 sm:grid-cols-2">
    <BooleanField field="show_subtotal" label={t('settings.documentLayout.totals.showSubtotal', 'Subtotal')} props={props} />
    <BooleanField field="show_discount" label={t('settings.documentLayout.totals.showDiscount', 'Discount')} props={props} />
    <BooleanField field="show_tax_breakdown" label={t('settings.documentLayout.totals.showTaxBreakdown', 'Tax breakdown')} props={props} />
    <BooleanField field="show_gross_total" label={t('settings.documentLayout.totals.showGrossTotal', 'Gross total')} props={props} />
    <BooleanField field="show_prepayments" label={t('settings.documentLayout.totals.showPrepayments', 'Prepayments')} props={props} />
    <BooleanField field="show_payment_terms" label={t('settings.documentLayout.totals.showPaymentTerms', 'Payment terms')} props={props} />
    <BooleanField field="show_bank_details" label={t('settings.documentLayout.totals.showBankDetails', 'Bank details')} props={props} />
    <SelectField field="totals_alignment" label={t('settings.documentLayout.totals.alignment', 'Totals alignment')} options={[{ value: 'left', label: t('settings.documentLayout.header.left', 'Left') }, { value: 'right', label: t('settings.documentLayout.header.right', 'Right') }]} props={props} />
  </div>;
}
