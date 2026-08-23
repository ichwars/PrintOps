import { useEffect } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { X, Stethoscope, CheckCircle2, XCircle, MinusCircle, Loader2, Activity } from 'lucide-react';
import { api, type CameraDiagnoseResult, type CameraDiagnoseStage } from '../api/client';

interface CameraDiagnoseModalProps {
  printerId: number;
  printerName: string | null;
  // Which player is actually rendering the feed right now, from the
  // caller's own useCameraStream state — the backend has no way to know
  // this (MSE and the MJPEG fallback both read from the same go2rtc
  // registration, see go2rtc_registry.py), so it can't be derived from
  // /camera/stream-info alone. Omitted by callers that don't use MSE.
  activePlayer?: 'mse' | 'mjpeg' | 'connecting';
  onClose: () => void;
}

function StageIcon({ status }: { status: CameraDiagnoseStage['status'] }) {
  if (status === 'ok') return <CheckCircle2 className="w-5 h-5 text-bambu-green flex-shrink-0" />;
  if (status === 'failed') return <XCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0" />;
  return <MinusCircle className="w-5 h-5 text-bambu-gray flex-shrink-0" />;
}

export function CameraDiagnoseModal({ printerId, printerName, activePlayer, onClose }: CameraDiagnoseModalProps) {
  const { t } = useTranslation();

  // Kick the diagnostic off as soon as the modal mounts. There's no
  // "Start" button — opening the modal IS the test. The mutation
  // shape is right here: we want a one-shot POST with isPending /
  // data / error, not a cached query.
  const diagnose = useMutation({
    mutationFn: () => api.diagnoseCamera(printerId),
  });

  useEffect(() => {
    diagnose.mutate();
    // Intentionally only on mount — re-running needs the user to click "Retry".
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Live pipeline/codec/bitrate readout — separate from the one-shot
  // diagnostic above, refreshed on a short interval so the numbers move
  // while the modal is open (useful to confirm a stream is really flowing,
  // not just that it was flowing when the modal opened).
  const streamInfo = useQuery({
    queryKey: ['cameraStreamInfo', printerId],
    queryFn: () => api.getCameraStreamInfo(printerId),
    refetchInterval: 2000,
  });

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const result = diagnose.data as CameraDiagnoseResult | undefined;

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-bambu-dark-secondary rounded-xl border border-bambu-dark-tertiary w-full max-w-lg flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-bambu-dark-tertiary">
          <div className="flex items-center gap-2 min-w-0">
            <Stethoscope className="w-5 h-5 text-bambu-green flex-shrink-0" />
            <h2 className="text-lg font-semibold text-white truncate">
              {t('camera.diagnose.modalTitle', { name: printerName || '' })}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-bambu-gray hover:text-white transition-colors"
            title={t('common.close')}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {diagnose.isPending && (
            <div className="flex items-center gap-2 text-bambu-gray">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>{t('camera.diagnose.running')}</span>
            </div>
          )}

          {diagnose.isError && (
            <div className="rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-300 dark:border-red-500/30 px-4 py-3 text-sm text-red-700 dark:text-red-300">
              {t('camera.diagnose.runFailed', { error: (diagnose.error as Error).message })}
            </div>
          )}

          {result && (
            <>
              {/* Per-stage results */}
              <ol className="space-y-2">
                {result.stages.map((stage) => (
                  <li
                    key={stage.name}
                    className="flex items-center gap-3 bg-bambu-dark rounded-lg px-4 py-2.5"
                  >
                    <StageIcon status={stage.status} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white">
                        {t(`camera.diagnose.stage.${stage.name}`)}
                      </div>
                      {stage.code && (
                        <div className="text-xs text-bambu-gray font-mono">{stage.code}</div>
                      )}
                    </div>
                    <div className="text-xs text-bambu-gray tabular-nums flex-shrink-0">
                      {stage.duration_ms} ms
                    </div>
                  </li>
                ))}
              </ol>

              {/* Summary + remediation */}
              <div
                className={
                  result.overall_status === 'ok'
                    ? 'rounded-lg bg-bambu-green/10 border border-bambu-green/30 px-4 py-3 text-sm text-bambu-green'
                    : 'rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-300 dark:border-red-500/30 px-4 py-3 text-sm text-red-700 dark:text-red-300'
                }
              >
                {t(`camera.diagnose.summary.${result.summary_code}`, {
                  defaultValue: t('camera.diagnose.summary.unknown_failure'),
                })}
              </div>

              {/* Metadata for support triage */}
              <div className="text-xs text-bambu-gray space-y-0.5">
                <div>
                  <span className="text-bambu-gray/60">{t('camera.diagnose.meta.protocol')}: </span>
                  <span className="font-mono">{result.protocol}</span>
                  {' • '}
                  <span className="text-bambu-gray/60">{t('camera.diagnose.meta.port')}: </span>
                  <span className="font-mono">{result.port}</span>
                  {' • '}
                  <span className="text-bambu-gray/60">{t('camera.diagnose.meta.profile')}: </span>
                  <span className="font-mono">{result.profile}</span>
                </div>
              </div>
            </>
          )}

          {/* Live pipeline/codec/bitrate — independent of the connectivity
              test above, so it's visible even while that's still running. */}
          <div className="rounded-lg bg-bambu-dark border border-bambu-dark-tertiary px-4 py-3">
            <div className="flex items-center gap-2 mb-2 text-sm font-medium text-white">
              <Activity className="w-4 h-4 text-bambu-green flex-shrink-0" />
              {t('camera.diagnose.info.title')}
            </div>
            {streamInfo.data && streamInfo.data.active ? (
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                <dt className="text-bambu-gray/60">{t('camera.diagnose.info.pipeline')}</dt>
                <dd className="font-mono text-white">
                  {t(`camera.diagnose.info.pipelineName.${streamInfo.data.pipeline}`, {
                    defaultValue: streamInfo.data.pipeline,
                  })}
                </dd>

                {activePlayer && (
                  <>
                    <dt className="text-bambu-gray/60">{t('camera.diagnose.info.player')}</dt>
                    <dd className="font-mono text-white">
                      {t(`camera.diagnose.info.playerName.${activePlayer}`)}
                    </dd>
                  </>
                )}

                {streamInfo.data.codec && (
                  <>
                    <dt className="text-bambu-gray/60">{t('camera.diagnose.info.codec')}</dt>
                    <dd className="font-mono text-white">
                      {streamInfo.data.codec.toUpperCase()}
                      {streamInfo.data.codec_profile && ` (${streamInfo.data.codec_profile}`}
                      {streamInfo.data.codec_level && ` @ L${streamInfo.data.codec_level}`}
                      {streamInfo.data.codec_profile && ')'}
                    </dd>
                  </>
                )}

                {streamInfo.data.resolution && (
                  <>
                    <dt className="text-bambu-gray/60">{t('camera.diagnose.info.resolution')}</dt>
                    <dd className="font-mono text-white">
                      {streamInfo.data.resolution.width}×{streamInfo.data.resolution.height}
                    </dd>
                  </>
                )}

                <dt className="text-bambu-gray/60">{t('camera.diagnose.info.fps')}</dt>
                <dd className="font-mono text-white">
                  {streamInfo.data.fps_target ?? '—'} / {streamInfo.data.fps_measured?.toFixed(1) ?? '—'}
                </dd>

                {streamInfo.data.bitrate_kbps != null && (
                  <>
                    <dt className="text-bambu-gray/60">{t('camera.diagnose.info.bitrate')}</dt>
                    <dd className="font-mono text-white">{streamInfo.data.bitrate_kbps.toLocaleString()} kbps</dd>
                  </>
                )}

                {streamInfo.data.stream_uptime_seconds != null && (
                  <>
                    <dt className="text-bambu-gray/60">{t('camera.diagnose.info.uptime')}</dt>
                    <dd className="font-mono text-white">{Math.round(streamInfo.data.stream_uptime_seconds)}s</dd>
                  </>
                )}

                {streamInfo.data.go2rtc_stream && (
                  <>
                    <dt className="text-bambu-gray/60">{t('camera.diagnose.info.go2rtcStream')}</dt>
                    <dd className="font-mono text-white">{streamInfo.data.go2rtc_stream}</dd>
                  </>
                )}

                <dt className="text-bambu-gray/60">{t('camera.diagnose.info.tlsProxy')}</dt>
                <dd className="font-mono text-white">{streamInfo.data.tls_proxy ? '✓' : '—'}</dd>
              </dl>
            ) : (
              <p className="text-xs text-bambu-gray">{t('camera.diagnose.info.notActive')}</p>
            )}
          </div>
        </div>

        <div className="px-6 py-4 border-t border-bambu-dark-tertiary flex justify-end gap-2">
          <button
            onClick={() => diagnose.mutate()}
            disabled={diagnose.isPending}
            className="px-4 py-2 bg-bambu-dark hover:bg-bambu-dark-tertiary disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
          >
            {t('camera.diagnose.retry')}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-bambu-green hover:bg-bambu-green/90 text-white text-sm rounded-lg transition-colors"
          >
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  );
}
