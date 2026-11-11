import { createContext, lazy, Suspense, useCallback, useContext, useEffect, useState, useSyncExternalStore, type ComponentType, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Video } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api, getAuthSessionId, subscribeAuthSession, type Printer } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useCameraOverlayStore } from '../hooks/useEmbeddedCameraSelection';
import { listenForCameraOverlay } from '../utils/cameraHandoff';
import type { EmbeddedCameraViewerProps } from './EmbeddedCameraViewer';
import { Modal } from './ui';

const CameraViewer = lazy<ComponentType<EmbeddedCameraViewerProps>>(() => import('./EmbeddedCameraViewer').then(
  ({ EmbeddedCameraViewer }) => ({ default: EmbeddedCameraViewer }),
).catch(() => ({ default: () => null })));

const LauncherContext = createContext<{ open: () => void } | null>(null);

export function CameraOverlayProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const { account: overlayAccount, app, page } = useCameraOverlayStore();
  const updateApp = app.update;
  const updatePage = page.update;
  const account = hasPermission('printers:read') ? overlayAccount : null;
  const [pickerOpen, setPickerOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useSyncExternalStore(subscribeAuthSession, getAuthSessionId);
  const printersQuery = useQuery({
    queryKey: ['camera-overlay-printers', session],
    queryFn: api.getPrinters,
    enabled: account !== null && (pickerOpen || app.serials.size > 0),
    staleTime: 0,
    gcTime: 0,
  });

  const selectPrinter = useCallback((printer: Printer) => {
    if (!printer.is_active || !printer.serial_number || !updateApp(printer.serial_number, true)) return false;
    updatePage(printer.serial_number, false);
    return true;
  }, [updateApp, updatePage]);

  const openVerified = useCallback(async (printerId: number, stillCurrent: () => boolean) => {
    if (account === null) return false;
    try {
      const printers = await queryClient.fetchQuery({
        queryKey: ['camera-overlay-printers', session],
        queryFn: api.getPrinters,
        staleTime: 0,
      });
      const printer = printers.find((entry) => entry.id === printerId);
      return printer && getAuthSessionId() === session && stillCurrent() ? selectPrinter(printer) : false;
    } catch {
      return false;
    }
  }, [account, queryClient, selectPrinter, session]);

  useEffect(() => {
    if (!account) return;
    return listenForCameraOverlay(account, openVerified);
  }, [account, openVerified]);

  useEffect(() => {
    const state = location.state;
    if (!account || state?.cameraOverlayAccount !== account || !Number.isSafeInteger(state?.cameraOverlayId)
      || state.cameraOverlayId <= 0) return;
    let current = true;
    void openVerified(state.cameraOverlayId, () => current).then(() => {
      if (current) navigate({ pathname: location.pathname, search: location.search, hash: location.hash }, { replace: true });
    });
    return () => { current = false; };
  }, [account, location, navigate, openVerified]);

  const printers = account && printersQuery.isSuccess ? printersQuery.data.filter((printer) => printer.is_active) : [];
  const cameras = printers.filter((printer) => app.serials.has(printer.serial_number));
  const title = t('printers.openCameraOverlay');
  return (
    <LauncherContext.Provider value={account ? { open: () => setPickerOpen(true) } : null}>
      {children}
      <Modal open={pickerOpen && account !== null} onClose={() => setPickerOpen(false)} title={title} closeLabel={t('common.close')}>
        {printersQuery.isPending && <p role="status">{t('common.loading')}</p>}
        {printersQuery.isError && <p role="alert">{t('printers.camWall.page.loadFailed')}</p>}
        {printersQuery.isSuccess && printers.length === 0 && <p>{t('printers.camWall.noPrinters')}</p>}
        <ul className="space-y-1">
          {printers.map((printer) => (
            <li key={printer.id}>
              <button type="button" className="w-full rounded px-3 py-2 text-left hover:bg-bambu-dark-tertiary"
                onClick={() => { if (selectPrinter(printer)) setPickerOpen(false); }}>
                {printer.name}
              </button>
            </li>
          ))}
        </ul>
      </Modal>
      {cameras.length > 0 && (
        <Suspense fallback={null}>
          {cameras.map((printer, index) => (
            <CameraViewer key={printer.serial_number} printerId={printer.id} printerName={printer.name}
              viewerIndex={index} onClose={() => app.update(printer.serial_number, false)} />
          ))}
        </Suspense>
      )}
    </LauncherContext.Provider>
  );
}

export function CameraOverlayButton({ className = '' }: { className?: string }) {
  const launcher = useContext(LauncherContext);
  const { t } = useTranslation();
  if (!launcher) return null;
  const title = t('printers.openCameraOverlay');
  return (
    <button type="button" className={`rounded p-2 text-bambu-gray-light hover:bg-bambu-dark-tertiary hover:text-white ${className}`}
      aria-label={title} title={title} aria-haspopup="dialog" onClick={launcher.open}>
      <Video className="h-5 w-5" />
    </button>
  );
}
