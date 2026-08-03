import { useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation, useSearchParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { CameraWall, type CameraWallStatus } from '../components/CameraWall';
import { type CameraTileStatusMode } from '../components/CameraTile';
import { api, getStreamToken, setStreamToken } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

const KIOSK_POLL_MS = 5000;
const DEFAULT_MAX_LIVE = 4;
const DEFAULT_SNAPSHOT_SEC = 8;
const MIN_MAX_LIVE = 1;
const MAX_MAX_LIVE = 16;
const MIN_SNAPSHOT_SEC = 2;
const MAX_SNAPSHOT_SEC = 60;

function clampInt(raw: string | null, fallback: number, min: number, max: number): number {
  const n = parseInt(raw ?? '', 10);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

function fromUrlOrStorage(
  params: URLSearchParams,
  urlKey: string,
  storageKey: string,
  fallback: number,
  min: number,
  max: number,
): number {
  if (params.has(urlKey)) return clampInt(params.get(urlKey), fallback, min, max);
  return clampInt(localStorage.getItem(storageKey), fallback, min, max);
}

export function CamWallPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const { authEnabled, loading: authLoading, user } = useAuth();
  const [searchParams] = useSearchParams();

  const token = searchParams.get('token');
  const kiosk = token != null && token !== '';

  const [maxLive, setMaxLive] = useState(() =>
    fromUrlOrStorage(searchParams, 'maxLive', 'camWallMaxLive', DEFAULT_MAX_LIVE, MIN_MAX_LIVE, MAX_MAX_LIVE),
  );
  const [snapshotIntervalSec, setSnapshotIntervalSec] = useState(() =>
    fromUrlOrStorage(
      searchParams,
      'interval',
      'camWallSnapshotSec',
      DEFAULT_SNAPSHOT_SEC,
      MIN_SNAPSHOT_SEC,
      MAX_SNAPSHOT_SEC,
    ),
  );
  const [statusMode, setStatusMode] = useState<CameraTileStatusMode>(() => {
    const requested = searchParams.get('status') ?? localStorage.getItem('camWallStatusMode');
    const allowed: CameraTileStatusMode[] = kiosk ? ['off', 'compact'] : ['off', 'compact', 'full'];
    return allowed.includes(requested as CameraTileStatusMode)
      ? (requested as CameraTileStatusMode)
      : 'compact';
  });

  useEffect(() => {
    if (!kiosk) return;
    const previousToken = getStreamToken();
    setStreamToken(token);
    return () => setStreamToken(previousToken);
  }, [kiosk, token]);

  const kioskQuery = useQuery({
    queryKey: ['camwall-printers', token],
    queryFn: () => api.getCamWallPrinters(token ?? undefined),
    enabled: kiosk,
    refetchInterval: KIOSK_POLL_MS,
  });

  const printersQuery = useQuery({
    queryKey: ['printers'],
    queryFn: () => api.getPrinters(),
    enabled: !kiosk && !authLoading && (!authEnabled || user !== null),
    refetchInterval: KIOSK_POLL_MS,
  });

  const kioskStatuses = useMemo(() => {
    const map = new Map<number, CameraWallStatus | undefined>();
    for (const printer of kioskQuery.data ?? []) {
      map.set(printer.id, {
        connected: printer.connected,
        state: printer.state,
        progress: printer.progress,
        remaining_time: printer.remaining_time,
        layer_num: printer.layer_num,
        total_layers: printer.total_layers,
        hms_errors: printer.hms_errors,
      });
    }
    return map;
  }, [kioskQuery.data]);

  if (!kiosk && authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bambu-dark text-bambu-gray">
        {t('common.loading')}
      </div>
    );
  }

  if (!kiosk && authEnabled && !user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  const query = kiosk ? kioskQuery : printersQuery;
  const printers = kiosk ? (kioskQuery.data ?? []) : (printersQuery.data ?? []);

  if (query.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bambu-dark p-6 text-center">
        <p className="max-w-md text-sm text-red-400">
          {kiosk ? t('printers.camWall.page.tokenRejected') : t('printers.camWall.page.loadFailed')}
        </p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bambu-dark p-4">
      <CameraWall
        printers={printers}
        maxLive={maxLive}
        snapshotIntervalSec={snapshotIntervalSec}
        statusMode={statusMode}
        statuses={kiosk ? kioskStatuses : undefined}
        showSettings={!kiosk}
        onTileClick={kiosk ? undefined : (id) => window.open(`/camera/${id}`, `camera-${id}`)}
        onChangeMaxLive={(next) => {
          setMaxLive(next);
          localStorage.setItem('camWallMaxLive', String(next));
        }}
        onChangeSnapshotIntervalSec={(next) => {
          setSnapshotIntervalSec(next);
          localStorage.setItem('camWallSnapshotSec', String(next));
        }}
        onChangeStatusMode={(next) => {
          setStatusMode(next);
          localStorage.setItem('camWallStatusMode', next);
        }}
      />
    </div>
  );
}

export default CamWallPage;
