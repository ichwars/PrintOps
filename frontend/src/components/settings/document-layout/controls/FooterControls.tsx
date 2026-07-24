import { useTranslation } from 'react-i18next';
import type { FooterRules } from '../../../../api/documentLayouts';
import { BooleanField, SelectField, TextField, type LayoutSectionProps } from './shared';

export function FooterControls(props: LayoutSectionProps<FooterRules>) {
  const { t } = useTranslation();
  return <div className="grid gap-3">
    <BooleanField field="enabled" label={t('settings.documentLayout.footer.enabled', 'Use footer')} props={props} />
    <SelectField field="column_layout" label={t('settings.documentLayout.footer.columnLayout', 'Footer layout')} options={[
      { value: 'one', label: t('settings.documentLayout.footer.oneColumn', 'One column') },
      { value: 'two', label: t('settings.documentLayout.footer.twoColumns', 'Two columns') },
      { value: 'three', label: t('settings.documentLayout.footer.threeColumns', 'Three columns') },
    ]} props={props} />
    <div className="grid gap-3 sm:grid-cols-2">
      <BooleanField field="show_company_data" label={t('settings.documentLayout.footer.showCompanyData', 'Company data')} props={props} />
      <BooleanField field="show_tax_data" label={t('settings.documentLayout.footer.showTaxData', 'Tax data')} props={props} />
      <BooleanField field="show_bank_data" label={t('settings.documentLayout.footer.showBankData', 'Bank details')} props={props} />
      <BooleanField field="show_alternative_payment" label={t('settings.documentLayout.footer.showAlternativePayment', 'Alternative payment details')} props={props} />
      <BooleanField field="show_additional_notes" label={t('settings.documentLayout.footer.showAdditionalNotes', 'Additional notes')} props={props} />
      <BooleanField field="show_page_numbers" label={t('settings.documentLayout.footer.showPageNumbers', 'Page numbers')} props={props} />
    </div>
    <TextField field="page_number_format" label={t('settings.documentLayout.footer.pageNumberFormat', 'Page number format')} help={t('settings.documentLayout.footer.pageNumberHint', 'Use {page} and {pages} as placeholders.')} props={props} />
  </div>;
}
