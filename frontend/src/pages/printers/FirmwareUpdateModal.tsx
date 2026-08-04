import { useState, useEffect } from 'react';
import { compareFwVersions } from '../../utils/firmwareVersion';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../contexts/AuthContext';
import { Box, AlertCircle, Loader2, Download, CheckCircle } from 'lucide-react';
import { firmwareApi } from '../../api/client';
import type { Printer, FirmwareUpdateInfo, FirmwareUploadStatus } from '../../api/client';
import { Card, CardContent } from '../../components/Card';
import { Button } from '../../components/Button';
import { useToast } from '../../contexts/ToastContext';

export function FirmwareUpdateModal({
  printer,
  firmwareInfo,
  onClose,
}: {
  printer: Printer;
  firmwareInfo: FirmwareUpdateInfo;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { hasPermission } = useAuth();
  const canUpdate = hasPermission('firmware:update');
  const [uploadStatus, setUploadStatus] = useState<FirmwareUploadStatus | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [pollInterval, setPollInterval] = useState<NodeJS.Timeout | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<string | null>(
    firmwareInfo.update_available ? firmwareInfo.latest_version : null,
  );

  // Prepare check query — runs when a version is selected and user can update
  const { data: prepareInfo, isLoading: isPreparing } = useQuery({
    queryKey: ['firmwarePrepare', printer.id, selectedVersion],
    queryFn: () => firmwareApi.prepareUpload(printer.id, selectedVersion ?? undefined),
    staleTime: 30000,
    enabled: !!selectedVersion && canUpdate && !isUploading,
  });

  // Start upload mutation
  const uploadMutation = useMutation({
    mutationFn: () => firmwareApi.startUpload(printer.id, selectedVersion ?? undefined),
    onSuccess: () => {
      setIsUploading(true);
      // Start polling for status
      const interval = setInterval(async () => {
        try {
          const status = await firmwareApi.getUploadStatus(printer.id);
          setUploadStatus(status);
          if (status.status === 'complete' || status.status === 'error') {
            clearInterval(interval);
            setPollInterval(null);
            setIsUploading(false);
            if (status.status === 'complete') {
              showToast(t('printers.firmwareModal.uploadedToast'), 'success');
              queryClient.invalidateQueries({ queryKey: ['firmwareUpdate', printer.id] });
            }
          }
        } catch {
          // Ignore errors during polling
        }
      }, 2000);
      setPollInterval(interval);
    },
    onError: (error: Error) => {
      showToast(t('printers.firmwareModal.uploadFailed', { error: error.message }), 'error');
      setIsUploading(false);
    },
  });

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [pollInterval]);

  const handleStartUpload = () => {
    setUploadStatus(null);
    uploadMutation.mutate();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <Card className="w-full max-w-md mx-4">
        <CardContent>
          <div className="flex items-start gap-3 mb-4">
            <div className={`p-2 rounded-full ${firmwareInfo.update_available ? 'bg-orange-100 dark:bg-orange-500/20' : 'bg-status-ok/20'}`}>
              {firmwareInfo.update_available
                ? <Download className="w-5 h-5 text-orange-600 dark:text-orange-400" />
                : <CheckCircle className="w-5 h-5 text-status-ok" />}
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-white">
                {firmwareInfo.update_available ? t('printers.firmwareModal.title') : t('printers.firmwareModal.titleUpToDate')}
              </h3>
              <p className="text-sm text-bambu-gray mt-1">
                {printer.name}
              </p>
            </div>
          </div>

          {/* Version Info */}
          {(() => {
            const selectedEntry = selectedVersion
              ? firmwareInfo.available_versions?.find((v) => v.version === selectedVersion)
              : null;
            const displayVersion = selectedVersion ?? firmwareInfo.latest_version;
            const displayNotes = selectedEntry?.release_notes ?? firmwareInfo.release_notes;
            const showSecondLine = !!displayVersion && displayVersion !== firmwareInfo.current_version;
            return (
              <div className="bg-bambu-dark rounded-lg p-3 mb-4">
                <div className="flex justify-between items-center text-sm">
                  <span className="text-bambu-gray">{t('printers.firmwareModal.currentVersion')}</span>
                  <span className={`font-mono ${showSecondLine ? 'text-white' : 'text-status-ok'}`}>
                    {firmwareInfo.current_version || t('common.unknown')}
                  </span>
                </div>
                {showSecondLine && (
                  <div className="flex justify-between items-center text-sm mt-1">
                    <span className="text-bambu-gray">{t('printers.firmwareModal.latestVersion')}</span>
                    <span className="text-orange-700 dark:text-orange-400 font-mono">{displayVersion}</span>
                  </div>
                )}
                {displayNotes && (
                  <details className="mt-3 text-sm" open={!showSecondLine} key={displayVersion ?? 'none'}>
                    <summary className={`cursor-pointer hover:underline ${showSecondLine ? 'text-orange-700 dark:text-orange-400' : 'text-status-ok'}`}>
                      {t('printers.firmwareModal.releaseNotes')}
                    </summary>
                    <div className="mt-2 text-bambu-gray text-xs max-h-40 overflow-y-auto whitespace-pre-wrap">
                      {displayNotes}
                    </div>
                  </details>
                )}
              </div>
            );
          })()}

          {/* Available versions list */}
          {firmwareInfo.available_versions && firmwareInfo.available_versions.length > 0 && !isUploading && uploadStatus?.status !== 'complete' && (
            <div className="mb-4">
              <div className="text-xs text-bambu-gray mb-2">{t('printers.firmwareModal.availableVersions')}</div>
              <div className="max-h-56 overflow-y-auto border border-bambu-dark-tertiary rounded-lg divide-y divide-bambu-dark-tertiary">
                {firmwareInfo.available_versions.map((v) => {
                  const isCurrent = firmwareInfo.current_version === v.version;
                  const isSelected = selectedVersion === v.version;
                  const cmp = firmwareInfo.current_version
                    ? compareFwVersions(v.version, firmwareInfo.current_version)
                    : 0;
                  const relLabel = isCurrent
                    ? t('printers.firmwareModal.currentBadge')
                    : cmp > 0
                      ? t('printers.firmwareModal.newerBadge')
                      : t('printers.firmwareModal.olderBadge');
                  const relClass = isCurrent
                    ? 'text-bambu-gray'
                    : cmp > 0
                      ? 'text-orange-700 dark:text-orange-400'
                      : 'text-blue-700 dark:text-blue-400';
                  return (
                    <button
                      key={v.version}
                      type="button"
                      disabled={!v.file_available || !canUpdate || isCurrent}
                      onClick={() => setSelectedVersion(v.version)}
                      className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between gap-2 transition-colors ${
                        isSelected ? 'bg-orange-50 dark:bg-orange-500/10' : 'hover:bg-bambu-dark'
                      } ${!v.file_available || !canUpdate || isCurrent ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-mono text-white">{v.version}</span>
                        <span className={`text-xs ${relClass}`}>{relLabel}</span>
                      </div>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        isCurrent
                          ? 'bg-blue-50 dark:bg-blue-500/15 text-blue-700 dark:text-blue-400 border border-blue-300 dark:border-blue-500/30'
                          : v.file_available
                            ? 'bg-bambu-green/15 text-bambu-green border border-bambu-green/30'
                            : 'bg-bambu-gray/10 text-bambu-gray border border-bambu-gray/30'
                      }`}>
                        {isCurrent
                          ? t('printers.firmwareModal.installed')
                          : v.file_available
                          ? t('printers.firmwareModal.usable')
                          : t('printers.firmwareModal.unavailable')}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Status / Progress (only when a version is selected) */}
          {!selectedVersion ? null : isPreparing ? (
            <div className="flex items-center gap-2 text-bambu-gray text-sm mb-4">
              <Loader2 className="w-4 h-4 animate-spin" />
              {t('printers.firmwareModal.checkingPrereqs')}
            </div>
          ) : prepareInfo && !isUploading && !uploadStatus ? (
            <div className="mb-4">
              {prepareInfo.can_proceed ? (
                <div className="flex items-center gap-2 text-bambu-green text-sm">
                  <Box className="w-4 h-4" />
                  {t('printers.firmwareModal.sdCardReady')}
                </div>
              ) : (
                <div className="space-y-1">
                  {prepareInfo.errors.map((error, i) => (
                    <div key={i} className="flex items-center gap-2 text-red-700 dark:text-red-400 text-sm">
                      <AlertCircle className="w-4 h-4 flex-shrink-0" />
                      {error}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : null}

          {/* Upload Progress */}
          {(isUploading || uploadStatus) && uploadStatus && (
            <div className="mb-4">
              <div className="flex items-center justify-between text-sm mb-1">
                <span className="text-bambu-gray capitalize">{uploadStatus.status}</span>
                <span className="text-white">{uploadStatus.progress}%</span>
              </div>
              <div className="w-full bg-bambu-dark-tertiary rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${
                    uploadStatus.status === 'error' ? 'bg-status-error' :
                    uploadStatus.status === 'complete' ? 'bg-status-ok' : 'bg-orange-500'
                  } ${uploadStatus.status === 'uploading' ? 'animate-pulse' : ''}`}
                  style={{ width: `${uploadStatus.progress}%` }}
                />
              </div>
              <p className="text-xs text-bambu-gray mt-1">{uploadStatus.message}</p>
              {uploadStatus.error && (
                <p className="text-xs text-red-700 dark:text-red-400 mt-1">{uploadStatus.error}</p>
              )}
            </div>
          )}

          {/* Success Message */}
          {uploadStatus?.status === 'complete' && (
            <div className="bg-bambu-green/10 border border-bambu-green/30 rounded-lg p-3 mb-4">
              <p className="text-sm text-bambu-green font-medium mb-2">
                {t('printers.firmwareModal.uploadedSuccess')}
              </p>
              <p className="text-xs text-bambu-gray">
                {t('printers.firmwareModal.applyInstructions')}
              </p>
              <ol className="text-xs text-bambu-gray mt-1 list-decimal list-inside space-y-1">
                <li dangerouslySetInnerHTML={{ __html: t('printers.firmwareModal.step1') }} />
                <li dangerouslySetInnerHTML={{ __html: t('printers.firmwareModal.step2') }} />
                <li dangerouslySetInnerHTML={{ __html: t('printers.firmwareModal.step3') }} />
                <li>{t('printers.firmwareModal.step4')}</li>
              </ol>
            </div>
          )}

          {/* Buttons */}
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={onClose}>
              {uploadStatus?.status === 'complete' ? t('printers.firmwareModal.done') : t('common.cancel')}
            </Button>
            {prepareInfo?.can_proceed && !isUploading && uploadStatus?.status !== 'complete' && canUpdate && (
              <Button
                onClick={handleStartUpload}
                disabled={uploadMutation.isPending}
              >
                {uploadMutation.isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    {t('printers.firmwareModal.starting')}
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4 mr-2" />
                    {t('printers.firmwareModal.uploadFirmware')}
                  </>
                )}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
