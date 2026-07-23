import { useTranslation } from 'react-i18next';
import type { HeaderRules } from '../../../../api/documentLayouts';
import { BooleanField, NumberField, SelectField, type LayoutSectionProps } from './shared';

export function HeaderControls(props: LayoutSectionProps<HeaderRules>) {
  const { t } = useTranslation();
  const alignment = [{ value: 'left', label: t('settings.documentLayout.header.left', 'Left') }, { value: 'center', label: t('settings.documentLayout.header.center', 'Center') }, { value: 'right', label: t('settings.documentLayout.header.right', 'Right') }];
  return <div className="grid gap-3">
    <BooleanField field="show_logo" label={t('settings.documentLayout.header.showLogo', 'Show logo')} props={props} />
    <div className="grid gap-3 sm:grid-cols-2">
      <NumberField field="logo_width_mm" label={t('settings.documentLayout.header.logoWidth', 'Logo width')} unit="mm" min={8} max={80} props={props} />
      <SelectField field="logo_alignment" label={t('settings.documentLayout.header.logoAlignment', 'Logo alignment')} options={alignment} props={props} />
    </div>
    <BooleanField field="show_company_details" label={t('settings.documentLayout.header.showCompanyDetails', 'Show company details')} props={props} />
    <BooleanField field="show_sender_line" label={t('settings.documentLayout.header.showSenderLine', 'Show sender line')} props={props} />
    <div className="grid gap-3 sm:grid-cols-2">
      <SelectField field="recipient_window" label={t('settings.documentLayout.header.recipientWindow', 'Recipient window')} options={[alignment[0], alignment[2]]} props={props} />
      <NumberField field="recipient_top_mm" label={t('settings.documentLayout.header.recipientTop', 'Recipient top')} unit="mm" min={30} max={90} props={props} />
    </div>
  </div>;
}
