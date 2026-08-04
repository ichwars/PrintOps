import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { formatPrintName } from '../../utils/printName';
import { BED_TEMP_DEFAULTS, CHAMBER_TEMP_DEFAULTS, FAN_SPEED_DEFAULTS, NOZZLE_TEMP_DEFAULTS } from '../../utils/temperatureFanPresets';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../contexts/AuthContext';
import { useNavigate } from 'react-router';
import { api, firmwareApi } from '../../api/client';
import type { PrinterStatus, AMSUnit, SmartPlug } from '../../api/client';
import type { HeaterSensorKind } from '../../api/client';
import { useToast } from '../../contexts/ToastContext';
import { getAmsLabel } from '../../utils/amsHelpers';
import { filterCompatibleQueueItems } from '../../utils/printer';
import { getPrinterControlCapability, isCloudControlCandidate, isCloudControlUncertain, isPrintOpsCloudControlImplemented, type PrinterControlAction } from '../../utils/printerControlCapabilities';
import { mapModelCode } from './printer-status';
import { DRYING_PRESETS, DRY_START_CONFIRM_MS } from './printer-card-constants';
import type { PrinterCardProps } from './printer-card-types';

export function usePrinterCardModel(props: PrinterCardProps) {
  const {
  printer,
  hideIfDisconnected,
  maintenanceInfo,
  viewMode = 'expanded',
  cardSize = 2,
  amsThresholds,
  spoolmanEnabled = false,
  linkedSpools,
  spoolmanUrl,
  spoolmanSyncMode,
  onGetAssignment,
  onUnassignSpool,
  spoolmanSpools,
  spoolmanSlotAssignments,
  spoolmanLoading = false,
  onUnassignSpoolmanSpool,
  timeFormat = 'system',
  cameraViewMode = 'window',
  onOpenEmbeddedCamera,
  checkPrinterFirmware = true,
  dryingPresets = DRYING_PRESETS,
  requirePlateClear = false,
  selectionMode = false,
  isSelected = false,
  onToggleSelect,
  onOpenCompactCard,
  nozzleTempPresets = NOZZLE_TEMP_DEFAULTS,
  bedTempPresets = BED_TEMP_DEFAULTS,
  chamberTempPresets = CHAMBER_TEMP_DEFAULTS,
  fanSpeedPresets = FAN_SPEED_DEFAULTS,
} = props;

const { t } = useTranslation();

const queryClient = useQueryClient();

const navigate = useNavigate();

const { showToast } = useToast();

const { hasPermission } = useAuth();

const [showMenu, setShowMenu] = useState(false);

const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

const [deleteArchives, setDeleteArchives] = useState(true);

const [showEditModal, setShowEditModal] = useState(false);

const [showFileManager, setShowFileManager] = useState(false);

const [showMQTTDebug, setShowMQTTDebug] = useState(false);

const [showControlMatrix, setShowControlMatrix] = useState(false);

const [showPowerOnConfirm, setShowPowerOnConfirm] = useState(false);

const [showPowerOffConfirm, setShowPowerOffConfirm] = useState(false);

const [haToggleConfirm, setHaToggleConfirm] = useState<SmartPlug | null>(null);

const [showHMSModal, setShowHMSModal] = useState(false);

// #1762: AMS Filament Backup status / control modal — opens from the badge.
const [amsBackupModalOpen, setAmsBackupModalOpen] = useState(false);

const [showStopConfirm, setShowStopConfirm] = useState(false);

const [showPauseConfirm, setShowPauseConfirm] = useState(false);

const [showSpeedMenu, setShowSpeedMenu] = useState<number | null>(null);

const [showAirductMenu, setShowAirductMenu] = useState<number | null>(null);

const [showBedJogMenu, setShowBedJogMenu] = useState<number | null>(null);

const [statusControlMenu, setStatusControlMenu] = useState<string | null>(null);

const [bedJogStep, setBedJogStep] = useState<number>(10);

const [showNotHomedModal, setShowNotHomedModal] = useState<null | { distance: number }>(null);

const [showResumeConfirm, setShowResumeConfirm] = useState(false);

const [showSkipObjectsModal, setShowSkipObjectsModal] = useState(false);

const [showUploadForPrint, setShowUploadForPrint] = useState(false);

const [showPrinterInfo, setShowPrinterInfo] = useState(false);

const [showDiagnostic, setShowDiagnostic] = useState(false);

const closePrinterInfo = useCallback(() => setShowPrinterInfo(false), []);

const [printAfterUpload, setPrintAfterUpload] = useState<{ id: number; filename: string } | null>(null);

// AMS drying popover state: which AMS unit has the popover open
const [dryingPopoverAmsId, setDryingPopoverAmsId] = useState<number | null>(null);

const [dryingPopoverModuleType, setDryingPopoverModuleType] = useState<string>('n3f');

const [dryingFilament, setDryingFilament] = useState('PLA');

const [dryingTemp, setDryingTemp] = useState(50);

const [dryingDuration, setDryingDuration] = useState(4);

const [dryingRotateTray, setDryingRotateTray] = useState(false);

const [dryingPopoverPos, setDryingPopoverPos] = useState<{ top: number; left: number } | null>(null);

const [dryStartWatch, setDryStartWatch] = useState<{ amsId: number } | null>(null);

const [isDraggingFile, setIsDraggingFile] = useState(false);

const [isDropUploading, setIsDropUploading] = useState(false);

const printerActionsMenuRef = useRef<HTMLDivElement>(null);

const dragCounterRef = useRef(0);

const [amsHistoryModal, setAmsHistoryModal] = useState<{
    amsId: number;
    amsLabel: string;
    mode: 'humidity' | 'temperature';
  } | null>(null);

const [heaterHistoryModal, setHeaterHistoryModal] = useState<{
    initialKind: HeaterSensorKind;
    availableKinds: HeaterSensorKind[];
  } | null>(null);

const [linkSpoolModal, setLinkSpoolModal] = useState<{
    tagUid: string;
    trayUuid: string;
    printerId: number;
    amsId: number;
    trayId: number;
  } | null>(null);

const [assignSpoolModal, setAssignSpoolModal] = useState<{
    printerId: number;
    amsId: number;
    trayId: number;
    trayInfo: { type: string; color: string; location: string; material?: string; profile?: string };
  } | null>(null);

const [configureSlotModal, setConfigureSlotModal] = useState<{
    amsId: number;
    trayId: number;
    trayCount: number;
    trayType?: string;
    trayColor?: string;
    traySubBrands?: string;
    trayInfoIdx?: string;
    extruderId?: number;
    caliIdx?: number | null;
    savedPresetId?: string;
  } | null>(null);

const [showFirmwareModal, setShowFirmwareModal] = useState(false);

const [plateCheckResult, setPlateCheckResult] = useState<{
    is_empty: boolean;
    confidence: number;
    difference_percent: number;
    message: string;
    debug_image_url?: string;
    needs_calibration: boolean;
    light_warning?: boolean;
    reference_count?: number;
    max_references?: number;
    roi?: { x: number; y: number; w: number; h: number };
  } | null>(null);

const [isCheckingPlate, setIsCheckingPlate] = useState(false);

const [isCalibrating, setIsCalibrating] = useState(false);

const [editingRoi, setEditingRoi] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

const [isSavingRoi, setIsSavingRoi] = useState(false);

const [plateCheckLightWasOff, setPlateCheckLightWasOff] = useState(false);

const { data: status } = useQuery({
    queryKey: ['printerStatus', printer.id],
    queryFn: () => api.getPrinterStatus(printer.id),
    refetchInterval: 30000, // Fallback polling, WebSocket handles real-time
  });

// Check for firmware updates (cached for 5 minutes, can be disabled in settings)
const { data: firmwareInfo } = useQuery({
    queryKey: ['firmwareUpdate', printer.id],
    queryFn: () => firmwareApi.checkPrinterUpdate(printer.id),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
    enabled: checkPrinterFirmware && hasPermission('firmware:read'),
  });

// Collect unique tray_info_idx values for cloud filament info lookup
const trayInfoIds = useMemo(() => {
    const ids = new Set<string>();
    if (status?.ams) {
      for (const ams of status.ams) {
        for (const tray of ams.tray || []) {
          if (tray.tray_info_idx) {
            ids.add(tray.tray_info_idx);
          }
        }
      }
    }
    for (const vt of status?.vt_tray ?? []) {
      if (vt.tray_info_idx) ids.add(vt.tray_info_idx);
    }
    if (status?.nozzle_rack) {
      for (const slot of status.nozzle_rack) {
        if (slot.filament_id) {
          ids.add(slot.filament_id);
        }
      }
    }
    return Array.from(ids);
  }, [status?.ams, status?.vt_tray, status?.nozzle_rack]);

// Collect loaded filament types for queue widget filtering
const loadedFilamentTypes = useMemo(() => {
    const types = new Set<string>();
    if (status?.ams) {
      for (const ams of status.ams) {
        for (const tray of ams.tray || []) {
          if (tray.tray_type) types.add(tray.tray_type.toUpperCase());
        }
      }
    }
    for (const vt of status?.vt_tray ?? []) {
      if (vt.tray_type) types.add(vt.tray_type.toUpperCase());
    }
    return types;
  }, [status?.ams, status?.vt_tray]);

// Collect loaded filament type+color pairs for queue widget override matching
  // Format: "TYPE:rrggbb" (e.g., "PETG:ffffff") — mirrors backend _count_override_color_matches()
const loadedFilaments = useMemo(() => {
    const filaments = new Set<string>();
    if (status?.ams) {
      for (const ams of status.ams) {
        for (const tray of ams.tray || []) {
          if (tray.tray_type && tray.tray_color) {
            const color = tray.tray_color.replace('#', '').toLowerCase().slice(0, 6);
            filaments.add(`${tray.tray_type.toUpperCase()}:${color}`);
          }
        }
      }
    }
    for (const vt of status?.vt_tray ?? []) {
      if (vt.tray_type && vt.tray_color) {
        const color = vt.tray_color.replace('#', '').toLowerCase().slice(0, 6);
        filaments.add(`${vt.tray_type.toUpperCase()}:${color}`);
      }
    }
    return filaments;
  }, [status?.ams, status?.vt_tray]);

const loadedVariants = useMemo(() => {
    const variants = new Set<string>();
    if (status?.ams) {
      for (const ams of status.ams) {
        for (const tray of ams.tray || []) {
          if (tray.tray_type && tray.tray_color) {
            const color = tray.tray_color.replace('#', '').toLowerCase().slice(0, 6);
            variants.add(`${tray.tray_type.toUpperCase()}:${color}:${tray.tray_info_idx || ''}`);
          }
        }
      }
    }
    for (const vt of status?.vt_tray ?? []) {
      if (vt.tray_type && vt.tray_color) {
        const color = vt.tray_color.replace('#', '').toLowerCase().slice(0, 6);
        variants.add(`${vt.tray_type.toUpperCase()}:${color}:${vt.tray_info_idx || ''}`);
      }
    }
    return variants;
  }, [status?.ams, status?.vt_tray]);

// Fetch cloud filament info for tooltips (name includes color, also has K value)
const { data: filamentInfo } = useQuery({
    queryKey: ['filamentInfo', trayInfoIds],
    queryFn: () => api.getFilamentInfo(trayInfoIds),
    enabled: trayInfoIds.length > 0,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

// Fetch slot preset mappings (stores preset name for user-configured slots)
const { data: slotPresets } = useQuery({
    queryKey: ['slotPresets', printer.id],
    queryFn: () => api.getSlotPresets(printer.id),
    staleTime: 2 * 60 * 1000, // 2 minutes
  });

// Fetch plate list for the archive linked to the active print (#881 follow-up).
  // Only queried when there's a running print backed by an archive; shared
  // React Query cache with the Queue / Archives pages keeps it cheap.
const activeArchiveId =
    (status?.state === 'RUNNING' || status?.state === 'PAUSE') ? status?.current_archive_id ?? null : null;

const { data: activeArchivePlates } = useQuery({
    queryKey: ['archive-plates', activeArchiveId],
    queryFn: () => api.getArchivePlates(activeArchiveId!),
    enabled: activeArchiveId != null,
    staleTime: 5 * 60 * 1000,
  });

const activePlateLabel = (() => {
    if (!activeArchivePlates?.is_multi_plate || status?.current_plate_id == null) return null;
    const plate = activeArchivePlates.plates.find(p => p.index === status.current_plate_id);
    return plate?.name || t('printers.plateNumber', 'Plate {{number}}', { number: status.current_plate_id });
  })();

// Fetch user-defined AMS friendly names from the database
const { data: amsLabels, refetch: refetchAmsLabels } = useQuery({
    queryKey: ['amsLabels', printer.id],
    queryFn: () => api.getAmsLabels(printer.id),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

// Cache WiFi signal to prevent it disappearing on updates
const [cachedWifiSignal, setCachedWifiSignal] = useState<number | null>(null);

useEffect(() => {
    if (status?.wifi_signal != null) {
      setCachedWifiSignal(status.wifi_signal);
    }
  }, [status?.wifi_signal]);

const wifiSignal = status?.wifi_signal ?? cachedWifiSignal;

// Cache connected state to prevent flicker when status briefly becomes undefined
const cachedConnected = useRef<boolean | undefined>(undefined);

useEffect(() => {
    if (status?.connected !== undefined) {
      cachedConnected.current = status.connected;
    }
  }, [status?.connected]);

const isConnected = status?.connected ?? cachedConnected.current;

// Cache ams_extruder_map to prevent L/R indicators bouncing on updates
const cachedAmsExtruderMap = useRef<Record<string, number>>({});

useEffect(() => {
    if (status?.ams_extruder_map && Object.keys(status.ams_extruder_map).length > 0) {
      cachedAmsExtruderMap.current = status.ams_extruder_map;
    }
  }, [status?.ams_extruder_map]);

const amsExtruderMap = (status?.ams_extruder_map && Object.keys(status.ams_extruder_map).length > 0)
    ? status.ams_extruder_map
    : cachedAmsExtruderMap.current;

// Cache AMS data to prevent it disappearing on idle/offline printers
const cachedAmsData = useRef<AMSUnit[]>([]);

useEffect(() => {
    if (status?.ams && status.ams.length > 0) {
      cachedAmsData.current = status.ams;
    }
  }, [status?.ams]);

const amsData = (status?.ams && status.ams.length > 0) ? status.ams : cachedAmsData.current;

useEffect(() => {
    if (!dryStartWatch) return;
    const unit = amsData.find(a => a.id === dryStartWatch.amsId);
    if (unit && (unit.dry_time > 0 || unit.dry_status > 0)) {
      setDryStartWatch(null);
    }
  }, [dryStartWatch, amsData]);

useEffect(() => {
    if (!dryStartWatch) return;
    const timer = setTimeout(() => {
      setDryStartWatch(null);
      showToast(t('printers.drying.toastNotStarted'), 'error');
    }, DRY_START_CONFIRM_MS);
    return () => clearTimeout(timer);
  }, [dryStartWatch, showToast, t]);

// Cache tray_now to prevent flickering when undefined values come in
  // Valid tray IDs: 0-253 for AMS, 254 for external spool
  // tray_now=255 means "no tray loaded" (Bambu protocol sentinel) — never active
const cachedTrayNow = useRef<number | undefined>(undefined);

const currentTrayNow = status?.tray_now;

// Update cache: 255 means "no tray" so clear cache; valid values get cached
if (currentTrayNow !== undefined && currentTrayNow !== 255) {
    cachedTrayNow.current = currentTrayNow;
  } else if (currentTrayNow === 255) {
    cachedTrayNow.current = undefined;
  }

const effectiveTrayNow = (currentTrayNow !== undefined && currentTrayNow !== 255)
    ? currentTrayNow
    : cachedTrayNow.current;

const expectedTray = status?.expected_tray ?? null;

const previousTray = status?.previous_tray ?? null;

const formatRunoutSlotLabel = (globalId: number | null): string | null => {
    if (globalId === null) return null;
    if (globalId === 254) return t('printers.expectedSlot.external');
    if (globalId >= 128 && globalId <= 135) {
      return amsLabels?.[globalId] || getAmsLabel(globalId, 1);
    }
    const amsId = Math.floor(globalId / 4);
    const slot = globalId % 4;
    const amsName = amsLabels?.[amsId] || getAmsLabel(amsId, 4);
    return t('printers.expectedSlot.label', { ams: amsName, slot: slot + 1 });
  };

const runoutGuidance = status?.state === 'PAUSE'
    ? {
        expectedSlotLabel: formatRunoutSlotLabel(expectedTray),
        ranOutSlotLabel: formatRunoutSlotLabel(previousTray),
      }
    : null;

// Fetch smart plug for this printer
const { data: smartPlug } = useQuery({
    queryKey: ['smartPlugByPrinter', printer.id],
    queryFn: () => api.getSmartPlugByPrinter(printer.id),
  });

// Fetch script plugs for this printer (for multi-device control)
const { data: scriptPlugs } = useQuery({
    queryKey: ['scriptPlugsByPrinter', printer.id],
    queryFn: () => api.getScriptPlugsByPrinter(printer.id),
  });

// Fetch smart plug status if plug exists (faster refresh for energy monitoring)
const { data: plugStatus } = useQuery({
    queryKey: ['smartPlugStatus', smartPlug?.id],
    queryFn: () => smartPlug ? api.getSmartPlugStatus(smartPlug.id) : null,
    enabled: !!smartPlug,
    refetchInterval: 10000, // 10 seconds for real-time power display
  });

// Fetch queue count for this printer
const { data: queueItems } = useQuery({
    queryKey: ['queue', printer.id, 'pending'],
    queryFn: () => api.getQueue(printer.id, 'pending'),
  });

// Filter queue items by filament compatibility (same logic as PrinterQueueWidget)
  // so the badge only shows on printers that can actually run the queued jobs.
  // An empty Set means no filaments are loaded — jobs requiring specific types are incompatible.
const queueCount = useMemo(() => {
    if (!queueItems?.length) return 0;
    return filterCompatibleQueueItems(queueItems, loadedFilamentTypes, loadedFilaments, loadedVariants).length;
  }, [queueItems, loadedFilamentTypes, loadedFilaments, loadedVariants]);

// Fetch currently printing queue item to show who started it (Issue #206)
const { data: printingQueueItems } = useQuery({
    queryKey: ['queue', printer.id, 'printing'],
    queryFn: () => api.getQueue(printer.id, 'printing'),
    enabled: status?.state === 'RUNNING',
  });

// Fetch reprint user info (for prints started via Reprint, not queue - Issue #206)
const { data: reprintUser } = useQuery({
    queryKey: ['currentPrintUser', printer.id],
    queryFn: () => api.getCurrentPrintUser(printer.id),
    enabled: status?.state === 'RUNNING',
  });

// Combine both sources: queue item user takes precedence, then reprint user
const currentPrintUser = printingQueueItems?.[0]?.created_by_username || reprintUser?.username;

// Fetch last completed print for this printer
const { data: lastPrints } = useQuery({
    queryKey: ['archives', printer.id, 'last'],
    queryFn: () => api.getArchives(printer.id, 1, 0),
    enabled: status?.connected && status?.state !== 'RUNNING',
  });

const lastPrint = lastPrints?.[0];

const isPrintingOrPaused = status?.state === 'RUNNING' || status?.state === 'PAUSE';

const needsPlateClear = requirePlateClear && status?.awaiting_plate_clear === true;

const showClearPlateButton = status?.connected && needsPlateClear && !isPrintingOrPaused;

const hasPrinterControlPermission = hasPermission('printers:control');

const localPrinterControlUnavailable = status?.connected === true && status.developer_mode === false;

const cloudControlConfigured = status?.control_connection?.cloud_configured === true;

const activeControlPath = status?.control_connection?.active_control_path ?? 'none';

const canUseLocalPrinterControl = status?.connected === true && hasPrinterControlPermission && !localPrinterControlUnavailable;

const canUsePrinterControlAction = (action: PrinterControlAction) => (
    canUseLocalPrinterControl
    || (
      status?.connected === true
      && hasPrinterControlPermission
      && localPrinterControlUnavailable
      && cloudControlConfigured
      && isPrintOpsCloudControlImplemented(action)
    )
  );

const canUseTemperatureControls = canUsePrinterControlAction('temperature');

const canUseFanControls = canUsePrinterControlAction('fan');

const canUseLightControl = canUsePrinterControlAction('light');

const getLocalPrinterControlUnavailableTitle = (action: PrinterControlAction = 'status') => {
    const capability = getPrinterControlCapability(action);
    const actionLabel = t(capability.labelKey, capability.labelFallback);
    if (isPrintOpsCloudControlImplemented(action)) {
      return t(
        'printers.localControlUnavailableCloudCandidate',
        '{{action}} wird bei fehlender LAN-Steuerung über Bambu Cloud gesendet.',
        { action: actionLabel },
      );
    }
    if (isCloudControlCandidate(action)) {
      return t(
        'printers.localControlUnavailableCloudNotImplemented',
        '{{action}} ist über Bambu Cloud grundsätzlich möglich, ist in PrintOps aber noch nicht als Cloud-Steuerung umgesetzt. Bitte Entwickler-LAN-Modus am Drucker aktivieren.',
        { action: actionLabel },
      );
    }
    if (isCloudControlUncertain(action)) {
      return t(
        'printers.localControlUnavailableCloudUncertain',
        '{{action}} benötigt in PrintOps aktuell lokale Steuerung. Cloud-Unterstützung ist für diese Funktion noch nicht belastbar bestätigt.',
        { action: actionLabel },
      );
    }
    return t(
      'printers.localControlUnavailableLocalOnly',
      '{{action}} benötigt lokale Steuerung. Bitte Entwickler-LAN-Modus am Drucker aktivieren und IP-Adresse sowie Zugangscode prüfen.',
      { action: actionLabel },
    );
  };

const getPrinterControlUnavailableTitle = (action: PrinterControlAction = 'status') => (
    !hasPrinterControlPermission
      ? t('printers.permission.noControl')
      : localPrinterControlUnavailable
        ? getLocalPrinterControlUnavailableTitle(action)
        : !status?.connected
          ? t('printers.connection.offline')
          : undefined
  );

const getControlActionTitle = (action: PrinterControlAction, localTitle?: string) => {
    if (canUseLocalPrinterControl) return localTitle;
    if (canUsePrinterControlAction(action)) {
      const capability = getPrinterControlCapability(action);
      return t(
        'printers.cloudControlActionTitle',
        '{{action}} wird über Bambu Cloud gesendet, weil die lokale LAN-Steuerung nicht verfügbar ist.',
        { action: t(capability.labelKey, capability.labelFallback) },
      );
    }
    return getPrinterControlUnavailableTitle(action);
  };

const canUsePrinterControl = canUseLocalPrinterControl;

useEffect(() => {
    if (canUsePrinterControl || canUseTemperatureControls || canUseFanControls || canUseLightControl) return;
    setStatusControlMenu(null);
    setShowAirductMenu(current => current === printer.id ? null : current);
    setShowBedJogMenu(current => current === printer.id ? null : current);
    setShowSpeedMenu(current => current === printer.id ? null : current);
    setDryingPopoverAmsId(null);
  }, [canUseFanControls, canUseLightControl, canUsePrinterControl, canUseTemperatureControls, printer.id]);

const activePrintName = status?.current_print && isPrintingOrPaused
    ? formatPrintName(status.subtask_name || status.current_print || null, status.gcode_file, t, activePlateLabel)
    : null;

const [retainedPrintJob, setRetainedPrintJob] = useState<{ name: string; coverUrl: string | null } | null>(null);

useEffect(() => {
    if (activePrintName) {
      setRetainedPrintJob({ name: activePrintName, coverUrl: status?.cover_url ?? null });
    } else if (!needsPlateClear) {
      setRetainedPrintJob(null);
    }
  }, [activePrintName, needsPlateClear, status?.cover_url]);

const plateStatus = (() => {
    if (!requirePlateClear || !status?.connected) return null;
    if (isPrintingOrPaused) {
      return {
        label: t('printers.plateStatus.inUse'),
        className: 'bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-400',
      };
    }
    if (status.awaiting_plate_clear) {
      return {
        label: t('printers.plateStatus.notCleared'),
        className: 'bg-yellow-100 dark:bg-yellow-500/20 text-yellow-700 dark:text-yellow-400',
      };
    }
    return {
      label: t('printers.plateStatus.cleared'),
      className: 'bg-status-ok/20 text-status-ok',
    };
  })();

// Determine if this card should be hidden (use cached connected state to prevent flicker)
const shouldHide = hideIfDisconnected && isConnected === false;

const deleteMutation = useMutation({
    mutationFn: (options: { deleteArchives: boolean }) =>
      api.deletePrinter(printer.id, options.deleteArchives),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] });
      queryClient.invalidateQueries({ queryKey: ['archives'] });
      queryClient.invalidateQueries({ queryKey: ['maintenanceOverview'] });
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToDelete'), 'error'),
  });

const connectMutation = useMutation({
    mutationFn: () => api.connectPrinter(printer.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
    },
  });

const forceRefreshMutation = useMutation({
    mutationFn: () => api.refreshPrinterStatus(printer.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
      showToast(t('printers.forceRefreshSuccess'), 'success');
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

const unlinkSpoolMutation = useMutation({
    mutationFn: (spoolId: number) => api.unlinkSpool(spoolId),
    onSuccess: (result) => {
      showToast(t('spoolman.unlinkSuccess') || result?.message, 'success');
      queryClient.invalidateQueries({ queryKey: ['linked-spools'] });
      queryClient.invalidateQueries({ queryKey: ['unlinked-spools'] });
      queryClient.invalidateQueries({ queryKey: ['spoolman-slot-assignments'] });
    },
    onError: (error: Error) => {
      showToast(error.message || t('spoolman.unlinkFailed'), 'error');
    },
  });

// AMS drying mutations
const startDryingMutation = useMutation({
    mutationFn: ({ amsId, temp, duration, filament, rotateTray }: { amsId: number; temp: number; duration: number; filament: string; rotateTray: boolean }) =>
      api.startDrying(printer.id, amsId, temp, duration, filament, rotateTray),
    onSuccess: (_data, { amsId }) => {
      setDryingPopoverAmsId(null);
      setDryStartWatch({ amsId });
      showToast(t('printers.drying.toastStarted'), 'success');
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

const stopDryingMutation = useMutation({
    mutationFn: (amsId: number) => api.stopDrying(printer.id, amsId),
    onSuccess: () => {
      setDryStartWatch(null);
      showToast(t('printers.drying.toastStopped'), 'success');
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

// AMS Filament Backup toggle (auto-switch to a backup spool when one runs out).
  // Invalidate BOTH printer-status cache keys — the codebase has two conventions
  // ('printerStatus' camelCase + 'printer-status' kebab-case used by PrintModal /
  // useMultiPrinterFilamentMapping). Hitting only one would leave PrintModal
  // showing the old backup state until the user reopens it.
const setAmsBackupMutation = useMutation({
    mutationFn: (enabled: boolean) => api.setAmsFilamentBackup(printer.id, enabled),
    onSuccess: (_data, enabled) => {
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
      queryClient.invalidateQueries({ queryKey: ['printer-status', printer.id] });
      showToast(t(enabled ? 'printers.amsBackup.toastEnabled' : 'printers.amsBackup.toastDisabled'), 'success');
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

// Smart plug control mutations
const powerControlMutation = useMutation({
    mutationFn: (action: 'on' | 'off') =>
      smartPlug ? api.controlSmartPlug(smartPlug.id, action) : Promise.reject('No plug'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smartPlugStatus', smartPlug?.id] });
    },
  });

const toggleAutoOffMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      smartPlug ? api.updateSmartPlug(smartPlug.id, { auto_off: enabled }) : Promise.reject('No plug'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smartPlugByPrinter', printer.id] });
      // Also invalidate the smart-plugs list to keep Settings page in sync
      queryClient.invalidateQueries({ queryKey: ['smart-plugs'] });
    },
  });

// Run HA entity mutation — scripts use 'on' (trigger), switches use 'toggle'
const runScriptMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'on' | 'toggle' }) => api.controlSmartPlug(id, action),
    onSuccess: () => {
      showToast(t('printers.toast.scriptTriggered'));
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToRunScript'), 'error'),
  });

// Print control mutations
const stopPrintMutation = useMutation({
    mutationFn: () => api.stopPrint(printer.id),
    onSuccess: () => {
      showToast(t('printers.toast.printStopped'));
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToStopPrint'), 'error'),
  });

const pausePrintMutation = useMutation({
    mutationFn: () => api.pausePrint(printer.id),
    onSuccess: () => {
      showToast(t('printers.toast.printPaused'));
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToPausePrint'), 'error'),
  });

const resumePrintMutation = useMutation({
    mutationFn: () => api.resumePrint(printer.id),
    onSuccess: () => {
      showToast(t('printers.toast.printResumed'));
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToResumePrint'), 'error'),
  });

const clearPlateMutation = useMutation({
    mutationFn: () => api.clearPlate(printer.id),
    onSuccess: () => {
      showToast(t('queue.clearPlateSuccess'));
      queryClient.setQueryData(['printerStatus', printer.id], (old: PrinterStatus | undefined) =>
        old ? { ...old, awaiting_plate_clear: false } : old
      );
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
      queryClient.invalidateQueries({ queryKey: ['queue', printer.id] });
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

const nozzleTemperatureMutation = useMutation({
    mutationFn: ({ target, nozzle }: { target: number; nozzle: number }) =>
      api.setNozzleTemperature(printer.id, target, nozzle),
    onSuccess: (result) => {
      setStatusControlMenu(null);
      showToast(result.message);
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

const bedTemperatureMutation = useMutation({
    mutationFn: (target: number) => api.setBedTemperature(printer.id, target),
    onSuccess: (result) => {
      setStatusControlMenu(null);
      showToast(result.message);
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

const chamberTemperatureMutation = useMutation({
    mutationFn: (target: number) => api.setChamberTemperature(printer.id, target),
    onSuccess: (result) => {
      setStatusControlMenu(null);
      showToast(result.message);
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

const fanSpeedMutation = useMutation({
    mutationFn: ({ fan, speed }: { fan: 'part' | 'aux' | 'chamber'; speed: number }) =>
      api.setFanSpeed(printer.id, fan, speed),
    onMutate: async ({ fan, speed }) => {
      await queryClient.cancelQueries({ queryKey: ['printerStatus', printer.id] });
      const previousStatus = queryClient.getQueryData(['printerStatus', printer.id]);
      const fanField = {
        part: 'cooling_fan_speed',
        aux: 'big_fan1_speed',
        chamber: 'big_fan2_speed',
      }[fan];
      queryClient.setQueryData(['printerStatus', printer.id], (old: PrinterStatus | undefined) =>
        old ? { ...old, [fanField]: speed } : old
      );
      return { previousStatus };
    },
    onSuccess: (result) => {
      setStatusControlMenu(null);
      showToast(result.message);
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
    },
    onError: (error: Error, _variables, context) => {
      if (context?.previousStatus) {
        queryClient.setQueryData(['printerStatus', printer.id], context.previousStatus);
      }
      showToast(error.message || t('printers.toast.failedToSendCommand'), 'error');
    },
  });

const selectExtruderMutation = useMutation({
    mutationFn: (extruder: number) => api.selectExtruder(printer.id, extruder),
    onMutate: async (extruder) => {
      await queryClient.cancelQueries({ queryKey: ['printerStatus', printer.id] });
      const previousStatus = queryClient.getQueryData(['printerStatus', printer.id]);
      queryClient.setQueryData(['printerStatus', printer.id], (old: PrinterStatus | undefined) =>
        old ? { ...old, active_extruder: extruder } : old
      );
      return { previousStatus };
    },
    onSuccess: (result) => {
      setStatusControlMenu(null);
      showToast(result.message);
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
    },
    onError: (error: Error, _extruder, context) => {
      if (context?.previousStatus) {
        queryClient.setQueryData(['printerStatus', printer.id], context.previousStatus);
      }
      showToast(error.message || t('printers.toast.failedToSendCommand'), 'error');
    },
  });

// Chamber light mutation with optimistic update
const chamberLightMutation = useMutation({
    mutationFn: (on: boolean) => api.setChamberLight(printer.id, on),
    onMutate: async (on) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['printerStatus', printer.id] });
      // Snapshot the previous value
      const previousStatus = queryClient.getQueryData(['printerStatus', printer.id]);
      // Optimistically update
      queryClient.setQueryData(['printerStatus', printer.id], (old: typeof status) => ({
        ...old,
        chamber_light: on,
      }));
      return { previousStatus };
    },
    onSuccess: (_, on) => {
      showToast(`Chamber light ${on ? 'on' : 'off'}`);
    },
    onError: (error: Error, _, context) => {
      // Rollback on error
      if (context?.previousStatus) {
        queryClient.setQueryData(['printerStatus', printer.id], context.previousStatus);
      }
      showToast(error.message || t('printers.toast.failedToControlChamberLight'), 'error');
    },
  });

// Print speed mutation with optimistic update
const printSpeedMutation = useMutation({
    mutationFn: (mode: number) => api.setPrintSpeed(printer.id, mode),
    onMutate: async (mode) => {
      await queryClient.cancelQueries({ queryKey: ['printerStatus', printer.id] });
      const previousStatus = queryClient.getQueryData(['printerStatus', printer.id]);
      queryClient.setQueryData(['printerStatus', printer.id], (old: typeof status) => ({
        ...old,
        speed_level: mode,
      }));
      return { previousStatus };
    },
    onError: (error: Error, _, context) => {
      if (context?.previousStatus) {
        queryClient.setQueryData(['printerStatus', printer.id], context.previousStatus);
      }
      showToast(error.message || t('printers.toast.failedToSetSpeed'), 'error');
    },
  });

const airductMutation = useMutation({
    mutationFn: (mode: 'cooling' | 'heating') => api.setAirductMode(printer.id, mode),
    onMutate: async (mode) => {
      await queryClient.cancelQueries({ queryKey: ['printerStatus', printer.id] });
      const previousStatus = queryClient.getQueryData(['printerStatus', printer.id]);
      queryClient.setQueryData(['printerStatus', printer.id], (old: typeof status) => ({
        ...old,
        airduct_mode: mode === 'cooling' ? 0 : 1,
      }));
      return { previousStatus };
    },
    onError: (error: Error, _, context) => {
      if (context?.previousStatus) {
        queryClient.setQueryData(['printerStatus', printer.id], context.previousStatus);
      }
      showToast(error.message || t('printers.toast.failedToSendCommand'), 'error');
    },
  });

const bedJogMutation = useMutation({
    mutationFn: ({ distance, force }: { distance: number; force?: boolean }) =>
      api.bedJog(printer.id, distance, force ?? false),
    onError: (error: Error) =>
      showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

const xyJogMutation = useMutation({
    mutationFn: ({ x, y }: { x: number; y: number }) =>
      api.xyJog(printer.id, x, y),
    onError: (error: Error) =>
      showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

const extruderJogMutation = useMutation({
    mutationFn: (distance: number) =>
      api.extruderJog(printer.id, distance),
    onError: (error: Error) =>
      showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

const homeAxesMutation = useMutation({
    mutationFn: (axes: 'z' | 'xy' | 'all') => api.homeAxes(printer.id, axes),
    onSuccess: () => {
      // Flip the session-scoped "warned" flag so the next bed-jog click doesn't re-prompt
      // the not-homed modal. The flag is the same one "Move anyway" sets; after a successful
      // auto-home request the printer is (or will shortly be) in a known-homed state, so
      // prompting again in the same session is noise — #1052 follow-up.
      try { sessionStorage.setItem(`printops.bedJog.warned.${printer.id}`, '1'); } catch { /* ignore */ }
      showToast(t('printers.bedJog.homingStarted'));
    },
    onError: (error: Error) =>
      showToast(error.message || t('printers.toast.failedToSendCommand'), 'error'),
  });

// Plate detection setting mutation
const plateDetectionMutation = useMutation({
    mutationFn: (enabled: boolean) => api.updatePrinter(printer.id, { plate_detection_enabled: enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] });
      showToast(plateDetectionMutation.variables ? t('printers.toast.plateCheckEnabled') : t('printers.toast.plateCheckDisabled'));
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToUpdateSetting'), 'error'),
  });

// Maintenance mode toggle (#1476). Wraps the `is_active` backend field that
  // already gates MQTT connection, queue dispatch, scheduler eligibility,
  // metrics, and the print picker — so flipping this flag puts the printer
  // out of service across every consumer in one place. Used from the
  // overflow menu and EditPrinterModal.
const maintenanceMutation = useMutation({
    mutationFn: (isActive: boolean) => api.updatePrinter(printer.id, { is_active: isActive }),
    onSuccess: (_data, isActive) => {
      queryClient.invalidateQueries({ queryKey: ['printers'] });
      queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
      showToast(
        isActive
          ? t('printers.maintenance.toastExited', { name: printer.name })
          : t('printers.maintenance.toastEntered', { name: printer.name }),
        'success',
      );
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToUpdateSetting'), 'error'),
  });

// Confirm before entering maintenance on a printing printer (entering mode
  // disconnects MQTT, which stops progress tracking + completion notifications
  // for the in-flight job).
const [confirmMaintenanceEnter, setConfirmMaintenanceEnter] = useState(false);

const handleEnterMaintenance = () => {
    if (status?.state === 'RUNNING' || status?.state === 'PAUSE') {
      setConfirmMaintenanceEnter(true);
    } else {
      maintenanceMutation.mutate(false);
    }
  };

// Query for printable objects (for skip functionality)
  // Fetch when printing with 2+ objects OR when modal is open
const isPrintingWithObjects = (status?.state === 'RUNNING' || status?.state === 'PAUSE') && (status?.printable_objects_count ?? 0) >= 2;

const { data: objectsData } = useQuery({
    queryKey: ['printableObjects', printer.id],
    queryFn: () => api.getPrintableObjects(printer.id),
    enabled: showSkipObjectsModal || isPrintingWithObjects,
    refetchInterval: showSkipObjectsModal ? 5000 : (isPrintingWithObjects ? 30000 : false), // 5s when modal open, 30s otherwise
  });

// State for tracking which AMS slot is being refreshed
const [refreshingSlot, setRefreshingSlot] = useState<{ amsId: number; slotId: number } | null>(null);

// Track if we've seen the printer enter "busy" state (ams_status_main !== 0)
const seenBusyStateRef = useRef<boolean>(false);

// Fallback timeout ref
const refreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

// Minimum display time passed
const minTimePassedRef = useRef<boolean>(false);

// AMS slot refresh mutation
const refreshAmsSlotMutation = useMutation({
    mutationFn: ({ amsId, slotId }: { amsId: number; slotId: number }) =>
      api.refreshAmsSlot(printer.id, amsId, slotId),
    onMutate: ({ amsId, slotId }) => {
      // Clear any existing timeout
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
      // Reset state
      seenBusyStateRef.current = false;
      minTimePassedRef.current = false;
      setRefreshingSlot({ amsId, slotId });
      // Minimum display time (2 seconds)
      setTimeout(() => {
        minTimePassedRef.current = true;
      }, 2000);
      // Fallback timeout (30 seconds max)
      refreshTimeoutRef.current = setTimeout(() => {
        setRefreshingSlot(null);
      }, 30000);
    },
    onSuccess: (data) => {
      showToast(data.message || t('printers.toast.rfidRereadInitiated'));
    },
    onError: (error: Error) => {
      showToast(error.message || t('printers.toast.failedToRereadRfid'), 'error');
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
      setRefreshingSlot(null);
    },
  });

// AMS load/unload mutations (#891)
const loadAmsTrayMutation = useMutation({
    mutationFn: ({ trayId }: { trayId: number }) => api.loadAmsTray(printer.id, trayId),
    onSuccess: (data) => {
      showToast(data.message || t('printers.toast.loadInitiated'));
    },
    onError: (error: Error) => {
      showToast(error.message || t('printers.toast.failedToLoad'), 'error');
    },
  });

const unloadAmsMutation = useMutation({
    mutationFn: () => api.unloadAms(printer.id),
    onSuccess: (data) => {
      showToast(data.message || t('printers.toast.unloadInitiated'));
    },
    onError: (error: Error) => {
      showToast(error.message || t('printers.toast.failedToUnload'), 'error');
    },
  });

// Plate references state
const [plateReferences, setPlateReferences] = useState<{
    references: Array<{ index: number; label: string; timestamp: string; has_image: boolean; thumbnail_url: string }>;
    max_references: number;
  } | null>(null);

const [editingRefLabel, setEditingRefLabel] = useState<{ index: number; label: string } | null>(null);

// Fetch plate references
const fetchPlateReferences = async () => {
    try {
      const data = await api.getPlateReferences(printer.id);
      setPlateReferences(data);
    } catch {
      // Ignore errors - references will show as empty
    }
  };

// Toggle plate detection enabled/disabled
const handleTogglePlateDetection = () => {
    plateDetectionMutation.mutate(!printer.plate_detection_enabled);
  };

// Open plate detection management modal (for calibration/references)
const handleOpenPlateManagement = async () => {
    setIsCheckingPlate(true);
    setPlateCheckResult(null);

    // Auto-turn on light if it's off
    const lightWasOff = status?.chamber_light === false;
    setPlateCheckLightWasOff(lightWasOff);
    if (lightWasOff) {
      await api.setChamberLight(printer.id, true);
      // Wait for light to physically turn on and camera to adjust exposure
      // (MQTT command is async, light takes ~1s to turn on, camera needs time to adjust)
      await new Promise(resolve => setTimeout(resolve, 2500));
    }

    try {
      const result = await api.checkPlateEmpty(printer.id, { includeDebugImage: true });
      setPlateCheckResult(result);
      fetchPlateReferences();
    } catch (error) {
      showToast(error instanceof Error ? error.message : t('printers.toast.failedToCheckPlate'), 'error');
      // Restore light if check failed
      if (lightWasOff) {
        await api.setChamberLight(printer.id, false);
        setPlateCheckLightWasOff(false);
      }
    } finally {
      setIsCheckingPlate(false);
    }
  };

// Close plate check modal and restore light state
const closePlateCheckModal = useCallback(async () => {
    setPlateCheckResult(null);
    // Restore light to original state if we turned it on
    if (plateCheckLightWasOff) {
      await api.setChamberLight(printer.id, false);
      setPlateCheckLightWasOff(false);
    }
  }, [plateCheckLightWasOff, printer.id]);

// Calibrate plate detection handler
const handleCalibratePlate = async (label?: string) => {
    setIsCalibrating(true);
    try {
      const result = await api.calibratePlateDetection(printer.id, { label });
      if (result.success) {
        showToast(result.message || t('printers.toast.calibrationSaved'), 'success');
        // Refresh references and re-check
        fetchPlateReferences();
        const checkResult = await api.checkPlateEmpty(printer.id, { includeDebugImage: true });
        setPlateCheckResult(checkResult);
      } else {
        showToast(result.message || t('printers.toast.calibrationFailed'), 'error');
      }
    } catch (error) {
      showToast(error instanceof Error ? error.message : t('printers.toast.calibrationFailed'), 'error');
    } finally {
      setIsCalibrating(false);
    }
  };

// Update reference label
const handleUpdateRefLabel = async (index: number, label: string) => {
    try {
      await api.updatePlateReferenceLabel(printer.id, index, label);
      setEditingRefLabel(null);
      fetchPlateReferences();
    } catch (error) {
      showToast(error instanceof Error ? error.message : t('printers.toast.failedToUpdateLabel'), 'error');
    }
  };

// Delete reference
const handleDeleteRef = async (index: number) => {
    try {
      await api.deletePlateReference(printer.id, index);
      showToast(t('printers.toast.referenceDeleted'), 'success');
      fetchPlateReferences();
      // Re-check to update counts
      const checkResult = await api.checkPlateEmpty(printer.id, { includeDebugImage: true });
      setPlateCheckResult(checkResult);
    } catch (error) {
      showToast(error instanceof Error ? error.message : t('printers.toast.failedToDeleteReference'), 'error');
    }
  };

// Save ROI settings
const handleSaveRoi = async () => {
    if (!editingRoi) return;
    setIsSavingRoi(true);
    try {
      await api.updatePrinter(printer.id, { plate_detection_roi: editingRoi });
      showToast(t('printers.toast.detectionAreaSaved'), 'success');
      setEditingRoi(null);
      // Re-check to see new ROI in action
      const checkResult = await api.checkPlateEmpty(printer.id, { includeDebugImage: true });
      setPlateCheckResult(checkResult);
    } catch (error) {
      showToast(error instanceof Error ? error.message : t('printers.toast.failedToSaveDetectionArea'), 'error');
    } finally {
      setIsSavingRoi(false);
    }
  };

// Close plate check modal on Escape key
useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && plateCheckResult) {
        closePlateCheckModal();
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [plateCheckResult, closePlateCheckModal]);

// Watch ams_status_main to detect when RFID read completes
  // ams_status_main: 0=idle, 2=rfid_identifying
const deferredClearRef = useRef<ReturnType<typeof setTimeout> | null>(null);

useEffect(() => {
    if (!refreshingSlot) return;

    const amsStatus = status?.ams_status_main ?? 0;

    // Track when we see non-idle state (printer is working)
    if (amsStatus !== 0) {
      seenBusyStateRef.current = true;
      // Cancel any deferred clear since we're back to busy
      if (deferredClearRef.current) {
        clearTimeout(deferredClearRef.current);
        deferredClearRef.current = null;
      }
    }

    // When we've seen busy and now idle, clear (with min time check)
    if (seenBusyStateRef.current && amsStatus === 0) {
      if (minTimePassedRef.current) {
        // Min time passed - clear now
        if (refreshTimeoutRef.current) {
          clearTimeout(refreshTimeoutRef.current);
        }
        setRefreshingSlot(null);
      } else {
        // Schedule clear after min time (2 seconds from start)
        if (!deferredClearRef.current) {
          deferredClearRef.current = setTimeout(() => {
            if (refreshTimeoutRef.current) {
              clearTimeout(refreshTimeoutRef.current);
            }
            setRefreshingSlot(null);
          }, 2000);
        }
      }
    }

    return () => {
      if (deferredClearRef.current) {
        clearTimeout(deferredClearRef.current);
      }
    };
  }, [status?.ams_status_main, refreshingSlot]);

useEffect(() => {
    if (!showMenu) return;

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!printerActionsMenuRef.current?.contains(target)) {
        setShowMenu(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showMenu]);

if (shouldHide) {
    return null;
  }

// Size-based styling helpers
const getImageSize = () => {
    switch (cardSize) {
      case 1: return 'w-10 h-10';
      case 2: return 'w-14 h-14';
      case 3: return 'w-16 h-16';
      case 4: return 'w-20 h-20';
      default: return 'w-14 h-14';
    }
  };

const getTitleSize = () => {
    switch (cardSize) {
      case 1: return 'text-base truncate';
      case 2: return 'text-lg';
      case 3: return 'text-xl';
      case 4: return 'text-2xl';
      default: return 'text-lg';
    }
  };

const getSpacing = () => {
    switch (cardSize) {
      case 1: return 'mb-2';
      case 2: return 'mb-4';
      case 3: return 'mb-5';
      case 4: return 'mb-6';
      default: return 'mb-4';
    }
  };

const canDrop = isConnected && status?.state !== 'RUNNING' && status?.state !== 'PAUSE' && hasPermission('printers:control');

const handleCardDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current++;
    if (dragCounterRef.current === 1) setIsDraggingFile(true);
  };

const handleCardDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = canDrop ? 'copy' : 'none';
  };

const handleCardDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current--;
    if (dragCounterRef.current === 0) setIsDraggingFile(false);
  };

const handleCardDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current = 0;
    setIsDraggingFile(false);

    if (!canDrop) return;

    const droppedFiles = Array.from(e.dataTransfer.files);
    const file = droppedFiles[0];
    if (!file) return;

    // Only accept sliced/printable files (.gcode, .gcode.3mf, etc.)
    const lower = file.name.toLowerCase();
    if (!lower.endsWith('.gcode') && !lower.includes('.gcode.')) {
      showToast(t('printers.dropNotPrintable', 'Only .gcode and .gcode.3mf files can be printed'), 'error');
      return;
    }

    setIsDropUploading(true);
    try {
      const result = await api.uploadLibraryFile(file, null);

      // Check printer compatibility if sliced_for_model is available in metadata
      const slicedFor = (result.metadata as Record<string, unknown>)?.sliced_for_model as string | undefined;
      const printerModel = mapModelCode(printer.model);
      if (slicedFor && printerModel && slicedFor.toLowerCase() !== printerModel.toLowerCase()) {
        await api.deleteLibraryFile(result.id).catch(() => {});
        showToast(
          t('printers.incompatibleFile', 'This file was sliced for {{slicedFor}}, but this printer is a {{printerModel}}', { slicedFor, printerModel }),
          'error'
        );
        return;
      }

      setPrintAfterUpload({ id: result.id, filename: result.filename });
    } catch {
      showToast(t('common.uploadFailed', 'Upload failed'), 'error');
    } finally {
      setIsDropUploading(false);
    }
  };

const handleCardClick = (e: React.MouseEvent) => {
    if (viewMode !== 'compact' || selectionMode) return;
    const target = e.target as HTMLElement;
    if (target.closest('button, a, input, select, textarea, [role="button"]')) return;
    onOpenCompactCard?.(printer.id);
  };

const footerActionButtonClass = '!h-8 !min-h-8 !px-2 !py-0';

const footerIconButtonClass = '!h-8 !min-h-8 !w-8 !px-0 !py-0';

  return {
    printer, maintenanceInfo, viewMode, cardSize,
    amsThresholds, spoolmanEnabled, linkedSpools, spoolmanUrl,
    spoolmanSyncMode, onGetAssignment, onUnassignSpool, spoolmanSpools,
    spoolmanSlotAssignments, spoolmanLoading, onUnassignSpoolmanSpool, timeFormat,
    cameraViewMode, onOpenEmbeddedCamera, checkPrinterFirmware, dryingPresets,
    selectionMode, isSelected, onToggleSelect, nozzleTempPresets,
    bedTempPresets, chamberTempPresets, fanSpeedPresets, t,
    queryClient, navigate, hasPermission, showMenu,
    setShowMenu, showDeleteConfirm, setShowDeleteConfirm, deleteArchives,
    setDeleteArchives, showEditModal, setShowEditModal, showFileManager,
    setShowFileManager, showMQTTDebug, setShowMQTTDebug, showControlMatrix,
    setShowControlMatrix, showPowerOnConfirm, setShowPowerOnConfirm, showPowerOffConfirm,
    setShowPowerOffConfirm, haToggleConfirm, setHaToggleConfirm, showHMSModal,
    setShowHMSModal, amsBackupModalOpen, setAmsBackupModalOpen, showStopConfirm,
    setShowStopConfirm, showPauseConfirm, setShowPauseConfirm, showSpeedMenu,
    setShowSpeedMenu, showAirductMenu, setShowAirductMenu, showBedJogMenu,
    setShowBedJogMenu, statusControlMenu, setStatusControlMenu, bedJogStep,
    setBedJogStep, showNotHomedModal, setShowNotHomedModal, showResumeConfirm,
    setShowResumeConfirm, showSkipObjectsModal, setShowSkipObjectsModal, showUploadForPrint,
    setShowUploadForPrint, showPrinterInfo, setShowPrinterInfo, showDiagnostic,
    setShowDiagnostic, closePrinterInfo, printAfterUpload, setPrintAfterUpload,
    dryingPopoverAmsId, setDryingPopoverAmsId, dryingPopoverModuleType, setDryingPopoverModuleType,
    dryingFilament, setDryingFilament, dryingTemp, setDryingTemp,
    dryingDuration, setDryingDuration, dryingRotateTray, setDryingRotateTray,
    dryingPopoverPos, setDryingPopoverPos, isDraggingFile, isDropUploading,
    printerActionsMenuRef, amsHistoryModal, setAmsHistoryModal, heaterHistoryModal,
    setHeaterHistoryModal, linkSpoolModal, setLinkSpoolModal, assignSpoolModal,
    setAssignSpoolModal, configureSlotModal, setConfigureSlotModal, showFirmwareModal,
    setShowFirmwareModal, plateCheckResult, isCheckingPlate, isCalibrating,
    editingRoi, setEditingRoi, isSavingRoi, status,
    firmwareInfo, loadedFilamentTypes, loadedFilaments, loadedVariants,
    filamentInfo, slotPresets, amsLabels, refetchAmsLabels,
    wifiSignal, isConnected, amsExtruderMap, amsData,
    effectiveTrayNow, expectedTray, previousTray, runoutGuidance,
    smartPlug, scriptPlugs, plugStatus, queueCount,
    currentPrintUser, lastPrint, needsPlateClear, showClearPlateButton,
    hasPrinterControlPermission, localPrinterControlUnavailable, cloudControlConfigured, activeControlPath,
    canUsePrinterControlAction, canUseTemperatureControls, canUseFanControls, canUseLightControl,
    getLocalPrinterControlUnavailableTitle, getPrinterControlUnavailableTitle, getControlActionTitle, canUsePrinterControl,
    activePrintName, retainedPrintJob, plateStatus, deleteMutation,
    connectMutation, forceRefreshMutation, unlinkSpoolMutation, startDryingMutation,
    stopDryingMutation, setAmsBackupMutation, powerControlMutation, toggleAutoOffMutation,
    runScriptMutation, stopPrintMutation, pausePrintMutation, resumePrintMutation,
    clearPlateMutation, nozzleTemperatureMutation, bedTemperatureMutation, chamberTemperatureMutation,
    fanSpeedMutation, selectExtruderMutation, chamberLightMutation, printSpeedMutation,
    airductMutation, bedJogMutation, xyJogMutation, extruderJogMutation,
    homeAxesMutation, plateDetectionMutation, maintenanceMutation, confirmMaintenanceEnter,
    setConfirmMaintenanceEnter, handleEnterMaintenance, objectsData, refreshingSlot,
    refreshAmsSlotMutation, loadAmsTrayMutation, unloadAmsMutation, plateReferences,
    editingRefLabel, setEditingRefLabel, handleTogglePlateDetection, handleOpenPlateManagement,
    closePlateCheckModal, handleCalibratePlate, handleUpdateRefLabel, handleDeleteRef,
    handleSaveRoi, getImageSize, getTitleSize, getSpacing,
    canDrop, handleCardDragEnter, handleCardDragOver, handleCardDragLeave,
    handleCardDrop, handleCardClick, footerActionButtonClass, footerIconButtonClass,
  };
}
