import { useEffect } from 'react';
import { AlertCircle, ScanEye, Settings, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { useAuth } from '../contexts/AuthContext';
import { aiDetectionClass, hasAiVerdict, type AiDetection } from '../utils/aiDetection';

type Props = {
  printerName: string;
  detection?: AiDetection;
  onClose: () => void;
};

export function AiDetectionModal({ printerName, detection, onClose }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const classification = aiDetectionClass(detection);
  const reason = detection?.error;
  const statusColor = {
    failure: 'text-status-error',
    warning: 'text-status-warning',
    safe: 'text-status-ok',
    error: 'text-amber-600 dark:text-amber-400',
    unknown: 'text-bambu-gray',
    idle: 'text-bambu-gray',
  }[classification];

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-lg bg-bambu-dark-secondary shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-bambu-dark-tertiary p-4">
          <div className="flex items-center gap-2">
            <ScanEye className="h-5 w-5 text-bambu-green" />
            <h2 className="text-lg font-semibold text-white">
              {t('printers.aiDetection.modalTitle', { name: printerName })}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 transition-colors hover:bg-bambu-dark-tertiary"
            aria-label={t('common.close')}
          >
            <X className="h-5 w-5 text-bambu-gray" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4 text-sm">
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-bambu-gray">{t('printers.aiDetection.currentStatus')}</span>
              <span className={`font-medium ${statusColor}`}>
                {t(`printers.aiDetection.${classification}`)}
              </span>
            </div>
            {detection && hasAiVerdict(classification) && (
              <>
                <div className="flex justify-between">
                  <span className="text-bambu-gray">{t('printers.aiDetection.score')}</span>
                  <span className="font-mono text-white">{detection.score.toFixed(3)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-bambu-gray">{t('printers.aiDetection.framesAnalyzed')}</span>
                  <span className="font-mono text-white">{detection.frame_count}</span>
                </div>
              </>
            )}
            {classification === 'error' && (
              <p className="text-bambu-gray">{t('printers.aiDetection.errorHint')}</p>
            )}
            {!detection && <p className="text-bambu-gray">{t('printers.aiDetection.idleHint')}</p>}
          </div>

          {reason && (
            <div className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 p-3 dark:border-red-500/30 dark:bg-red-500/10">
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-700 dark:text-red-400" />
              <div className="min-w-0">
                <div className="font-medium text-red-700 dark:text-red-400">
                  {t('printers.aiDetection.lastError')}
                </div>
                <p className="mt-1 break-words text-red-700/80 dark:text-red-300/80">{reason}</p>
              </div>
            </div>
          )}
        </div>

        {hasPermission('settings:read') && (
          <div className="flex justify-end border-t border-bambu-dark-tertiary p-4">
            <button
              onClick={() => navigate('/settings?tab=printers-production&sub=failure-detection')}
              className="flex items-center gap-1.5 rounded-lg bg-bambu-dark-tertiary px-3 py-1.5 text-sm font-medium text-bambu-gray transition-colors hover:text-white"
            >
              <Settings className="h-4 w-4" />
              {t('printers.aiDetection.openSettings')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
