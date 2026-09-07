import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { EyeOff, ScanEye } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import { aiDetectionClass } from '../utils/aiDetection';
import { AiDetectionModal } from './AiDetectionModal';

type Props = {
  printerId: number;
  printerName: string;
};

export function AiDetectionBadge({ printerId, printerName }: Props) {
  const { t } = useTranslation();
  const [showDetails, setShowDetails] = useState(false);
  const { data } = useQuery({
    queryKey: ['obico-printer-status'],
    queryFn: api.getObicoPrinterStatus,
    refetchInterval: 10000,
  });
  const monitored =
    data?.enabled &&
    (data.monitored_printers === null || data.monitored_printers.includes(printerId));
  if (!monitored) return null;

  const detection = data.per_printer[String(printerId)];
  const classification = aiDetectionClass(detection);
  const colorClass = {
    failure: 'bg-status-error/20 text-status-error',
    warning: 'bg-status-warning/20 text-status-warning',
    safe: 'bg-status-ok/20 text-status-ok',
    error: 'bg-amber-500/20 text-amber-600 dark:text-amber-400',
    unknown: 'bg-bambu-dark-tertiary text-bambu-gray',
    idle: 'bg-bambu-dark-tertiary text-bambu-gray',
  }[classification];
  const title =
    classification === 'error'
      ? t('printers.aiDetection.tooltipError', {
          reason: detection?.error ?? t('printers.aiDetection.error'),
        })
      : classification === 'unknown'
        ? t('printers.aiDetection.tooltipUnknown')
        : detection
          ? t('printers.aiDetection.tooltip', {
              status: t(`printers.aiDetection.${classification}`),
              score: detection.score.toFixed(3),
            })
          : t('printers.aiDetection.tooltipIdle');
  const Icon = classification === 'error' ? EyeOff : ScanEye;

  return (
    <>
      <button
        onClick={() => setShowDetails(true)}
        className={`flex cursor-pointer items-center gap-1 rounded-full px-2 py-1 text-xs transition-opacity hover:opacity-80 ${colorClass}`}
        title={title}
      >
        <Icon className="h-3 w-3" />
        {t(`printers.aiDetection.${classification}`)}
      </button>
      {showDetails && (
        <AiDetectionModal
          printerName={printerName}
          detection={detection}
          onClose={() => setShowDetails(false)}
        />
      )}
    </>
  );
}
