import type { CSSProperties, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { CARD_TEXT_SCALES, usePrinterCardTextScale } from '../../hooks/usePrinterCardTextScale';
import { Select } from '../../components/ui';
import { CardContent } from '../../components/Card';
import './printer-card-text-scale.css';

export function PrinterCardTextScaleControl({ disabled = false }: { disabled?: boolean }) {
  const { t } = useTranslation();
  const { scale, setScale, ready } = usePrinterCardTextScale();
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-white" title={t('printers.textScale.description')}>
      <span>{t('printers.textScale.label')}</span>
      <Select
        ariaLabel={t('printers.textScale.label')}
        value={scale}
        onValueChange={setScale}
        disabled={disabled || !ready}
        className="w-36"
        controlClassName="h-8 px-2 text-xs bg-bambu-dark"
        options={CARD_TEXT_SCALES.map(value => ({ value, label: value === 100 ? t('printers.textScale.default') : `${value}%` }))}
      />
    </div>
  );
}

/** Scope scaling to the body: portaled controls and card overlays keep their own sizing. */
export function PrinterCardScaledContent({ children, className = '' }: { children: ReactNode; className?: string }) {
  const { scale } = usePrinterCardTextScale();
  return (
    <div
      className={`flex flex-1 flex-col${scale === 100 ? '' : ' printer-card-scaled'}`}
      data-card-text-scale={scale}
      style={scale === 100 ? undefined : { '--card-text-scale': scale / 100 } as CSSProperties}
    >
      <CardContent className={className}>{children}</CardContent>
    </div>
  );
}
