import { useTranslation } from 'react-i18next';
import type { TypographyRules } from '../../../../api/documentLayouts';
import { NumberField, TextField as LayoutTextField, type LayoutSectionProps } from './shared';

export function TypographyControls(props: LayoutSectionProps<TypographyRules>) {
  const { t } = useTranslation();
  return <div className="grid gap-3 sm:grid-cols-2">
    <LayoutTextField field="font_family" label={t('settings.documentLayout.typography.fontFamily', 'Font family')} help={t('settings.documentLayout.typography.embeddingHint', 'Only embeddable fonts may be published.')} props={props} />
    <NumberField field="base_size_pt" label={t('settings.documentLayout.typography.baseSize', 'Base font size')} unit="pt" min={7} max={16} step={0.5} props={props} />
    <NumberField field="table_size_pt" label={t('settings.documentLayout.typography.tableSize', 'Table font size')} unit="pt" min={7} max={14} step={0.5} props={props} />
    <NumberField field="metadata_size_pt" label={t('settings.documentLayout.typography.metadataSize', 'Metadata font size')} unit="pt" min={7} max={12} step={0.5} props={props} />
    <NumberField field="heading_scale" label={t('settings.documentLayout.typography.headingScale', 'Heading scale')} min={1.1} max={2} step={0.1} props={props} />
    <NumberField field="line_height" label={t('settings.documentLayout.typography.lineHeight', 'Line height')} min={1} max={2} step={0.05} props={props} />
    <NumberField field="paragraph_spacing_mm" label={t('settings.documentLayout.typography.paragraphSpacing', 'Paragraph spacing')} unit="mm" min={0} max={12} step={0.5} props={props} />
    <LayoutTextField field="accent_color" label={t('settings.documentLayout.typography.accentColor', 'Accent color')} type="color" props={props} />
    <LayoutTextField field="text_color" label={t('settings.documentLayout.typography.textColor', 'Text color')} type="color" props={props} />
    <LayoutTextField field="muted_color" label={t('settings.documentLayout.typography.mutedColor', 'Muted color')} type="color" props={props} />
  </div>;
}
