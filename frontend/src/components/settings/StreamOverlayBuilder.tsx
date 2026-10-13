import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '../../api/client';
import { CopyButton } from '../PrinterInfoModal';
import { Button, Checkbox, NumberField, Select, TextField } from '../ui';
import { buildOverlayUrl, overlayFields, parseOverlayConfig, type OverlayConfig } from '../../utils/streamOverlay';

/** Share an OBS URL without opening a camera connection until explicitly requested. */
export function StreamOverlayBuilder() {
  const { t } = useTranslation();
  const { data: printers = [] } = useQuery({ queryKey: ['printers'], queryFn: api.getPrinters });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [config, setConfig] = useState(() => parseOverlayConfig(new URLSearchParams()));
  const [token, setToken] = useState('');
  const [preview, setPreview] = useState(false);
  const printerId = selectedId ?? printers[0]?.id;
  const validToken = !token || token.startsWith('bblt_');
  const url = printerId ? buildOverlayUrl(window.location.origin, printerId, config, validToken ? token : '') : '';
  const update = (next: Partial<OverlayConfig>) => { setPreview(false); setConfig(current => ({ ...current, ...next })); };
  return (
    <section className="mt-6 border-t border-bambu-dark-tertiary pt-6" aria-label={t('streamOverlay.builder.title')}>
      <h3 className="font-semibold text-white mb-2">{t('streamOverlay.builder.title')}</h3>
      <p className="text-sm text-bambu-gray mb-4">{t('streamOverlay.builder.hint')}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label={t('streamOverlay.builder.printer')} ariaLabel={t('streamOverlay.builder.printer')} value={String(printerId ?? '')}
          options={printers.map(printer => ({ value: String(printer.id), label: printer.name }))}
          onValueChange={value => { setSelectedId(Number(value)); setPreview(false); }} />
        <Select label={t('streamOverlay.builder.size')} ariaLabel={t('streamOverlay.builder.size')} value={config.size}
          options={(['small', 'medium', 'large'] as const).map(value => ({ value, label: t(`streamOverlay.builder.${value}`) }))}
          onValueChange={size => update({ size })} />
        <Select label={t('streamOverlay.builder.artwork')} ariaLabel={t('streamOverlay.builder.artwork')} value={config.artwork}
          options={(['none', 'portrait', 'landscape'] as const).map(value => ({ value, label: t(`streamOverlay.builder.${value}`) }))}
          onValueChange={artwork => update({ artwork })} />
        <NumberField label={t('streamOverlay.builder.fps')} aria-label={t('streamOverlay.builder.fps')} value={config.fps} min={1} max={30}
          onChange={event => update({ fps: Math.min(30, Math.max(1, Number(event.target.value) || 15)) })} />
      </div>
      <div className="flex flex-wrap gap-4 my-4">
        <Checkbox checked={config.showCamera} label={t('streamOverlay.cameraStream')} onCheckedChange={showCamera => update({ showCamera })} />
        {overlayFields.map(field => (
          <Checkbox key={field} checked={config.fields.includes(field)} label={t(`streamOverlay.fields.${field}`)}
            onCheckedChange={checked => update({ fields: checked ? [...config.fields, field] : config.fields.filter(value => value !== field) })} />
        ))}
      </div>
      <TextField label={t('streamOverlay.builder.token')} aria-label={t('streamOverlay.builder.token')} value={token} type="password" autoComplete="off"
        placeholder={t('streamOverlay.builder.token')} aria-invalid={!validToken}
        className="w-full bg-bambu-dark rounded p-2 text-white border border-bambu-dark-tertiary"
        onChange={event => { setToken(event.target.value.trim()); setPreview(false); }} />
      {!validToken && <p role="alert" className="text-red-400 text-sm mt-2">{t('streamOverlay.builder.tokenHint')}</p>}
      <div className="flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <TextField label={t('streamOverlay.builder.url')} aria-label={t('streamOverlay.builder.url')} value={url} readOnly
            className="w-full bg-bambu-dark rounded p-2 mt-3 text-white border border-bambu-dark-tertiary" />
        </div>
        {url && <CopyButton value={url} />}
      </div>
      <p className="text-xs text-bambu-gray my-3">{t('streamOverlay.builder.previewHint')}</p>
      <Button type="button" disabled={!printerId || !validToken} onClick={() => setPreview(value => !value)}>
        {t(preview ? 'streamOverlay.builder.hidePreview' : 'streamOverlay.builder.showPreview')}
      </Button>
      {preview && <iframe src={url} title={t('streamOverlay.title')} className="w-full h-80 rounded mt-4 border border-bambu-dark-tertiary" />}
    </section>
  );
}
