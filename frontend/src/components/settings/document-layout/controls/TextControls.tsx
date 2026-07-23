import { useTranslation } from 'react-i18next';
import type { NotesRules } from '../../../../api/documentLayouts';
import { BooleanField, SelectField, type LayoutSectionProps } from './shared';

export function TextControls(props: LayoutSectionProps<NotesRules>) {
  const { t } = useTranslation();
  return <div className="grid gap-3">
    <div className="grid gap-3 sm:grid-cols-2">
      <BooleanField field="show_intro_text" label={t('settings.documentLayout.notes.showIntro', 'Introduction text')} props={props} />
      <BooleanField field="show_outro_text" label={t('settings.documentLayout.notes.showOutro', 'Closing text')} props={props} />
      <BooleanField field="show_payment_note" label={t('settings.documentLayout.notes.showPaymentNote', 'Payment note')} props={props} />
      <BooleanField field="show_legal_note" label={t('settings.documentLayout.notes.showLegalNote', 'Legal note')} props={props} />
    </div>
    <SelectField field="intro_placement" label={t('settings.documentLayout.notes.introPlacement', 'Introduction position')} options={[{ value: 'before_title', label: t('settings.documentLayout.notes.beforeTitle', 'Before title') }, { value: 'before_positions', label: t('settings.documentLayout.notes.beforePositions', 'Before positions') }]} props={props} />
    <SelectField field="outro_placement" label={t('settings.documentLayout.notes.outroPlacement', 'Closing position')} options={[{ value: 'after_positions', label: t('settings.documentLayout.notes.afterPositions', 'After positions') }, { value: 'after_totals', label: t('settings.documentLayout.notes.afterTotals', 'After totals') }]} props={props} />
    <BooleanField field="keep_with_next" label={t('settings.documentLayout.notes.keepWithNext', 'Keep heading with content')} props={props} />
  </div>;
}
