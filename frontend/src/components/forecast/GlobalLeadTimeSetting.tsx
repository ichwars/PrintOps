import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Edit2, Info } from 'lucide-react';
import { NumberField } from '../ui';

export function GlobalLeadTimeSetting({ value, onSave }: { value: number; onSave: (v: number) => void }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [input, setInput] = useState(String(value));

  function save() {
    const v = parseInt(input, 10);
    if (isNaN(v) || v < 0) return;
    onSave(v);
    setEditing(false);
  }

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-bambu-dark-tertiary/40 rounded-lg border border-bambu-dark-tertiary text-xs text-bambu-gray">
      <Info className="w-3.5 h-3.5 flex-shrink-0" aria-label={t('forecast.globalLeadTimeHint')} />
      <span className="hidden sm:inline">{t('forecast.globalLeadTime')}:</span>
      {editing ? (
        <form className="flex items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); save(); }}>
          <NumberField
            min={0} max={365}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="w-14 px-1.5 py-0.5 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded text-sm text-white focus:outline-none focus:border-bambu-green"
            autoFocus
          />
          <span className="text-bambu-gray">d</span>
          <button type="submit" className="px-2 py-0.5 bg-bambu-green text-white text-xs rounded hover:bg-bambu-green/80">{t('forecast.save')}</button>
          <button type="button" onClick={() => setEditing(false)} className="text-xs text-bambu-gray hover:text-white">✕</button>
        </form>
      ) : (
        <div className="flex items-center gap-1.5">
          <span className="font-semibold text-white">{value}d</span>
          <button onClick={() => { setInput(String(value)); setEditing(true); }} className="p-0.5 text-bambu-gray hover:text-white rounded transition-colors">
            <Edit2 className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}
