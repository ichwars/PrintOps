import { useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown, Video } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useCameraPlacementPreference, type CameraPlacement, type CameraViewPreference } from '../hooks/useCameraViewPreference';
import { openCameraWindow } from '../utils/cameraWindow';
import { Button } from './Button';

interface CameraLaunchButtonProps {
  printerId: number;
  printerName: string;
  serialNumber?: string;
  fallback?: CameraPlacement;
  contentMode: CameraViewPreference;
  ready: boolean;
  connected: boolean;
  permitted: boolean;
  onOpenEmbeddedCamera?: (id: number, name: string) => void;
  className?: string;
}

/** Placement is local and independent of the stream/snapshot content choice. */
export function CameraLaunchButton({ printerId, printerName, serialNumber, fallback = 'window', contentMode,
  ready, connected, permitted, onOpenEmbeddedCamera, className }: CameraLaunchButtonProps) {
  const { t } = useTranslation();
  const placement = useCameraPlacementPreference(serialNumber, fallback);
  const disabled = !ready || !placement.ready || !connected || !permitted;
  const [openIdentity, setOpenIdentity] = useState<string | null>(null);
  const open = openIdentity === placement.identity && !disabled;
  if (openIdentity !== null && !open) setOpenIdentity(null);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<Array<HTMLButtonElement | null>>([]);
  const menuId = useId();
  const initialFocus = useRef(0);
  const modes = ['window', 'embedded'] as const;
  const label = (mode: CameraPlacement) => t(mode === 'embedded' ? 'printers.openCameraOverlay' : 'printers.openCameraWindow');
  const close = (focus = false) => { setOpenIdentity(null); if (focus) trigger.current?.focus(); };
  useEffect(() => {
    if (!open) return;
    items.current[initialFocus.current]?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpenIdentity(null);
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);
  const launch = (mode: CameraPlacement) => {
    if (disabled) return;
    if (mode === 'embedded' && onOpenEmbeddedCamera) onOpenEmbeddedCamera(printerId, printerName);
    else openCameraWindow(printerId, contentMode); // Synchronous: preserve popup gesture and sessionStorage opener.
  };
  return <div ref={root} className="relative inline-flex shrink-0" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) close();
  }}>
    <Button variant="secondary" size="sm" disabled={disabled}
      title={!permitted ? t('printers.permission.noCamera') : label(placement.mode)} aria-label={label(placement.mode)}
      className={`${className ?? ''} rounded-r-none`} onClick={() => launch(placement.mode)}>
      <Video className="w-4 h-4" />
    </Button>
    <Button ref={trigger} variant="secondary" size="sm" disabled={disabled}
      aria-label={t('camera.choosePlacement')} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
      className="h-8 rounded-l-none border-l border-bambu-dark-tertiary px-1.5"
      onClick={() => { initialFocus.current = 0; if (open) close(); else setOpenIdentity(placement.identity); }}
      onKeyDown={event => { if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault(); initialFocus.current = event.key === 'ArrowUp' ? 1 : 0; setOpenIdentity(placement.identity);
      } }}><ChevronDown className="w-3 h-3" /></Button>
    {open && <div id={menuId} role="menu" aria-label={t('camera.choosePlacement')}
      className="absolute bottom-full left-0 z-50 mb-1 w-max max-w-[calc(100vw-2rem)] rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary p-1 shadow-xl"
      onKeyDown={event => {
        const index = items.current.indexOf(document.activeElement as HTMLButtonElement);
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); }
        else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + 2) % 2;
          items.current[next]?.focus();
        }
      }}>
      {modes.map((mode, index) => <button key={mode} ref={node => { items.current[index] = node; }}
        type="button" role="menuitemradio" aria-checked={placement.mode === mode} tabIndex={-1}
        className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm hover:bg-bambu-dark-tertiary focus:bg-bambu-dark-tertiary focus:outline-none"
        onClick={() => { if (disabled) return; placement.setPreference(mode); close(true); launch(mode); }}>
        <Check className={`h-4 w-4 shrink-0 ${placement.mode === mode ? '' : 'invisible'}`} />{label(mode)}
      </button>)}
    </div>}
  </div>;
}
