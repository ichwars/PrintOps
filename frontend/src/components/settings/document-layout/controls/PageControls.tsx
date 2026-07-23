import { useTranslation } from 'react-i18next';
import type { PageRules } from '../../../../api/documentLayouts';
import { BooleanField, NumberField, SelectField, type LayoutSectionProps } from './shared';

export function PageControls(props: LayoutSectionProps<PageRules>) {
  const { t } = useTranslation();
  return <div className="grid gap-3">
    <SelectField field="template_key" label={t('settings.documentLayout.templates.label', 'Template')} options={[
      { value: 'classic', label: t('settings.documentLayout.templates.classic', 'Classic') },
      { value: 'modern', label: t('settings.documentLayout.templates.modern', 'Modern') },
      { value: 'compact', label: t('settings.documentLayout.templates.compact', 'Compact') },
    ]} props={props} />
    <div className="grid gap-3 sm:grid-cols-2">
      <SelectField field="page_format" label={t('settings.documentLayout.page.format', 'Paper format')} options={[{ value: 'A4', label: 'A4' }, { value: 'Letter', label: 'Letter' }]} props={props} />
      <SelectField field="orientation" label={t('settings.documentLayout.page.orientation', 'Orientation')} options={[{ value: 'portrait', label: t('settings.documentLayout.page.portrait', 'Portrait') }]} props={props} />
      <NumberField field="margin_top_mm" label={t('settings.documentLayout.page.marginTop', 'Top margin')} unit="mm" min={4} max={30} props={props} />
      <NumberField field="margin_right_mm" label={t('settings.documentLayout.page.marginRight', 'Right margin')} unit="mm" min={4} max={30} props={props} />
      <NumberField field="margin_bottom_mm" label={t('settings.documentLayout.page.marginBottom', 'Bottom margin')} unit="mm" min={4} max={30} props={props} />
      <NumberField field="margin_left_mm" label={t('settings.documentLayout.page.marginLeft', 'Left margin')} unit="mm" min={4} max={30} props={props} />
      <NumberField field="first_page_content_top_mm" label={t('settings.documentLayout.page.firstPageTop', 'First page content top')} unit="mm" min={10} max={90} props={props} />
      <NumberField field="following_page_content_top_mm" label={t('settings.documentLayout.page.followingPageTop', 'Following page content top')} unit="mm" min={10} max={60} props={props} />
    </div>
    <BooleanField field="use_first_page_letterhead" label={t('settings.documentLayout.page.firstLetterhead', 'Use first-page letterhead')} props={props} />
    <BooleanField field="use_following_page_letterhead" label={t('settings.documentLayout.page.followingLetterhead', 'Use following-page letterhead')} props={props} />
    <BooleanField field="reuse_first_letterhead" label={t('settings.documentLayout.page.reuseFirstLetterhead', 'Reuse first letterhead')} props={props} />
  </div>;
}
