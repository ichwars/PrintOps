import { useTranslation } from 'react-i18next';
import type { TitleRules } from '../../../../api/documentLayouts';
import { BooleanField, NumberField, SelectField, type LayoutSectionProps } from './shared';

export function TitleControls(props: LayoutSectionProps<TitleRules>) {
  const { t } = useTranslation();
  return <div className="grid gap-3">
    <BooleanField field="show_title" label={t('settings.documentLayout.titleBlock.showTitle', 'Show document title')} props={props} />
    <BooleanField field="show_document_number" label={t('settings.documentLayout.titleBlock.showDocumentNumber', 'Show document number')} props={props} />
    <BooleanField field="show_issue_date" label={t('settings.documentLayout.titleBlock.showIssueDate', 'Show issue date')} props={props} />
    <BooleanField field="show_service_date" label={t('settings.documentLayout.titleBlock.showServiceDate', 'Show service date')} props={props} />
    <BooleanField field="show_due_date" label={t('settings.documentLayout.titleBlock.showDueDate', 'Show due date')} props={props} />
    <BooleanField field="show_customer_number" label={t('settings.documentLayout.titleBlock.showCustomerNumber', 'Show customer number')} props={props} />
    <div className="grid gap-3 sm:grid-cols-2">
      <SelectField field="metadata_alignment" label={t('settings.documentLayout.titleBlock.metadataAlignment', 'Metadata alignment')} options={[{ value: 'left', label: t('settings.documentLayout.header.left', 'Left') }, { value: 'right', label: t('settings.documentLayout.header.right', 'Right') }]} props={props} />
      <NumberField field="title_spacing_mm" label={t('settings.documentLayout.titleBlock.titleSpacing', 'Title spacing')} unit="mm" min={0} max={20} props={props} />
    </div>
  </div>;
}
