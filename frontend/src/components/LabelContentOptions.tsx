import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, type SpoolLabelTemplate } from '../api/client';
import { DEFAULT_FIELDS, FIELDS, type LabelPreferences } from '../utils/labelPreferences';
import { Checkbox, LegacySelect } from './ui';


interface Props {
  source: 'inventory' | 'spoolman' | 'small-parts';
  id?: number;
  preferences: LabelPreferences;
  onChange: (value: LabelPreferences) => void;
}
export function LabelContentOptions({ source, id, preferences, onChange }: Props) {
  const { t } = useTranslation();
  const [template, setTemplate] = useState<SpoolLabelTemplate>('box_40x30');
  const [preview, setPreview] = useState<string>();
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    let url: string | undefined;
    setPreview(undefined);
    setError('');
    if (id === undefined) return;
    const timer = setTimeout(() => {
      const ids = source === 'small-parts' ? { small_part_ids: [id] } : { spool_ids: [id] };
      api.previewLabels(source, { ...ids, template, fields: preferences.fields, monochrome: preferences.monochrome, dpi: 203 })
        .then(blob => {
          if (cancelled) return;
          url = URL.createObjectURL(blob);
          setPreview(url);
        }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); if (url) URL.revokeObjectURL(url); };
  }, [source, id, template, preferences.fields, preferences.monochrome]);
  return <div className="space-y-3 px-4 py-3 border-t border-bambu-dark-tertiary">
    <fieldset className="flex flex-wrap gap-x-4 gap-y-2 text-sm text-white">
      <legend className="mb-2">{t('inventory.labels.content')}</legend>
      {FIELDS.map(([field, key]) => <Checkbox key={field} label={t(`inventory.labels.fields.${key}`)}
        checked={preferences.fields.includes(field)} onCheckedChange={checked => onChange({ ...preferences,
          fields: checked ? [...preferences.fields, field] : preferences.fields.filter(value => value !== field),
        })} />)}
      <button type="button" className="text-bambu-green" onClick={() => onChange({ ...preferences, fields: [...DEFAULT_FIELDS] })}>
        {t('inventory.labels.resetFields')}
      </button>
    </fieldset>
    <div className="flex flex-wrap gap-3 text-sm text-white">
      <label>{t('inventory.labels.format')} <LegacySelect aria-label={t('inventory.labels.format')} className="bg-bambu-dark" value={preferences.format}
        onChange={event => onChange({ ...preferences, format: event.target.value as 'pdf' | 'png' })}>
        <option value="pdf">PDF</option><option value="png">PNG / ZIP</option>
      </LegacySelect></label>
      {preferences.format === 'png' && <label>{t('inventory.labels.dpi')} <LegacySelect aria-label={t('inventory.labels.dpi')} className="bg-bambu-dark" value={preferences.dpi}
        onChange={event => onChange({ ...preferences, dpi: Number(event.target.value) as 203 | 300 | 600 })}>
        {[203, 300, 600].map(dpi => <option key={dpi} value={dpi}>{dpi} dpi</option>)}
      </LegacySelect></label>}
      <label>{t('inventory.labels.preview')} <LegacySelect aria-label={t('inventory.labels.preview')} value={template} className="bg-bambu-dark"
        onChange={event => setTemplate(event.target.value as SpoolLabelTemplate)}>
        {([['ams_holder_74x33', 'amsHolderSmall'], ['ams_holder_75x55', 'amsHolderLarge'], ['box_40x30', 'box40x30'], ['box_62x29', 'box'], ['avery_l7160', 'averyL7160'], ['avery_5160', 'avery5160']] as const).map(([value, key]) => <option key={value} value={value}>{t(`inventory.labels.templates.${key}.label`)}</option>)}
      </LegacySelect></label>
    </div>
    {preview && <img src={preview} alt={t('inventory.labels.previewAlt')} className="max-h-40 max-w-full bg-white rounded" />}
    {id === undefined && <p className="text-sm text-bambu-gray">{t('inventory.labels.previewNoSelection')}</p>}
    {error && <p role="status" className="text-sm text-red-400">{t('inventory.labels.previewError', { msg: error })}</p>}
    <p className="text-xs text-bambu-gray">{t(preferences.format === 'png' ? 'inventory.labels.pngHint' : 'inventory.labels.previewHint')}</p>
  </div>;
}
