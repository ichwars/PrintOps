import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { formatPrintName } from '../../utils/printName';
import { computePopoverPosition } from '../../utils/popoverPosition';
import { BED_TEMP_DEFAULTS, CHAMBER_TEMP_DEFAULTS, FAN_SPEED_DEFAULTS, NOZZLE_TEMP_DEFAULTS, buildPresetOptions } from '../../utils/temperatureFanPresets';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../contexts/AuthContext';
import { NumberField, Checkbox, Slider, TextField } from '../../components/ui';
import { Link, Unlink, Signal, Clock, MoreVertical, Trash2, RefreshCw, RotateCw, HardDrive, AlertTriangle, Terminal, Zap, Wrench, ChevronDown, Pencil, ArrowLeft, ArrowRight, ArrowUp, ArrowDown, Layers, Video, Loader2, Square, Pause, Play, X, Fan, Wind, AirVent, Download, ScanSearch, CheckCircle, CheckSquare, XCircle, User, Home, Printer as PrinterIcon, Info, Cable, Flame, Snowflake, Gauge, DoorOpen, DoorClosed, Move, LogIn, LogOut, Stethoscope, LineChart as LineChartIcon } from 'lucide-react';
import { useNavigate } from 'react-router';
import { api, firmwareApi } from '../../api/client';
import { formatDateOnly, formatETA, formatDuration, parseUTCDate } from '../../utils/date';
import type { Printer, PrinterStatus, AMSUnit, LinkedSpoolInfo, SpoolAssignment, InventorySpool, SmartPlug } from '../../api/client';
import { Card, CardContent } from '../../components/Card';
import { Button } from '../../components/Button';
import { ConfirmModal } from '../../components/ConfirmModal';
import { FileManagerModal } from '../../components/FileManagerModal';
import { MQTTDebugModal } from '../../components/MQTTDebugModal';
import { HMSErrorModal, filterKnownHMSErrors } from '../../components/HMSErrorModal';
import { PrinterQueueWidget } from '../../components/PrinterQueueWidget';
import { AMSHistoryModal } from '../../components/AMSHistoryModal';
import { AmsBackupModal } from '../../components/AmsBackupModal';
import { HeaterHistoryModal } from '../../components/HeaterHistoryModal';
import type { HeaterSensorKind } from '../../api/client';
import { FilamentHoverCard, EmptySlotHoverCard } from '../../components/FilamentHoverCard';
import { LinkSpoolModal } from '../../components/LinkSpoolModal';
import { AssignSpoolModal } from '../../components/AssignSpoolModal';
import { ConfigureAmsSlotModal } from '../../components/ConfigureAmsSlotModal';
import { useToast } from '../../contexts/ToastContext';
import { ChamberLight } from '../../components/icons/ChamberLight';
import { PlateClearedIcon } from '../../components/icons/PlateClearedIcon';
import { SkipObjectsModal, SkipObjectsIcon } from '../../components/SkipObjectsModal';
import { FileUploadModal } from '../../components/FileUploadModal';
import { PrintModal } from '../../components/PrintModal';
import { PrinterInfoModal } from '../../components/PrinterInfoModal';
import { getAmsLabel, getGlobalTrayId, getFillBarColor, getSpoolmanFillLevel, getFallbackSpoolTag, isBambuLabSpool } from '../../utils/amsHelpers';
import { getPrinterImage, getWifiStrength, filterCompatibleQueueItems } from '../../utils/printer';
import { PRINTER_CONTROL_CAPABILITIES, getPrinterControlCapability, isCloudControlCandidate, isCloudControlUncertain, isPrintOpsCloudControlImplemented, type PrinterControlAction } from '../../utils/printerControlCapabilities';
import { FilamentSlotCircle } from '../../components/FilamentSlotCircle';
import { ConnectionDiagnosticModal } from '../../components/ConnectionDiagnostic';
import { getColorName } from '../../utils/colors';
import type { PrinterMaintenanceInfo, SpoolmanSlotAssignmentRow, ViewMode } from './types';
import { MODELS_WITH_CHAMBER_FAN, getStatusDisplay, mapModelCode } from './printer-status';
import { AmsBackupBadge, CoverImage, DualNozzleHoverCard, HeaterThermometer, HumidityIndicator, NozzleBadge, NozzleIcon, NozzleRackCard, NozzleSlotHoverCard, TemperatureIndicator } from './printer-card-visuals';
import { IndicatorControlPopover, NozzleTemperatureControlBox, ToolbarDropdown } from './printer-toolbar';
import { AmsNameHoverCard } from './AmsNameHoverCard';
import { EditPrinterModal } from './EditPrinterModal';
import { FirmwareUpdateModal } from './FirmwareUpdateModal';
import { DRYING_POPOVER_ESTIMATED_HEIGHT, DRYING_POPOVER_WIDTH, DRYING_PRESETS, DRY_START_CONFIRM_MS } from './printer-card-constants';
import { formatKValue, getEmptySlotKind } from './printer-card-utils';

export function PrinterCard({
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
}: {
  printer: Printer;
  hideIfDisconnected?: boolean;
  maintenanceInfo?: PrinterMaintenanceInfo;
  viewMode?: ViewMode;
  cardSize?: number;
  amsThresholds?: {
    humidityGood: number;
    humidityFair: number;
    tempGood: number;
    tempFair: number;
  };
  spoolmanEnabled?: boolean;
  hasUnlinkedSpools?: boolean;
  linkedSpools?: Record<string, LinkedSpoolInfo>;
  spoolmanUrl?: string | null;
  spoolmanSyncMode?: string | null;
  spoolAssignments?: SpoolAssignment[];
  onGetAssignment?: (printerId: number, amsId: number, trayId: number) => SpoolAssignment | undefined;
  onUnassignSpool?: (printerId: number, amsId: number, trayId: number) => void;
  spoolmanSpools?: InventorySpool[];
  spoolmanSlotAssignments?: SpoolmanSlotAssignmentRow[];
  spoolmanLoading?: boolean;
  onUnassignSpoolmanSpool?: (spoolmanSpoolId: number) => void;
  timeFormat?: 'system' | '12h' | '24h';
  cameraViewMode?: 'window' | 'embedded';
  onOpenEmbeddedCamera?: (printerId: number, printerName: string) => void;
  checkPrinterFirmware?: boolean;
  dryingPresets?: Record<string, { n3f: number; n3s: number; n3f_hours: number; n3s_hours: number }>;
  requirePlateClear?: boolean;
  selectionMode?: boolean;
  isSelected?: boolean;
  onToggleSelect?: (id: number) => void;
  onOpenCompactCard?: (id: number) => void;
  nozzleTempPresets?: readonly [number, number, number];
  bedTempPresets?: readonly [number, number, number];
  chamberTempPresets?: readonly [number, number, number];
  fanSpeedPresets?: readonly [number, number, number];
}) {
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
  const plateStatusPill = plateStatus ? (
    <span className={`inline-flex flex-shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${plateStatus.className}`}>
      {plateStatus.label}
    </span>
  ) : null;

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
  const renderAmsSlotActions = ({
    amsId,
    slotId,
    loadTrayId,
    isRefreshing,
    includeRfid = true,
  }: {
    amsId: number;
    slotId: number;
    loadTrayId: number;
    isRefreshing?: boolean;
    includeRfid?: boolean;
  }) => {
    const printerBusy = status?.state === 'RUNNING';

    return (
      <>
        {includeRfid && (
          <button
            className={`w-full px-2 py-1.5 text-left text-xs flex items-center gap-2 rounded transition-colors ${
              hasPermission('printers:ams_rfid') && !localPrinterControlUnavailable
                ? 'text-white hover:bg-bambu-dark-tertiary'
                : 'text-bambu-gray/50 cursor-not-allowed'
            }`}
            onClick={(e) => {
              e.stopPropagation();
              if (printerBusy || localPrinterControlUnavailable || !hasPermission('printers:ams_rfid')) return;
              refreshAmsSlotMutation.mutate({ amsId, slotId });
            }}
            disabled={printerBusy || isRefreshing || localPrinterControlUnavailable || !hasPermission('printers:ams_rfid')}
            title={printerBusy ? t('printers.bedJog.disabledWhilePrinting') : localPrinterControlUnavailable ? getLocalPrinterControlUnavailableTitle('amsSlot') : !hasPermission('printers:ams_rfid') ? t('printers.permission.noAmsRfid') : undefined}
          >
            <RefreshCw className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
            {t('printers.rfid.reread')}
          </button>
        )}
        <button
          className={`w-full px-2 py-1.5 text-left text-xs flex items-center gap-2 rounded transition-colors ${
            canUsePrinterControl
              ? 'text-white hover:bg-bambu-dark-tertiary'
              : 'text-bambu-gray/50 cursor-not-allowed'
          }`}
          onClick={(e) => {
            e.stopPropagation();
            if (printerBusy || !canUsePrinterControl) return;
            loadAmsTrayMutation.mutate({ trayId: loadTrayId });
          }}
          disabled={printerBusy || !canUsePrinterControl}
          title={printerBusy ? t('printers.bedJog.disabledWhilePrinting') : !canUsePrinterControl ? getPrinterControlUnavailableTitle('amsSlot') : undefined}
        >
          <LogIn className="w-3 h-3" />
          {t('printers.ams.load')}
        </button>
        <button
          className={`w-full px-2 py-1.5 text-left text-xs flex items-center gap-2 rounded transition-colors ${
            canUsePrinterControl
              ? 'text-white hover:bg-bambu-dark-tertiary'
              : 'text-bambu-gray/50 cursor-not-allowed'
          }`}
          onClick={(e) => {
            e.stopPropagation();
            if (printerBusy || !canUsePrinterControl) return;
            unloadAmsMutation.mutate();
          }}
          disabled={printerBusy || !canUsePrinterControl}
          title={printerBusy ? t('printers.bedJog.disabledWhilePrinting') : !canUsePrinterControl ? getPrinterControlUnavailableTitle('amsSlot') : undefined}
        >
          <LogOut className="w-3 h-3" />
          {t('printers.ams.unload')}
        </button>
      </>
    );
  };

  const printerActionsMenu = (
    <div ref={printerActionsMenuRef} className="relative flex-shrink-0">
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setShowMenu(!showMenu)}
        title={t('common.more', 'More')}
        className={footerIconButtonClass}
      >
        <MoreVertical className="w-4 h-4" />
      </Button>
      {showMenu && (
        <div className="absolute left-0 bottom-full mb-2 w-48 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg shadow-lg z-20">
          <button
            className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 ${
              hasPermission('printers:update')
                ? 'hover:bg-bambu-dark-tertiary'
                : 'opacity-50 cursor-not-allowed'
            }`}
            onClick={() => {
              if (!hasPermission('printers:update')) return;
              setShowEditModal(true);
              setShowMenu(false);
            }}
            title={!hasPermission('printers:update') ? t('printers.permission.noEdit') : undefined}
          >
            <Pencil className="w-4 h-4" />
            {t('common.edit')}
          </button>
          <button
            className="w-full px-4 py-2 text-left text-sm hover:bg-bambu-dark-tertiary flex items-center gap-2"
            onClick={() => {
              setShowPrinterInfo(true);
              setShowMenu(false);
            }}
          >
            <Info className="w-4 h-4" />
            {t('printers.printerInformation')}
          </button>
          {/* Maintenance Mode toggle (#1476) — leverages backend is_active flag */}
          <button
            className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 ${
              hasPermission('printers:update')
                ? 'hover:bg-bambu-dark-tertiary'
                : 'opacity-50 cursor-not-allowed'
            }`}
            disabled={maintenanceMutation.isPending || !hasPermission('printers:update')}
            onClick={() => {
              if (!hasPermission('printers:update')) return;
              setShowMenu(false);
              if (printer.is_active !== false) {
                handleEnterMaintenance();
              } else {
                maintenanceMutation.mutate(true);
              }
            }}
            title={!hasPermission('printers:update') ? t('printers.permission.noEdit') : undefined}
          >
            <Wrench className="w-4 h-4" />
            {printer.is_active !== false
              ? t('printers.maintenance.menuEnter')
              : t('printers.maintenance.menuExit')}
          </button>
          <button
            className="w-full px-4 py-2 text-left text-sm hover:bg-bambu-dark-tertiary flex items-center gap-2"
            onClick={() => {
              connectMutation.mutate();
              setShowMenu(false);
            }}
          >
            <RefreshCw className="w-4 h-4" />
            {t('printers.reconnect')}
          </button>
          <button
            className="w-full px-4 py-2 text-left text-sm hover:bg-bambu-dark-tertiary flex items-center gap-2 disabled:opacity-50"
            disabled={forceRefreshMutation.isPending}
            onClick={() => {
              forceRefreshMutation.mutate();
              setShowMenu(false);
            }}
          >
            <RotateCw className={`w-4 h-4 ${forceRefreshMutation.isPending ? 'animate-spin' : ''}`} />
            {t('printers.forceRefresh')}
          </button>
          <button
            className="w-full px-4 py-2 text-left text-sm hover:bg-bambu-dark-tertiary flex items-center gap-2"
            onClick={() => {
              setShowMQTTDebug(true);
              setShowMenu(false);
            }}
          >
            <Terminal className="w-4 h-4" />
            {t('printers.mqttDebug')}
          </button>
          <button
            className="w-full px-4 py-2 text-left text-sm hover:bg-bambu-dark-tertiary flex items-center gap-2"
            onClick={() => {
              setShowDiagnostic(true);
              setShowMenu(false);
            }}
          >
            <Stethoscope className="w-4 h-4" />
            {t('diagnostic.runButton')}
          </button>
          <button
            className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 ${
              hasPermission('printers:delete')
                ? 'text-red-700 dark:text-red-400 hover:bg-bambu-dark-tertiary'
                : 'text-red-700/50 dark:text-red-400/50 cursor-not-allowed'
            }`}
            onClick={() => {
              if (!hasPermission('printers:delete')) return;
              setShowDeleteConfirm(true);
              setShowMenu(false);
            }}
            title={!hasPermission('printers:delete') ? t('printers.permission.noDelete') : undefined}
          >
            <Trash2 className="w-4 h-4" />
            {t('common.delete')}
          </button>
        </div>
      )}
    </div>
  );

  return (
    <Card
      id={`printer-card-${printer.id}`}
      className={`relative flex h-full flex-col ${isSelected ? 'ring-2 ring-bambu-green' : ''} ${selectionMode || viewMode === 'compact' ? 'cursor-pointer' : ''}`}
      onClick={handleCardClick}
      onDragEnter={handleCardDragEnter}
      onDragOver={handleCardDragOver}
      onDragLeave={handleCardDragLeave}
      onDrop={handleCardDrop}
    >
      {/* Selection mode click overlay — captures all clicks, preventing nested interactions */}
      {selectionMode && (
        <div
          className="absolute inset-0 z-20 flex items-start p-2"
          onClick={(e) => { e.stopPropagation(); onToggleSelect?.(printer.id); }}
        >
          {isSelected ? (
            <CheckSquare className="w-5 h-5 text-bambu-green" />
          ) : (
            <Square className="w-5 h-5 text-bambu-gray" />
          )}
        </div>
      )}
      {/* Drop zone overlay */}
      {(isDraggingFile || isDropUploading) && (
        <div
          className={`absolute inset-0 z-10 rounded-xl border-2 border-dashed flex items-center justify-center transition-colors ${
            isDropUploading
              ? 'bg-bambu-green/10 border-bambu-green/50'
              : canDrop
                ? 'bg-bambu-green/10 border-bambu-green'
                : 'bg-red-50 dark:bg-red-500/10 border-red-300 dark:border-red-500/50'
          }`}
        >
          <div className="text-center">
            {isDropUploading ? (
              <>
                <Loader2 className="w-8 h-8 mx-auto mb-2 text-bambu-green animate-spin" />
                <p className="text-sm font-medium text-bambu-green">{t('common.uploading', 'Uploading...')}</p>
              </>
            ) : canDrop ? (
              <>
                <PrinterIcon className="w-8 h-8 mx-auto mb-2 text-bambu-green" />
                <p className="text-sm font-medium text-bambu-green">{t('printers.dropToPrint', 'Drop to print')}</p>
              </>
            ) : (
              <>
                <X className="w-8 h-8 mx-auto mb-2 text-red-600 dark:text-red-400" />
                <p className="text-sm font-medium text-red-700 dark:text-red-400">{t('printers.cannotPrint', 'Printer busy')}</p>
              </>
            )}
          </div>
        </div>
      )}
      <CardContent className={`${cardSize >= 3 ? 'p-5' : ''} flex flex-1 flex-col`}>
        {/* Header */}
        <div className={getSpacing()}>
          {/* Top row: Image, Name, Menu */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              {/* Printer Model Image */}
              <img
                src={getPrinterImage(printer.model)}
                alt={printer.model || t('common.printer')}
                className={`object-contain rounded-lg flex-shrink-0 ${getImageSize()}`}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <h3 className={`font-semibold text-white ${getTitleSize()}`}>{printer.name}</h3>
                    {/* Connection indicator dot for compact mode */}
                    {viewMode === 'compact' && (() => {
                      const hmsErrors = status?.connected && status.hms_errors ? filterKnownHMSErrors(status.hms_errors) : [];
                      const hasSevere = hmsErrors.some(e => e.severity <= 2);
                      const hasWarning = hmsErrors.length > 0;
                      const pipColor = !status?.connected
                        ? 'bg-status-error'
                        : hasSevere
                          ? 'bg-status-error'
                          : hasWarning
                            ? 'bg-status-warning'
                            : 'bg-status-ok';
                      const pipTitle = !status?.connected
                        ? t('printers.connection.offline')
                        : hasWarning
                          ? `${hmsErrors.length} HMS ${hmsErrors.length === 1 ? 'error' : 'errors'}`
                          : t('printers.connection.connected');
                      return (
                        <div
                          className={`w-2 h-2 rounded-full flex-shrink-0 ${pipColor}`}
                          title={pipTitle}
                        />
                      );
                    })()}
                  </div>
                  {viewMode === 'compact' && showClearPlateButton && (
                    <button
                      type="button"
                      onClick={() => clearPlateMutation.mutate()}
                      disabled={clearPlateMutation.isPending || !hasPermission('printers:clear_plate')}
                      aria-label={t('printers.plateStatus.markCleared')}
                      className="inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-md bg-yellow-100 dark:bg-yellow-500/20 border border-yellow-300 dark:border-yellow-400/40 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-500/30 transition-colors disabled:opacity-50"
                      title={!hasPermission('printers:clear_plate') ? t('printers.permission.noControl') : t('printers.plateStatus.markCleared')}
                    >
                      {clearPlateMutation.isPending ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <PlateClearedIcon className="w-3 h-3" />
                      )}
                    </button>
                  )}
                </div>
                <p className="text-sm text-bambu-gray">
                  {printer.model || 'Unknown Model'}
                  {/* Nozzle Info - only in expanded */}
                  {viewMode === 'expanded' && status?.nozzles && status.nozzles[0]?.nozzle_diameter && (
                    <span className="ml-1.5 text-bambu-gray" title={status.nozzles[0].nozzle_type || 'Nozzle'}>
                      • {status.nozzles[0].nozzle_diameter}mm
                    </span>
                  )}
                  {viewMode === 'expanded' && maintenanceInfo && maintenanceInfo.total_print_hours > 0 && (
                    <span className="ml-2 text-bambu-gray">
                      <Clock className="w-3 h-3 inline-block mr-1" />
                      {Math.round(maintenanceInfo.total_print_hours)}h
                    </span>
                  )}
                </p>
              </div>
            </div>
          </div>

          {/* Badges row - only in expanded mode */}
          {viewMode === 'expanded' && (
            <div className="mt-2">
              <div className="flex flex-wrap items-center gap-2">
              {/* Connection status badge (or Maintenance pill when out of service).
                  Defensive: only swap when is_active is EXPLICITLY false. An
                  undefined / missing field defaults to "active" so the regular
                  pill renders — matches the backend default and prevents test
                  fixtures (or stale clients) from accidentally tripping the
                  maintenance UI. */}
              {printer.is_active === false ? (
                <span
                  className="flex items-center gap-1.5 px-2 py-1 rounded-full text-xs bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400"
                  title={t('printers.maintenance.subtitle')}
                >
                  <Wrench className="w-3 h-3" />
                  {t('printers.maintenance.pillLabel')}
                </span>
              ) : (
                <span
                  className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs ${
                    status?.connected
                      ? 'bg-status-ok/20 text-status-ok'
                      : 'bg-status-error/20 text-status-error'
                  }`}
                >
                  {status?.connected ? (
                    <Link className="w-3 h-3" />
                  ) : (
                    <Unlink className="w-3 h-3" />
                  )}
                  {status?.connected ? t('printers.connection.connected') : t('printers.connection.offline')}
                </span>
              )}
              {localPrinterControlUnavailable && (
                <span
                  className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20"
                  title={t(
                    'printers.localControlBadgeTitle',
                    'Lokale Druckersteuerung ist deaktiviert. PrintOps zeigt Statusdaten, sperrt aber lokale Steuerbefehle.',
                  )}
                >
                  <Cable className="w-3 h-3" />
                  {t('printers.localControlBadge', 'LAN-Steuerung aus')}
                </span>
              )}
              <span
                className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs border ${
                  activeControlPath === 'local'
                    ? 'bg-status-ok/20 text-status-ok border-status-ok/20'
                    : activeControlPath === 'cloud'
                      ? 'bg-sky-500/10 text-sky-400 border-sky-500/20'
                      : 'bg-bambu-dark-tertiary text-bambu-gray border-bambu-dark-tertiary'
                }`}
                title={t(
                  'printers.controlPathTitle',
                  'Aktiver Steuerweg: {{path}}',
                  { path: t(`printers.controlPath.${activeControlPath}`, activeControlPath) },
                )}
              >
                {activeControlPath === 'local' ? <Cable className="w-3 h-3" /> : <Zap className="w-3 h-3" />}
                {t(`printers.controlPath.${activeControlPath}`, activeControlPath)}
              </span>
              {cloudControlConfigured && (
                <span
                  className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-sky-500/10 text-sky-400 border border-sky-500/20"
                  title={t('printers.cloudControlConfiguredTitle', 'Bambu Cloud ist konfiguriert und kann für unterstützte Fallback-Aktionen genutzt werden.')}
                >
                  <Zap className="w-3 h-3" />
                  {t('printers.cloudControlConfigured', 'Cloud bereit')}
                </span>
              )}
              <button
                type="button"
                onClick={() => setShowControlMatrix(open => !open)}
                className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-bambu-dark-tertiary text-bambu-gray hover:text-white transition-colors"
                title={t('printers.controlMatrix.toggle', 'Steuerwege anzeigen')}
              >
                <Info className="w-3 h-3" />
                {t('printers.controlMatrix.title', 'Steuerwege')}
              </button>
              {/* Run connection diagnostic — offered when the printer is offline, NOT in maintenance */}
              {printer.is_active !== false && !status?.connected && (
                <button
                  onClick={() => setShowDiagnostic(true)}
                  className="flex items-center gap-1 px-2 py-1 rounded-full text-xs cursor-pointer bg-bambu-dark-tertiary text-bambu-gray hover:text-white transition-colors"
                  title={t('diagnostic.runButton')}
                >
                  <Stethoscope className="w-3 h-3" />
                  {t('diagnostic.runButton')}
                </button>
              )}
              {/* Network connection indicator */}
              {status?.connected && status?.wired_network && (
                <span
                  className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-status-ok/20 text-status-ok"
                  title={t('printers.connection.ethernet', 'Ethernet')}
                >
                  <Cable className="w-3 h-3" />
                  {t('printers.connection.ethernet', 'Ethernet')}
                </span>
              )}
              {/* WiFi signal indicator */}
              {status?.connected && !status?.wired_network && wifiSignal != null && (
                <span
                  className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs ${
                    wifiSignal >= -50
                      ? 'bg-status-ok/20 text-status-ok'
                      : wifiSignal >= -60
                      ? 'bg-status-ok/20 text-status-ok'
                      : wifiSignal >= -70
                      ? 'bg-status-warning/20 text-status-warning'
                      : wifiSignal >= -80
                      ? 'bg-orange-500/20 text-orange-600'
                      : 'bg-status-error/20 text-status-error'
                  }`}
                  title={`WiFi: ${wifiSignal} dBm - ${t(getWifiStrength(wifiSignal).labelKey)}`}
                >
                  <Signal className="w-3 h-3" />
                  {wifiSignal}dBm
                </span>
              )}
              {/* HMS Status Indicator */}
              {status?.connected && (() => {
                const knownErrors = status.hms_errors ? filterKnownHMSErrors(status.hms_errors) : [];
                return (
                  <button
                    onClick={() => setShowHMSModal(true)}
                    className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs cursor-pointer hover:opacity-80 transition-opacity ${
                      knownErrors.length > 0
                        ? knownErrors.some(e => e.severity <= 2)
                          ? 'bg-status-error/20 text-status-error'
                          : 'bg-status-warning/20 text-status-warning'
                        : 'bg-status-ok/20 text-status-ok'
                    }`}
                    title={t('printers.clickToViewHmsErrors')}
                  >
                    <AlertTriangle className="w-3 h-3" />
                    {knownErrors.length > 0 ? knownErrors.length : 'OK'}
                  </button>
                );
              })()}
              {/* Maintenance Status Indicator */}
              {maintenanceInfo && (
                <button
                  onClick={() => navigate('/maintenance')}
                  className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs cursor-pointer hover:opacity-80 transition-opacity ${
                    maintenanceInfo.due_count > 0
                      ? 'bg-status-error/20 text-status-error'
                      : maintenanceInfo.warning_count > 0
                      ? 'bg-status-warning/20 text-status-warning'
                      : 'bg-status-ok/20 text-status-ok'
                  }`}
                  title={
                    maintenanceInfo.due_count > 0 || maintenanceInfo.warning_count > 0
                      ? `${maintenanceInfo.due_count > 0 ? `${maintenanceInfo.due_count} maintenance due` : ''}${maintenanceInfo.due_count > 0 && maintenanceInfo.warning_count > 0 ? ', ' : ''}${maintenanceInfo.warning_count > 0 ? `${maintenanceInfo.warning_count} due soon` : ''} - Click to view`
                      : t('printers.maintenanceUpToDate')
                  }
                >
                  <Wrench className="w-3 h-3" />
                  {maintenanceInfo.due_count > 0 || maintenanceInfo.warning_count > 0
                    ? maintenanceInfo.due_count + maintenanceInfo.warning_count
                    : 'OK'}
                </button>
              )}
              {/* Queue Count Badge */}
              {queueCount > 0 && (
                <button
                  onClick={() => navigate('/queue')}
                  className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-indigo-100 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-400 hover:opacity-80 transition-opacity"
                  title={t('printers.queue.inQueue', { count: queueCount })}
                >
                  <Layers className="w-3 h-3" />
                  {queueCount}
                </button>
              )}
              {/* Firmware Version Badge */}
              {checkPrinterFirmware && firmwareInfo?.current_version && firmwareInfo?.latest_version ? (
                <button
                  onClick={() => setShowFirmwareModal(true)}
                  className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs hover:opacity-80 transition-opacity ${
                    firmwareInfo.update_available
                      ? 'bg-orange-100 dark:bg-orange-500/20 text-orange-700 dark:text-orange-400'
                      : 'bg-status-ok/20 text-status-ok'
                  }`}
                  title={
                    firmwareInfo.update_available
                      ? t('printers.firmwareUpdateAvailable', { current: firmwareInfo.current_version, latest: firmwareInfo.latest_version })
                      : t('printers.firmwareUpToDate', { version: firmwareInfo.current_version })
                  }
                >
                  {firmwareInfo.update_available ? <Download className="w-3 h-3" /> : <CheckCircle className="w-3 h-3" />}
                  {firmwareInfo.current_version}
                </button>
              ) : status?.firmware_version ? (
                <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-bambu-dark-tertiary/50 text-bambu-gray">
                  {status.firmware_version}
                </span>
              ) : null}

              {/* Enclosure Door Badge — models with an actual door sensor.
                  P1S has an enclosure door but no sensor; P1P has no enclosure at all. */}
              {status?.connected && ['X1C', 'X1', 'X1E', 'X2D', 'P2S', 'H2D', 'H2D Pro', 'H2C', 'H2S'].includes(printer.model ?? '') && (
                <span
                  className={`flex items-center px-2 py-1 rounded-full text-xs ${
                    status.door_open
                      ? 'bg-yellow-100 dark:bg-yellow-500/20 text-yellow-700 dark:text-yellow-400'
                      : 'bg-status-ok/20 text-status-ok'
                  }`}
                  title={status.door_open ? t('printers.door.open') : t('printers.door.closed')}
                >
                  {status.door_open ? <DoorOpen className="w-3 h-3" /> : <DoorClosed className="w-3 h-3" />}
                </span>
              )}
              </div>
              {showControlMatrix && (
                <div className="mt-2 overflow-hidden rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary/70">
                  <div className="grid grid-cols-[1.4fr_0.7fr_0.9fr_1fr] gap-2 border-b border-bambu-dark-tertiary px-3 py-2 text-[10px] font-medium uppercase tracking-wide text-bambu-gray">
                    <span>{t('printers.controlMatrix.action', 'Aktion')}</span>
                    <span>{t('printers.controlMatrix.local', 'LAN')}</span>
                    <span>{t('printers.controlMatrix.cloud', 'Cloud')}</span>
                    <span>{t('printers.controlMatrix.printops', 'PrintOps')}</span>
                  </div>
                  <div className="divide-y divide-bambu-dark-tertiary/70">
                    {Object.values(PRINTER_CONTROL_CAPABILITIES).map((capability) => {
                      const cloudCandidate = isCloudControlCandidate(capability.action);
                      const cloudUncertain = isCloudControlUncertain(capability.action);
                      const cloudImplemented = isPrintOpsCloudControlImplemented(capability.action);
                      const printOpsMode = !capability.localRequired
                        ? t('printers.controlMatrix.statusOnly', 'Status')
                        : cloudImplemented
                          ? t('printers.controlMatrix.localCloudFallback', 'LAN + Cloud-Fallback')
                          : cloudCandidate
                            ? t('printers.controlMatrix.cloudNotImplemented', 'Cloud möglich, PrintOps lokal')
                            : t('printers.controlMatrix.localOnly', 'nur LAN');
                      return (
                        <div
                          key={capability.action}
                          className="grid grid-cols-[1.4fr_0.7fr_0.9fr_1fr] gap-2 px-3 py-2 text-xs text-bambu-gray-light"
                        >
                          <span className="truncate text-white">{t(capability.labelKey, capability.labelFallback)}</span>
                          <span className={status?.control_connection?.local_control_available ? 'text-status-ok' : 'text-bambu-gray'}>
                            {capability.localRequired
                              ? status?.control_connection?.local_control_available
                                ? t('common.yes', 'Ja')
                                : t('common.no', 'Nein')
                              : t('printers.controlMatrix.status', 'Status')}
                          </span>
                          <span className={cloudCandidate ? 'text-sky-400' : cloudUncertain ? 'text-status-warning' : 'text-bambu-gray'}>
                            {cloudCandidate
                              ? t('printers.controlMatrix.available', 'möglich')
                              : cloudUncertain
                                ? t('printers.controlMatrix.uncertain', 'unklar')
                                : t('common.no', 'Nein')}
                          </span>
                          <span className={cloudImplemented && cloudControlConfigured ? 'text-sky-400' : cloudCandidate ? 'text-amber-300' : capability.localRequired ? 'text-bambu-gray-light' : 'text-status-ok'}>
                            {printOpsMode}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Delete Confirmation */}
        {showDeleteConfirm && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <Card className="w-full max-w-md mx-4">
              <CardContent>
                <div className="flex items-start gap-3 mb-4">
                  <div className="p-2 rounded-full bg-red-100 dark:bg-red-500/20">
                    <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-white">{t('printers.confirm.deleteTitle')}</h3>
                    <p className="text-sm text-bambu-gray mt-1">
                      {t('printers.confirm.deleteMessage', { name: printer.name })}
                    </p>
                  </div>
                </div>

                <div className="bg-bambu-dark rounded-lg p-3 mb-4">
                  <label className="flex items-start gap-3 cursor-pointer">
                    <Checkbox
                      checked={deleteArchives}
                      onChange={(e) => setDeleteArchives(e.target.checked)}
                    />
                    <div>
                      <span className="text-sm text-white">{t('printers.deleteArchives')}</span>
                      <p className="text-xs text-bambu-gray mt-0.5">
                        {deleteArchives
                          ? t('printers.confirm.deleteArchivesNote')
                          : t('printers.confirm.keepArchivesNote')}
                      </p>
                    </div>
                  </label>
                </div>

                <div className="flex justify-end gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setShowDeleteConfirm(false);
                      setDeleteArchives(true);
                    }}
                  >
                    {t('common.cancel')}
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => {
                      deleteMutation.mutate({ deleteArchives });
                      setShowDeleteConfirm(false);
                      setDeleteArchives(true);
                    }}
                  >
                    Delete
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Status — see the equivalent defensive `=== false` check on the
            header pill above for why this is not `!printer.is_active`. */}
        {printer.is_active === false ? (
          // Maintenance mode (#1476) — replaces the cover/progress container
          // so the card keeps the same height. Renders for both compact and
          // expanded view modes so the printer stays visible but plainly
          // out-of-service.
          <>
            {viewMode === 'compact' ? (
              <div className="mt-2 flex items-center gap-2 px-2 py-1.5 rounded-full bg-amber-50 dark:bg-amber-500/15 border border-amber-300 dark:border-amber-500/30">
                <Wrench className="w-3 h-3 text-amber-600 dark:text-amber-400 shrink-0" />
                <span className="text-[11px] text-amber-700 dark:text-amber-400 font-medium truncate">
                  {t('printers.maintenance.pillLabel')}
                </span>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] uppercase tracking-wider text-bambu-gray font-medium">
                    {t('printers.status.title', 'Status')}
                  </span>
                  <div className="flex-1 h-[2px] bg-bambu-dark-tertiary" />
                </div>
                <div className="p-3 bg-amber-50 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-500/30 rounded-[10px] flex items-center gap-3">
                  <Wrench className="w-6 h-6 text-amber-600 dark:text-amber-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-amber-700 dark:text-amber-400 font-medium">
                      {t('printers.maintenance.title')}
                    </p>
                    <p className="text-xs text-bambu-gray mt-0.5">
                      {t('printers.maintenance.subtitle')}
                    </p>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={maintenanceMutation.isPending || !hasPermission('printers:update')}
                    onClick={() => maintenanceMutation.mutate(true)}
                    title={!hasPermission('printers:update') ? t('printers.permission.noEdit') : undefined}
                  >
                    {t('printers.maintenance.exitButton')}
                  </Button>
                </div>
              </>
            )}
          </>
        ) : status?.connected && (
          <>
            {/* Compact: Simple status bar */}
            {viewMode === 'compact' ? (
              (() => {
                const hmsErrors = status.hms_errors ? filterKnownHMSErrors(status.hms_errors) : [];
                const hasProblem = status.state === 'FAILED' || hmsErrors.length > 0;
                const compactProgress = status.state === 'RUNNING' || status.state === 'PAUSE'
                  ? Math.max(0, Math.min(100, status.progress || 0))
                  : showClearPlateButton
                    ? 100
                    : hasProblem
                      ? 100
                      : 0;
                const isActiveCompactPrint = status.state === 'RUNNING' || status.state === 'PAUSE';
                const compactProgressClass = hasProblem
                  ? 'bg-status-error'
                  : status.state === 'PAUSE'
                    ? 'bg-status-warning'
                    : 'bg-bambu-green';

                return (
                  <div className="relative mt-2 flex items-center gap-2">
                    <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-bambu-dark-tertiary">
                      <div
                        className={`${compactProgressClass} h-1.5 rounded-full transition-all`}
                        style={{ width: `${compactProgress}%` }}
                      />
                    </div>
                    <span className={`w-9 shrink-0 text-right text-[11px] leading-none ${isActiveCompactPrint ? 'text-white' : 'text-bambu-gray'}`}>
                      {isActiveCompactPrint ? `${Math.round(compactProgress)}%` : '---%'}
                    </span>
                  </div>
                );
              })()
            ) : (
              /* Expanded: Full status section */
              <>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] uppercase tracking-wider text-bambu-gray font-medium">
                    {t('printers.status.title', 'Status')}
                  </span>
                  <div className="flex-1 h-[2px] bg-bambu-dark-tertiary" />
                </div>

                {/* Current Print or Idle Placeholder */}
                {(() => {
                  const isActivePrint = !!(status.current_print && (status.state === 'RUNNING' || status.state === 'PAUSE'));
                  const showRetainedPrint = !isActivePrint && needsPlateClear && retainedPrintJob;
                  const printName = isActivePrint ? activePrintName : showRetainedPrint ? retainedPrintJob.name : null;
                  const coverUrl = isActivePrint ? status.cover_url : showRetainedPrint ? retainedPrintJob.coverUrl : null;
                  const progress = isActivePrint ? (status.progress || 0) : showRetainedPrint ? 100 : 0;

                  return (
                    <div className="p-2 bg-bambu-dark rounded-[10px] relative overflow-hidden">
                      <button
                        onClick={() => setShowSkipObjectsModal(true)}
                        disabled={!isActivePrint || (status.printable_objects_count ?? 0) < 2 || !hasPermission('printers:control')}
                        className={`absolute top-2 right-2 p-1.5 rounded transition-colors z-10 ${
                          isActivePrint && (status.printable_objects_count ?? 0) >= 2 && hasPermission('printers:control')
                            ? 'text-bambu-gray hover:text-white hover:bg-white/10'
                            : 'text-bambu-gray/30 cursor-not-allowed'
                        }`}
                        title={
                          !hasPermission('printers:control')
                            ? t('printers.permission.noControl')
                            : !isActivePrint
                              ? t('printers.skipObjects.onlyWhilePrinting')
                              : (status.printable_objects_count ?? 0) >= 2
                                ? t('printers.skipObjects.tooltip')
                                : t('printers.skipObjects.requiresMultiple')
                        }
                      >
                        <SkipObjectsIcon className="w-4 h-4" />
                        {objectsData && objectsData.skipped_count > 0 && (
                          <span className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 flex items-center justify-center text-[10px] font-bold bg-red-500 text-white rounded-full">
                            {objectsData.skipped_count}
                          </span>
                        )}
                      </button>
                      <div className="flex items-stretch gap-2">
                        <CoverImage
                          url={coverUrl}
                          printName={printName || undefined}
                          className="w-24 h-24 max-[520px]:w-20 max-[520px]:h-20"
                        />
                        <div className="flex h-24 max-[520px]:h-20 min-w-0 flex-1 flex-col justify-between pt-1">
                          <div className="flex min-h-[18px] items-center gap-2 pr-8">
                            <p className="min-w-0 truncate text-sm text-bambu-gray">{getStatusDisplay(status.state, status.stg_cur_name)}</p>
                            {plateStatusPill}
                          </div>
                          <p className={`min-h-[18px] truncate pr-8 text-sm ${printName ? 'text-white' : 'text-bambu-gray/70'}`}>
                            {printName || t('printers.noActiveJob', 'No active job')}
                          </p>
                          <div className="flex h-3 items-center gap-2 text-sm">
                            <div className="h-1.5 min-w-0 flex-1 rounded-full bg-bambu-dark-tertiary">
                              <div
                                className={`${isActivePrint ? (status.state === 'PAUSE' ? 'bg-status-warning' : 'bg-bambu-green') : showRetainedPrint ? 'bg-bambu-green' : 'bg-bambu-dark-tertiary'} h-1.5 rounded-full transition-all`}
                                style={{ width: `${progress}%` }}
                              />
                            </div>
                            <span className={`w-9 shrink-0 pr-1 text-right text-[11px] leading-none ${isActivePrint || showRetainedPrint ? 'text-white' : 'text-bambu-gray'}`}>{isActivePrint || showRetainedPrint ? `${Math.round(progress)}%` : '---%'}</span>
                          </div>
                          <div className="flex min-h-[16px] items-center gap-2 text-xs text-bambu-gray">
                            {isActivePrint ? (
                              <>
                                {status.remaining_time != null && status.remaining_time > 0 && (
                                  <>
                                    <span className="flex items-center gap-1">
                                      <Clock className="w-3 h-3" />
                                      {formatDuration(status.remaining_time * 60)}
                                    </span>
                                    <span className="text-bambu-green font-medium" title={t('printers.estimatedCompletion')}>
                                      ETA {formatETA(status.remaining_time, timeFormat, t)}
                                    </span>
                                  </>
                                )}
                                {status.layer_num != null && status.total_layers != null && status.total_layers > 0 && (
                                  <span className="flex items-center gap-1">
                                    <Layers className="w-3 h-3" />
                                    {status.layer_num}/{status.total_layers}
                                  </span>
                                )}
                                {currentPrintUser && (
                                  <span className="flex items-center gap-1" title={`Started by ${currentPrintUser}`}>
                                    <User className="w-3 h-3" />
                                    {currentPrintUser}
                                  </span>
                                )}
                              </>
                            ) : lastPrint ? (
                              <p className="truncate" title={lastPrint.print_name || lastPrint.filename}>
                                Last: {lastPrint.print_name || lastPrint.filename}
                                {lastPrint.completed_at && (
                                  <span className="ml-1 text-bambu-gray/60">
                                    • {formatDateOnly(lastPrint.completed_at, { month: 'short', day: 'numeric' })}
                                  </span>
                                )}
                              </p>
                            ) : (
                              <span>{t('printers.readyToPrint')}</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <PrinterQueueWidget
                        printerId={printer.id}
                        printerModel={printer.model}
                        loadedFilamentTypes={loadedFilamentTypes}
                        loadedFilaments={loadedFilaments}
                        loadedVariants={loadedVariants}
                        variant="panelExtension"
                      />
                    </div>
                  );
                })()}
              </>
            )}

            {/* Temperatures */}
            {status.temperatures && viewMode === 'expanded' && (() => {
              // Use actual heater states from MQTT stream
              const nozzleHeating = status.temperatures.nozzle_heating || status.temperatures.nozzle_2_heating || false;
              const bedHeating = status.temperatures.bed_heating || false;
              const chamberHeating = status.temperatures.chamber_heating || false;
              const isDualNozzle = printer.nozzle_count === 2 || status.temperatures.nozzle_2 !== undefined;
              const availableHeaterKinds: HeaterSensorKind[] = (() => {
                const kinds: HeaterSensorKind[] = ['nozzle'];
                if (status.temperatures.nozzle_2 !== undefined) kinds.push('nozzle_2');
                kinds.push('bed');
                if (status.temperatures.chamber !== undefined) kinds.push('chamber');
                return kinds;
              })();
              // active_extruder: 0=right, 1=left
              const activeNozzle = status.active_extruder === 1 ? 'L' : 'R';
              // Extended nozzle data from nozzle_rack (H2 series: wear, serial, max_temp, etc.)
              // nozzle_rack id 0 = extruder 0 = RIGHT, id 1 = extruder 1 = LEFT
              const leftNozzleSlot = status.nozzle_rack?.find(s => s.id === 1);
              const rightNozzleSlot = status.nozzle_rack?.find(s => s.id === 0);
              // Single-nozzle models (H2D, H2C): use the primary nozzle (id 0)
              const singleNozzleSlot = rightNozzleSlot || leftNozzleSlot;
              const temperatureControlTitle = canUseTemperatureControls
                ? getControlActionTitle('temperature')
                : getPrinterControlUnavailableTitle('temperature');
              const fanControlTitle = canUseFanControls
                ? getControlActionTitle('fan')
                : getPrinterControlUnavailableTitle('fan');
              const statusControlClass = `relative text-center px-2 py-1.5 bg-bambu-dark rounded-lg flex-1 flex flex-col justify-center items-center transition-colors ${
                canUseTemperatureControls ? 'cursor-pointer hover:bg-bambu-dark-tertiary' : 'cursor-default opacity-80'
              }`;
              // Chamber fan only exists on enclosed Bambu models. Open-frame
              // printers (A1, A1 Mini, A2L, P1P) have no chamber fan — showing
              // the widget there is at best dead UI and at worst suggests a
              // control that does nothing. Mirrors the enclosure-door badge
              // gate above.
              const hasChamberFan = MODELS_WITH_CHAMBER_FAN.has(printer.model ?? '');
              const fanItems = [
                {
                  key: 'part',
                  label: t('printers.fans.partCooling'),
                  value: status.cooling_fan_speed ?? 0,
                  Icon: Fan,
                  activeClass: 'text-cyan-600 dark:text-cyan-400',
                },
                {
                  key: 'aux',
                  label: t('printers.fans.auxiliary'),
                  value: status.big_fan1_speed ?? 0,
                  Icon: Wind,
                  activeClass: 'text-blue-600 dark:text-blue-400',
                },
                ...(hasChamberFan
                  ? [
                      {
                        key: 'chamber',
                        label: t('printers.fans.chamber'),
                        value: status.big_fan2_speed ?? 0,
                        Icon: AirVent,
                        activeClass: 'text-green-600 dark:text-green-400',
                      },
                    ]
                  : []),
              ];

              return (
                <>
                  <div className="mt-2 flex items-stretch gap-1.5 flex-wrap">
                    {/* Nozzle temp - combined for dual nozzle */}
                    <div
                      className={statusControlClass}
                      title={temperatureControlTitle}
                      onClick={() => canUseTemperatureControls && setStatusControlMenu(statusControlMenu === 'nozzle-temp' ? null : 'nozzle-temp')}
                    >
                      <button
                        type="button"
                        className="absolute top-0.5 right-0.5 p-0.5 rounded text-bambu-gray hover:text-white hover:bg-white/10 transition-colors"
                        title={t('printers.heaterHistory.openLabel', 'View heater history')}
                        onClick={(e) => {
                          e.stopPropagation();
                          setHeaterHistoryModal({ initialKind: 'nozzle', availableKinds: availableHeaterKinds });
                        }}
                      >
                        <LineChartIcon className="w-2.5 h-2.5" />
                      </button>
                      <HeaterThermometer className="w-3.5 h-3.5 mb-0.5" color="text-orange-400" isHeating={nozzleHeating} />
                      {status.temperatures.nozzle_2 !== undefined ? (
                        <>
                          <p className="text-[9px] text-bambu-gray">L / R</p>
                          <p className="text-[11px] text-white">
                            {Math.round(status.temperatures.nozzle || 0)}° / {Math.round(status.temperatures.nozzle_2 || 0)}°
                          </p>
                        </>
                      ) : singleNozzleSlot ? (
                        <NozzleSlotHoverCard slot={singleNozzleSlot} index={0} activeStatus filamentName={singleNozzleSlot.filament_id ? filamentInfo?.[singleNozzleSlot.filament_id]?.name : undefined}>
                          <div className="cursor-default">
                            <p className="text-[9px] text-bambu-gray">{t('printers.temperatures.nozzle')}</p>
                            <p className="text-[11px] text-white">
                              {Math.round(status.temperatures.nozzle || 0)}°C
                            </p>
                          </div>
                        </NozzleSlotHoverCard>
                      ) : (
                        <>
                          <p className="text-[9px] text-bambu-gray">{t('printers.temperatures.nozzle')}</p>
                          <p className="text-[11px] text-white">
                            {Math.round(status.temperatures.nozzle || 0)}°C
                          </p>
                        </>
                      )}
                      {statusControlMenu === 'nozzle-temp' && (
                        isDualNozzle ? (
                          <IndicatorControlPopover
                            title="Set Nozzle Temperatures"
                            widthClass="w-[300px]"
                            popoverWidth={300}
                            popoverHeight={260}
                            isPending={nozzleTemperatureMutation.isPending}
                            onClose={() => setStatusControlMenu(null)}
                          >
                            <div className="grid grid-cols-2 gap-2 px-3 py-2.5">
                              <NozzleTemperatureControlBox
                                label="Left Temp"
                                current={status.temperatures.nozzle}
                                target={status.temperatures.nozzle_target}
                                isActive={activeNozzle === 'L'}
                                isPending={nozzleTemperatureMutation.isPending}
                                onSubmit={(target) => nozzleTemperatureMutation.mutate({ target, nozzle: 1 })}
                                options={buildPresetOptions(nozzleTempPresets, 'C')}
                              />
                              <NozzleTemperatureControlBox
                                label="Right Temp"
                                current={status.temperatures.nozzle_2}
                                target={status.temperatures.nozzle_2_target}
                                isActive={activeNozzle === 'R'}
                                isPending={nozzleTemperatureMutation.isPending}
                                onSubmit={(target) => nozzleTemperatureMutation.mutate({ target, nozzle: 0 })}
                                options={buildPresetOptions(nozzleTempPresets, 'C')}
                              />
                            </div>
                          </IndicatorControlPopover>
                        ) : (
                          <IndicatorControlPopover
                            title="Set Nozzle Temperature"
                            unit="°C"
                            customMin={0}
                            customMax={320}
                            isPending={nozzleTemperatureMutation.isPending}
                            options={buildPresetOptions(nozzleTempPresets, 'C')}
                            onClose={() => setStatusControlMenu(null)}
                            onSubmit={(target) => nozzleTemperatureMutation.mutate({ target, nozzle: status.active_extruder ?? 0 })}
                          />
                        )
                      )}
                    </div>
                    <div
                      className={statusControlClass}
                      title={temperatureControlTitle}
                      onClick={() => canUseTemperatureControls && setStatusControlMenu(statusControlMenu === 'bed-temp' ? null : 'bed-temp')}
                    >
                      <button
                        type="button"
                        className="absolute top-0.5 right-0.5 p-0.5 rounded text-bambu-gray hover:text-white hover:bg-white/10 transition-colors"
                        title={t('printers.heaterHistory.openLabel', 'View heater history')}
                        onClick={(e) => {
                          e.stopPropagation();
                          setHeaterHistoryModal({ initialKind: 'bed', availableKinds: availableHeaterKinds });
                        }}
                      >
                        <LineChartIcon className="w-2.5 h-2.5" />
                      </button>
                      <HeaterThermometer className="w-3.5 h-3.5 mb-0.5" color="text-blue-400" isHeating={bedHeating} />
                      <p className="text-[9px] text-bambu-gray">{t('printers.temperatures.bed')}</p>
                      <p className="text-[11px] text-white">
                        {Math.round(status.temperatures.bed || 0)}°C
                      </p>
                      {statusControlMenu === 'bed-temp' && (
                        <IndicatorControlPopover
                          title="Set Bed Temperature"
                          unit="°C"
                          customMin={0}
                          customMax={140}
                          isPending={bedTemperatureMutation.isPending}
                          options={buildPresetOptions(bedTempPresets, 'C')}
                          onClose={() => setStatusControlMenu(null)}
                          onSubmit={(target) => bedTemperatureMutation.mutate(target)}
                        />
                      )}
                    </div>
                    {status.temperatures.chamber !== undefined && (() => {
                      // Sensor-only models (X1C, X1E, P2S) show the chamber reading
                      // but can't act on M141, so we keep the card read-only there.
                      const hasChamberHeater = status.supports_chamber_heater === true;
                      return (
                        <div
                          className={hasChamberHeater
                            ? statusControlClass
                            : 'relative text-center px-2 py-1.5 bg-bambu-dark rounded-lg flex-1 flex flex-col justify-center items-center'}
                          title={hasChamberHeater ? temperatureControlTitle : undefined}
                          onClick={hasChamberHeater
                            ? () => canUseTemperatureControls && setStatusControlMenu(statusControlMenu === 'chamber-temp' ? null : 'chamber-temp')
                            : undefined}
                        >
                          <button
                            type="button"
                            className="absolute top-0.5 right-0.5 p-0.5 rounded text-bambu-gray hover:text-white hover:bg-white/10 transition-colors"
                            title={t('printers.heaterHistory.openLabel', 'View heater history')}
                            onClick={(e) => {
                              e.stopPropagation();
                              setHeaterHistoryModal({ initialKind: 'chamber', availableKinds: availableHeaterKinds });
                            }}
                          >
                            <LineChartIcon className="w-2.5 h-2.5" />
                          </button>
                          <HeaterThermometer className="w-3.5 h-3.5 mb-0.5" color="text-green-400" isHeating={chamberHeating} />
                          <p className="text-[9px] text-bambu-gray">{t('printers.temperatures.chamber')}</p>
                          <p className="text-[11px] text-white">
                            {Math.round(status.temperatures.chamber || 0)}°C
                          </p>
                          {hasChamberHeater && statusControlMenu === 'chamber-temp' && (
                            <IndicatorControlPopover
                              title="Set Chamber Temperature"
                              unit="°C"
                              customMin={0}
                              customMax={60}
                              isPending={chamberTemperatureMutation.isPending}
                              options={buildPresetOptions(chamberTempPresets, 'C')}
                              onClose={() => setStatusControlMenu(null)}
                              onSubmit={(target) => chamberTemperatureMutation.mutate(target)}
                            />
                          )}
                        </div>
                      );
                    })()}
                    {/* Active nozzle indicator for dual-nozzle printers */}
                    {isDualNozzle && (
                      <DualNozzleHoverCard
                        leftSlot={leftNozzleSlot}
                        rightSlot={rightNozzleSlot}
                        activeNozzle={activeNozzle}
                        filamentInfo={filamentInfo}
                      >
                        <div
                          className={`relative text-center px-3 py-1.5 bg-bambu-dark rounded-lg h-full flex flex-col justify-center items-center transition-colors ${
                            canUsePrinterControl ? 'cursor-pointer hover:bg-bambu-dark-tertiary' : 'cursor-default opacity-80'
                          }`}
                          title={canUsePrinterControl ? t('printers.activeNozzle', { nozzle: activeNozzle === 'L' ? t('common.left') : t('common.right') }) : getPrinterControlUnavailableTitle('amsSlot')}
                          onClick={() => canUsePrinterControl && setStatusControlMenu(statusControlMenu === 'nozzle-select' ? null : 'nozzle-select')}
                        >
                          <NozzleIcon className="w-3.5 h-3.5 mb-0.5 text-amber-600 dark:text-amber-400" />
                          <div className="flex items-center gap-2">
                            <span className={`text-[11px] font-bold ${activeNozzle === 'L' ? 'text-amber-700 dark:text-amber-400' : 'text-gray-500'}`}>
                              L{leftNozzleSlot?.nozzle_diameter ? ` ${leftNozzleSlot.nozzle_diameter}` : ''}
                            </span>
                            <span className="text-[9px] text-bambu-gray/40">·</span>
                            <span className={`text-[11px] font-bold ${activeNozzle === 'R' ? 'text-amber-700 dark:text-amber-400' : 'text-gray-500'}`}>
                              R{rightNozzleSlot?.nozzle_diameter ? ` ${rightNozzleSlot.nozzle_diameter}` : ''}
                            </span>
                          </div>
                          <p className="text-[9px] text-bambu-gray">{t('printers.temperatures.nozzle')}</p>
                          {statusControlMenu === 'nozzle-select' && (
                            <IndicatorControlPopover
                              title="Set Nozzle Selection"
                              widthClass="w-[300px]"
                              popoverWidth={300}
                              popoverHeight={140}
                              isPending={selectExtruderMutation.isPending}
                              options={[
                                { label: 'Left', value: 1 },
                                { label: 'Right', value: 0 },
                              ]}
                              onClose={() => setStatusControlMenu(null)}
                              onSubmit={(extruder) => selectExtruderMutation.mutate(extruder)}
                            />
                          )}
                        </div>
                      </DualNozzleHoverCard>
                    )}
                    {/* H2C nozzle rack (tool-changer dock) — only show when rack nozzles exist (IDs >= 2) */}
                    {status.nozzle_rack && status.nozzle_rack.some(s => s.id >= 2) && (
                      <NozzleRackCard slots={status.nozzle_rack} filamentInfo={filamentInfo} />
                    )}
                  </div>
                  <div className="mt-2 flex items-center gap-1.5">
                    {fanItems.map(({ key, label, value, Icon, activeClass }) => {
                      const active = value > 0;
                      return (
                        <div
                          key={key}
                          className={`relative px-2 py-1.5 bg-bambu-dark rounded-lg flex-1 min-w-0 flex items-center justify-center gap-1 transition-colors ${
                            canUseFanControls ? 'cursor-pointer hover:bg-bambu-dark-tertiary' : 'cursor-default opacity-80'
                          }`}
                          title={canUseFanControls ? getControlActionTitle('fan', label) : fanControlTitle}
                          onClick={() => canUseFanControls && setStatusControlMenu(statusControlMenu === `fan-${key}` ? null : `fan-${key}`)}
                        >
                          <Icon className={`w-3 h-3 shrink-0 ${active ? activeClass : 'text-bambu-gray/50'}`} />
                          <span className={`text-[10px] leading-none ${active ? 'text-white' : 'text-bambu-gray/50'}`}>
                            {value}%
                          </span>
                          {statusControlMenu === `fan-${key}` && (
                            <IndicatorControlPopover
                              title={`Set ${label} Speed`}
                              unit="%"
                              customMin={0}
                              customMax={100}
                              isPending={fanSpeedMutation.isPending}
                              options={buildPresetOptions(fanSpeedPresets, '%')}
                              onClose={() => setStatusControlMenu(null)}
                              onSubmit={(speed) => fanSpeedMutation.mutate({ fan: key as 'part' | 'aux' | 'chamber', speed })}
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </>
              );
            })()}

            {viewMode === 'expanded' && showClearPlateButton && (
              <button
                type="button"
                onClick={() => clearPlateMutation.mutate()}
                disabled={clearPlateMutation.isPending || !hasPermission('printers:clear_plate')}
                className="mt-2 w-full inline-flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg bg-yellow-100 dark:bg-yellow-500/20 border border-yellow-300 dark:border-yellow-400/40 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-500/30 transition-colors text-xs font-medium disabled:opacity-50"
                title={!hasPermission('printers:clear_plate') ? t('printers.permission.noControl') : t('printers.plateStatus.markCleared')}
              >
                {clearPlateMutation.isPending ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <PlateClearedIcon className="w-4 h-4" />
                )}
                {t('printers.plateStatus.markCleared')}
              </button>
            )}

            {/* Controls */}
            {viewMode === 'expanded' && (() => {
              // Determine print state for control buttons
              const isRunning = status.state === 'RUNNING';
              const isPaused = status.state === 'PAUSE';
              const isPrinting = isRunning || isPaused;
              const isControlBusy = stopPrintMutation.isPending || pausePrintMutation.isPending || resumePrintMutation.isPending;
              const unavailablePrintActionClass = 'bg-bambu-dark text-bambu-gray/50 cursor-not-allowed opacity-50';
              const iconControlClass = 'flex h-8 w-8 items-center justify-center rounded-lg text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
              const printControlClass = 'flex h-8 w-20 items-center justify-center gap-1 px-2 rounded-lg text-xs font-medium transition-colors';

              return (
                <div className="mt-3">
                  {/* Section Header */}
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] uppercase tracking-wider text-bambu-gray font-medium">
                      {t('printers.controls')}
                    </span>
                    <div className="flex-1 h-[2px] bg-bambu-dark-tertiary" />
                  </div>

                  <div className="flex flex-wrap items-start justify-between gap-x-2 gap-y-2">
                    {/* Left: Secondary controls */}
                    <div className="flex flex-wrap items-center gap-2 min-w-0">
                      <button
                        onClick={() => chamberLightMutation.mutate(!status.chamber_light)}
                        disabled={!canUseLightControl || chamberLightMutation.isPending}
                        className={`${iconControlClass} ${
                          status.chamber_light
                            ? 'bg-yellow-50 dark:bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-500/20'
                            : 'bg-bambu-dark text-bambu-gray/50 hover:bg-bambu-dark-tertiary hover:text-white'
                        }`}
                        title={!canUseLightControl ? getPrinterControlUnavailableTitle('light') : getControlActionTitle('light', status.chamber_light ? t('printers.chamberLightOff') : t('printers.chamberLightOn'))}
                      >
                        <ChamberLight on={status.chamber_light ?? false} className="w-4 h-4" />
                      </button>

                      {/* Airduct Mode (P2S / X2D / H2*) */}
                      {(['P2S', 'X2D', 'H2D', 'H2C', 'H2S'].includes(printer.model ?? '')) && (() => {
                        const isHeating = status.airduct_mode === 1;
                        const Icon = isHeating ? Flame : Snowflake;
                        const color = isHeating ? 'text-orange-600 dark:text-orange-400' : 'text-sky-600 dark:text-sky-400';
                        const bg = isHeating ? 'bg-orange-50 dark:bg-orange-500/10 text-orange-700 dark:text-orange-400 hover:bg-orange-500/20' : 'bg-sky-50 dark:bg-sky-500/10 text-sky-700 dark:text-sky-400 hover:bg-sky-500/20';
                        return (
                          <div className="relative">
                            <button
                              onClick={() => setShowAirductMenu(showAirductMenu === printer.id ? null : printer.id)}
                              disabled={!canUsePrinterControl}
                              className={`${iconControlClass} ${bg}`}
                              title={!canUsePrinterControl ? getPrinterControlUnavailableTitle('airduct') : `${t('printers.airduct.title')}: ${isHeating ? t('printers.airduct.heating') : t('printers.airduct.cooling')}`}
                            >
                              <Icon className={`w-4 h-4 ${color}`} />
                            </button>
                            {showAirductMenu === printer.id && (
                              <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowAirductMenu(null)} />
                                <div className="absolute bottom-full left-0 mb-1 z-50 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg shadow-lg py-1 min-w-[130px]">
                                  {([
                                    { mode: 'cooling', label: t('printers.airduct.cooling'), modeId: 0 },
                                    { mode: 'heating', label: t('printers.airduct.heating'), modeId: 1 },
                                  ] as const).map(({ mode, label, modeId }) => (
                                    <button
                                      key={mode}
                                      onClick={() => {
                                        airductMutation.mutate(mode);
                                        setShowAirductMenu(null);
                                      }}
                                      className={`w-full text-left px-3 py-1.5 text-xs transition-colors flex items-center gap-2 ${
                                        status.airduct_mode === modeId
                                          ? 'text-bambu-green bg-bambu-green/10'
                                          : 'text-white hover:bg-bambu-dark-tertiary'
                                      }`}
                                    >
                                      {mode === 'heating' ? <Flame className="w-3 h-3" /> : <Snowflake className="w-3 h-3" />}
                                      {label}
                                    </button>
                                  ))}
                                </div>
                              </>
                            )}
                          </div>
                        );
                      })()}

                      {/* Movement — compact badge, popover holds XY, Z, and home controls */}
                      {(() => {
                        const canControl = canUsePrinterControl;
                        const disabled = isPrinting || !canControl;
                        const bambuIsPlateBelow = true; // positive Z moves plate away from nozzle
                        const jogButtonClass = 'flex h-8 w-8 items-center justify-center rounded bg-indigo-100 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 transition-colors hover:bg-indigo-200 dark:hover:bg-indigo-500/30 disabled:cursor-not-allowed disabled:opacity-50';
                        const requestZJog = (direction: 1 | -1) => {
                          const signed = direction * bedJogStep * (bambuIsPlateBelow ? 1 : -1);
                          const warnedKey = `printops.bedJog.warned.${printer.id}`;
                          const warned = (() => {
                            try { return sessionStorage.getItem(warnedKey) === '1'; }
                            catch { return false; }
                          })();
                          if (warned) {
                            bedJogMutation.mutate({ distance: signed, force: true });
                          } else {
                            setShowNotHomedModal({ distance: signed });
                          }
                        };
                        const requestXyJog = (x: number, y: number) => {
                          xyJogMutation.mutate({ x, y });
                        };
                        const requestExtruderJog = (distance: number) => {
                          extruderJogMutation.mutate(distance);
                        };
                        return (
                          <div className="relative">
                            <button
                              onClick={() => setShowBedJogMenu(showBedJogMenu === printer.id ? null : printer.id)}
                              disabled={disabled}
                              className={`${iconControlClass} ${
                                disabled
                                  ? 'bg-bambu-dark text-bambu-gray/50 cursor-not-allowed'
                                  : 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-400 hover:bg-indigo-500/20'
                              }`}
                              title={!canControl ? getPrinterControlUnavailableTitle('movement') : isPrinting ? t('printers.bedJog.disabledWhilePrinting') : t('printers.bedJog.title')}
                            >
                              <Move className="w-4 h-4" />
                            </button>
                            {showBedJogMenu === printer.id && (
                              <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowBedJogMenu(null)} />
                                <div className="absolute bottom-full left-0 mb-1 z-50 flex w-[216px] flex-col overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary shadow-2xl">
                                  <div className="shrink-0 px-3 py-2.5 text-center text-sm font-medium text-white">
                                    {t('printers.bedJog.title')}
                                  </div>
                                  <div className="h-px bg-bambu-dark-tertiary" />
                                  <div className="flex justify-center px-3 py-2.5">
                                    <div className="flex items-center justify-center gap-3">
                                    <div className="grid grid-cols-3 gap-1">
                                      <div />
                                      <button
                                        onClick={() => requestXyJog(0, bedJogStep)}
                                        disabled={xyJogMutation.isPending}
                                        className={jogButtonClass}
                                        aria-label="Move Y forward"
                                      >
                                        <ArrowUp className="w-4 h-4" />
                                      </button>
                                      <div />
                                      <button
                                        onClick={() => requestXyJog(-bedJogStep, 0)}
                                        disabled={xyJogMutation.isPending}
                                        className={jogButtonClass}
                                        aria-label="Move X left"
                                      >
                                        <ArrowLeft className="w-4 h-4" />
                                      </button>
                                      <button
                                        onClick={() => {
                                          setShowBedJogMenu(null);
                                          homeAxesMutation.mutate('all');
                                        }}
                                        disabled={homeAxesMutation.isPending}
                                        className={jogButtonClass}
                                        aria-label={t('printers.bedJog.homeZ')}
                                      >
                                        <Home className="w-4 h-4" />
                                      </button>
                                      <button
                                        onClick={() => requestXyJog(bedJogStep, 0)}
                                        disabled={xyJogMutation.isPending}
                                        className={jogButtonClass}
                                        aria-label="Move X right"
                                      >
                                        <ArrowRight className="w-4 h-4" />
                                      </button>
                                      <div />
                                      <button
                                        onClick={() => requestXyJog(0, -bedJogStep)}
                                        disabled={xyJogMutation.isPending}
                                        className={jogButtonClass}
                                        aria-label="Move Y back"
                                      >
                                        <ArrowDown className="w-4 h-4" />
                                      </button>
                                      <div />
                                    </div>
                                    <div className="flex flex-col items-center gap-1">
                                      <button
                                        onClick={() => requestZJog(-1)}
                                        disabled={bedJogMutation.isPending}
                                        className={jogButtonClass}
                                        aria-label={t('printers.bedJog.up')}
                                      >
                                        <ArrowUp className="w-4 h-4" />
                                      </button>
                                      <div className="flex h-8 w-8 items-center justify-center text-bambu-gray/80">
                                        <Layers className="w-4 h-4" />
                                      </div>
                                      <button
                                        onClick={() => requestZJog(1)}
                                        disabled={bedJogMutation.isPending}
                                        className={jogButtonClass}
                                        aria-label={t('printers.bedJog.down')}
                                      >
                                        <ArrowDown className="w-4 h-4" />
                                      </button>
                                    </div>
                                    <div className="flex flex-col items-center gap-1">
                                      <button
                                        onClick={() => requestExtruderJog(-bedJogStep)}
                                        disabled={extruderJogMutation.isPending}
                                        className={jogButtonClass}
                                        aria-label="Retract filament"
                                      >
                                        <ArrowUp className="w-4 h-4" />
                                      </button>
                                      <div className="flex h-8 w-8 items-center justify-center text-bambu-gray/80">
                                        <span className="text-sm font-semibold leading-none">E</span>
                                      </div>
                                      <button
                                        onClick={() => requestExtruderJog(bedJogStep)}
                                        disabled={extruderJogMutation.isPending}
                                        className={jogButtonClass}
                                        aria-label="Extrude filament"
                                      >
                                        <ArrowDown className="w-4 h-4" />
                                      </button>
                                    </div>
                                    </div>
                                  </div>
                                  <div className="h-px bg-bambu-dark-tertiary" />
                                  <div className="px-3 pt-2.5 pb-3">
                                    <div className="mb-1 text-[9px] uppercase tracking-wider text-bambu-gray/70">
                                      {t('printers.bedJog.step')}
                                    </div>
                                    <div className="flex gap-1">
                                    {[1, 10, 50].map((step) => (
                                      <button
                                        key={step}
                                        onClick={() => setBedJogStep(step)}
                                        className={`flex-1 px-1 py-1 rounded text-[10px] transition-colors ${
                                          bedJogStep === step
                                            ? 'bg-bambu-green/20 text-bambu-green'
                                            : 'bg-bambu-dark text-bambu-gray hover:bg-bambu-dark-tertiary'
                                        }`}
                                      >
                                        {step}
                                      </button>
                                    ))}
                                    </div>
                                  </div>
                                </div>
                              </>
                            )}
                          </div>
                        );
                      })()}

                      <div className={`inline-flex rounded-lg ${printer.plate_detection_enabled ? 'ring-1 ring-green-500' : ''}`}>
                        <button
                          onClick={handleTogglePlateDetection}
                          disabled={!status.connected || plateDetectionMutation.isPending || !hasPermission('printers:update')}
                          className={`${iconControlClass} rounded-r-none ${
                            printer.plate_detection_enabled
                              ? 'bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 hover:bg-green-500/20'
                              : 'bg-bambu-dark text-bambu-gray/50 hover:bg-bambu-dark-tertiary hover:text-white'
                          }`}
                          title={!hasPermission('printers:update') ? t('printers.plateDetection.noPermission') : (printer.plate_detection_enabled ? t('printers.plateDetection.enabledClick') : t('printers.plateDetection.disabledClick'))}
                        >
                          {plateDetectionMutation.isPending ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <ScanSearch className="w-4 h-4" />
                          )}
                        </button>
                        <button
                          onClick={handleOpenPlateManagement}
                          disabled={!status.connected || isCheckingPlate || !hasPermission('printers:update')}
                          className={`flex h-8 w-8 items-center justify-center rounded-r-lg border-l border-bambu-dark-tertiary transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                            printer.plate_detection_enabled
                              ? 'bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 hover:bg-green-500/20'
                              : 'bg-bambu-dark text-bambu-gray/50 hover:bg-bambu-dark-tertiary hover:text-white'
                          }`}
                          title={!hasPermission('printers:update') ? t('printers.plateDetection.noPermission') : t('printers.plateDetection.manageCalibration')}
                        >
                          {isCheckingPlate ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <ChevronDown className="w-4 h-4" />
                          )}
                        </button>
                      </div>

                      {/* Print Speed */}
                      {(() => {
                        const canUseSpeedControl = canUsePrinterControlAction('speed');
                        return (
                        <div className="relative">
                          <button
                            data-testid="speed-control"
                            onClick={() => setShowSpeedMenu(showSpeedMenu === printer.id ? null : printer.id)}
                            disabled={!isPrinting || !canUseSpeedControl}
                            className={`${iconControlClass} ${
                              isPrinting && canUseSpeedControl
                                ? 'bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 hover:bg-amber-500/20'
                                : 'bg-bambu-dark text-bambu-gray/50 cursor-not-allowed'
                            }`}
                            title={!canUseSpeedControl ? getPrinterControlUnavailableTitle('speed') : isPrinting ? getControlActionTitle('speed', t('printers.speed.title')) : undefined}
                          >
                            <Gauge className="w-4 h-4" />
                          </button>
                          {showSpeedMenu === printer.id && (
                            <>
                              <div className="fixed inset-0 z-40" onClick={() => setShowSpeedMenu(null)} />
                              <div className="absolute bottom-full left-0 mb-1 z-50 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg shadow-lg py-1 min-w-[130px]">
                                {([
                                  { mode: 1, label: t('printers.speed.silent') },
                                  { mode: 2, label: t('printers.speed.standard') },
                                  { mode: 3, label: t('printers.speed.sport') },
                                  { mode: 4, label: t('printers.speed.ludicrous') },
                                ] as const).map(({ mode, label }) => (
                                  <button
                                    key={mode}
                                    onClick={() => {
                                      printSpeedMutation.mutate(mode);
                                      setShowSpeedMenu(null);
                                    }}
                                    className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                                      status.speed_level === mode
                                        ? 'text-bambu-green bg-bambu-green/10'
                                        : 'text-white hover:bg-bambu-dark-tertiary'
                                    }`}
                                  >
                                    {label}
                                  </button>
                                ))}
                              </div>
                            </>
                          )}
                        </div>
                        );
                      })()}

                    </div>

                    {/* Right: Print Control Buttons */}
                    <div className="ml-auto flex items-center justify-end gap-2 flex-shrink-0">
                      {/* Pause/Resume button */}
                      {(() => {
                        const pauseAction: PrinterControlAction = isPaused ? 'resume' : 'pause';
                        const canUsePauseAction = canUsePrinterControlAction(pauseAction);
                        const pauseUnavailable = !isPrinting || isControlBusy || !canUsePauseAction;
                        return (
                      <button
                        onClick={() => isPaused ? setShowResumeConfirm(true) : setShowPauseConfirm(true)}
                        disabled={pauseUnavailable}
                        className={`
                          ${printControlClass}
                          ${pauseUnavailable
                            ? unavailablePrintActionClass
                            : isPaused
                              ? 'bg-bambu-green/20 text-bambu-green hover:bg-bambu-green/30'
                              : 'bg-yellow-100 dark:bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-500/30'
                          }
                        `}
                        title={!canUsePauseAction ? getPrinterControlUnavailableTitle(pauseAction) : getControlActionTitle(pauseAction, isPaused ? t('printers.resume') : t('printers.pause'))}
                      >
                        {isPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
                        {isPaused ? t('printers.resume') : t('printers.pause')}
                      </button>
                        );
                      })()}

                      {/* Stop button */}
                      {(() => {
                        const canUseStopAction = canUsePrinterControlAction('stop');
                        const stopUnavailable = !isPrinting || isControlBusy || !canUseStopAction;
                        return (
                      <button
                        onClick={() => setShowStopConfirm(true)}
                        disabled={stopUnavailable}
                        className={`
                          ${printControlClass}
                          ${stopUnavailable
                            ? unavailablePrintActionClass
                            : 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400 hover:bg-red-500/30'
                          }
                        `}
                        title={!canUseStopAction ? getPrinterControlUnavailableTitle('stop') : getControlActionTitle('stop', t('printers.stop'))}
                      >
                        <Square className="w-3 h-3" />
                        {t('printers.stop')}
                      </button>
                        );
                      })()}
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* AMS Units - 2-Column Grid Layout */}
            {(amsData?.length > 0 || status.vt_tray.length > 0) && viewMode === 'expanded' && (() => {
              // Separate regular AMS (4-tray) from HT AMS (1-tray)
              const regularAms = amsData.filter(ams => ams.tray.length > 1);
              const htAms = amsData.filter(ams => ams.tray.length === 1);
              const isDualNozzle = printer.nozzle_count === 2 || status?.temperatures?.nozzle_2 !== undefined;
              const filamentSlotClass = 'min-w-14';
              // #1762 (comment 2): while a print is running/paused, overlay a small
              // "P1 / P2 / P3" pill on each slot referenced by the active print's
              // mapping. Catches the reporter's scenario — "any X1C" queue job
              // staged to a printer with mismatched filament: the wrong-slot pill
              // is visible the instant printing starts.
              const isPrintingForMapping = status.state === 'RUNNING' || status.state === 'PAUSE';
              const activeMapping: number[] = isPrintingForMapping && Array.isArray(status.ams_mapping)
                ? status.ams_mapping
                : [];
              const getAmsCardStyle = (slotCount: number): React.CSSProperties => {
                const boundedSlotCount = Math.max(1, slotCount);
                const gapCount = Math.max(0, boundedSlotCount - 1);
                const minWidth = `calc(${boundedSlotCount} * 3.5rem + ${gapCount} * 0.25rem + 1rem)`;
                return {
                  flex: `1 1 ${minWidth}`,
                  minWidth,
                };
              };

              return (
                <div className="mt-3">
                  {/* Section Header */}
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] uppercase tracking-wider text-bambu-gray font-medium">
                      {t('printers.filaments')}
                    </span>
                    <AmsBackupBadge
                      state={status.ams_filament_backup}
                      onClick={() => setAmsBackupModalOpen(true)}
                    />
                    <div className="flex-1 h-[2px] bg-bambu-dark-tertiary" />
                  </div>

                  {/* AMS Content */}
                  <div className="flex flex-wrap gap-2">
                    {/* Regular AMS units */}
                    {regularAms.map((ams) => {
                      const mappedExtruderId = amsExtruderMap[String(ams.id)];
                      const normalizedId = ams.id >= 128 ? ams.id - 128 : ams.id;
                      const extruderId = mappedExtruderId !== undefined ? mappedExtruderId : normalizedId;
                      const isLeftNozzle = extruderId === 1;
                      const isRightNozzle = extruderId === 0;

                      return (
                        <div key={ams.id} style={getAmsCardStyle(4)} className="min-w-0 p-2 bg-bambu-dark rounded-[10px] space-y-1">
                            {/* Header: Label + Stats (no icon) */}
                            <div className="flex w-full min-h-7 items-center justify-between gap-2 rounded-lg bg-bambu-dark-secondary px-2 py-1">
                              <div className="flex min-w-0 flex-1 items-center gap-1.5">
                                {/* AMS name — hover to see serial, firmware, and edit friendly name */}
                                <AmsNameHoverCard
                                  ams={ams}
                                  printerId={printer.id}
                                  label={getAmsLabel(ams.id, ams.tray.length)}
                                  amsLabels={amsLabels}
                                  canEdit={hasPermission('printers:update')}
                                  onSaved={refetchAmsLabels}
                                >
                                  <span className="block truncate text-[10px] text-white font-medium cursor-default select-none">
                                    {amsLabels?.[ams.id] || getAmsLabel(ams.id, ams.tray.length)}
                                  </span>
                                </AmsNameHoverCard>
                                {isDualNozzle && (isLeftNozzle || isRightNozzle) && (
                                  <NozzleBadge side={isLeftNozzle ? 'L' : 'R'} />
                                )}
                              </div>
                              {(ams.humidity != null || ams.temp != null) && (
                                <div className="flex shrink-0 items-center gap-1.5">
                                  {ams.humidity != null && (
                                    <HumidityIndicator
                                      humidity={ams.humidity}
                                      goodThreshold={amsThresholds?.humidityGood}
                                      fairThreshold={amsThresholds?.humidityFair}
                                      onClick={() => setAmsHistoryModal({
                                        amsId: ams.id,
                                        amsLabel: getAmsLabel(ams.id, ams.tray.length),
                                        mode: 'humidity',
                                      })}
                                      compact
                                    />
                                  )}
                                  {ams.temp != null && (
                                    <div className="mr-1">
                                      <TemperatureIndicator
                                        temp={ams.temp}
                                        goodThreshold={amsThresholds?.tempGood}
                                        fairThreshold={amsThresholds?.tempFair}
                                        onClick={() => setAmsHistoryModal({
                                          amsId: ams.id,
                                          amsLabel: getAmsLabel(ams.id, ams.tray.length),
                                          mode: 'temperature',
                                        })}
                                        compact
                                      />
                                    </div>
                                  )}
                                  {/* Drying button — only for AMS 2 Pro (n3f) and AMS-HT (n3s) */}
                                  {(status.supports_drying || status.drying_screen_only) && (ams.module_type === 'n3f' || ams.module_type === 'n3s') && hasPrinterControlPermission && (
                                    <button
                                      disabled={localPrinterControlUnavailable || status.drying_screen_only || !!(ams.dry_sf_reason?.length && ams.dry_time === 0)}
                                      onClick={(e) => {
                                        if (!canUsePrinterControl) return;
                                        if (ams.dry_time > 0) {
                                          stopDryingMutation.mutate(ams.id);
                                        } else if (dryingPopoverAmsId === ams.id) {
                                          setDryingPopoverAmsId(null);
                                        } else {
                                          const firstTray = ams.tray.find(t => t.tray_type);
                                          const filType = (firstTray?.tray_type || 'PLA').split(' ')[0].toUpperCase();
                                          const preset = dryingPresets[filType] || dryingPresets['PLA'];
                                          const moduleType = ams.module_type as 'n3f' | 'n3s';
                                          setDryingFilament(filType);
                                          setDryingTemp(preset[moduleType] || preset.n3f);
                                          setDryingDuration(moduleType === 'n3s' ? preset.n3s_hours : preset.n3f_hours);
                                          setDryingRotateTray(false);
                                          setDryingPopoverModuleType(ams.module_type);
                                          setDryingPopoverAmsId(ams.id);
                                          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                                          setDryingPopoverPos(computePopoverPosition({ triggerRect: rect, popoverWidth: DRYING_POPOVER_WIDTH, estimatedHeight: DRYING_POPOVER_ESTIMATED_HEIGHT, horizontalAlign: 'center' }));
                                        }
                                      }}
                                      className={`ml-1 flex items-center gap-0.5 px-1 py-0.5 rounded text-[9px] transition-colors ${
                                        ams.dry_time > 0
                                          ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400'
                                          : localPrinterControlUnavailable || status.drying_screen_only || ams.dry_sf_reason?.length
                                            ? 'bg-bambu-dark text-bambu-gray/50 cursor-not-allowed'
                                            : 'bg-bambu-dark text-bambu-gray hover:text-white hover:bg-bambu-dark/80'
                                      }`}
                                      title={localPrinterControlUnavailable ? getLocalPrinterControlUnavailableTitle('drying') : status.drying_screen_only ? t('printers.drying.screenOnly') : ams.dry_time > 0 ? t('printers.drying.stop') : ams.dry_sf_reason?.length ? t('printers.drying.powerRequired') : t('printers.drying.start')}
                                    >
                                      <Flame className="w-3 h-3" />
                                    </button>
                                  )}
                                </div>
                              )}
                            </div>
                            {/* Drying status bar */}
                            {ams.dry_time > 0 && (
                              <div className="flex items-center gap-2 rounded-lg bg-amber-50 dark:bg-amber-500/10 px-2 py-1 text-[9px]">
                                <Flame className="w-3 h-3 text-amber-600 dark:text-amber-400 shrink-0" />
                                <span className="text-amber-700 dark:text-amber-400 font-medium">{t('printers.drying.active')}</span>
                                {ams.dry_filament && ams.dry_target_temp != null && (
                                  <span className="text-amber-700/80 dark:text-amber-300/70">
                                    {t('printers.drying.targetSummary', { filament: ams.dry_filament, temp: ams.dry_target_temp })}
                                  </span>
                                )}
                                <span className="text-amber-700/80 dark:text-amber-300/70">
                                  {t('printers.drying.timeRemaining', {
                                    time: ams.dry_time >= 60
                                      ? `${Math.floor(ams.dry_time / 60)}h ${ams.dry_time % 60}m`
                                      : `${ams.dry_time}m`
                                  })}
                                </span>
                                {!status.drying_screen_only && (
                                  <button
                                    onClick={() => stopDryingMutation.mutate(ams.id)}
                                    disabled={stopDryingMutation.isPending}
                                    className="ml-auto text-amber-700 dark:text-amber-400 hover:text-amber-900 dark:hover:text-amber-300 transition-colors disabled:opacity-50"
                                    title={t('printers.drying.stop')}
                                  >
                                    <X className="w-3 h-3" />
                                  </button>
                                )}
                              </div>
                            )}
                            {/* Slots grid: 4 columns - always render 4 slots */}
                            <div className="grid w-full grid-cols-[repeat(4,minmax(3.5rem,1fr))] gap-1">
                              {[0, 1, 2, 3].map((slotIdx) => {
                                // Find tray data for this slot (may be undefined if data incomplete)
                                // Use array index if available, as tray.id may not always be set
                                const tray = ams.tray[slotIdx] || ams.tray.find(t => t.id === slotIdx);
                                const hasFillLevel = tray?.tray_type && tray.remain >= 0;
                                const isEmpty = !tray?.tray_type;
                                const emptyKind = getEmptySlotKind(tray);
                                // Check if this is the currently loaded tray
                                // Global tray ID = ams.id * 4 + slot index (for standard AMS)
                                const globalTrayId = ams.id * 4 + slotIdx;
                                const isActive = effectiveTrayNow === globalTrayId;
                                const isExpectedSlot = expectedTray !== null && expectedTray === globalTrayId;
                                const isRanOutSlot = previousTray !== null && previousTray === globalTrayId;
                                // Get cloud preset info if available
                                const cloudInfo = tray?.tray_info_idx ? filamentInfo?.[tray.tray_info_idx] : null;
                                // Get saved slot preset mapping (for user-configured slots)
                                const slotPreset = slotPresets?.[globalTrayId];

                                // Fill level fallback chain: Spoolman → Inventory → AMS remain
                                const trayTag = (tray?.tray_uuid || tray?.tag_uid || getFallbackSpoolTag(printer.serial_number, ams.id, slotIdx))?.toUpperCase();
                                const linkedSpool = trayTag ? linkedSpools?.[trayTag] : undefined;
                                const spoolmanFill = getSpoolmanFillLevel(linkedSpool);
                                // Slot-assigned-only spool fill (no tag link required)
                                const slotAssignmentForFill = spoolmanEnabled && !spoolmanLoading
                                  ? spoolmanSlotAssignments?.find(a => a.printer_id === printer.id && a.ams_id === ams.id && a.tray_id === slotIdx)
                                  : undefined;
                                const slotSpoolForFill = slotAssignmentForFill
                                  ? spoolmanSpools?.find(s => s.id === slotAssignmentForFill.spoolman_spool_id)
                                  : undefined;
                                const slotSpoolFill = (slotSpoolForFill && (slotSpoolForFill.label_weight ?? 0) > 0)
                                  ? Math.round(Math.max(0, (slotSpoolForFill.label_weight ?? 0) - slotSpoolForFill.weight_used) / (slotSpoolForFill.label_weight ?? 1) * 100)
                                  : null;
                                const inventoryAssignment = onGetAssignment?.(printer.id, ams.id, slotIdx);
                                const inventoryFill = (() => {
                                  const sp = inventoryAssignment?.spool;
                                  if (sp && sp.label_weight > 0 && sp.weight_used != null) {
                                    return Math.round(Math.max(0, sp.label_weight - sp.weight_used) / sp.label_weight * 100);
                                  }
                                  return null;
                                })();
                                // If inventory says 0% but AMS reports positive remain, prefer AMS
                                // (inventory weight_used may be stale or over-counted — #676)
                                const resolvedInventoryFill = (inventoryFill === 0 && hasFillLevel && tray.remain > 0)
                                  ? null : inventoryFill;
                                const effectiveFill = spoolmanFill ?? slotSpoolFill ?? resolvedInventoryFill ?? (hasFillLevel ? tray.remain : null);
                                const fillSource = (spoolmanFill !== null || slotSpoolFill !== null) ? 'spoolman' as const
                                  : resolvedInventoryFill !== null ? 'inventory' as const
                                  : hasFillLevel ? 'ams' as const
                                  : undefined;

                                // Build filament data for hover card
                                const filamentData = tray?.tray_type ? {
                                  vendor: (isBambuLabSpool(tray) ? 'Bambu Lab' : 'Generic') as 'Bambu Lab' | 'Generic',
                                  // Spoolman spool name wins over cloud lookup so a slot bound to
                                  // a Spoolman spool shows that spool's preset name (e.g. "Devil
                                  // Design PLA") instead of whatever the printer's filament_id
                                  // resolves to in the cloud catalog (often "Generic PLA" for
                                  // P-prefix local presets). Spoolman's filament.name is just the
                                  // material+subtype ("PLA Basic"); prepend the spool's brand so
                                  // the hover card shows "Devil Design PLA Basic" rather than the
                                  // vendor-less form. Strip the "@<printer>..." suffix that
                                  // BambuStudio appends to user-preset names.
                                  profile: slotPreset?.preset_name || (slotSpoolForFill ? [slotSpoolForFill.brand, slotSpoolForFill.slicer_filament_name?.split('@')[0].trim() || slotSpoolForFill.material].filter(Boolean).join(' ').trim() : null) || inventoryAssignment?.spool?.slicer_filament_name || cloudInfo?.name || tray.tray_sub_brands || tray.tray_type,
                                  colorName: getColorName(tray.tray_color || ''),
                                  colorHex: tray.tray_color || null,
                                  kFactor: formatKValue(tray.k),
                                  fillLevel: effectiveFill,
                                  trayUuid: tray.tray_uuid || null,
                                  tagUid: tray.tag_uid || null,
                                  fillSource,
                                } : null;

                                // Check if this specific slot is being refreshed
                                const isRefreshing = refreshingSlot?.amsId === ams.id &&
                                  refreshingSlot?.slotId === slotIdx;

                                // #1762 (comment 2): which print-slot is mapped to THIS AMS slot.
                                const activePrintSlotIdx = activeMapping.indexOf(globalTrayId);
                                const activePrintSlotLabel = activePrintSlotIdx >= 0
                                  ? `P${activePrintSlotIdx + 1}`
                                  : null;
                                // Slot visual content (goes inside hover card)
                                const slotVisual = (
                                  <div
                                    className={`relative w-full bg-bambu-dark-secondary rounded-lg p-1 text-center ${isEmpty ? 'opacity-50' : ''} ${
                                      isExpectedSlot
                                        ? 'ring-2 ring-amber-400 ring-offset-1 ring-offset-bambu-dark animate-pulse'
                                        : isRanOutSlot
                                          ? 'ring-2 ring-red-500/60 ring-offset-1 ring-offset-bambu-dark'
                                          : isActive
                                            ? 'ring-2 ring-bambu-green ring-offset-1 ring-offset-bambu-dark'
                                            : ''
                                    }`}
                                  >
                                    {isExpectedSlot && (
                                      <span
                                        aria-label={t('printers.expectedSlot.ariaLabel', { n: slotIdx + 1 })}
                                        title={t('printers.expectedSlot.title')}
                                        className="absolute top-0.5 left-0.5 px-1 py-px text-[8px] font-bold text-bambu-dark bg-amber-400 rounded pointer-events-none leading-none"
                                      >
                                        !
                                      </span>
                                    )}
                                    {activePrintSlotLabel && (
                                      <span
                                        aria-label={t('printers.activeJobSlot.ariaLabel', { n: activePrintSlotIdx + 1 })}
                                        title={t('printers.activeJobSlot.title', { n: activePrintSlotIdx + 1 })}
                                        className="absolute top-0.5 right-0.5 px-1 py-px text-[8px] font-bold text-bambu-dark bg-bambu-green rounded pointer-events-none leading-none"
                                      >
                                        {activePrintSlotLabel}
                                      </span>
                                    )}
                                    {/* Filament color circle with 1-based slot number centered inside */}
                                    <FilamentSlotCircle
                                      trayColor={tray?.tray_color}
                                      trayType={tray?.tray_type}
                                      isEmpty={isEmpty}
                                      emptyKind={emptyKind}
                                      slotNumber={slotIdx + 1}
                                    />
                                    <div className="text-[9px] text-white font-bold truncate">
                                      {tray?.tray_type || t(emptyKind === 'reset' ? 'ams.slotUnconfigured' : 'ams.slotEmpty')}
                                    </div>
                                    {/* Fill bar */}
                                    <div className="mt-1 h-1.5 bg-black/30 rounded-full overflow-hidden">
                                      {effectiveFill !== null && effectiveFill >= 0 && !isEmpty && tray && (
                                        <div
                                          className="h-full rounded-full transition-all"
                                          style={{
                                            width: `${effectiveFill}%`,
                                            backgroundColor: getFillBarColor(effectiveFill),
                                          }}
                                        />
                                      )}
                                    </div>
                                  </div>
                                );

                                // Wrapper with menu button, dropdown, and loading overlay (outside hover card)
                                return (
                                  <div key={slotIdx} className={`relative group w-full ${filamentSlotClass}`}>
                                    {/* Loading overlay during RFID re-read */}
                                    {isRefreshing && (
                                      <div className="absolute inset-0 bg-bambu-dark-tertiary/80 rounded flex items-center justify-center z-20">
                                        <RefreshCw className="w-4 h-4 text-bambu-green animate-spin" />
                                      </div>
                                    )}
                                    {/* Hover card wraps only the visual content */}
                                    {filamentData ? (
                                      <FilamentHoverCard
                                        data={filamentData}
                                        actions={renderAmsSlotActions({
                                          amsId: ams.id,
                                          slotId: slotIdx,
                                          loadTrayId: ams.id * 4 + slotIdx,
                                          isRefreshing,
                                        })}
                                        spoolman={{
                                          enabled: spoolmanEnabled,
                                          // #1457: slot assignment is the user's most explicit action — it must
                                          // outrank the tag-link, which can be stale when a non-RFID slot's
                                          // fallback tag is still attached to a previous spool in Spoolman.
                                          linkedSpoolId: slotAssignmentForFill?.spoolman_spool_id
                                            ?? (trayTag ? linkedSpools?.[trayTag]?.id : undefined),
                                          spoolmanUrl,
                                          syncMode: spoolmanSyncMode,
                                          // Suppress Link button when slot is already occupied by ANY assignment
                                          // (Spoolman SlotAssignment OR local SpoolAssignment). Phase 9 only
                                          // suppressed for Spoolman; the maintainer screenshot shows the badge
                                          // still appearing on slots with a local Devil Design PLA assigned.
                                          onLinkSpool: (spoolmanEnabled && !slotAssignmentForFill && !inventoryAssignment) ? () => {
                                            const linkTag = (filamentData.trayUuid || filamentData.tagUid || getFallbackSpoolTag(printer.serial_number, ams.id, slotIdx)).toUpperCase();
                                            setLinkSpoolModal({
                                              tagUid: filamentData.tagUid || linkTag,
                                              trayUuid: filamentData.trayUuid || '',
                                              printerId: printer.id,
                                              amsId: ams.id,
                                              trayId: slotIdx,
                                            });
                                          } : undefined,
                                          onUnlinkSpool: linkedSpool?.id ? () => unlinkSpoolMutation.mutate(linkedSpool.id) : undefined,
                                        }}
                                        inventory={(() => {
                                          if (spoolmanEnabled) {
                                            if (spoolmanLoading) return undefined;
                                            const slotAssignment = slotAssignmentForFill;
                                            const spoolmanSpool = slotSpoolForFill;
                                            return {
                                              assignedSpool: spoolmanSpool ? {
                                                id: spoolmanSpool.id,
                                                material: spoolmanSpool.material,
                                                brand: spoolmanSpool.brand ?? null,
                                                color_name: spoolmanSpool.color_name ?? null,
                                                remainingWeightGrams: spoolmanSpool.label_weight
                                                  ? Math.max(0, Math.round(spoolmanSpool.label_weight - spoolmanSpool.weight_used))
                                                  : undefined,
                                              } : null,
                                              onAssignSpool: () => setAssignSpoolModal({
                                                printerId: printer.id,
                                                amsId: ams.id,
                                                trayId: slotIdx,
                                                trayInfo: {
                                                  type: tray?.tray_type || filamentData.profile,
                                                  material: tray?.tray_type ?? undefined,
                                                  profile: filamentData.profile,
                                                  color: filamentData.colorHex || '',
                                                  location: `${getAmsLabel(ams.id, ams.tray.length)} Slot ${slotIdx + 1}`,
                                                },
                                              }),
                                              onUnassignSpool: (spoolmanSpool && !isBambuLabSpool(tray)) ? () => onUnassignSpoolmanSpool?.(spoolmanSpool.id) : undefined,
                                              isAssigned: !!slotAssignment || isBambuLabSpool(tray),
                                            };
                                          }
                                          const assignment = onGetAssignment?.(printer.id, ams.id, slotIdx);
                                          return {
                                            assignedSpool: assignment?.spool ? {
                                              id: assignment.spool.id,
                                              material: assignment.spool.material,
                                              brand: assignment.spool.brand,
                                              color_name: assignment.spool.color_name,
                                              remainingWeightGrams: Math.max(0, Math.round(assignment.spool.label_weight - assignment.spool.weight_used)),
                                            } : null,
                                            onAssignSpool: () => setAssignSpoolModal({
                                              printerId: printer.id,
                                              amsId: ams.id,
                                              trayId: slotIdx,
                                              trayInfo: {
                                                type: tray?.tray_type || filamentData.profile,
                                                material: tray?.tray_type ?? undefined,
                                                profile: filamentData.profile,
                                                color: filamentData.colorHex || '',
                                                location: `${getAmsLabel(ams.id, ams.tray.length)} Slot ${slotIdx + 1}`,
                                              },
                                            }),
                                            onUnassignSpool: (assignment && !isBambuLabSpool(tray)) ? () => onUnassignSpool?.(printer.id, ams.id, slotIdx) : undefined,
                                            isAssigned: !!assignment || isBambuLabSpool(tray),
                                          };
                                        })()}
                                        configureSlot={{
                                          enabled: hasPermission('printers:control'),
                                          onConfigure: () => setConfigureSlotModal({
                                            amsId: ams.id,
                                            trayId: slotIdx,
                                            trayCount: ams.tray.length,
                                            trayType: tray?.tray_type || undefined,
                                            trayColor: tray?.tray_color || undefined,
                                            traySubBrands: tray?.tray_sub_brands || undefined,
                                            trayInfoIdx: tray?.tray_info_idx || undefined,
                                            extruderId: mappedExtruderId,
                                            caliIdx: tray?.cali_idx,
                                            savedPresetId: slotPreset?.preset_id,
                                          }),
                                        }}
                                      >
                                        {slotVisual}
                                      </FilamentHoverCard>
                                    ) : (
                                      <EmptySlotHoverCard
                                        kind={emptyKind ?? undefined}
                                        actions={renderAmsSlotActions({
                                          amsId: ams.id,
                                          slotId: slotIdx,
                                          loadTrayId: ams.id * 4 + slotIdx,
                                          isRefreshing,
                                        })}
                                        configureSlot={{
                                          enabled: hasPermission('printers:control'),
                                          onConfigure: () => setConfigureSlotModal({
                                            amsId: ams.id,
                                            trayId: slotIdx,
                                            trayCount: ams.tray.length,
                                            extruderId: mappedExtruderId,
                                          }),
                                        }}
                                        onAssignSpool={() => setAssignSpoolModal({
                                          printerId: printer.id,
                                          amsId: ams.id,
                                          trayId: slotIdx,
                                          trayInfo: {
                                            type: '',
                                            material: undefined,
                                            profile: '',
                                            color: '',
                                            location: `${getAmsLabel(ams.id, ams.tray.length)} Slot ${slotIdx + 1}`,
                                          },
                                        })}
                                      >
                                        {slotVisual}
                                      </EmptySlotHoverCard>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                        </div>
                      );
                    })}
                    {/* HT AMS units */}
                    {htAms.map((ams) => {
                      const mappedExtruderId = amsExtruderMap[String(ams.id)];
                      const normalizedId = ams.id >= 128 ? ams.id - 128 : ams.id;
                      const extruderId = mappedExtruderId !== undefined ? mappedExtruderId : normalizedId;
                      const isLeftNozzle = extruderId === 1;
                      const isRightNozzle = extruderId === 0;
                      const tray = ams.tray[0];
                      const hasFillLevel = tray?.tray_type && tray.remain >= 0;
                      const isEmpty = !tray?.tray_type;
                      const emptyKind = getEmptySlotKind(tray);
                      // Check if this is the currently loaded tray
                      const globalTrayId = getGlobalTrayId(ams.id, tray?.id ?? 0, false);
                      const isActive = effectiveTrayNow === globalTrayId;
                      const isExpectedSlot = expectedTray !== null && expectedTray === globalTrayId;
                      const isRanOutSlot = previousTray !== null && previousTray === globalTrayId;
                      // Get cloud preset info if available
                      const cloudInfo = tray?.tray_info_idx ? filamentInfo?.[tray.tray_info_idx] : null;
                      // Get saved slot preset mapping (for user-configured slots)
                      const slotPreset = slotPresets?.[globalTrayId];
                      const htSlotId = tray?.id ?? 0;

                        // Fill level fallback chain: Spoolman → Inventory → AMS remain
                        const htTrayTag = (tray?.tray_uuid || tray?.tag_uid || getFallbackSpoolTag(printer.serial_number, ams.id, htSlotId))?.toUpperCase();
                        const htLinkedSpool = htTrayTag ? linkedSpools?.[htTrayTag] : undefined;
                        const htSpoolmanFill = getSpoolmanFillLevel(htLinkedSpool);
                        const htInventoryAssignment = onGetAssignment?.(printer.id, ams.id, htSlotId);
                        const htInventoryFill = (() => {
                          const sp = htInventoryAssignment?.spool;
                          if (sp && sp.label_weight > 0 && sp.weight_used != null) {
                            return Math.round(Math.max(0, sp.label_weight - sp.weight_used) / sp.label_weight * 100);
                          }
                          return null;
                        })();
                        // If inventory says 0% but AMS reports positive remain, prefer AMS (#676)
                        const htResolvedInventoryFill = (htInventoryFill === 0 && hasFillLevel && tray.remain > 0)
                          ? null : htInventoryFill;
                        // Slot-assigned-only fill (when spool has no NFC tag but is slot-assigned)
                        const htSlotAssignmentForFill = spoolmanEnabled && !spoolmanLoading
                          ? spoolmanSlotAssignments?.find(a => a.printer_id === printer.id && a.ams_id === ams.id && a.tray_id === htSlotId)
                          : undefined;
                        const htSlotSpoolForFill = htSlotAssignmentForFill
                          ? spoolmanSpools?.find(s => s.id === htSlotAssignmentForFill.spoolman_spool_id)
                          : undefined;
                        const htSlotSpoolFill = (htSlotSpoolForFill && (htSlotSpoolForFill.label_weight ?? 0) > 0)
                          ? Math.round(Math.max(0, (htSlotSpoolForFill.label_weight ?? 0) - htSlotSpoolForFill.weight_used) / (htSlotSpoolForFill.label_weight ?? 1) * 100)
                          : null;
                        const htEffectiveFill = htSpoolmanFill ?? htSlotSpoolFill ?? htResolvedInventoryFill ?? (hasFillLevel ? tray.remain : null);
                        const htFillSource = (htSpoolmanFill !== null || htSlotSpoolFill !== null) ? 'spoolman' as const
                          : htResolvedInventoryFill !== null ? 'inventory' as const
                          : hasFillLevel ? 'ams' as const
                          : undefined;

                        // Build filament data for hover card
                        const filamentData = tray?.tray_type ? {
                          vendor: (isBambuLabSpool(tray) ? 'Bambu Lab' : 'Generic') as 'Bambu Lab' | 'Generic',
                          profile: slotPreset?.preset_name || (htSlotSpoolForFill ? [htSlotSpoolForFill.brand, htSlotSpoolForFill.slicer_filament_name?.split('@')[0].trim() || htSlotSpoolForFill.material].filter(Boolean).join(' ').trim() : null) || htInventoryAssignment?.spool?.slicer_filament_name || cloudInfo?.name || tray.tray_sub_brands || tray.tray_type,
                          colorName: getColorName(tray.tray_color || ''),
                          colorHex: tray.tray_color || null,
                          kFactor: formatKValue(tray.k),
                          fillLevel: htEffectiveFill,
                          trayUuid: tray.tray_uuid || null,
                          tagUid: tray.tag_uid || null,
                          fillSource: htFillSource,
                        } : null;

                        // Check if this specific slot is being refreshed
                        const isHtRefreshing = refreshingSlot?.amsId === ams.id &&
                          refreshingSlot?.slotId === htSlotId;

                        // #1762 (comment 2): active print-slot index for this HT slot.
                        const htActivePrintSlotIdx = activeMapping.indexOf(globalTrayId);
                        const htActivePrintSlotLabel = htActivePrintSlotIdx >= 0
                          ? `P${htActivePrintSlotIdx + 1}`
                          : null;
                        // Slot visual content (goes inside hover card)
                        const slotVisual = (
                          <div
                            className={`relative w-full bg-bambu-dark-secondary rounded-lg p-1 text-center ${isEmpty ? 'opacity-50' : ''} ${
                              isExpectedSlot
                                ? 'ring-2 ring-amber-400 ring-offset-1 ring-offset-bambu-dark animate-pulse'
                                : isRanOutSlot
                                  ? 'ring-2 ring-red-500/60 ring-offset-1 ring-offset-bambu-dark'
                                  : isActive
                                    ? 'ring-2 ring-bambu-green ring-offset-1 ring-offset-bambu-dark'
                                    : ''
                            }`}
                          >
                            {isExpectedSlot && (
                              <span
                                aria-label={t('printers.expectedSlot.ariaLabel', { n: 1 })}
                                title={t('printers.expectedSlot.title')}
                                className="absolute top-0.5 left-0.5 px-1 py-px text-[8px] font-bold text-bambu-dark bg-amber-400 rounded pointer-events-none leading-none"
                              >
                                !
                              </span>
                            )}
                            {htActivePrintSlotLabel && (
                              <span
                                aria-label={t('printers.activeJobSlot.ariaLabel', { n: htActivePrintSlotIdx + 1 })}
                                title={t('printers.activeJobSlot.title', { n: htActivePrintSlotIdx + 1 })}
                                className="absolute top-0.5 right-0.5 px-1 py-px text-[8px] font-bold text-bambu-dark bg-bambu-green rounded pointer-events-none leading-none"
                              >
                                {htActivePrintSlotLabel}
                              </span>
                            )}
                            {/* Filament color circle with 1-based slot number centered inside */}
                            <FilamentSlotCircle
                              trayColor={tray?.tray_color}
                              trayType={tray?.tray_type}
                              isEmpty={isEmpty}
                              emptyKind={emptyKind}
                              slotNumber={1}
                            />
                            <div className="text-[9px] text-white font-bold truncate">
                              {tray?.tray_type || t(emptyKind === 'reset' ? 'ams.slotUnconfigured' : 'ams.slotEmpty')}
                            </div>
                            {/* Fill bar */}
                            <div className="mt-1 h-1.5 bg-black/30 rounded-full overflow-hidden">
                              {htEffectiveFill !== null && htEffectiveFill >= 0 && !isEmpty && (
                                <div
                                  className="h-full rounded-full transition-all"
                                  style={{
                                    width: `${htEffectiveFill}%`,
                                    backgroundColor: getFillBarColor(htEffectiveFill),
                                  }}
                                />
                              )}
                            </div>
                          </div>
                        );

                        // HT cards lay out slot + stats side-by-side in Row 2 (not stats-in-header
                        // like regular AMS), so they need more horizontal room than a 1-slot basis.
                        // Without this override, the L view squishes HT into a sliver next to the
                        // 4-slot AMS neighbors.
                        const htCardStyle: React.CSSProperties = { flex: '1 1 11rem', minWidth: '11rem' };
                        return (
                          <div key={ams.id} style={htCardStyle} className="min-w-0 p-2 bg-bambu-dark rounded-[10px] space-y-1">
                            {/* Row 1: Label + Nozzle + Drying */}
                            <div className="flex w-full min-h-7 items-center gap-1.5 rounded-lg bg-bambu-dark-secondary px-2 py-1">
                              {/* AMS name — hover to see serial, firmware, and edit friendly name */}
                              <div className="flex min-w-0 flex-1 items-center gap-1.5">
                                <AmsNameHoverCard
                                  ams={ams}
                                  printerId={printer.id}
                                  label={getAmsLabel(ams.id, ams.tray.length)}
                                  amsLabels={amsLabels}
                                  canEdit={hasPermission('printers:update')}
                                  onSaved={refetchAmsLabels}
                                >
                                  <span className="block truncate text-[10px] text-white font-medium cursor-default select-none">
                                    {amsLabels?.[ams.id] || getAmsLabel(ams.id, ams.tray.length)}
                                  </span>
                                </AmsNameHoverCard>
                                {isDualNozzle && (isLeftNozzle || isRightNozzle) && (
                                  <NozzleBadge side={isLeftNozzle ? 'L' : 'R'} />
                                )}
                              </div>
                              {/* Drying button for HT AMS */}
                              {(status.supports_drying || status.drying_screen_only) && (ams.module_type === 'n3f' || ams.module_type === 'n3s') && hasPrinterControlPermission && (
                                <div className="relative ml-auto">
                                  <button
                                    disabled={localPrinterControlUnavailable || status.drying_screen_only}
                                    onClick={(e) => {
                                      if (!canUsePrinterControl) return;
                                      if (ams.dry_time > 0) {
                                        stopDryingMutation.mutate(ams.id);
                                      } else if (dryingPopoverAmsId === ams.id) {
                                        setDryingPopoverAmsId(null);
                                      } else {
                                        const firstTray = ams.tray.find(t => t.tray_type);
                                        const filType = (firstTray?.tray_type || 'PLA').split(' ')[0].toUpperCase();
                                        const preset = dryingPresets[filType] || dryingPresets['PLA'];
                                        const moduleType = ams.module_type as 'n3f' | 'n3s';
                                        setDryingFilament(filType);
                                        setDryingTemp(preset[moduleType] || preset.n3f);
                                        setDryingDuration(moduleType === 'n3s' ? preset.n3s_hours : preset.n3f_hours);
                                        setDryingRotateTray(false);
                                        setDryingPopoverModuleType(ams.module_type);
                                        setDryingPopoverAmsId(ams.id);
                                        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                                        setDryingPopoverPos(computePopoverPosition({ triggerRect: rect, popoverWidth: DRYING_POPOVER_WIDTH, estimatedHeight: DRYING_POPOVER_ESTIMATED_HEIGHT, horizontalAlign: 'center' }));
                                      }
                                    }}
                                    className={`flex items-center gap-0.5 px-1 py-0.5 rounded text-[9px] transition-colors ${
                                      ams.dry_time > 0
                                        ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400'
                                        : localPrinterControlUnavailable || status.drying_screen_only
                                          ? 'bg-bambu-dark text-bambu-gray/50 cursor-not-allowed'
                                          : 'bg-bambu-dark text-bambu-gray hover:text-white hover:bg-bambu-dark/80'
                                    }`}
                                    title={localPrinterControlUnavailable ? getLocalPrinterControlUnavailableTitle('drying') : status.drying_screen_only ? t('printers.drying.screenOnly') : ams.dry_time > 0 ? t('printers.drying.stop') : t('printers.drying.start')}
                                  >
                                    <Flame className="w-3 h-3" />
                                  </button>
                                </div>
                              )}
                            </div>
                            {/* HT AMS drying status bar */}
                            {ams.dry_time > 0 && (
                              <div className="flex items-center gap-1.5 overflow-hidden whitespace-nowrap rounded-lg bg-amber-50 dark:bg-amber-500/10 px-2 py-1 text-[9px]">
                                <Flame className="w-3 h-3 text-amber-600 dark:text-amber-400 shrink-0" />
                                {ams.dry_filament && ams.dry_target_temp != null && (
                                  <span className="text-amber-700/80 dark:text-amber-300/70 text-[8px] truncate">
                                    {t('printers.drying.targetSummary', { filament: ams.dry_filament, temp: ams.dry_target_temp })}
                                  </span>
                                )}
                                <span className="text-amber-700/80 dark:text-amber-300/70 text-[8px] truncate">
                                  {ams.dry_time >= 60
                                    ? `${Math.floor(ams.dry_time / 60)}h ${ams.dry_time % 60}m`
                                    : `${ams.dry_time}m`}
                                </span>
                                {!status.drying_screen_only && (
                                  <button
                                    onClick={() => stopDryingMutation.mutate(ams.id)}
                                    disabled={stopDryingMutation.isPending}
                                    className="ml-auto text-amber-700 dark:text-amber-400 hover:text-amber-900 dark:hover:text-amber-300 transition-colors disabled:opacity-50 shrink-0"
                                    title={t('printers.drying.stop')}
                                  >
                                    <X className="w-3 h-3" />
                                  </button>
                                )}
                              </div>
                            )}
                            {/* Row 2: Slot (left) + Stats (right stacked) */}
                            <div className="flex gap-1.5 max-[550px]:flex-col max-[550px]:items-start">
                              {/* Slot wrapper with loading overlay */}
                              <div className="relative group min-w-14 flex-1">
                                {/* Loading overlay during RFID re-read */}
                                {isHtRefreshing && (
                                  <div className="absolute inset-0 bg-bambu-dark-tertiary/80 rounded flex items-center justify-center z-20">
                                    <RefreshCw className="w-4 h-4 text-bambu-green animate-spin" />
                                  </div>
                                )}
                                {/* Hover card wraps only the visual content */}
                                {filamentData ? (
                                  <FilamentHoverCard
                                    data={filamentData}
                                    actions={renderAmsSlotActions({
                                      amsId: ams.id,
                                      slotId: htSlotId,
                                      loadTrayId: ams.id * 4 + htSlotId,
                                      isRefreshing: isHtRefreshing,
                                    })}
                                    spoolman={{
                                      enabled: spoolmanEnabled,
                                      // #1457: slot assignment outranks tag-link (see top-level slot block).
                                      linkedSpoolId: htSlotAssignmentForFill?.spoolman_spool_id
                                        ?? (htTrayTag ? linkedSpools?.[htTrayTag]?.id : undefined),
                                      spoolmanUrl,
                                      syncMode: spoolmanSyncMode,
                                      // Suppress Link button when slot is occupied by ANY assignment (Phase 13 P13-6d)
                                      onLinkSpool: (spoolmanEnabled && !htSlotAssignmentForFill && !htInventoryAssignment) ? () => {
                                        const linkTag = (filamentData.trayUuid || filamentData.tagUid || getFallbackSpoolTag(printer.serial_number, ams.id, htSlotId)).toUpperCase();
                                        setLinkSpoolModal({
                                          tagUid: filamentData.tagUid || linkTag,
                                          trayUuid: filamentData.trayUuid || '',
                                          printerId: printer.id,
                                          amsId: ams.id,
                                          trayId: htSlotId,
                                        });
                                      } : undefined,
                                      onUnlinkSpool: htLinkedSpool?.id ? () => unlinkSpoolMutation.mutate(htLinkedSpool.id) : undefined,
                                    }}
                                    inventory={(() => {
                                      if (spoolmanEnabled) {
                                        if (spoolmanLoading) return undefined;
                                        const slotAssignment = htSlotAssignmentForFill;
                                        const spoolmanSpool = htSlotSpoolForFill;
                                        return {
                                          assignedSpool: spoolmanSpool ? {
                                            id: spoolmanSpool.id,
                                            material: spoolmanSpool.material,
                                            brand: spoolmanSpool.brand ?? null,
                                            color_name: spoolmanSpool.color_name ?? null,
                                            remainingWeightGrams: spoolmanSpool.label_weight
                                              ? Math.max(0, Math.round(spoolmanSpool.label_weight - spoolmanSpool.weight_used))
                                              : undefined,
                                          } : null,
                                          onAssignSpool: () => setAssignSpoolModal({
                                            printerId: printer.id,
                                            amsId: ams.id,
                                            trayId: htSlotId,
                                            trayInfo: {
                                              type: tray?.tray_type || filamentData.profile,
                                              material: tray?.tray_type ?? undefined,
                                              profile: filamentData.profile,
                                              color: filamentData.colorHex || '',
                                              location: getAmsLabel(ams.id, ams.tray.length),
                                            },
                                          }),
                                          onUnassignSpool: (spoolmanSpool && !isBambuLabSpool(tray)) ? () => onUnassignSpoolmanSpool?.(spoolmanSpool.id) : undefined,
                                          isAssigned: !!slotAssignment || isBambuLabSpool(tray),
                                        };
                                      }
                                      const assignment = onGetAssignment?.(printer.id, ams.id, htSlotId);
                                      return {
                                        assignedSpool: assignment?.spool ? {
                                          id: assignment.spool.id,
                                          material: assignment.spool.material,
                                          brand: assignment.spool.brand,
                                          color_name: assignment.spool.color_name,
                                          remainingWeightGrams: Math.max(0, Math.round(assignment.spool.label_weight - assignment.spool.weight_used)),
                                        } : null,
                                        onAssignSpool: () => setAssignSpoolModal({
                                          printerId: printer.id,
                                          amsId: ams.id,
                                          trayId: htSlotId,
                                          trayInfo: {
                                            type: tray?.tray_type || filamentData.profile,
                                            material: tray?.tray_type ?? undefined,
                                            profile: filamentData.profile,
                                            color: filamentData.colorHex || '',
                                            location: getAmsLabel(ams.id, ams.tray.length),
                                          },
                                        }),
                                        onUnassignSpool: (assignment && !isBambuLabSpool(tray)) ? () => onUnassignSpool?.(printer.id, ams.id, htSlotId) : undefined,
                                        isAssigned: !!assignment || isBambuLabSpool(tray),
                                      };
                                    })()}
                                    configureSlot={{
                                      enabled: hasPermission('printers:control'),
                                      onConfigure: () => setConfigureSlotModal({
                                        amsId: ams.id,
                                        trayId: htSlotId,
                                        trayCount: ams.tray.length,
                                        trayType: tray?.tray_type || undefined,
                                        trayColor: tray?.tray_color || undefined,
                                        traySubBrands: tray?.tray_sub_brands || undefined,
                                        trayInfoIdx: tray?.tray_info_idx || undefined,
                                        extruderId: mappedExtruderId,
                                        caliIdx: tray?.cali_idx,
                                        savedPresetId: slotPreset?.preset_id,
                                      }),
                                    }}
                                  >
                                    {slotVisual}
                                  </FilamentHoverCard>
                                ) : (
                                  <EmptySlotHoverCard
                                    kind={emptyKind ?? undefined}
                                    actions={renderAmsSlotActions({
                                      amsId: ams.id,
                                      slotId: htSlotId,
                                      loadTrayId: ams.id * 4 + htSlotId,
                                      isRefreshing: isHtRefreshing,
                                    })}
                                    configureSlot={{
                                      enabled: hasPermission('printers:control'),
                                      onConfigure: () => setConfigureSlotModal({
                                        amsId: ams.id,
                                        trayId: htSlotId,
                                        trayCount: ams.tray.length,
                                        extruderId: mappedExtruderId,
                                      }),
                                    }}
                                    onAssignSpool={() => setAssignSpoolModal({
                                      printerId: printer.id,
                                      amsId: ams.id,
                                      trayId: htSlotId,
                                      trayInfo: {
                                        type: '',
                                        material: undefined,
                                        profile: '',
                                        color: '',
                                        location: getAmsLabel(ams.id, ams.tray.length),
                                      },
                                    })}
                                  >
                                    {slotVisual}
                                  </EmptySlotHoverCard>
                                )}
                              </div>
                              {/* Stats stacked vertically: Temp on top, Humidity below */}
                              {(ams.humidity != null || ams.temp != null) && (
                                <div className="flex flex-col justify-center gap-1 shrink-0 max-[550px]:w-full">
                                  {ams.temp != null && (
                                    <TemperatureIndicator
                                      temp={ams.temp}
                                      goodThreshold={amsThresholds?.tempGood}
                                      fairThreshold={amsThresholds?.tempFair}
                                      onClick={() => setAmsHistoryModal({
                                        amsId: ams.id,
                                        amsLabel: getAmsLabel(ams.id, ams.tray.length),
                                        mode: 'temperature',
                                      })}
                                      compact
                                    />
                                  )}
                                  {ams.humidity != null && (
                                    <HumidityIndicator
                                      humidity={ams.humidity}
                                      goodThreshold={amsThresholds?.humidityGood}
                                      fairThreshold={amsThresholds?.humidityFair}
                                      onClick={() => setAmsHistoryModal({
                                        amsId: ams.id,
                                        amsLabel: getAmsLabel(ams.id, ams.tray.length),
                                        mode: 'humidity',
                                      })}
                                      compact
                                    />
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                      {/* External spool(s) - grouped in one card like regular AMS */}
                      {status.vt_tray.length > 0 && (
                        <div style={getAmsCardStyle(status.vt_tray.length)} className="min-w-0 p-2 bg-bambu-dark rounded-[10px] space-y-1">
                          <div className="flex w-full min-h-7 items-center gap-1.5 rounded-lg bg-bambu-dark-secondary px-2 py-1">
                            <span className="block min-w-0 flex-1 truncate text-[10px] text-white font-medium">{t('printers.external')}</span>
                          </div>
                          <div className={`grid w-full ${status.vt_tray.length > 1 ? 'grid-cols-[repeat(2,minmax(3.5rem,1fr))]' : 'grid-cols-[minmax(3.5rem,1fr)]'} gap-1`}>
                            {[...status.vt_tray].sort((a, b) => (a.id ?? 254) - (b.id ?? 254)).map((extTray) => {
                              const extTrayId = extTray.id ?? 254;
                              // On dual-nozzle (H2C/H2D), tray_now=254 means "external spool"
                              // generically — use active_extruder to determine L vs R:
                              // extruder 1=left → Ext-L (id=254), extruder 0=right → Ext-R (id=255)
                              const isExtActive = isDualNozzle && effectiveTrayNow === 254
                                ? (extTrayId === 254 && status.active_extruder === 1) ||
                                  (extTrayId === 255 && status.active_extruder === 0)
                                : effectiveTrayNow === extTrayId;
                              const slotTrayId = extTrayId - 254; // 0 or 1
                              const extLabel = isDualNozzle
                                ? (extTrayId === 254 ? t('printers.extL') : t('printers.extR'))
                                : '';
                              const extCloudInfo = extTray.tray_info_idx ? filamentInfo?.[extTray.tray_info_idx] : null;
                              const extSlotPreset = slotPresets?.[255 * 4 + slotTrayId];

                              const extTrayTag = (extTray.tray_uuid || extTray.tag_uid || getFallbackSpoolTag(printer.serial_number, 255, slotTrayId))?.toUpperCase();
                              const extLinkedSpool = extTrayTag ? linkedSpools?.[extTrayTag] : undefined;
                              const extSpoolmanFill = getSpoolmanFillLevel(extLinkedSpool);
                              const extInventoryAssignment = onGetAssignment?.(printer.id, 255, slotTrayId);
                              const extInventoryFill = (() => {
                                const sp = extInventoryAssignment?.spool;
                                if (sp && sp.label_weight > 0 && sp.weight_used != null) {
                                  return Math.round(Math.max(0, sp.label_weight - sp.weight_used) / sp.label_weight * 100);
                                }
                                return null;
                              })();
                              const extHasFillLevel = extTray.tray_type && extTray.remain >= 0;
                              // If inventory says 0% but AMS reports positive remain, prefer AMS (#676)
                              const extResolvedInventoryFill = (extInventoryFill === 0 && extHasFillLevel && extTray.remain > 0)
                                ? null : extInventoryFill;
                              // Slot-assigned-only fill (when spool has no NFC tag but is slot-assigned)
                              const extSlotAssignmentForFill = spoolmanEnabled && !spoolmanLoading
                                ? spoolmanSlotAssignments?.find(a => a.printer_id === printer.id && a.ams_id === 255 && a.tray_id === slotTrayId)
                                : undefined;
                              const extSlotSpoolForFill = extSlotAssignmentForFill
                                ? spoolmanSpools?.find(s => s.id === extSlotAssignmentForFill.spoolman_spool_id)
                                : undefined;
                              const extSlotSpoolFill = (extSlotSpoolForFill && (extSlotSpoolForFill.label_weight ?? 0) > 0)
                                ? Math.round(Math.max(0, (extSlotSpoolForFill.label_weight ?? 0) - extSlotSpoolForFill.weight_used) / (extSlotSpoolForFill.label_weight ?? 1) * 100)
                                : null;
                              const extEffectiveFill = extSpoolmanFill ?? extSlotSpoolFill ?? extResolvedInventoryFill ?? (extHasFillLevel ? extTray.remain : null);
                              const extFillSource = (extSpoolmanFill !== null || extSlotSpoolFill !== null) ? 'spoolman' as const
                                : extResolvedInventoryFill !== null ? 'inventory' as const
                                : extHasFillLevel ? 'ams' as const
                                : undefined;

                              const extFilamentData = {
                                vendor: (isBambuLabSpool(extTray) ? 'Bambu Lab' : 'Generic') as 'Bambu Lab' | 'Generic',
                                profile: extSlotPreset?.preset_name || (extSlotSpoolForFill ? [extSlotSpoolForFill.brand, extSlotSpoolForFill.slicer_filament_name?.split('@')[0].trim() || extSlotSpoolForFill.material].filter(Boolean).join(' ').trim() : null) || extInventoryAssignment?.spool?.slicer_filament_name || extCloudInfo?.name || extTray.tray_sub_brands || extTray.tray_type || 'Unknown',
                                colorName: getColorName(extTray.tray_color || ''),
                                colorHex: extTray.tray_color || null,
                                kFactor: formatKValue(extTray.k),
                                fillLevel: extEffectiveFill,
                                trayUuid: extTray.tray_uuid || null,
                                tagUid: extTray.tag_uid || null,
                                fillSource: extFillSource,
                              };

                              const isEmpty = !extTray.tray_type;
                              const emptyKind = getEmptySlotKind(extTray);
                              const extSlotContent = (
                                <div className={`w-full bg-bambu-dark-secondary rounded-lg p-1 text-center ${isEmpty ? 'opacity-50' : ''} ${isExtActive ? 'ring-2 ring-bambu-green ring-offset-1 ring-offset-bambu-dark' : ''}`}>
                                  {/* Color circle: L/R inside on dual-nozzle external (replaces
                                      the separate Ext-L/Ext-R caption that made the row taller than
                                      regular AMS slots), 1-based slot number on single-nozzle. */}
                                  <FilamentSlotCircle
                                    trayColor={extTray.tray_color}
                                    trayType={extTray.tray_type}
                                    isEmpty={isEmpty}
                                    emptyKind={emptyKind}
                                    slotNumber={isDualNozzle ? (extTrayId === 254 ? 'L' : 'R') : slotTrayId + 1}
                                  />
                                  <div className={`text-[9px] font-bold truncate ${isEmpty ? 'text-white/40' : 'text-white'}`}>
                                    {extTray.tray_type || t('ams.slotEmpty')}
                                  </div>
                                  <div className="mt-1 h-1.5 bg-black/30 rounded-full overflow-hidden">
                                    {extEffectiveFill !== null && extEffectiveFill >= 0 && !isEmpty && (
                                      <div
                                        className="h-full rounded-full transition-all"
                                        style={{
                                          width: `${extEffectiveFill}%`,
                                          backgroundColor: getFillBarColor(extEffectiveFill),
                                        }}
                                      />
                                    )}
                                  </div>
                                </div>
                              );

                              return (
                                <div key={extTrayId} className={`relative group w-full ${filamentSlotClass}`}>
                                  {!isEmpty ? (
                                    <FilamentHoverCard
                                      data={extFilamentData}
                                      actions={renderAmsSlotActions({
                                        amsId: 255,
                                        slotId: slotTrayId,
                                        loadTrayId: extTrayId,
                                        includeRfid: false,
                                      })}
                                      spoolman={{
                                        enabled: spoolmanEnabled,
                                        // #1457: slot assignment outranks tag-link (see top-level slot block).
                                        linkedSpoolId: extSlotAssignmentForFill?.spoolman_spool_id
                                          ?? (extTrayTag ? linkedSpools?.[extTrayTag]?.id : undefined),
                                        spoolmanUrl,
                                        syncMode: spoolmanSyncMode,
                                        // Suppress Link button when slot is occupied by ANY assignment (Phase 13 P13-6d)
                                        onLinkSpool: (spoolmanEnabled && !extSlotAssignmentForFill && !extInventoryAssignment) ? () => {
                                          const linkTag = (extFilamentData.trayUuid || extFilamentData.tagUid || getFallbackSpoolTag(printer.serial_number, 255, slotTrayId)).toUpperCase();
                                          setLinkSpoolModal({
                                            tagUid: extFilamentData.tagUid || linkTag,
                                            trayUuid: extFilamentData.trayUuid || '',
                                            printerId: printer.id,
                                            amsId: 255,
                                            trayId: slotTrayId,
                                          });
                                        } : undefined,
                                        onUnlinkSpool: extLinkedSpool?.id ? () => unlinkSpoolMutation.mutate(extLinkedSpool.id) : undefined,
                                      }}
                                      inventory={(() => {
                                        if (spoolmanEnabled) {
                                          if (spoolmanLoading) return undefined;
                                          const slotAssignment = extSlotAssignmentForFill;
                                          const spoolmanSpool = extSlotSpoolForFill;
                                          return {
                                            assignedSpool: spoolmanSpool ? {
                                              id: spoolmanSpool.id,
                                              material: spoolmanSpool.material,
                                              brand: spoolmanSpool.brand ?? null,
                                              color_name: spoolmanSpool.color_name ?? null,
                                              remainingWeightGrams: spoolmanSpool.label_weight
                                                ? Math.max(0, Math.round(spoolmanSpool.label_weight - spoolmanSpool.weight_used))
                                                : undefined,
                                            } : null,
                                            onAssignSpool: () => setAssignSpoolModal({
                                              printerId: printer.id,
                                              amsId: 255,
                                              trayId: slotTrayId,
                                              trayInfo: {
                                                type: extTray.tray_type || extFilamentData.profile,
                                                material: extTray.tray_type ?? undefined,
                                                profile: extFilamentData.profile,
                                                color: extFilamentData.colorHex || '',
                                                location: extLabel || t('printers.external'),
                                              },
                                            }),
                                            onUnassignSpool: (spoolmanSpool && !isBambuLabSpool(extTray)) ? () => onUnassignSpoolmanSpool?.(spoolmanSpool.id) : undefined,
                                            isAssigned: !!slotAssignment || isBambuLabSpool(extTray),
                                          };
                                        }
                                        const assignment = onGetAssignment?.(printer.id, 255, slotTrayId);
                                        return {
                                          assignedSpool: assignment?.spool ? {
                                            id: assignment.spool.id,
                                            material: assignment.spool.material,
                                            brand: assignment.spool.brand,
                                            color_name: assignment.spool.color_name,
                                            remainingWeightGrams: Math.max(0, Math.round(assignment.spool.label_weight - assignment.spool.weight_used)),
                                          } : null,
                                          onAssignSpool: () => setAssignSpoolModal({
                                            printerId: printer.id,
                                            amsId: 255,
                                            trayId: slotTrayId,
                                            trayInfo: {
                                              type: extTray.tray_type || extFilamentData.profile,
                                              material: extTray.tray_type ?? undefined,
                                              profile: extFilamentData.profile,
                                              color: extFilamentData.colorHex || '',
                                              location: extLabel || t('printers.external'),
                                            },
                                          }),
                                          onUnassignSpool: (assignment && !isBambuLabSpool(extTray)) ? () => onUnassignSpool?.(printer.id, 255, slotTrayId) : undefined,
                                          isAssigned: !!assignment || isBambuLabSpool(extTray),
                                        };
                                      })()}
                                      configureSlot={{
                                        enabled: hasPermission('printers:control'),
                                        onConfigure: () => setConfigureSlotModal({
                                          amsId: 255,
                                          trayId: slotTrayId,
                                          trayCount: 1,
                                          trayType: extTray.tray_type || undefined,
                                          trayColor: extTray.tray_color || undefined,
                                          traySubBrands: extTray.tray_sub_brands || undefined,
                                          trayInfoIdx: extTray.tray_info_idx || undefined,
                                          extruderId: isDualNozzle ? (extTrayId === 254 ? 1 : 0) : undefined,
                                          caliIdx: extTray.cali_idx,
                                          savedPresetId: extSlotPreset?.preset_id,
                                        }),
                                      }}
                                    >
                                      {extSlotContent}
                                    </FilamentHoverCard>
                                  ) : (
                                    <EmptySlotHoverCard
                                      kind={emptyKind ?? undefined}
                                      actions={renderAmsSlotActions({
                                        amsId: 255,
                                        slotId: slotTrayId,
                                        loadTrayId: extTrayId,
                                        includeRfid: false,
                                      })}
                                      configureSlot={{
                                        enabled: hasPermission('printers:control'),
                                        onConfigure: () => setConfigureSlotModal({
                                          amsId: 255,
                                          trayId: slotTrayId,
                                          trayCount: 1,
                                          extruderId: isDualNozzle ? (extTrayId === 254 ? 1 : 0) : undefined,
                                        }),
                                      }}
                                      onAssignSpool={() => setAssignSpoolModal({
                                        printerId: printer.id,
                                        amsId: 255,
                                        trayId: slotTrayId,
                                        trayInfo: {
                                          type: '',
                                          material: undefined,
                                          profile: '',
                                          color: '',
                                          location: `External Slot ${slotTrayId + 1}`,
                                        },
                                      })}
                                    >
                                      {extSlotContent}
                                    </EmptySlotHoverCard>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                  </div>
                </div>
              );
            })()}
          </>
        )}

        {/* Bottom block (power row + action bar). Wrapped together so the
            power row hugs the action bar at the card bottom instead of
            floating up when there's less filament content above. */}
        {viewMode === 'expanded' && (
          <div className="mt-auto">
        {smartPlug && (
          <div className="pt-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] uppercase tracking-wider text-bambu-gray font-medium">
                {t('printers.power', 'Power')}
              </span>
              <div className="flex-1 h-[2px] bg-bambu-dark-tertiary" />
            </div>
            <div className="flex items-center gap-2 rounded-[10px] bg-bambu-dark p-2">
              {/* Plug name + current power */}
              <div className="flex items-center gap-2 min-w-0 pl-1">
                <Zap className="w-4 h-4 text-bambu-gray flex-shrink-0" />
                <span className="text-sm text-white truncate">{smartPlug.name}</span>
                <span
                  className="px-1.5 py-0.5 rounded-full bg-bambu-dark-tertiary text-bambu-gray text-[10px] font-medium flex-shrink-0"
                  title={t('smartPlugs.power')}
                >
                  {plugStatus?.energy?.power !== null && plugStatus?.energy?.power !== undefined ? `${Math.round(plugStatus.energy.power)}W` : '--'}
                </span>
              </div>

              {/* Spacer */}
              <div className="flex-1" />

              <div className="flex items-center gap-2">
                {/* Auto-off */}
                <button
                  onClick={() => toggleAutoOffMutation.mutate(!smartPlug.auto_off)}
                  disabled={toggleAutoOffMutation.isPending || smartPlug.auto_off_executed || !hasPermission('smart_plugs:control')}
                  title={!hasPermission('smart_plugs:control') ? t('printers.permission.noSmartPlugControl') : (smartPlug.auto_off_executed ? t('printers.autoOffExecuted') : t('printers.autoOffAfterPrint'))}
                  className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-xs font-bold transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                    !hasPermission('smart_plugs:control')
                      ? 'bg-bambu-dark-tertiary/50 text-bambu-gray/50'
                      : smartPlug.auto_off || smartPlug.auto_off_executed
                        ? 'bg-bambu-green/20 text-bambu-green hover:bg-bambu-green/30'
                        : 'bg-bambu-dark-tertiary text-bambu-gray hover:text-white hover:bg-bambu-dark-tertiary/80'
                  }`}
                >
                  <Clock className="w-4 h-4" />
                </button>
                <button
                  onClick={() => {
                    if (plugStatus?.state === 'ON') {
                      setShowPowerOffConfirm(true);
                    } else {
                      setShowPowerOnConfirm(true);
                    }
                  }}
                  disabled={powerControlMutation.isPending || !hasPermission('smart_plugs:control')}
                  className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                    !hasPermission('smart_plugs:control')
                      ? 'bg-bambu-dark-tertiary/50 text-bambu-gray/50'
                      : plugStatus?.state === 'ON'
                        ? 'bg-bambu-green/20 text-bambu-green hover:bg-bambu-green/30'
                        : 'bg-bambu-dark-tertiary text-bambu-gray hover:text-white hover:bg-bambu-dark-tertiary/80'
                  }`}
                  title={!hasPermission('smart_plugs:control') ? t('printers.permission.noSmartPlugControl') : (plugStatus?.state === 'ON' ? 'Turn off' : 'Turn on')}
                >
                  <Zap className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* HA entity buttons row */}
            {scriptPlugs && scriptPlugs.length > 0 && (
              <div className="flex items-center gap-2 mt-2">
                <Home className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                <span className="text-xs text-bambu-gray">HA:</span>
                <div className="h-[2px] w-5 bg-bambu-dark-tertiary/50" />
                <div className="flex flex-wrap gap-1">
                  {scriptPlugs.map(script => {
                    const isScript = script.ha_entity_id?.startsWith('script.');
                    return (
                      <button
                        key={script.id}
                        onClick={() => {
                          if (isScript) {
                            runScriptMutation.mutate({ id: script.id, action: 'on' });
                          } else {
                            setHaToggleConfirm(script);
                          }
                        }}
                        disabled={runScriptMutation.isPending}
                        title={`${isScript ? 'Run' : 'Toggle'} ${script.ha_entity_id}`}
                        className="px-2 py-0.5 text-xs bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-400 hover:bg-blue-500/30 rounded transition-colors flex items-center gap-1"
                      >
                        <Play className="w-2.5 h-2.5" />
                        {script.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Connection Info & Actions */}
        <div className="pt-4">
            <div className="mb-3 h-[2px] bg-bambu-dark-tertiary" />
            <div className="flex items-center justify-between gap-2">
              {printerActionsMenu}
              <div className="flex items-center justify-end gap-2 flex-wrap">
                {/* Camera Button */}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    if (cameraViewMode === 'embedded' && onOpenEmbeddedCamera) {
                      onOpenEmbeddedCamera(printer.id, printer.name);
                    } else {
                      // Use saved window state or defaults
                      const saved = localStorage.getItem('cameraWindowState');
                      const state = saved ? JSON.parse(saved) : { width: 640, height: 400 };
                      const features = [
                        `width=${state.width}`,
                        `height=${state.height}`,
                        state.left !== undefined ? `left=${state.left}` : '',
                        state.top !== undefined ? `top=${state.top}` : '',
                        // No `noopener`: same-origin popup needs opener so the browser
                        // copies sessionStorage (auth token) into the new window.
                        'menubar=no,toolbar=no,location=no,status=no',
                      ].filter(Boolean).join(',');
                      window.open(`/camera/${printer.id}`, `camera-${printer.id}`, features);
                    }
                  }}
                  disabled={!status?.connected || !hasPermission('camera:view')}
                  title={!hasPermission('camera:view') ? t('printers.permission.noCamera') : (cameraViewMode === 'embedded' ? t('printers.openCameraOverlay') : t('printers.openCameraWindow'))}
                  className={footerIconButtonClass}
                >
                  <Video className="w-4 h-4" />
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowFileManager(true)}
                  disabled={!isConnected || !hasPermission('printers:files')}
                  title={!hasPermission('printers:files') ? t('printers.permission.noFiles') : t('printers.browseFiles')}
                  className={footerIconButtonClass}
                >
                  <HardDrive className="w-4 h-4" />
                </Button>
                {isConnected && status?.state !== 'RUNNING' && status?.state !== 'PAUSE' && (
                  <Button
                    size="sm"
                    onClick={() => setShowUploadForPrint(true)}
                    disabled={!hasPermission('library:upload') || !hasPermission('queue:create')}
                    title={
                      !hasPermission('library:upload')
                        ? t('fileManager.noPermissionUpload')
                        : !hasPermission('queue:create')
                          ? t('fileManager.noPermissionAddToQueue')
                          : t('common.print')
                    }
                    className={`${footerActionButtonClass} !bg-bambu-green hover:!bg-bambu-green/80 !text-white`}
                  >
                    <PrinterIcon className="w-4 h-4" />
                    {t('common.print')}
                  </Button>
                )}
              </div>
            </div>
        </div>
          </div>
        )}
      </CardContent>

      {/* File Manager Modal */}
      {showFileManager && (
        <FileManagerModal
          printerId={printer.id}
          printerName={printer.name}
          onClose={() => setShowFileManager(false)}
        />
      )}

      {/* Upload for Print Modal */}
      {showUploadForPrint && (
        <FileUploadModal
          folderId={null}
          onClose={() => setShowUploadForPrint(false)}
          onUploadComplete={() => {}}
          autoUpload
          accept=".gcode,.3mf"
          validateFile={(file) => {
            const lower = file.name.toLowerCase();
            if (!lower.endsWith('.gcode') && !lower.includes('.gcode.')) {
              return t('printers.dropNotPrintable', 'Only .gcode and .gcode.3mf files can be printed');
            }
          }}
          onFileUploaded={(uploadedFile) => {
            // Check printer compatibility if sliced_for_model is available in metadata
            const slicedFor = (uploadedFile.metadata as Record<string, unknown>)?.sliced_for_model as string | undefined;
            const printerModel = mapModelCode(printer.model);
            if (slicedFor && printerModel && slicedFor.toLowerCase() !== printerModel.toLowerCase()) {
              api.deleteLibraryFile(uploadedFile.id).catch(() => {});
              return t('printers.incompatibleFile', 'This file was sliced for {{slicedFor}}, but this printer is a {{printerModel}}', { slicedFor, printerModel });
            }
            setPrintAfterUpload({ id: uploadedFile.id, filename: uploadedFile.filename });
          }}
        />
      )}

      {/* Print Modal (after upload) */}
      {printAfterUpload && (
        <PrintModal
          mode="create"
          libraryFileId={printAfterUpload.id}
          archiveName={printAfterUpload.filename}
          initialSelectedPrinterIds={[printer.id]}
          onClose={() => setPrintAfterUpload(null)}
          onSuccess={() => setPrintAfterUpload(null)}
          cleanupLibraryAfterDispatch
        />
      )}

      {/* MQTT Debug Modal */}
      {showMQTTDebug && (
        <MQTTDebugModal
          printerId={printer.id}
          printerName={printer.name}
          onClose={() => setShowMQTTDebug(false)}
        />
      )}

      {showDiagnostic && (
        <ConnectionDiagnosticModal
          printerId={printer.id}
          printerName={printer.name}
          onClose={() => setShowDiagnostic(false)}
        />
      )}

      {showPrinterInfo && (
        <PrinterInfoModal
          printer={printer}
          status={status}
          totalPrintHours={maintenanceInfo?.total_print_hours}
          onClose={closePrinterInfo}
        />
      )}

      {/* Plate Check Result Modal */}
      {plateCheckResult && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => closePlateCheckModal()}>
          <div className="bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-xl shadow-2xl max-w-lg w-full" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-bambu-dark-tertiary">
              <div className="flex items-center gap-2">
                {plateCheckResult.needs_calibration ? (
                  <ScanSearch className="w-5 h-5 text-blue-500" />
                ) : plateCheckResult.is_empty ? (
                  <CheckCircle className="w-5 h-5 text-green-500" />
                ) : (
                  <XCircle className="w-5 h-5 text-yellow-500" />
                )}
                <h2 className="text-lg font-semibold text-white">
                  Build Plate Check
                </h2>
                {plateCheckResult.reference_count !== undefined && plateCheckResult.max_references && (
                  <span className="text-xs text-bambu-gray bg-bambu-dark-tertiary px-2 py-1 rounded">
                    {plateCheckResult.reference_count}/{plateCheckResult.max_references} refs
                  </span>
                )}
              </div>
              <button
                onClick={() => closePlateCheckModal()}
                className="p-1 text-bambu-gray hover:text-white rounded transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 space-y-4">
              {plateCheckResult.needs_calibration ? (
                <>
                  <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-500/20 border border-blue-300 dark:border-blue-500/50">
                    <p className="font-medium text-blue-700 dark:text-blue-400">
                      {t('printers.plateDetection.calibrationRequired')}
                    </p>
                    <p className="text-sm text-bambu-gray mt-1" dangerouslySetInnerHTML={{ __html: t('printers.plateDetection.calibrationInstructions') }} />
                  </div>
                  <div className="text-sm text-bambu-gray space-y-2">
                    <p>{t('printers.plateDetection.calibrationDescription')}</p>
                    <p dangerouslySetInnerHTML={{ __html: t('printers.plateDetection.calibrationTip') }} />
                  </div>
                </>
              ) : (
                <>
                  <div className={`p-3 rounded-lg ${plateCheckResult.is_empty ? 'bg-green-100 dark:bg-green-500/20 border border-green-300 dark:border-green-500/50' : 'bg-yellow-100 dark:bg-yellow-500/20 border border-yellow-300 dark:border-yellow-500/50'}`}>
                    <p className={`font-medium ${plateCheckResult.is_empty ? 'text-green-700 dark:text-green-400' : 'text-yellow-700 dark:text-yellow-400'}`}>
                      {plateCheckResult.is_empty ? t('printers.plateDetection.plateEmpty') : t('printers.plateDetection.objectsDetected')}
                    </p>
                    <p className="text-sm text-bambu-gray mt-1">
                      {t('printers.plateDetection.confidence')}: {Math.round(plateCheckResult.confidence * 100)}% | {t('printers.plateDetection.difference')}: {plateCheckResult.difference_percent.toFixed(1)}%
                    </p>
                  </div>
                  {plateCheckResult.debug_image_url && (
                    <div>
                      <p className="text-sm text-bambu-gray mb-2">{t('printers.plateDetection.analysisPreview')}</p>
                      <img
                        src={plateCheckResult.debug_image_url}
                        alt={t('printers.plateDetection.analysisPreview')}
                        className="w-full rounded-lg border border-bambu-dark-tertiary"
                      />
                      <p className="text-xs text-bambu-gray mt-2">
                        {t('printers.plateDetection.analysisLegend')}
                      </p>
                    </div>
                  )}
                  <p className="text-xs text-bambu-gray">
                    {plateCheckResult.message}
                  </p>
                </>
              )}

              {/* Saved References Grid */}
              {plateReferences && plateReferences.references.length > 0 && (
                <div className="mt-4">
                  <div className="flex items-center gap-2 mb-2">
                    <p className="text-sm font-medium text-white shrink-0">
                      {t('printers.plateDetection.savedReferences', { count: plateReferences.references.length, max: plateReferences.max_references })}
                    </p>
                    <div className="flex-1 h-[2px] bg-bambu-dark-tertiary" />
                  </div>
                  <div className="grid grid-cols-5 gap-2">
                    {plateReferences.references.map((ref) => (
                      <div key={ref.index} className="relative group">
                        <img
                          src={api.getPlateReferenceThumbnailUrl(printer.id, ref.index)}
                          alt={ref.label || `Reference ${ref.index + 1}`}
                          className="w-full aspect-video object-cover rounded border border-bambu-dark-tertiary"
                        />
                        {/* Delete button */}
                        <button
                          onClick={() => handleDeleteRef(ref.index)}
                          className="absolute top-1 right-1 p-0.5 bg-red-500/80 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                          title={t('printers.plateDetection.deleteReference')}
                        >
                          <X className="w-3 h-3 text-white" />
                        </button>
                        {/* Label */}
                        {editingRefLabel?.index === ref.index ? (
                          <TextField
                            type="text"
                            value={editingRefLabel.label}
                            onChange={(e) => setEditingRefLabel({ ...editingRefLabel, label: e.target.value })}
                            onBlur={() => handleUpdateRefLabel(ref.index, editingRefLabel.label)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleUpdateRefLabel(ref.index, editingRefLabel.label);
                              if (e.key === 'Escape') setEditingRefLabel(null);
                            }}
                            className="w-full mt-1 px-1 py-0.5 text-xs bg-bambu-dark-tertiary border border-bambu-green rounded text-white"
                            autoFocus
                            placeholder={t('printers.plateDetection.labelPlaceholder')}
                          />
                        ) : (
                          <p
                            className="text-xs text-bambu-gray mt-1 truncate cursor-pointer hover:text-white"
                            onClick={() => setEditingRefLabel({ index: ref.index, label: ref.label })}
                            title={ref.label ? t('printers.plateDetection.clickToEdit', { label: ref.label }) : t('printers.plateDetection.clickToAddLabel')}
                          >
                            {ref.label || <span className="italic opacity-50">{t('printers.noLabel')}</span>}
                          </p>
                        )}
                        {/* Timestamp */}
                        <p className="text-[10px] text-bambu-gray/60">
                          {ref.timestamp ? parseUTCDate(ref.timestamp)?.toLocaleDateString() ?? '' : ''}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ROI Editor */}
              {!plateCheckResult.needs_calibration && (
                <div className="mt-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex min-w-0 flex-1 items-center gap-2">
                      <p className="text-sm font-medium text-white shrink-0">{t('printers.roi.title')}</p>
                      <div className="flex-1 h-[2px] bg-bambu-dark-tertiary" />
                    </div>
                    {!editingRoi ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingRoi(plateCheckResult.roi || { x: 0.15, y: 0.35, w: 0.70, h: 0.55 })}
                      >
                        <Pencil className="w-3 h-3 mr-1" />
                        {t('common.edit')}
                      </Button>
                    ) : (
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingRoi(null)}
                          disabled={isSavingRoi}
                        >
                          {t('common.cancel')}
                        </Button>
                        <Button
                          size="sm"
                          onClick={handleSaveRoi}
                          disabled={isSavingRoi}
                        >
                          {isSavingRoi ? <Loader2 className="w-3 h-3 animate-spin" /> : t('common.save')}
                        </Button>
                      </div>
                    )}
                  </div>
                  {editingRoi ? (
                    <div className="space-y-3 bg-bambu-dark-tertiary/50 p-3 rounded-lg">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-xs text-bambu-gray">{t('printers.roi.xStart')}</label>
                          <Slider
                            min="0"
                            max="0.9"
                            step="0.01"
                            value={editingRoi.x}
                            onChange={(e) => setEditingRoi({ ...editingRoi, x: parseFloat(e.target.value) })}
                            className="w-full h-1.5 bg-bambu-dark-tertiary rounded-lg cursor-pointer accent-green-500"
                          />
                          <span className="text-xs text-bambu-gray">{Math.round(editingRoi.x * 100)}%</span>
                        </div>
                        <div>
                          <label className="text-xs text-bambu-gray">{t('printers.roi.yStart')}</label>
                          <Slider
                            min="0"
                            max="0.9"
                            step="0.01"
                            value={editingRoi.y}
                            onChange={(e) => setEditingRoi({ ...editingRoi, y: parseFloat(e.target.value) })}
                            className="w-full h-1.5 bg-bambu-dark-tertiary rounded-lg cursor-pointer accent-green-500"
                          />
                          <span className="text-xs text-bambu-gray">{Math.round(editingRoi.y * 100)}%</span>
                        </div>
                        <div>
                          <label className="text-xs text-bambu-gray">{t('printers.width')}</label>
                          <Slider
                            min="0.1"
                            max="1"
                            step="0.01"
                            value={editingRoi.w}
                            onChange={(e) => setEditingRoi({ ...editingRoi, w: parseFloat(e.target.value) })}
                            className="w-full h-1.5 bg-bambu-dark-tertiary rounded-lg cursor-pointer accent-green-500"
                          />
                          <span className="text-xs text-bambu-gray">{Math.round(editingRoi.w * 100)}%</span>
                        </div>
                        <div>
                          <label className="text-xs text-bambu-gray">{t('printers.height')}</label>
                          <Slider
                            min="0.1"
                            max="1"
                            step="0.01"
                            value={editingRoi.h}
                            onChange={(e) => setEditingRoi({ ...editingRoi, h: parseFloat(e.target.value) })}
                            className="w-full h-1.5 bg-bambu-dark-tertiary rounded-lg cursor-pointer accent-green-500"
                          />
                          <span className="text-xs text-bambu-gray">{Math.round(editingRoi.h * 100)}%</span>
                        </div>
                      </div>
                      <p className="text-xs text-bambu-gray">
                        {t('printers.roi.instruction')}
                      </p>
                    </div>
                  ) : (
                    <p className="text-xs text-bambu-gray">
                      Current: X={Math.round((plateCheckResult.roi?.x || 0.15) * 100)}%, Y={Math.round((plateCheckResult.roi?.y || 0.35) * 100)}%,
                      W={Math.round((plateCheckResult.roi?.w || 0.70) * 100)}%, H={Math.round((plateCheckResult.roi?.h || 0.55) * 100)}%
                    </p>
                  )}
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 p-4">
              {plateCheckResult.needs_calibration ? (
                <>
                  <Button variant="ghost" onClick={() => closePlateCheckModal()}>
                    {t('common.cancel')}
                  </Button>
                  <Button
                    onClick={() => handleCalibratePlate()}
                    disabled={isCalibrating}
                  >
                    {isCalibrating ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Calibrating...
                      </>
                    ) : (
                      'Calibrate Empty Plate'
                    )}
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="ghost" onClick={() => handleCalibratePlate()} disabled={isCalibrating}>
                    {isCalibrating ? 'Adding...' : `Add Reference (${plateReferences?.references.length || 0}/${plateReferences?.max_references || 5})`}
                  </Button>
                  <Button onClick={() => closePlateCheckModal()}>
                    Close
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Power On Confirmation */}
      {showPowerOnConfirm && smartPlug && (
        <ConfirmModal
          title={t('printers.confirm.powerOnTitle')}
          message={t('printers.confirm.powerOnMessage', { name: printer.name })}
          confirmText={t('printers.confirm.powerOnButton')}
          variant="default"
          onConfirm={() => {
            powerControlMutation.mutate('on');
            setShowPowerOnConfirm(false);
          }}
          onCancel={() => setShowPowerOnConfirm(false)}
        />
      )}

      {/* Maintenance Mode mid-print confirmation (#1476) — entering maintenance
          disconnects MQTT, which stops progress tracking + completion
          notifications for the in-flight job. Idle / FINISH / FAILED states
          skip this dialog and toggle directly. */}
      {confirmMaintenanceEnter && (
        <ConfirmModal
          title={t('printers.maintenance.confirmMidPrintTitle')}
          message={t('printers.maintenance.confirmMidPrintMessage', { name: printer.name })}
          confirmText={t('printers.maintenance.menuEnter')}
          variant="danger"
          onConfirm={() => {
            maintenanceMutation.mutate(false);
            setConfirmMaintenanceEnter(false);
          }}
          onCancel={() => setConfirmMaintenanceEnter(false)}
        />
      )}

      {/* Power Off Confirmation */}
      {showPowerOffConfirm && smartPlug && (
        <ConfirmModal
          title={t('printers.confirm.powerOffTitle')}
          message={
            status?.state === 'RUNNING'
              ? t('printers.confirm.powerOffWarning', { name: printer.name })
              : t('printers.confirm.powerOffMessage', { name: printer.name })
          }
          confirmText={t('printers.confirm.powerOffButton')}
          variant="danger"
          onConfirm={() => {
            powerControlMutation.mutate('off');
            setShowPowerOffConfirm(false);
          }}
          onCancel={() => setShowPowerOffConfirm(false)}
        />
      )}

      {/* HA entity toggle confirmation (Show on Printer Card switches) */}
      {haToggleConfirm && (
        <ConfirmModal
          title={t('printers.confirm.haToggleTitle', { name: haToggleConfirm.name })}
          message={
            status?.state === 'RUNNING'
              ? t('printers.confirm.haToggleWarning', { name: printer.name, entity: haToggleConfirm.ha_entity_id || haToggleConfirm.name })
              : t('printers.confirm.haToggleMessage', { entity: haToggleConfirm.ha_entity_id || haToggleConfirm.name })
          }
          confirmText={t('printers.confirm.haToggleButton')}
          variant={status?.state === 'RUNNING' ? 'danger' : 'default'}
          onConfirm={() => {
            runScriptMutation.mutate({ id: haToggleConfirm.id, action: 'toggle' });
            setHaToggleConfirm(null);
          }}
          onCancel={() => setHaToggleConfirm(null)}
        />
      )}

      {/* Stop Print Confirmation */}
      {showStopConfirm && (
        <ConfirmModal
          title={t('printers.confirm.stopTitle')}
          message={t('printers.confirm.stopMessage', { name: printer.name })}
          confirmText={t('printers.confirm.stopButton')}
          variant="danger"
          onConfirm={() => {
            stopPrintMutation.mutate();
            setShowStopConfirm(false);
          }}
          onCancel={() => setShowStopConfirm(false)}
        />
      )}

      {/* Pause Print Confirmation */}
      {showPauseConfirm && (
        <ConfirmModal
          title={t('printers.confirm.pauseTitle')}
          message={t('printers.confirm.pauseMessage', { name: printer.name })}
          confirmText={t('printers.confirm.pauseButton')}
          variant="default"
          onConfirm={() => {
            pausePrintMutation.mutate();
            setShowPauseConfirm(false);
          }}
          onCancel={() => setShowPauseConfirm(false)}
        />
      )}

      {/* Resume Print Confirmation */}
      {showResumeConfirm && (
        <ConfirmModal
          title={t('printers.confirm.resumeTitle')}
          message={t('printers.confirm.resumeMessage', { name: printer.name })}
          confirmText={t('printers.confirm.resumeButton')}
          variant="default"
          onConfirm={() => {
            resumePrintMutation.mutate();
            setShowResumeConfirm(false);
          }}
          onCancel={() => setShowResumeConfirm(false)}
        />
      )}

      {/* Bed Jog — not-homed warning (Studio-style) */}
      {showNotHomedModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg shadow-xl w-full max-w-sm p-5">
            <div className="flex items-start gap-3 mb-4">
              <AlertTriangle className="w-5 h-5 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="text-sm font-semibold text-white mb-1">
                  {t('printers.bedJog.notHomedTitle')}
                </h3>
                <p className="text-xs text-bambu-gray leading-relaxed">
                  {t('printers.bedJog.notHomedMessage')}
                </p>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => {
                  homeAxesMutation.mutate('all');
                  setShowNotHomedModal(null);
                }}
                className="w-full px-3 py-2 rounded-lg text-xs font-medium bg-bambu-green/20 text-bambu-green hover:bg-bambu-green/30 transition-colors"
              >
                {t('printers.bedJog.homeZ')}
              </button>
              <button
                onClick={() => {
                  const d = showNotHomedModal.distance;
                  try { sessionStorage.setItem(`printops.bedJog.warned.${printer.id}`, '1'); } catch { /* ignore */ }
                  bedJogMutation.mutate({ distance: d, force: true });
                  setShowNotHomedModal(null);
                }}
                className="w-full px-3 py-2 rounded-lg text-xs font-medium bg-yellow-100 dark:bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-500/30 transition-colors"
              >
                {t('printers.bedJog.moveAnyway')}
              </button>
              <button
                onClick={() => setShowNotHomedModal(null)}
                className="w-full px-3 py-2 rounded-lg text-xs font-medium bg-bambu-dark text-bambu-gray hover:bg-bambu-dark-tertiary transition-colors"
              >
                {t('common.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Skip Objects Modal */}
      <SkipObjectsModal
        printerId={printer.id}
        isOpen={showSkipObjectsModal}
        onClose={() => setShowSkipObjectsModal(false)}
      />

      {/* HMS Error Modal */}
      {showHMSModal && (
        <HMSErrorModal
          printerName={printer.name}
          errors={status?.hms_errors || []}
          onClose={() => setShowHMSModal(false)}
          printerId={printer.id}
          hasPermission={hasPermission}
          runoutGuidance={runoutGuidance}
        />
      )}

      {/* AMS Filament Backup status / control modal (#1762) */}
      {amsBackupModalOpen && status && (
        <AmsBackupModal
          isOpen={amsBackupModalOpen}
          state={status.ams_filament_backup}
          amsUnits={status.ams}
          amsExtruderMap={status.ams_extruder_map}
          isDualNozzle={printer.nozzle_count === 2 || status?.temperatures?.nozzle_2 !== undefined}
          canToggle={canUsePrinterControl}
          pending={setAmsBackupMutation.isPending}
          onToggle={(next) => setAmsBackupMutation.mutate(next)}
          onClose={() => setAmsBackupModalOpen(false)}
        />
      )}

      {/* AMS History Modal */}
      {amsHistoryModal && (
        <AMSHistoryModal
          isOpen={!!amsHistoryModal}
          onClose={() => setAmsHistoryModal(null)}
          printerId={printer.id}
          printerName={printer.name}
          amsId={amsHistoryModal.amsId}
          amsLabel={amsHistoryModal.amsLabel}
          initialMode={amsHistoryModal.mode}
          thresholds={amsThresholds}
        />
      )}

      {/* Heater History Modal (nozzle / bed / chamber) */}
      {heaterHistoryModal && (
        <HeaterHistoryModal
          isOpen={!!heaterHistoryModal}
          onClose={() => setHeaterHistoryModal(null)}
          printerId={printer.id}
          printerName={printer.name}
          initialKind={heaterHistoryModal.initialKind}
          availableKinds={heaterHistoryModal.availableKinds}
        />
      )}

      {/* Link Spool Modal */}
      {linkSpoolModal && (
        <LinkSpoolModal
          isOpen={!!linkSpoolModal}
          onClose={() => setLinkSpoolModal(null)}
          tagUid={linkSpoolModal.tagUid}
          trayUuid={linkSpoolModal.trayUuid}
          printerId={linkSpoolModal.printerId}
          amsId={linkSpoolModal.amsId}
          trayId={linkSpoolModal.trayId}
        />
      )}

      {/* Assign Spool Modal */}
      {assignSpoolModal && (
        <AssignSpoolModal
          isOpen={!!assignSpoolModal}
          onClose={() => setAssignSpoolModal(null)}
          printerId={assignSpoolModal.printerId}
          amsId={assignSpoolModal.amsId}
          trayId={assignSpoolModal.trayId}
          trayInfo={assignSpoolModal.trayInfo}
          spoolmanEnabled={!!spoolmanEnabled}
        />
      )}

      {/* Configure AMS Slot Modal */}
      {configureSlotModal && (
        <ConfigureAmsSlotModal
          isOpen={!!configureSlotModal}
          onClose={() => setConfigureSlotModal(null)}
          printerId={printer.id}
          slotInfo={configureSlotModal}
          printerModel={mapModelCode(printer.model) || undefined}
          onSuccess={() => {
            // Refresh slot presets to show updated profile name
            queryClient.invalidateQueries({ queryKey: ['slotPresets', printer.id] });
            // Printer status will update automatically via WebSocket when AMS data changes
            queryClient.invalidateQueries({ queryKey: ['printerStatus', printer.id] });
          }}
        />
      )}

      {/* Edit Printer Modal */}
      {showEditModal && (
        <EditPrinterModal
          printer={printer}
          onClose={() => setShowEditModal(false)}
        />
      )}

      {/* Firmware Update Modal */}
      {showFirmwareModal && firmwareInfo && (
        <FirmwareUpdateModal
          printer={printer}
          firmwareInfo={firmwareInfo}
          onClose={() => setShowFirmwareModal(false)}
        />
      )}

      {/* AMS Drying Popover — fixed position to avoid overflow/z-index issues */}
      {dryingPopoverAmsId !== null && dryingPopoverPos && (() => {
        const maxTemp = dryingPopoverModuleType === 'n3s' ? 85 : 65;
        const sliderMin = 35;
        const sliderMax = maxTemp + 10;
        return (
          <>
            {/* Backdrop */}
            <div className="fixed inset-0 z-[100]" onClick={() => setDryingPopoverAmsId(null)} />
            {/* Popover */}
            <div
              className="fixed z-[101] flex flex-col w-[240px] bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-xl shadow-2xl overflow-hidden"
              style={{
                top: dryingPopoverPos.top,
                left: dryingPopoverPos.left,
                // Cap to the space between the popover's top and the bottom
                // viewport margin (8px, matching computePopoverPosition's
                // margin). When the popover is taller than that space — short
                // viewport, landscape phone, zoomed-in — the body scrolls and
                // the footer stays pinned, so the Start button is always
                // reachable (#1458 / #1447 follow-up). dvh (not vh) so iOS
                // Safari's bottom toolbar overlay doesn't clip the footer
                // (#1669, iPhone 17 Safari).
                maxHeight: `calc(100dvh - ${dryingPopoverPos.top}px - 8px)`,
              }}
              onClick={e => e.stopPropagation()}
            >
              {/* Header */}
              <div className="shrink-0 flex items-center justify-center gap-2 px-3 py-2.5">
                <Flame className="w-3.5 h-3.5 text-bambu-green" />
                <span className="text-sm text-white font-medium text-center">{t('printers.drying.start')}</span>
              </div>
              <div className="shrink-0 h-px bg-bambu-dark-tertiary" />
              {/* Body */}
              <div className="px-3 py-2.5 space-y-2.5 overflow-y-auto min-h-0">
                {/* Filament type select */}
                <div>
                  <label className="text-[10px] text-white/70 font-medium mb-1 block">{t('printers.filaments')}</label>
                  <ToolbarDropdown
                    value={dryingFilament}
                    options={Object.keys(dryingPresets).map(fil => ({ value: fil, label: fil }))}
                    onChange={fil => {
                      setDryingFilament(fil);
                      const preset = dryingPresets[fil];
                      if (preset) {
                        const key = dryingPopoverModuleType === 'n3s' ? 'n3s' : 'n3f';
                        setDryingTemp(preset[key]);
                        setDryingDuration(dryingPopoverModuleType === 'n3s' ? preset.n3s_hours : preset.n3f_hours);
                      }
                    }}
                    fullWidth
                  />
                </div>
                {/* Temperature */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[10px] text-white/70 font-medium">{t('printers.drying.temperature')}</label>
                    <div className="flex items-center gap-1">
                      <NumberField
                        min={45}
                        max={maxTemp}
                        value={dryingTemp}
                        onChange={e => setDryingTemp(Math.min(maxTemp, Math.max(45, Number(e.target.value) || 45)))}
                        className="w-12 px-1 py-0.5 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-[11px] text-center focus:outline-none focus:border-bambu-green [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                      <span className="text-[10px] text-bambu-gray">°C</span>
                    </div>
                  </div>
                  <Slider
                    min={sliderMin}
                    max={sliderMax}
                    value={dryingTemp}
                    onChange={e => setDryingTemp(Math.min(maxTemp, Math.max(45, Number(e.target.value))))}
                    className="w-full h-1 accent-bambu-green cursor-pointer"
                  />
                  <div className="flex justify-between text-[9px] text-bambu-gray/50 mt-0.5">
                    <span>45°C</span>
                    <span>{maxTemp}°C</span>
                  </div>
                </div>
                {/* Duration */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[10px] text-white/70 font-medium">{t('printers.drying.duration')}</label>
                    <div className="flex items-center gap-1">
                      <NumberField
                        min={1}
                        max={24}
                        value={dryingDuration}
                        onChange={e => setDryingDuration(Math.min(24, Math.max(1, Number(e.target.value) || 1)))}
                        className="w-10 px-1 py-0.5 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white text-[11px] text-center focus:outline-none focus:border-bambu-green [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                      <span className="text-[10px] text-bambu-gray">{t('printers.drying.hours')}</span>
                    </div>
                  </div>
                  <Slider
                    min={1}
                    max={24}
                    value={dryingDuration}
                    onChange={e => setDryingDuration(Number(e.target.value))}
                    className="w-full h-1 accent-bambu-green cursor-pointer"
                  />
                  <div className="flex justify-between text-[9px] text-bambu-gray/50 mt-0.5">
                    <span>1h</span>
                    <span>24h</span>
                  </div>
                </div>
                {/* Rotate tray — disabled when any tray in THIS AMS has its
                    filament threaded out into the feed tube. The whole AMS
                    rotates as one mechanism (all 4 spools turn together), so a
                    single loaded slot locks the entire unit. Bambu per-tray
                    `state`: 9 = empty, 10 = spool present but not loaded
                    (rotation possible), 11 = loaded into tube (rotation impossible).
                    Catches both mid-print (active feed) AND idle-with-threaded-
                    filament — the H2D's post-print state leaves filament in the
                    tube but tray_now resets to 255, which a tray_now-only check
                    would silently miss. */}
                {(() => {
                  const targetAms = dryingPopoverAmsId !== null
                    ? amsData.find(a => a.id === dryingPopoverAmsId)
                    : undefined;
                  const trayLoadedInThisAms = (targetAms?.tray ?? []).some(
                    tray => tray.state === 11,
                  );
                  const rotateChecked = dryingRotateTray && !trayLoadedInThisAms;
                  return (
                    <div title={trayLoadedInThisAms ? t('printers.drying.rotateUnavailableReason') : undefined}>
                      <button
                        type="button"
                        onClick={() => setDryingRotateTray(enabled => !enabled)}
                        aria-pressed={rotateChecked}
                        aria-disabled={trayLoadedInThisAms}
                        disabled={trayLoadedInThisAms}
                        className={`min-h-10 w-full rounded-lg border px-3 py-1.5 text-[11px] font-medium leading-tight transition-colors ${
                          rotateChecked
                            ? 'bg-bambu-green border-bambu-green text-white'
                            : trayLoadedInThisAms
                              ? 'cursor-not-allowed bg-bambu-dark/80 border-bambu-dark-tertiary text-bambu-gray opacity-60'
                              : 'bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary'
                        }`}
                      >
                        <span className="block whitespace-normal text-center">
                          {t('printers.drying.rotateTray')}
                        </span>
                      </button>
                    </div>
                  );
                })()}
              </div>
              <div className="shrink-0 h-px bg-bambu-dark-tertiary" />
              {/* Footer */}
              <div className="shrink-0 px-3 pt-2.5 pb-3">
                <button
                  onClick={() => {
                    if (dryingPopoverAmsId !== null) {
                      // Clamp rotateTray off when any tray in this AMS is loaded into
                      // the tube — the rotate UI is disabled there, but the state may
                      // linger as `true` from a previous AMS, or a print may have
                      // started while the popover was open. Without this clamp the
                      // Start payload would carry rotate_tray=true and firmware would
                      // reject with dry_sf_reason=[3] (ConsumableAtAmsOutlet).
                      const targetAms = amsData.find(a => a.id === dryingPopoverAmsId);
                      const trayLoadedInThisAms = (targetAms?.tray ?? []).some(
                        tray => tray.state === 11,
                      );
                      startDryingMutation.mutate({
                        amsId: dryingPopoverAmsId,
                        temp: dryingTemp,
                        duration: dryingDuration,
                        filament: dryingFilament,
                        rotateTray: dryingRotateTray && !trayLoadedInThisAms,
                      });
                    }
                  }}
                  disabled={startDryingMutation.isPending}
                  className="w-full py-1.5 bg-bambu-green hover:bg-bambu-green/80 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50"
                >
                  {startDryingMutation.isPending ? t('printers.drying.startingDrying') : t('printers.drying.start')}
                </button>
              </div>
            </div>
          </>
        );
      })()}
    </Card>
  );
}
