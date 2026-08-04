import { useState, useEffect, useLayoutEffect, useMemo, useRef, useCallback } from 'react';
import { BED_TEMP_DEFAULTS, CHAMBER_TEMP_DEFAULTS, FAN_SPEED_DEFAULTS, NOZZLE_TEMP_DEFAULTS, parsePresetTriple } from '../../utils/temperatureFanPresets';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../../contexts/ThemeContext';
import { useAuth } from '../../contexts/AuthContext';
import { TextField } from '../../components/ui';
import { Plus, Power, ChevronDown, Filter, ArrowLeft, ArrowUp, ArrowDown, Search, X, CheckSquare, Printer as PrinterIcon, MoreHorizontal, SlidersHorizontal, LayoutGrid, MonitorPlay } from 'lucide-react';
import { api, ApiError } from '../../api/client';
import type { Printer, SpoolAssignment, HMSError } from '../../api/client';
import { Card, CardContent } from '../../components/Card';
import { Button } from '../../components/Button';
import { ConfirmModal } from '../../components/ConfirmModal';
import { BulkPrinterToolbar, type PrinterState } from '../../components/BulkPrinterToolbar';
import { EmbeddedCameraViewer } from '../../components/EmbeddedCameraViewer';
import { CameraWall } from '../../components/CameraWall';
import { filterKnownHMSErrors } from '../../components/HMSErrorModal';
import { useToast } from '../../contexts/ToastContext';
import { Collapsible } from '../../components/Collapsible';
import type { PrinterMaintenanceInfo, SortOption, ViewMode } from './types';
import { DRYING_PRESETS, PrinterCard } from './PrinterCard';
import { STATUS_GROUP_META, STATUS_GROUP_ORDER, classifyPrinterStatus } from './printer-status';
import { ToolbarDropdown, ToolbarMenu } from './printer-toolbar';
import { StatusSummaryBar } from './printer-card-visuals';
import { AddPrinterModal } from './AddPrinterModal';

// Component to check if a printer is offline (for power dropdown)
export function usePrinterOfflineStatus(printerId: number) {
  const { data: status } = useQuery({
    queryKey: ['printerStatus', printerId],
    queryFn: () => api.getPrinterStatus(printerId),
    refetchInterval: 30000,
  });
  return !status?.connected;
}

// Power dropdown item for an offline printer
export function PowerDropdownItem({
  printer,
  plug,
  onPowerOn,
  isPowering,
}: {
  printer: Printer;
  plug: { id: number; name: string };
  onPowerOn: (plugId: number) => void;
  isPowering: boolean;
}) {
  const isOffline = usePrinterOfflineStatus(printer.id);

  // Fetch plug status
  const { data: plugStatus } = useQuery({
    queryKey: ['smartPlugStatus', plug.id],
    queryFn: () => api.getSmartPlugStatus(plug.id),
    refetchInterval: 10000,
  });

  // Only show if printer is offline
  if (!isOffline) {
    return null;
  }

  return (
    <div className="flex items-center justify-between px-3 py-2 hover:bg-gray-100 dark:hover:bg-bambu-dark-tertiary">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-sm text-white truncate">{printer.name}</span>
        {plugStatus && (
          <span
            className={`text-xs px-1.5 py-0.5 rounded ${
              plugStatus.state === 'ON'
                ? 'bg-bambu-green/20 text-bambu-green'
                : 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400'
            }`}
          >
            {plugStatus.state || '?'}
          </span>
        )}
      </div>
      <button
        onClick={() => onPowerOn(plug.id)}
        disabled={isPowering || plugStatus?.state === 'ON'}
        className={`px-2 py-1 text-xs rounded transition-colors flex items-center gap-1 ${
          plugStatus?.state === 'ON'
            ? 'bg-bambu-green/20 text-bambu-green cursor-default'
            : 'bg-bambu-green/20 text-bambu-green hover:bg-bambu-green hover:text-white'
        }`}
      >
        <Power className="w-3 h-3" />
        {isPowering ? '...' : 'On'}
      </button>
    </div>
  );
}

export function PrintersPage() {
  const { t } = useTranslation();
  const { resolvedMode, darkAccent, lightAccent } = useTheme();
  const activeAccent = resolvedMode === 'dark' ? darkAccent : lightAccent;
  const accentButtonClass = {
    green: 'bg-green-500 text-white hover:bg-green-400 border-green-400/60',
    teal: 'bg-teal-500 text-white hover:bg-teal-400 border-teal-400/60',
    blue: 'bg-blue-500 text-white hover:bg-blue-400 border-blue-400/60',
    orange: 'bg-orange-500 text-white hover:bg-orange-400 border-orange-400/60',
    purple: 'bg-purple-500 text-white hover:bg-purple-400 border-purple-400/60',
    red: 'bg-red-500 text-white hover:bg-red-400 border-red-400/60',
  }[activeAccent];
  const [showAddModal, setShowAddModal] = useState(false);
  const [hideDisconnected, setHideDisconnected] = useState(() => {
    return localStorage.getItem('hideDisconnectedPrinters') === 'true';
  });
  const [showPowerDropdown, setShowPowerDropdown] = useState(false);
  const [poweringOn, setPoweringOn] = useState<number | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>(() => {
    return (localStorage.getItem('printerSortBy') as SortOption) || 'name';
  });
  const [sortAsc, setSortAsc] = useState<boolean>(() => {
    return localStorage.getItem('printerSortAsc') !== 'false';
  });
  // Card size: 1=small, 2=medium, 3=large, 4=xl
  const [cardSize, setCardSize] = useState<number>(() => {
    const saved = localStorage.getItem('printerCardSize');
    return saved ? parseInt(saved, 10) : 2; // Default to medium
  });
  // Page view: 'cards' = printer cards (default), 'camwall' = grid of live camera tiles
  const [pageView, setPageView] = useState<'cards' | 'camwall'>(() => {
    return localStorage.getItem('printerPageView') === 'camwall' ? 'camwall' : 'cards';
  });
  // Cam-wall settings — per-user, no backend write (a Pi 4 install caps the
  // live count lower than a NUC; default 4 is the documented Pi 4 ceiling).
  const [camWallMaxLive, setCamWallMaxLive] = useState<number>(() => {
    const saved = parseInt(localStorage.getItem('camWallMaxLive') || '', 10);
    return Number.isFinite(saved) && saved > 0 ? saved : 4;
  });
  const [camWallSnapshotSec, setCamWallSnapshotSec] = useState<number>(() => {
    const saved = parseInt(localStorage.getItem('camWallSnapshotSec') || '', 10);
    return Number.isFinite(saved) && saved > 0 ? saved : 8;
  });
  // 'off' hides the printer-state overlay; 'compact' shows only a state chip;
  // 'full' adds progress, layer, and time-left on printing/paused tiles.
  // Defaulting to 'full' because the cards already show this info — users who
  // pick cam-wall view still want to glance the same details without flipping.
  const [camWallStatusMode, setCamWallStatusMode] = useState<'off' | 'compact' | 'full'>(() => {
    const saved = localStorage.getItem('camWallStatusMode');
    return saved === 'off' || saved === 'compact' || saved === 'full' ? saved : 'full';
  });
  // Derive viewMode from cardSize: S=compact, M/L/XL=expanded
  const viewMode: ViewMode = cardSize === 1 ? 'compact' : 'expanded';
  const [compactDrilldownPrinterId, setCompactDrilldownPrinterId] = useState<number | null>(null);
  const scrollPrinterIntoView = useCallback((printerId: number) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const card = document.getElementById(`printer-card-${printerId}`);
        if (!card) return;
        const fixedHeaderHeight = document.querySelector('header')?.getBoundingClientRect().height ?? 56;
        const top = card.getBoundingClientRect().top + window.scrollY - fixedHeaderHeight - 16;
        window.scrollTo({
          top: Math.max(0, top),
          behavior: 'smooth',
        });
      });
    });
  }, []);
  const openCompactCard = useCallback((printerId: number) => {
    setCompactDrilldownPrinterId(printerId);
    setCardSize(2);
    localStorage.setItem('printerCardSize', '2');
    scrollPrinterIntoView(printerId);
  }, [scrollPrinterIntoView]);
  const returnToCompactCards = useCallback(() => {
    const printerId = compactDrilldownPrinterId;
    setCompactDrilldownPrinterId(null);
    setCardSize(1);
    localStorage.setItem('printerCardSize', '1');
    if (printerId != null) {
      scrollPrinterIntoView(printerId);
    }
  }, [compactDrilldownPrinterId, scrollPrinterIntoView]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [locationFilter, setLocationFilter] = useState<string>('all');
  const [statusCacheVersion, setStatusCacheVersion] = useState(0);
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>(() => {
    try {
      const saved = localStorage.getItem('printerCollapsedSections');
      return saved ? JSON.parse(saved) : {};
    } catch { return {}; }
  });
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { hasPermission } = useAuth();
  // Embedded camera viewer state - supports multiple simultaneous viewers
  // Persisted to localStorage so cameras reopen after navigation
  const [embeddedCameraPrinters, setEmbeddedCameraPrinters] = useState<Map<number, { id: number; name: string }>>(() => {
    // Initialize from localStorage if camera_view_mode is embedded
    const saved = localStorage.getItem('openEmbeddedCameras');
    if (saved) {
      try {
        const cameras = JSON.parse(saved) as Array<{ id: number; name: string }>;
        return new Map(cameras.map(c => [c.id, c]));
      } catch {
        return new Map();
      }
    }
    return new Map();
  });

  // Persist open cameras to localStorage when they change
  useEffect(() => {
    const cameras = Array.from(embeddedCameraPrinters.values());
    if (cameras.length > 0) {
      localStorage.setItem('openEmbeddedCameras', JSON.stringify(cameras));
    } else {
      localStorage.removeItem('openEmbeddedCameras');
    }
  }, [embeddedCameraPrinters]);

  const { data: printers, isLoading } = useQuery({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  });

  // Fetch the UI-rendering subset of settings. Uses /ui-preferences (not /settings)
  // so users with printers:read but no settings:read still get the values needed
  // to render the clear-plate button, drying presets, AMS thresholds, etc. (#1293).
  const { data: settings } = useQuery({
    queryKey: ['ui-preferences'],
    queryFn: api.getUiPreferences,
  });

  // Parse user-configured temperature/fan presets once, with defensive fallback
  // to built-in defaults on parse failure (validators on the backend already
  // reject malformed writes, so this is just forward-compat).
  const effectiveNozzleTempPresets = useMemo(
    () => parsePresetTriple(settings?.nozzle_temp_presets, NOZZLE_TEMP_DEFAULTS, 0, 320),
    [settings?.nozzle_temp_presets],
  );
  const effectiveBedTempPresets = useMemo(
    () => parsePresetTriple(settings?.bed_temp_presets, BED_TEMP_DEFAULTS, 0, 140),
    [settings?.bed_temp_presets],
  );
  const effectiveChamberTempPresets = useMemo(
    () => parsePresetTriple(settings?.chamber_temp_presets, CHAMBER_TEMP_DEFAULTS, 0, 60),
    [settings?.chamber_temp_presets],
  );
  const effectiveFanSpeedPresets = useMemo(
    () => parsePresetTriple(settings?.fan_speed_presets, FAN_SPEED_DEFAULTS, 0, 100),
    [settings?.fan_speed_presets],
  );

  // Compute drying presets: user-configured (from settings) merged over built-in defaults
  const effectiveDryingPresets = useMemo(() => {
    if (settings?.drying_presets) {
      try {
        const userPresets = JSON.parse(settings.drying_presets);
        if (typeof userPresets === 'object' && userPresets !== null && Object.keys(userPresets).length > 0) {
          return { ...DRYING_PRESETS, ...userPresets };
        }
      } catch { /* ignore parse errors, use defaults */ }
    }
    return DRYING_PRESETS;
  }, [settings?.drying_presets]);

  // Close embedded cameras if mode changes to 'window'
  useEffect(() => {
    if (settings?.camera_view_mode === 'window' && embeddedCameraPrinters.size > 0) {
      setEmbeddedCameraPrinters(new Map());
    }
  }, [settings?.camera_view_mode, embeddedCameraPrinters.size]);

  // Fetch all smart plugs to know which printers have them
  const { data: smartPlugs } = useQuery({
    queryKey: ['smart-plugs'],
    queryFn: api.getSmartPlugs,
  });

  // Fetch maintenance overview for all printers to show badges
  const { data: maintenanceOverview } = useQuery({
    queryKey: ['maintenanceOverview'],
    queryFn: api.getMaintenanceOverview,
    staleTime: 60 * 1000, // 1 minute
  });

  // Fetch Spoolman status to enable link spool feature
  const { data: spoolmanStatus } = useQuery({
    queryKey: ['spoolman-status'],
    queryFn: api.getSpoolmanStatus,
    staleTime: 60 * 1000, // 1 minute
  });
  const spoolmanEnabled = spoolmanStatus?.enabled && spoolmanStatus?.connected;

  // Fetch Spoolman settings to get sync mode
  const { data: spoolmanSettings } = useQuery({
    queryKey: ['spoolman-settings'],
    queryFn: api.getSpoolmanSettings,
    enabled: !!spoolmanEnabled,
    staleTime: 60 * 1000, // 1 minute
  });
  const spoolmanSyncMode = spoolmanSettings?.spoolman_sync_mode;

  // Fetch unlinked spools to know if link button should be enabled
  const { data: unlinkedSpools } = useQuery({
    queryKey: ['unlinked-spools'],
    queryFn: api.getUnlinkedSpools,
    enabled: !!spoolmanEnabled,
    staleTime: 30 * 1000, // 30 seconds
  });
  const hasUnlinkedSpools = unlinkedSpools && unlinkedSpools.length > 0;

  // Fetch linked spools map (tag -> spool_id) to know which spools are already in Spoolman
  const { data: linkedSpoolsData } = useQuery({
    queryKey: ['linked-spools'],
    queryFn: api.getLinkedSpools,
    enabled: !!spoolmanEnabled,
    staleTime: 30 * 1000, // 30 seconds
  });
  const linkedSpools = linkedSpoolsData?.linked;

  // Fetch spool assignments for inventory feature
  const { data: spoolAssignments } = useQuery({
    queryKey: ['spool-assignments'],
    queryFn: () => api.getAssignments(),
    enabled: hasPermission('inventory:view_assignments'),
    staleTime: 30 * 1000,
  });

  const unassignMutation = useMutation({
    mutationFn: ({ printerId, amsId, trayId }: { printerId: number; amsId: number; trayId: number }) =>
      api.unassignSpool(printerId, amsId, trayId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spool-assignments'] });
    },
  });

  const { data: spoolmanSpools, isLoading: spoolmanSpoolsLoading } = useQuery({
    queryKey: ['spoolman-inventory-spools'],
    queryFn: () => api.getSpoolmanInventorySpools(false),
    enabled: !!spoolmanEnabled,
    staleTime: 30 * 1000,
  });

  const { data: spoolmanSlotAssignments, isLoading: spoolmanAssignmentsLoading } = useQuery({
    queryKey: ['spoolman-slot-assignments'],
    queryFn: () => api.getSpoolmanSlotAssignments(),
    enabled: !!spoolmanEnabled,
    staleTime: 30 * 1000,
  });

  const unassignSpoolmanMutation = useMutation({
    mutationFn: (spoolmanSpoolId: number) => api.unassignSpoolmanSlot(spoolmanSpoolId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spoolman-inventory-spools'] });
      queryClient.invalidateQueries({ queryKey: ['spoolman-slot-assignments'] });
    },
  });

  // Helper to find assignment for a specific slot
  const getAssignment = (printerId: number, amsId: number | string, trayId: number | string): SpoolAssignment | undefined => {
    return spoolAssignments?.find(
      (a) => a.printer_id === printerId && a.ams_id === Number(amsId) && a.tray_id === Number(trayId)
    );
  };

  // Create a map of printer_id -> maintenance info for quick lookup
  const maintenanceByPrinter = maintenanceOverview?.reduce(
    (acc, overview) => {
      acc[overview.printer_id] = {
        due_count: overview.due_count,
        warning_count: overview.warning_count,
        total_print_hours: overview.total_print_hours,
      };
      return acc;
    },
    {} as Record<number, PrinterMaintenanceInfo>
  ) || {};

  // Create a map of printer_id -> smart plug
  const smartPlugByPrinter = smartPlugs?.reduce(
    (acc, plug) => {
      if (plug.printer_id) {
        acc[plug.printer_id] = plug;
      }
      return acc;
    },
    {} as Record<number, typeof smartPlugs[0]>
  ) || {};

  const addMutation = useMutation({
    mutationFn: api.createPrinter,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printers'] });
      queryClient.invalidateQueries({ queryKey: ['maintenanceOverview'] });
      setShowAddModal(false);
    },
    onError: (error: Error) => {
      // Localized message when the backend returns a stable error code;
      // the raw message is an English fallback for non-UI clients.
      if (error instanceof ApiError && error.code === 'printer_connection_failed') {
        showToast(t('printers.toast.connectionFailedNotAdded'), 'error');
        return;
      }
      showToast(error.message || t('printers.toast.failedToAdd'), 'error');
    },
  });

  const powerOnMutation = useMutation({
    mutationFn: (plugId: number) => api.controlSmartPlug(plugId, 'on'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart-plugs'] });
      setPoweringOn(null);
    },
    onError: () => {
      setPoweringOn(null);
    },
  });

  // Bulk selection state
  const [selectedPrinterIds, setSelectedPrinterIds] = useState<Set<number>>(new Set());
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [bulkConfirmAction, setBulkConfirmAction] = useState<'stop' | 'pause' | 'clearPlate' | null>(null);
  const [bulkActionPending, setBulkActionPending] = useState(false);
  const selectionMode = isSelectionMode || selectedPrinterIds.size > 0;

  const toggleSelect = useCallback((id: number) => {
    setSelectedPrinterIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedPrinterIds(new Set());
    setIsSelectionMode(false);
  }, []);

  // Escape key exits selection mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && selectionMode) {
        clearSelection();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectionMode, clearSelection]);

  const executeBulkAction = useCallback(async (action: 'stop' | 'pause' | 'resume' | 'clearPlate' | 'clearHMS') => {
    setBulkActionPending(true);
    const ids = Array.from(selectedPrinterIds);

    // Filter to only applicable printers based on cached state
    const applicableIds = ids.filter(id => {
      const status = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', id]);
      if (!status?.connected) return false;
      switch (action) {
        case 'stop': return status.state === 'RUNNING' || status.state === 'PAUSE';
        case 'pause': return status.state === 'RUNNING';
        case 'resume': return status.state === 'PAUSE';
        case 'clearPlate': return !!(status as { awaiting_plate_clear?: boolean }).awaiting_plate_clear;
        case 'clearHMS': return status.hms_errors && filterKnownHMSErrors(status.hms_errors).length > 0;
        default: return false;
      }
    });

    if (applicableIds.length === 0) {
      showToast(t('printers.bulk.noneApplicable'), 'error');
      setBulkActionPending(false);
      setBulkConfirmAction(null);
      return;
    }

    const apiCall = {
      stop: api.stopPrint,
      pause: api.pausePrint,
      resume: api.resumePrint,
      clearPlate: api.clearPlate,
      clearHMS: api.clearHMSErrors,
    }[action];

    const results = await Promise.allSettled(
      applicableIds.map(id => apiCall(id))
    );

    const succeeded = results.filter(r => r.status === 'fulfilled').length;
    const failed = results.filter(r => r.status === 'rejected').length;

    if (failed === 0) {
      showToast(t('printers.bulk.success', { action: t(`printers.bulk.actions.${action}`), count: succeeded }));
    } else {
      showToast(t('printers.bulk.partial', { succeeded, failed }), 'error');
    }

    // Invalidate status queries for affected printers
    applicableIds.forEach(id => {
      queryClient.invalidateQueries({ queryKey: ['printerStatus', id] });
    });

    setBulkActionPending(false);
    setBulkConfirmAction(null);
  }, [selectedPrinterIds, queryClient, showToast, t]);

  const handleBulkAction = useCallback((action: 'stop' | 'pause' | 'resume' | 'clearPlate' | 'clearHMS') => {
    // Actions that need confirmation
    if (action === 'stop' || action === 'pause' || action === 'clearPlate') {
      setBulkConfirmAction(action);
    } else {
      executeBulkAction(action);
    }
  }, [executeBulkAction]);

  const toggleHideDisconnected = () => {
    const newValue = !hideDisconnected;
    setHideDisconnected(newValue);
    localStorage.setItem('hideDisconnectedPrinters', String(newValue));
  };

  const handleSortChange = (newSort: SortOption) => {
    setSortBy(newSort);
    localStorage.setItem('printerSortBy', newSort);
  };

  const toggleSortDirection = () => {
    const newAsc = !sortAsc;
    setSortAsc(newAsc);
    localStorage.setItem('printerSortAsc', String(newAsc));
  };

  // Grid classes based on card size (1=small, 2=medium, 3=large, 4=xl)
  const getGridClasses = () => {
    switch (cardSize) {
      case 1: return 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5'; // S: many small cards
      case 2: return 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3'; // M: medium cards
      case 3: return 'grid-cols-1 lg:grid-cols-2'; // L: large cards, 2 columns max
      case 4: return 'grid-cols-1'; // XL: single column, full width
      default: return 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3';
    }
  };

  const cardSizeLabels = ['S', 'M', 'L', 'XL'];

  // Increment version counter whenever a printer status cache entry is updated so
  // filteredPrinters re-computes reactively on WebSocket-driven status changes.
  useEffect(() => {
    const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
      if (
        event.type === 'updated' &&
        Array.isArray(event.query.queryKey) &&
        event.query.queryKey[0] === 'printerStatus'
      ) {
        setStatusCacheVersion(v => v + 1);
      }
    });
    return unsubscribe;
  }, [queryClient]);

  // Filter printers by search term, status, and location
  const filteredPrinters = useMemo(() => {
    if (!printers) return [];
    let result = printers;

    // Text search
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter(p =>
        p.name.toLowerCase().includes(q) ||
        (p.model || '').toLowerCase().includes(q) ||
        (p.location || '').toLowerCase().includes(q) ||
        (p.serial_number || '').toLowerCase().includes(q)
      );
    }

    // Location filter
    if (locationFilter !== 'all') {
      result = result.filter(p => (p.location || '') === locationFilter);
    }

    // Status filter
    if (statusFilter !== 'all') {
      result = result.filter(p => {
        const status = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', p.id]);
        if (!status?.connected) return statusFilter === 'offline';
        const hmsErrors = status.hms_errors ? filterKnownHMSErrors(status.hms_errors) : [];
        switch (statusFilter) {
          case 'printing': return status.state === 'RUNNING';
          case 'paused':   return status.state === 'PAUSE';
          case 'finished': return status.state === 'FINISH';
          case 'error':    return status.state === 'FAILED' || hmsErrors.length > 0;
          case 'idle':     return status.state !== 'RUNNING' && status.state !== 'PAUSE' && status.state !== 'FINISH' && status.state !== 'FAILED' && hmsErrors.length === 0;
          case 'offline':  return false; // Connected printers are never offline
          default:         return true;
        }
      });
    }

    return result;
  // eslint-disable-next-line react-hooks/exhaustive-deps -- statusCacheVersion is intentional: it forces recompute when WebSocket updates printer status cache
  }, [printers, search, statusFilter, locationFilter, queryClient, statusCacheVersion]);

  // Derive unique locations for the location filter dropdown
  const availableLocations = useMemo(() => {
    if (!printers) return [];
    return [...new Set(printers.map(p => p.location || '').filter(Boolean))].sort();
  }, [printers]);

  // Sort printers based on selected option
  const sortedPrinters = useMemo(() => {
    const sorted = [...filteredPrinters];

    switch (sortBy) {
      case 'name':
        sorted.sort((a, b) => a.name.localeCompare(b.name));
        break;
      case 'model':
        sorted.sort((a, b) => (a.model || '').localeCompare(b.model || ''));
        break;
      case 'location':
        // Sort by location, with ungrouped printers last
        sorted.sort((a, b) => {
          const locA = a.location || '';
          const locB = b.location || '';
          if (!locA && locB) return 1;
          if (locA && !locB) return -1;
          return locA.localeCompare(locB) || a.name.localeCompare(b.name);
        });
        break;
      case 'status':
        // Sort by status: HMS errors > printing > idle > offline
        sorted.sort((a, b) => {
          const statusA = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', a.id]);
          const statusB = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', b.id]);

          const getPriority = (s: typeof statusA) => {
            if (!s?.connected) return 3; // offline
            const hmsErrors = s.hms_errors ? filterKnownHMSErrors(s.hms_errors) : [];
            if (hmsErrors.length > 0) return 0; // HMS errors - top priority
            if (s.state === 'RUNNING') return 1; // printing
            return 2; // idle
          };

          return getPriority(statusA) - getPriority(statusB);
        });
        break;
      case 'eta':
        sorted.sort((a, b) => {
          const statusA = queryClient.getQueryData<{ connected: boolean; state: string | null; remaining_time: number | null }>(['printerStatus', a.id]);
          const statusB = queryClient.getQueryData<{ connected: boolean; state: string | null; remaining_time: number | null }>(['printerStatus', b.id]);

          const tier = (s: typeof statusA) => {
            if (!s?.connected) return 3; // offline last
            if (s.state === 'RUNNING' && s.remaining_time != null && s.remaining_time > 0) return 0; // printing with ETA
            if (s.state === 'RUNNING') return 1; // printing without ETA
            return 2; // idle
          };

          const ta = tier(statusA);
          const tb = tier(statusB);
          if (ta !== tb) return ta - tb;
          if (ta === 0) {
            const diff = (statusA!.remaining_time ?? 0) - (statusB!.remaining_time ?? 0);
            if (diff !== 0) return diff;
          }
          return a.name.localeCompare(b.name);
        });
        break;
    }

    // Apply ascending/descending
    if (!sortAsc) {
      sorted.reverse();
    }

    return sorted;
  }, [filteredPrinters, sortBy, sortAsc, queryClient]);

  const selectAll = useCallback(() => {
    setSelectedPrinterIds(new Set(sortedPrinters.map(p => p.id)));
    setIsSelectionMode(true);
  }, [sortedPrinters]);

  const selectByState = useCallback((state: PrinterState) => {
    setSelectedPrinterIds(prev => {
      const next = new Set(prev);
      sortedPrinters.forEach(p => {
        const status = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', p.id]);
        if (classifyPrinterStatus(status) === state) next.add(p.id);
      });
      return next;
    });
    setIsSelectionMode(true);
  }, [sortedPrinters, queryClient]);

  const selectByLocation = useCallback((location: string) => {
    setSelectedPrinterIds(prev => {
      const next = new Set(prev);
      sortedPrinters.filter(p => (p.location || '') === location).forEach(p => next.add(p.id));
      return next;
    });
    setIsSelectionMode(true);
  }, [sortedPrinters]);

  const selectByModel = useCallback((model: string) => {
    setSelectedPrinterIds(prev => {
      const next = new Set(prev);
      sortedPrinters.filter(p => (p.model || 'Unknown') === model).forEach(p => next.add(p.id));
      return next;
    });
    setIsSelectionMode(true);
  }, [sortedPrinters]);

  const toggleSectionCollapse = useCallback((key: string) => {
    setCollapsedSections(prev => {
      const next = { ...prev, [key]: !prev[key] };
      try { localStorage.setItem('printerCollapsedSections', JSON.stringify(next)); } catch { /* quota exceeded / private mode */ }
      return next;
    });
  }, []);

  // Group printers when sorted by location, status, or model
  const groupedPrinters = useMemo(() => {
    if (sortBy === 'name' || sortBy === 'eta') return null;

    const groups: Record<string, typeof sortedPrinters> = {};

    if (sortBy === 'location') {
      sortedPrinters.forEach(printer => {
        const location = printer.location || 'Ungrouped';
        if (!groups[location]) groups[location] = [];
        groups[location].push(printer);
      });
    } else if (sortBy === 'model') {
      sortedPrinters.forEach(printer => {
        const model = printer.model || 'Unknown';
        if (!groups[model]) groups[model] = [];
        groups[model].push(printer);
      });
    } else if (sortBy === 'status') {
      sortedPrinters.forEach(printer => {
        const status = queryClient.getQueryData<{ connected: boolean; state: string | null; hms_errors?: HMSError[] }>(['printerStatus', printer.id]);
        const group = classifyPrinterStatus(status);
        if (!groups[group]) groups[group] = [];
        groups[group].push(printer);
      });
    }

    return groups;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- classifyPrinterStatus & filterKnownHMSErrors are stable module-level functions, not reactive deps; statusCacheVersion forces recompute on WebSocket status updates
  }, [sortBy, sortedPrinters, queryClient, statusCacheVersion]);

  const toolbarRef = useRef<HTMLDivElement>(null);
  const expandedToolbarControlsRef = useRef<HTMLDivElement>(null);
  const expandedToolbarWidthRef = useRef(0);
  const [compactToolbar, setCompactToolbar] = useState(false);

  const measureToolbar = useCallback(() => {
    const toolbar = toolbarRef.current;
    if (!toolbar) return;

    const measuredControlsWidth = expandedToolbarControlsRef.current?.offsetWidth;
    if (measuredControlsWidth) {
      expandedToolbarWidthRef.current = measuredControlsWidth;
    }

    const searchMinimumWidth = 220;
    const gapWidth = 8;
    const shouldCompact = expandedToolbarWidthRef.current > 0 && toolbar.clientWidth < expandedToolbarWidthRef.current + searchMinimumWidth + gapWidth;
    setCompactToolbar(prev => (prev === shouldCompact ? prev : shouldCompact));
  }, []);

  const smartPlugCount = Object.keys(smartPlugByPrinter).length;
  useLayoutEffect(() => {
    measureToolbar();

    const toolbar = toolbarRef.current;
    if (!toolbar) return;

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measureToolbar);
      return () => window.removeEventListener('resize', measureToolbar);
    }

    const resizeObserver = new ResizeObserver(() => measureToolbar());
    resizeObserver.observe(toolbar);
    window.addEventListener('resize', measureToolbar);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('resize', measureToolbar);
    };
  }, [
    measureToolbar,
    printers?.length,
    availableLocations.length,
    hideDisconnected,
    smartPlugCount,
  ]);

  const renderFilterControls = (inMenu = false) => (
    <>
      {/* Status filter */}
      {printers && printers.length > 0 && (
        <ToolbarDropdown
          value={statusFilter}
          onChange={setStatusFilter}
          fullWidth={inMenu}
          options={[
            { value: 'all', label: t('printers.filter.allStatuses') },
            { value: 'printing', label: t('printers.status.printing') },
            { value: 'paused', label: t('printers.status.paused') },
            { value: 'idle', label: t('printers.status.idle') },
            { value: 'finished', label: t('printers.status.finished') },
            { value: 'error', label: t('printers.status.error') },
            { value: 'offline', label: t('printers.status.offline') },
          ]}
        />
      )}

      {/* Location filter — only shown when at least one printer has a location */}
      {printers && printers.length > 0 && availableLocations.length > 0 && (
        <ToolbarDropdown
          value={locationFilter}
          onChange={setLocationFilter}
          fullWidth={inMenu}
          options={[
            { value: 'all', label: t('printers.filter.allLocations') },
            ...availableLocations.map(loc => ({ value: loc, label: loc })),
          ]}
        />
      )}

      <button
        type="button"
        onClick={toggleHideDisconnected}
        aria-pressed={hideDisconnected}
        className={`h-8 px-2 rounded-lg border text-sm font-medium transition-colors ${inMenu ? 'w-full' : ''} ${
          hideDisconnected
            ? 'bg-bambu-green border-bambu-green text-white'
            : 'bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary'
        }`}
      >
        {t('printers.hideOffline')}
      </button>
    </>
  );

  const renderViewControls = (inMenu = false) => (
    <>
      {/* Sort dropdown */}
      <div className={`flex items-center gap-1 ${inMenu ? 'w-full' : ''}`}>
        <ToolbarDropdown<SortOption>
          value={sortBy}
          onChange={handleSortChange}
          fullWidth={inMenu}
          options={[
            { value: 'name', label: t('printers.sort.name') },
            { value: 'status', label: t('printers.sort.status') },
            { value: 'model', label: t('printers.sort.model') },
            { value: 'location', label: t('printers.sort.location') },
            { value: 'eta', label: t('printers.sort.eta') },
          ]}
        />
        <button
          onClick={toggleSortDirection}
          className="h-8 shrink-0 px-2 rounded-lg border bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary transition-colors flex items-center justify-center"
          title={sortAsc ? t('printers.sort.descending') : t('printers.sort.ascending')}
        >
          {sortAsc ? (
            <ArrowUp className="w-4 h-4 text-white" />
          ) : (
            <ArrowDown className="w-4 h-4 text-white" />
          )}
        </button>
      </div>

      {/* Page view toggle: Cards / Cam Wall */}
      <div className={`flex h-8 items-center bg-bambu-dark rounded-lg border border-bambu-dark-tertiary ${inMenu ? 'w-full' : ''}`}>
        <button
          type="button"
          onClick={() => {
            setPageView('cards');
            localStorage.setItem('printerPageView', 'cards');
          }}
          className={`flex h-full items-center gap-1 rounded-l-lg px-2 text-xs font-medium transition-colors ${inMenu ? 'flex-1 justify-center' : ''} ${
            pageView === 'cards' ? 'bg-bambu-green text-white' : 'text-white hover:bg-bambu-dark-tertiary'
          }`}
          title={t('printers.pageView.cards')}
          aria-pressed={pageView === 'cards'}
        >
          <LayoutGrid className="w-3.5 h-3.5" />
          {inMenu && <span>{t('printers.pageView.cards')}</span>}
        </button>
        <button
          type="button"
          onClick={() => {
            setPageView('camwall');
            localStorage.setItem('printerPageView', 'camwall');
          }}
          className={`flex h-full items-center gap-1 rounded-r-lg px-2 text-xs font-medium transition-colors ${inMenu ? 'flex-1 justify-center' : ''} ${
            pageView === 'camwall' ? 'bg-bambu-green text-white' : 'text-white hover:bg-bambu-dark-tertiary'
          }`}
          title={t('printers.pageView.camWall')}
          aria-pressed={pageView === 'camwall'}
          disabled={!hasPermission('camera:view')}
        >
          <MonitorPlay className="w-3.5 h-3.5" />
          {inMenu && <span>{t('printers.pageView.camWall')}</span>}
        </button>
      </div>

      {/* Card size selector */}
      <div className={`flex h-8 items-center bg-bambu-dark rounded-lg border border-bambu-dark-tertiary ${pageView === 'camwall' ? 'opacity-40 pointer-events-none' : ''} ${inMenu ? 'w-full' : ''}`}>
        {cardSizeLabels.map((label, index) => {
          const size = index + 1;
          const isSelected = cardSize === size;
          return (
            <button
              key={label}
              onClick={() => {
                setCompactDrilldownPrinterId(null);
                setCardSize(size);
                localStorage.setItem('printerCardSize', String(size));
              }}
              className={`h-full px-2 text-xs font-medium transition-colors ${inMenu ? 'flex-1' : ''} ${
                index === 0 ? 'rounded-l-lg' : ''
              } ${
                index === cardSizeLabels.length - 1 ? 'rounded-r-lg' : ''
              } ${
                isSelected
                  ? 'bg-bambu-green text-white'
                  : 'text-white hover:bg-bambu-dark-tertiary'
              }`}
              title={label === 'S' ? t('printers.cardSize.small') : label === 'M' ? t('printers.cardSize.medium') : label === 'L' ? t('printers.cardSize.large') : t('printers.cardSize.extraLarge')}
            >
              {label}
            </button>
          );
        })}
      </div>
    </>
  );

  const renderActionControls = (inMenu = false) => (
    <>
      {/* Bulk select toggle */}
      <button
        onClick={() => {
          if (selectionMode) clearSelection();
          else setIsSelectionMode(true);
        }}
        className={`h-8 px-2 rounded-lg border transition-colors ${inMenu ? 'w-full justify-center gap-1.5 text-sm font-medium flex items-center' : ''} ${
          selectionMode
            ? 'bg-bambu-green border-bambu-green text-white'
            : 'bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary'
        }`}
        title={t('printers.bulk.select')}
        disabled={!hasPermission('printers:control')}
      >
        <CheckSquare className="w-4 h-4" />
        {inMenu && <span>{t('printers.bulk.select')}</span>}
      </button>

      {/* Power dropdown for offline printers with smart plugs */}
      {hideDisconnected && Object.keys(smartPlugByPrinter).length > 0 && (
        <div className={`relative ${inMenu ? 'w-full' : ''}`}>
          <button
            onClick={() => setShowPowerDropdown(!showPowerDropdown)}
            className={`h-8 flex items-center gap-1.5 px-2 text-sm rounded-lg border transition-colors ${
              inMenu
                ? 'w-full justify-between bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary hover:text-white'
                : 'bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <Power className="w-4 h-4" />
              {t('printers.powerOn')}
            </span>
            <ChevronDown className={`w-3 h-3 transition-transform ${showPowerDropdown ? 'rotate-180' : ''}`} />
          </button>
          {showPowerDropdown && (
            <>
              {/* Backdrop to close dropdown */}
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowPowerDropdown(false)}
              />
              <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-bambu-dark-secondary border border-gray-200 dark:border-bambu-dark-tertiary rounded-lg shadow-lg z-20 py-1">
                <div className="px-3 py-2 text-xs text-gray-500 dark:text-bambu-gray border-b border-gray-200 dark:border-bambu-dark-tertiary">
                  {t('printers.offlinePrintersWithPlugs')}
                </div>
                {printers?.filter(p => smartPlugByPrinter[p.id]).map(printer => (
                  <PowerDropdownItem
                    key={printer.id}
                    printer={printer}
                    plug={smartPlugByPrinter[printer.id]}
                    onPowerOn={(plugId) => {
                      setPoweringOn(plugId);
                      powerOnMutation.mutate(plugId);
                    }}
                    isPowering={poweringOn === smartPlugByPrinter[printer.id]?.id}
                  />
                ))}
                {printers?.filter(p => smartPlugByPrinter[p.id]).length === 0 && (
                  <div className="px-3 py-2 text-sm text-bambu-gray">
                    No printers with smart plugs
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
      <Button
        onClick={() => setShowAddModal(true)}
        disabled={!hasPermission('printers:create')}
        title={!hasPermission('printers:create') ? t('printers.permission.noAdd') : undefined}
        className={`!h-8 !min-h-8 px-2 py-0 ${inMenu ? 'w-full' : ''}`}
      >
        <Plus className="w-4 h-4" />
        {t('printers.addPrinter')}
      </Button>
    </>
  );

  return (
    <div className="p-4 md:p-8">
      <div className="space-y-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <PrinterIcon className="w-7 h-7 text-bambu-green" />
            {t('printers.title')}
          </h1>
          <StatusSummaryBar printers={printers} />
        </div>
        <div ref={toolbarRef} className="relative flex items-center gap-2">
          {/* Only show search bar when printers exist */}
          {printers && printers.length > 0 && (
            <div className="relative min-w-0 flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-bambu-gray/50" />
              <TextField
                type="search"
                name="printer-search"
                autoComplete="off"
                data-1p-ignore
                data-lpignore="true"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('printers.search')}
                aria-label={t('printers.search')}
                className="w-full h-8 pl-9 pr-8 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm placeholder:text-bambu-gray/50 focus:outline-none focus:border-bambu-green"
              />
              {search && (
                <button
                  type="button"
                  aria-label={t('common.clear')}
                  onClick={() => setSearch('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-bambu-gray hover:text-white"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          )}
          <div
            ref={expandedToolbarControlsRef}
            aria-hidden={compactToolbar}
            inert={compactToolbar}
            className={`${compactToolbar ? 'absolute -left-[9999px] top-0 flex w-max pointer-events-none opacity-0' : 'flex'} ml-auto items-center justify-end gap-2 flex-nowrap [&>*]:shrink-0`}
          >
            <div className="h-6 w-px bg-bambu-dark-tertiary" />
            <div className="flex items-center gap-2">{renderFilterControls()}</div>
            <div className="h-6 w-px bg-bambu-dark-tertiary" />
            <div className="flex items-center gap-2">{renderViewControls()}</div>
            <div className="h-6 w-px bg-bambu-dark-tertiary" />
            <div className="flex items-center gap-2">{renderActionControls()}</div>
          </div>

          {compactToolbar && (
            <div className="ml-auto flex items-center justify-end gap-1">
              <ToolbarMenu label={t('printers.toolbar.filters', 'Filters')} icon={<Filter className="w-4 h-4" />}>
                <div className="flex w-48 flex-col gap-2">{renderFilterControls(true)}</div>
              </ToolbarMenu>
              <ToolbarMenu label={t('printers.toolbar.view', 'View')} icon={<SlidersHorizontal className="w-4 h-4" />}>
                <div className="flex w-48 flex-col gap-2">{renderViewControls(true)}</div>
              </ToolbarMenu>
              <ToolbarMenu label={t('printers.toolbar.actions', 'Actions')} icon={<MoreHorizontal className="w-4 h-4" />}>
                <div className="flex w-48 flex-col gap-2">{renderActionControls(true)}</div>
              </ToolbarMenu>
            </div>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-bambu-gray">{t('common.loading')}</div>
      ) : printers?.length === 0 ? (
        <Card>
          <CardContent className="text-center py-12">
            <p className="text-bambu-gray mb-4">{t('printers.noPrintersConfigured')}</p>
            <Button
              onClick={() => setShowAddModal(true)}
              disabled={!hasPermission('printers:create')}
              title={!hasPermission('printers:create') ? t('printers.permission.noAdd') : undefined}
            >
              <Plus className="w-4 h-4" />
              {t('printers.addPrinter')}
            </Button>
          </CardContent>
        </Card>
      ) : sortedPrinters.length === 0 && (search.trim() || statusFilter !== 'all' || locationFilter !== 'all') ? (
        <Card>
          <CardContent className="text-center py-12">
            <p className="text-bambu-gray">{t('printers.noSearchResults')}</p>
          </CardContent>
        </Card>
      ) : pageView === 'camwall' ? (
        <CameraWall
          printers={sortedPrinters}
          maxLive={camWallMaxLive}
          snapshotIntervalSec={camWallSnapshotSec}
          onTileClick={(id, name) => {
            const cameraMode = settings?.camera_view_mode || 'window';
            if (cameraMode === 'embedded') {
              setEmbeddedCameraPrinters(prev => new Map(prev).set(id, { id, name }));
            } else {
              const saved = localStorage.getItem('cameraWindowState');
              const state = saved ? JSON.parse(saved) : { width: 640, height: 400 };
              const features = [
                `width=${state.width}`,
                `height=${state.height}`,
                state.left !== undefined ? `left=${state.left}` : '',
                state.top !== undefined ? `top=${state.top}` : '',
                'menubar=no,toolbar=no,location=no,status=no',
              ].filter(Boolean).join(',');
              window.open(`/camera/${id}`, `camera-${id}`, features);
            }
          }}
          statusMode={camWallStatusMode}
          onChangeMaxLive={(next) => {
            setCamWallMaxLive(next);
            localStorage.setItem('camWallMaxLive', String(next));
          }}
          onChangeSnapshotIntervalSec={(next) => {
            setCamWallSnapshotSec(next);
            localStorage.setItem('camWallSnapshotSec', String(next));
          }}
          onChangeStatusMode={(next) => {
            setCamWallStatusMode(next);
            localStorage.setItem('camWallStatusMode', next);
          }}
        />
      ) : groupedPrinters ? (
        /* Grouped view (location, status, or model) */
        <div className="space-y-6">
          {(() => {
            const keys = sortBy === 'status'
              ? STATUS_GROUP_ORDER.filter(k => groupedPrinters[k]?.length > 0)
              : Object.keys(groupedPrinters);
            // For status grouping, asc/desc flips the fixed priority order
            // (asc = error→offline, desc = offline→error). This matches the
            // sort-toggle behaviour for other groupings.
            return (sortAsc ? keys : [...keys].reverse());
          })().map((groupKey) => {
            const groupPrinters = groupedPrinters[groupKey];
            const collapseKey = `${sortBy}:${groupKey}`;
            const isOpen = !collapsedSections[collapseKey];

            const dot = sortBy === 'status'
              ? STATUS_GROUP_META[groupKey]?.dot || 'bg-bambu-green'
              : 'bg-bambu-green';
            const label = sortBy === 'status'
              ? t(STATUS_GROUP_META[groupKey]?.labelKey || groupKey)
              : groupKey;

            return (
              <Collapsible
                key={groupKey}
                open={isOpen}
                onToggle={() => toggleSectionCollapse(collapseKey)}
                summaryClassName="py-1"
                summary={
                  <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${dot}`} />
                    {label}
                    <span className="text-sm font-normal text-bambu-gray">({groupPrinters.length})</span>
                    {selectionMode && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (sortBy === 'location') selectByLocation(groupKey === 'Ungrouped' ? '' : groupKey);
                          else if (sortBy === 'status') selectByState(groupKey as PrinterState);
                          else if (sortBy === 'model') selectByModel(groupKey);
                        }}
                        className="text-xs text-bambu-green hover:text-bambu-green-light transition-colors ml-1"
                      >
                        {t('printers.bulk.selectAll')}
                      </button>
                    )}
                  </h2>
                }
              >
                <div className={`grid gap-4 ${cardSize >= 3 ? 'gap-6' : ''} ${getGridClasses()}`}>
                  {groupPrinters.map((printer) => (
                    <PrinterCard
                      key={printer.id}
                      printer={printer}
                      hideIfDisconnected={hideDisconnected}
                      maintenanceInfo={maintenanceByPrinter[printer.id]}
                      viewMode={viewMode}
                      cardSize={cardSize}
                      amsThresholds={settings ? {
                        humidityGood: Number(settings.ams_humidity_good) || 40,
                        humidityFair: Number(settings.ams_humidity_fair) || 60,
                        tempGood: Number(settings.ams_temp_good) || 28,
                        tempFair: Number(settings.ams_temp_fair) || 35,
                      } : undefined}
                      spoolmanEnabled={spoolmanEnabled}
                      hasUnlinkedSpools={hasUnlinkedSpools}
                      linkedSpools={linkedSpools}
                      spoolmanUrl={spoolmanStatus?.url}
                      spoolmanSyncMode={spoolmanSyncMode}
                      onGetAssignment={getAssignment}
                      onUnassignSpool={(pid, aid, tid) => unassignMutation.mutate({ printerId: pid, amsId: aid, trayId: tid })}
                      spoolmanSpools={spoolmanSpools}
                      spoolmanSlotAssignments={spoolmanSlotAssignments}
                      spoolmanLoading={spoolmanSpoolsLoading || spoolmanAssignmentsLoading}
                      onUnassignSpoolmanSpool={(id) => unassignSpoolmanMutation.mutate(id)}
                      timeFormat={settings?.time_format || 'system'}
                      cameraViewMode={settings?.camera_view_mode || 'window'}
                      onOpenEmbeddedCamera={(id, name) => setEmbeddedCameraPrinters(prev => new Map(prev).set(id, { id, name }))}
                      checkPrinterFirmware={settings?.check_printer_firmware !== false}
                      dryingPresets={effectiveDryingPresets}
                      nozzleTempPresets={effectiveNozzleTempPresets}
                      bedTempPresets={effectiveBedTempPresets}
                      chamberTempPresets={effectiveChamberTempPresets}
                      fanSpeedPresets={effectiveFanSpeedPresets}
                      requirePlateClear={settings?.require_plate_clear === true}
                      selectionMode={selectionMode}
                      isSelected={selectedPrinterIds.has(printer.id)}
                      onToggleSelect={toggleSelect}
                      onOpenCompactCard={openCompactCard}
                    />
                  ))}
                </div>
              </Collapsible>
            );
          })}
        </div>
      ) : (
        /* Regular grid view */
        <div className={`grid gap-4 ${cardSize >= 3 ? 'gap-6' : ''} ${getGridClasses()}`}>
          {sortedPrinters.map((printer) => (
            <PrinterCard
              key={printer.id}
              printer={printer}
              hideIfDisconnected={hideDisconnected}
              maintenanceInfo={maintenanceByPrinter[printer.id]}
              viewMode={viewMode}
              cardSize={cardSize}
              spoolmanEnabled={spoolmanEnabled}
              hasUnlinkedSpools={hasUnlinkedSpools}
              linkedSpools={linkedSpools}
              spoolmanUrl={spoolmanStatus?.url}
              spoolmanSyncMode={spoolmanSyncMode}
              onGetAssignment={getAssignment}
              onUnassignSpool={(pid, aid, tid) => unassignMutation.mutate({ printerId: pid, amsId: aid, trayId: tid })}
              spoolmanSpools={spoolmanSpools}
              spoolmanSlotAssignments={spoolmanSlotAssignments}
              spoolmanLoading={spoolmanSpoolsLoading || spoolmanAssignmentsLoading}
              onUnassignSpoolmanSpool={(id) => unassignSpoolmanMutation.mutate(id)}
              amsThresholds={settings ? {
                humidityGood: Number(settings.ams_humidity_good) || 40,
                humidityFair: Number(settings.ams_humidity_fair) || 60,
                tempGood: Number(settings.ams_temp_good) || 28,
                tempFair: Number(settings.ams_temp_fair) || 35,
              } : undefined}
              timeFormat={settings?.time_format || 'system'}
              cameraViewMode={settings?.camera_view_mode || 'window'}
              onOpenEmbeddedCamera={(id, name) => setEmbeddedCameraPrinters(prev => new Map(prev).set(id, { id, name }))}
              checkPrinterFirmware={settings?.check_printer_firmware !== false}
              dryingPresets={effectiveDryingPresets}
              nozzleTempPresets={effectiveNozzleTempPresets}
              bedTempPresets={effectiveBedTempPresets}
              chamberTempPresets={effectiveChamberTempPresets}
              fanSpeedPresets={effectiveFanSpeedPresets}
              requirePlateClear={settings?.require_plate_clear === true}
              selectionMode={selectionMode}
              isSelected={selectedPrinterIds.has(printer.id)}
              onToggleSelect={toggleSelect}
              onOpenCompactCard={openCompactCard}
            />
          ))}
        </div>
      )}

      {cardSize === 2 && compactDrilldownPrinterId != null && (
        <button
          type="button"
          onClick={returnToCompactCards}
          className={`fixed bottom-5 left-1/2 z-40 inline-flex -translate-x-1/2 items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium shadow-xl transition-colors ${accentButtonClass}`}
          title={t('common.back', 'Back')}
        >
          <ArrowLeft className="w-4 h-4" />
          {t('common.back', 'Back')}
        </button>
      )}

      {showAddModal && (
        <AddPrinterModal
          onClose={() => setShowAddModal(false)}
          onAdd={(data) => addMutation.mutate(data)}
          existingSerials={printers?.map(p => p.serial_number) || []}
        />
      )}

      {/* Bulk selection toolbar */}
      {selectionMode && printers && (
        <BulkPrinterToolbar
          selectedIds={selectedPrinterIds}
          printers={printers}
          onClose={clearSelection}
          onSelectAll={selectAll}
          onSelectByLocation={selectByLocation}
          onSelectByState={selectByState}
          onAction={handleBulkAction}
          actionPending={bulkActionPending}
        />
      )}

      {/* Bulk action confirmation modals */}
      {bulkConfirmAction === 'stop' && (
        <ConfirmModal
          title={t('printers.bulk.confirm.stopTitle', { count: selectedPrinterIds.size })}
          message={t('printers.bulk.confirm.stopMessage', { count: selectedPrinterIds.size })}
          confirmText={t('printers.bulk.confirm.stopButton')}
          variant="danger"
          isLoading={bulkActionPending}
          onConfirm={() => executeBulkAction('stop')}
          onCancel={() => setBulkConfirmAction(null)}
        />
      )}
      {bulkConfirmAction === 'pause' && (
        <ConfirmModal
          title={t('printers.bulk.confirm.pauseTitle', { count: selectedPrinterIds.size })}
          message={t('printers.bulk.confirm.pauseMessage', { count: selectedPrinterIds.size })}
          confirmText={t('printers.bulk.confirm.pauseButton')}
          isLoading={bulkActionPending}
          onConfirm={() => executeBulkAction('pause')}
          onCancel={() => setBulkConfirmAction(null)}
        />
      )}
      {bulkConfirmAction === 'clearPlate' && (
        <ConfirmModal
          title={t('printers.bulk.confirm.clearPlateTitle', { count: selectedPrinterIds.size })}
          message={t('printers.bulk.confirm.clearPlateMessage', { count: selectedPrinterIds.size })}
          confirmText={t('printers.bulk.confirm.clearPlateButton')}
          isLoading={bulkActionPending}
          onConfirm={() => executeBulkAction('clearPlate')}
          onCancel={() => setBulkConfirmAction(null)}
        />
      )}

      {/* Embedded Camera Viewers - multiple viewers can be open simultaneously */}
      {Array.from(embeddedCameraPrinters.values()).map((camera, index) => (
        <EmbeddedCameraViewer
          key={camera.id}
          printerId={camera.id}
          printerName={camera.name}
          viewerIndex={index}
          onClose={() => setEmbeddedCameraPrinters(prev => {
            const next = new Map(prev);
            next.delete(camera.id);
            return next;
          })}
        />
      ))}
    </div>
  );
}
