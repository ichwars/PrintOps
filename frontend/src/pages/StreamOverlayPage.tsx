import { useEffect, useMemo } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Layers, Clock, Timer, Printer } from 'lucide-react';
import { api, ApiError, withStreamToken } from '../api/client';
import { parseOverlayConfig, overlayReadings, type OverlaySize } from '../utils/streamOverlay';
import { useOverlayCameraRecovery } from '../hooks/useOverlayCameraRecovery';
import { formatDuration, formatETA, type TimeFormat } from '../utils/date';

type TFunction = (key: string, options?: Record<string, unknown>) => string;

function formatPrintName(name: string | null, gcodeFile: string | null | undefined, t: (key: string, fallback: string, opts?: Record<string, unknown>) => string): string {
  if (!name) return '';
  if (!gcodeFile) return name;
  const match = gcodeFile.match(/plate_(\d+)\.gcode/);
  if (match && parseInt(match[1], 10) > 1) {
    return `${name} — ${t('printers.plateNumber', 'Plate {{number}}', { number: match[1] })}`;
  }
  return name;
}

function getStatusText(status: { state: string | null; stg_cur_name?: string | null }, t: TFunction): string {
  if (status.stg_cur_name) return status.stg_cur_name;

  switch (status.state) {
    case 'RUNNING': return t('streamOverlay.status.printing');
    case 'PAUSE': return t('streamOverlay.status.paused');
    case 'FINISH': return t('streamOverlay.status.finished');
    case 'FAILED': return t('streamOverlay.status.failed');
    case 'IDLE': return t('streamOverlay.status.idle');
    default: return status.state || t('streamOverlay.status.unknown');
  }
}

function getSizeClasses(size: OverlaySize) {
  switch (size) {
    case 'small':
      return {
        container: 'p-3',
        text: 'text-sm',
        textLarge: 'text-lg',
        progressHeight: 'h-2',
        icon: 'w-3 h-3',
        gap: 'gap-2',
        logoHeight: 'h-12',
      };
    case 'large':
      return {
        container: 'p-6',
        text: 'text-xl',
        textLarge: 'text-3xl',
        progressHeight: 'h-4',
        icon: 'w-6 h-6',
        gap: 'gap-4',
        logoHeight: 'h-24',
      };
    case 'medium':
    default:
      return {
        container: 'p-4',
        text: 'text-base',
        textLarge: 'text-xl',
        progressHeight: 'h-3',
        icon: 'w-4 h-4',
        gap: 'gap-3',
        logoHeight: 'h-16',
      };
  }
}

export function StreamOverlayPage() {
  const { printerId } = useParams<{ printerId: string }>();
  const [searchParams] = useSearchParams();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const id = parseInt(printerId || '0', 10);

  const config = useMemo(() => parseOverlayConfig(searchParams), [searchParams]);
  const sizes = getSizeClasses(config.size);

  const token = searchParams.get('token');
  const kiosk = token != null && token !== '';
  const recovery = useOverlayCameraRecovery(config.showCamera && id > 0, `${id}:${token}:${config.fps}`);
  const { imageKey } = recovery;

  const { data: overlay } = useQuery({
    queryKey: ['overlayStatus', id, token],
    queryFn: () => api.getOverlayStatus(id, token ?? undefined),
    enabled: id > 0 && kiosk,
    refetchInterval: 2000,
  });

  const { data: printerData } = useQuery({
    queryKey: ['printer', id],
    queryFn: () => api.getPrinter(id),
    enabled: id > 0 && !kiosk,
  });

  const { data: statusData } = useQuery({
    queryKey: ['printerStatus', id],
    queryFn: () => api.getPrinterStatus(id),
    enabled: id > 0 && !kiosk,
    refetchInterval: 2000,
  });

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
    enabled: !kiosk,
  });

  const printer = useMemo(
    () =>
      kiosk
        ? overlay && { name: overlay.name, camera_rotation: overlay.camera_rotation, model: overlay.model }
        : printerData,
    [kiosk, overlay, printerData],
  );
  const status = kiosk ? overlay : statusData;
  const timeFormat: TimeFormat = (kiosk ? overlay?.time_format : settings?.time_format) || 'system';

  // WebSocket for real-time updates
  useEffect(() => {
    if (!id || kiosk) return;

    let ws: WebSocket | null = null;
    let cancelled = false;

    // GHSA-r2qv follow-up: mint a ws-token before connecting. Uses
    // api.getWebSocketToken so the JWT Authorization header rides along
    // (raw fetch+credentials:'include' would miss it — PrintOps uses
    // Bearer tokens, not cookies, for JWT auth). Auth-disabled deployments
    // succeed even without a token.
    (async () => {
      let token: string | undefined;
      try {
        const resp = await api.getWebSocketToken();
        token = resp.token;
      } catch (err) {
        // A 401 (JWT expired) / 403 (no WEBSOCKET_CONNECT permission) is an
        // auth decision — a tokenless socket would just be closed 4401, so
        // skip opening one and let the REST polling fallback keep the overlay
        // fresh. There's no reconnect loop on this page, so this is purely
        // avoiding one doomed socket per mount. A network/5xx error is not
        // auth: fall through and try anyway (auth-disabled deployments land
        // here with no token and connect fine).
        const status = err instanceof ApiError ? err.status : 0;
        if (status === 401 || status === 403) return;
      }
      if (cancelled) return;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
      const wsUrl = `${protocol}//${window.location.host}/api/v1/ws${tokenParam}`;
      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'printer_status' && data.printer_id === id) {
          queryClient.setQueryData(['printerStatus', id], data.status);
        }
      } catch {
        // Ignore parse errors
      }
    };

      ws.onerror = () => {
        // WebSocket error - polling will continue as fallback
      };
    })();

    return () => {
      cancelled = true;
      if (ws) ws.close();
    };
  }, [id, kiosk, queryClient]);

  // Update document title
  useEffect(() => {
    document.title = printer ? `${printer.name} - ${t('streamOverlay.title')}` : t('streamOverlay.title');
    return () => {
      document.title = 'PrintOps';
    };
  }, [printer, t]);

  if (!id) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <p className="text-white">{t('streamOverlay.invalidPrinterId')}</p>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <p className="text-gray-400">{t('common.loading')}</p>
      </div>
    );
  }

  const isPrinting = status.state === 'RUNNING' || status.state === 'PAUSE';
  const progress = status.progress || 0;
  const baseStreamUrl = `/api/v1/printers/${id}/camera/stream?fps=${config.fps}&t=${imageKey}`;
  const streamUrl = kiosk && token
    ? `${baseStreamUrl}&token=${encodeURIComponent(token)}`
    : withStreamToken(baseStreamUrl);

  const readings = overlayReadings(status.temperatures, kiosk ? overlay?.supports_chamber_sensor === true : status.temperatures?.chamber != null);

  return (
    <div className="min-h-screen bg-black relative overflow-hidden">
      {config.artwork !== 'none' && (
        <div data-testid="overlay-artwork" data-layout={config.artwork} aria-hidden="true"
          className="absolute inset-0 z-10 pointer-events-none border-8 border-bambu-green/40"
          style={{ background: config.artwork === 'portrait'
            ? 'linear-gradient(155deg, rgba(0,174,66,.28), transparent 40%, rgba(0,174,66,.15))'
            : 'linear-gradient(100deg, rgba(0,174,66,.25), transparent 55%, rgba(0,174,66,.15))' }}>
          <div className="absolute top-6 left-6 text-white/70 font-semibold tracking-widest text-sm">PrintOps</div>
        </div>
      )}
      {/* Camera feed - fullscreen background (optional) */}
      {config.showCamera && (
        <img
          key={imageKey}
          src={streamUrl}
          alt={t('streamOverlay.cameraStream')}
          className="absolute inset-0 w-full h-full object-contain"
          style={printer?.camera_rotation ? { transform: `rotate(${printer.camera_rotation}deg)` } : undefined}
          onError={recovery.onError}
          onLoad={recovery.onLoad}
        />
      )}

      {/* PrintOps logo - top right */}
      <a
        href="https://github.com/ichwars/PrintOps"
        target="_blank"
        rel="noopener noreferrer"
        className="absolute top-4 right-4 z-10"
      >
        <img
          src="/img/printops_logo.svg"
          alt="PrintOps"
          className={`${sizes.logoHeight} object-contain drop-shadow-lg hover:scale-105 transition-transform`}
        />
      </a>

      {/* Status overlay - bottom */}
      <div className="absolute bottom-0 left-0 right-0 z-10 bg-gradient-to-t from-black/80 via-black/60 to-transparent">
        <div className={`${sizes.container}`}>
          {/* Printer name */}
          {config.fields.includes('printer') && printer && (
            <div className={`flex items-center ${sizes.gap} mb-2`}>
              <Printer className={`${sizes.icon} text-white/70`} />
              <span className={`${sizes.text} text-white font-medium`}>{printer.name}</span>
            </div>
          )}

          {config.fields.includes('model') && printer?.model && (
            <div className={`${sizes.text} text-white/70 mb-2`}>{printer.model}</div>
          )}
          {config.fields.includes('temperatures') && readings.length > 0 && (
            <div className={`flex flex-wrap ${sizes.gap} mb-2 ${sizes.text} text-white`}>
              {readings.map(reading => (
                <div key={reading.sensor} className="flex flex-wrap gap-x-2">
                  <span className="text-white/70">{t(`streamOverlay.sensors.${reading.sensor}`)}</span>
                  <span>{reading.actual}°C{reading.target != null && ` → ${reading.target}°C`}</span>
                </div>
              ))}
            </div>
          )}

          {/* Filename */}
          {config.fields.includes('filename') && status.current_print && (
            <div className={`${sizes.textLarge} text-white font-semibold mb-2 truncate drop-shadow-md`}>
              {formatPrintName(status.current_print.replace(/\.gcode\.3mf$|\.3mf$|\.gcode$/i, ''), status.gcode_file, t)}
            </div>
          )}

          {/* Status text */}
          {config.fields.includes('status') && (
            <div className={`${sizes.text} text-white/70 mb-2`}>
              {getStatusText(status, t)}
            </div>
          )}

          {/* Progress bar */}
          {config.fields.includes('progress') && isPrinting && (
            <div className="mb-3">
              <div className={`flex items-center justify-between mb-1 ${sizes.text}`}>
                <span className="text-white/70">{t('streamOverlay.progress')}</span>
                <span className="text-white font-bold">{Math.round(progress)}%</span>
              </div>
              <div className={`w-full bg-white/20 rounded-full ${sizes.progressHeight}`}>
                <div
                  className={`bg-bambu-green ${sizes.progressHeight} rounded-full transition-all duration-500`}
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Stats row */}
          {isPrinting && (config.fields.includes('layers') || config.fields.includes('eta')) && (
            <div className={`flex items-center ${sizes.gap} flex-wrap`}>
              {/* Layers */}
              {config.fields.includes('layers') && status.layer_num != null && status.total_layers != null && status.total_layers > 0 && (
                <div className={`flex items-center ${sizes.gap} text-white/70`}>
                  <Layers className={sizes.icon} />
                  <span className={sizes.text}>
                    <span className="text-white">{status.layer_num}</span>
                    <span className="mx-1">/</span>
                    <span>{status.total_layers}</span>
                  </span>
                </div>
              )}

              {/* Remaining time */}
              {config.fields.includes('eta') && status.remaining_time != null && status.remaining_time > 0 && (
                <>
                  <div className={`flex items-center ${sizes.gap} text-white/70`}>
                    <Timer className={sizes.icon} />
                    <span className={`${sizes.text} text-white`}>
                      {formatDuration(status.remaining_time * 60)}
                    </span>
                  </div>

                  <div className={`flex items-center ${sizes.gap} text-white/70`}>
                    <Clock className={sizes.icon} />
                    <span className={`${sizes.text} text-white`}>
                      {t('streamOverlay.eta')} {formatETA(status.remaining_time, timeFormat, t)}
                    </span>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Idle state */}
          {!isPrinting && (
            <div className={`${sizes.text} text-white/70 py-2`}>
              {status.connected ? t('streamOverlay.printerIdle') : t('streamOverlay.printerOffline')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
