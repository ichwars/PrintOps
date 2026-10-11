import { useTranslation } from 'react-i18next';
import { NumberField } from '../ui';

export function DryingPresetsEditor({ value, onChange }: { value: string | null | undefined; onChange: (value: string) => void }) {
  const { t } = useTranslation();
  return (
        <div className="space-y-2">
          <p className="text-sm text-white font-medium">{t('settings.dryingPresets')}</p>
          <p className="text-xs text-bambu-gray">{t('settings.dryingPresetsDescription')}</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-bambu-gray border-b border-bambu-dark-tertiary">
                  <th className="text-left py-1.5">{t('settings.dryingFilament')}</th>
                  <th className="text-center py-1.5" colSpan={2}>AMS 2 Pro</th>
                  <th className="text-center py-1.5" colSpan={2}>AMS-HT</th>
                </tr>
              </thead>
              <tbody>
                {(() => {
                  const defaults: Record<string, { n3f: number; n3s: number; n3f_hours: number; n3s_hours: number }> = {
                    PLA: { n3f: 45, n3s: 45, n3f_hours: 12, n3s_hours: 12 },
                    PETG: { n3f: 65, n3s: 65, n3f_hours: 12, n3s_hours: 12 },
                    TPU: { n3f: 65, n3s: 75, n3f_hours: 12, n3s_hours: 18 },
                    ABS: { n3f: 65, n3s: 80, n3f_hours: 12, n3s_hours: 8 },
                    ASA: { n3f: 65, n3s: 80, n3f_hours: 12, n3s_hours: 8 },
                    PA: { n3f: 65, n3s: 85, n3f_hours: 12, n3s_hours: 12 },
                    PC: { n3f: 65, n3s: 80, n3f_hours: 12, n3s_hours: 8 },
                    PVA: { n3f: 65, n3s: 85, n3f_hours: 12, n3s_hours: 18 },
                  };
                  let presets = { ...defaults };
                  try {
                    if (value) {
                      const parsed = JSON.parse(value);
                      if (typeof parsed === 'object' && parsed !== null) {
                        presets = { ...defaults, ...parsed };
                      }
                    }
                  } catch { /* use defaults */ }

                  const updatePreset = (fil: string, key: string, value: number) => {
                    const updated = { ...presets, [fil]: { ...presets[fil], [key]: value } };
                    onChange(JSON.stringify(updated));
                  };

                  return Object.entries(presets).map(([fil, preset]) => (
                    <tr key={fil} className="border-b border-bambu-dark-tertiary/50">
                      <td className="py-1.5 pr-2 text-white font-medium">{fil}</td>
                      <td className="py-1 px-1">
                        <div className="flex items-center justify-end gap-1">
                          <NumberField min={30} max={65} value={preset.n3f}
                            onChange={e => updatePreset(fil, 'n3f', Math.max(1, parseInt(e.target.value) || 0))}
                            className="w-14 px-1.5 py-1 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-center text-xs focus:border-amber-500/50 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                          />
                          <span className="text-bambu-gray">°C</span>
                        </div>
                      </td>
                      <td className="py-1 px-1">
                        <div className="flex items-center gap-1">
                          <NumberField min={1} max={24} value={preset.n3f_hours}
                            onChange={e => updatePreset(fil, 'n3f_hours', Math.max(1, parseInt(e.target.value) || 0))}
                            className="w-14 px-1.5 py-1 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-center text-xs focus:border-amber-500/50 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                          />
                          <span className="text-bambu-gray">h</span>
                        </div>
                      </td>
                      <td className="py-1 px-1">
                        <div className="flex items-center justify-end gap-1">
                          <NumberField min={30} max={85} value={preset.n3s}
                            onChange={e => updatePreset(fil, 'n3s', Math.max(1, parseInt(e.target.value) || 0))}
                            className="w-14 px-1.5 py-1 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-center text-xs focus:border-amber-500/50 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                          />
                          <span className="text-bambu-gray">°C</span>
                        </div>
                      </td>
                      <td className="py-1 px-1">
                        <div className="flex items-center gap-1">
                          <NumberField min={1} max={24} value={preset.n3s_hours}
                            onChange={e => updatePreset(fil, 'n3s_hours', Math.max(1, parseInt(e.target.value) || 0))}
                            className="w-14 px-1.5 py-1 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-center text-xs focus:border-amber-500/50 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                          />
                          <span className="text-bambu-gray">h</span>
                        </div>
                      </td>
                    </tr>
                  ));
                })()}
              </tbody>
            </table>
          </div>
        </div>
  );
}
