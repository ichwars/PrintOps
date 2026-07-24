import { useTranslation } from 'react-i18next';
import type { PositionRules, TechnicalRules } from '../../../../api/documentLayouts';
import { BooleanField, SelectField, type LayoutSectionProps } from './shared';

export interface PositionControlsProps { positions: LayoutSectionProps<PositionRules>; technical: LayoutSectionProps<TechnicalRules>; }

export function PositionControls({ positions, technical }: PositionControlsProps) {
  const { t } = useTranslation();
  return <div className="grid gap-3">
    <SelectField field="table_style" label={t('settings.documentLayout.positions.tableStyle', 'Table density')} options={[
      { value: 'compact', label: t('settings.documentLayout.positions.compact', 'Compact') },
      { value: 'standard', label: t('settings.documentLayout.positions.standard', 'Standard') },
      { value: 'spacious', label: t('settings.documentLayout.positions.spacious', 'Spacious') },
    ]} props={positions} />
    <div className="grid gap-3 sm:grid-cols-2">
      <BooleanField field="show_position_number" label={t('settings.documentLayout.positions.showPositionNumber', 'Position number')} props={positions} />
      <BooleanField field="show_description" label={t('settings.documentLayout.positions.showDescription', 'Description')} props={positions} />
      <BooleanField field="show_quantity" label={t('settings.documentLayout.positions.showQuantity', 'Quantity')} props={positions} />
      <BooleanField field="show_unit" label={t('settings.documentLayout.positions.showUnit', 'Unit')} props={positions} />
      <BooleanField field="show_unit_price" label={t('settings.documentLayout.positions.showUnitPrice', 'Unit price')} props={positions} />
      <BooleanField field="show_net_amount" label={t('settings.documentLayout.positions.showNetAmount', 'Net amount')} props={positions} />
      <BooleanField field="show_tax_rate" label={t('settings.documentLayout.positions.showTaxRate', 'Tax rate')} props={positions} />
      <BooleanField field="show_total" label={t('settings.documentLayout.positions.showTotal', 'Total')} props={positions} />
      <BooleanField field="show_secondary_description" label={t('settings.documentLayout.positions.showSecondaryDescription', 'Secondary description')} props={positions} />
      <BooleanField field="repeat_header" label={t('settings.documentLayout.positions.repeatHeader', 'Repeat table header')} props={positions} />
    </div>
    <div className="mt-2 border-t border-bambu-dark-tertiary pt-3">
      <BooleanField field="enabled" label={t('settings.documentLayout.technical.enabled', 'Show technical print data')} props={technical} />
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <BooleanField field="show_printer" label={t('settings.documentLayout.technical.showPrinter', 'Printer')} props={technical} />
        <BooleanField field="show_plate" label={t('settings.documentLayout.technical.showPlate', 'Build plate')} props={technical} />
        <BooleanField field="show_material" label={t('settings.documentLayout.technical.showMaterial', 'Material')} props={technical} />
        <BooleanField field="show_print_time" label={t('settings.documentLayout.technical.showPrintTime', 'Print time')} props={technical} />
        <BooleanField field="show_weight" label={t('settings.documentLayout.technical.showWeight', 'Weight')} props={technical} />
        <BooleanField field="show_file_name" label={t('settings.documentLayout.technical.showFileName', 'File name')} props={technical} />
      </div>
      <div className="mt-3"><SelectField field="placement" label={t('settings.documentLayout.technical.placement', 'Placement')} options={[{ value: 'position', label: t('settings.documentLayout.technical.atPosition', 'At position') }, { value: 'notes', label: t('settings.documentLayout.technical.inNotes', 'In notes') }]} props={technical} /></div>
    </div>
  </div>;
}
