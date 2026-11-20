import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, AlertTriangle, Loader2, Pencil, Printer, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PrinterStatus, PrintQueueItemCreate, PrintQueueItemUpdate, SlotMaterial } from '../../api/client';
import { api } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import { Card, CardContent } from '../Card';
import { Button } from '../Button';
import { ConfirmModal } from '../ConfirmModal';
import { NumberField } from '../ui';
import { useToast } from '../../contexts/ToastContext';
import { buildLoadedFilaments, useFilamentMapping } from '../../hooks/useFilamentMapping';
import { useMultiPrinterFilamentMapping, type PerPrinterConfig } from '../../hooks/useMultiPrinterFilamentMapping';
import { useDisplayCurrency } from '../../hooks/useDisplayCurrency';
import { getBedTypeInfo } from '../../utils/bedType';
import { toDateTimeLocalValue, parseUTCDate } from '../../utils/date';
import { isPlaceholderDate, effectivePreferLowest, filamentTypesCompatible } from '../../utils/amsHelpers';
import { FilamentMapping } from './FilamentMapping';
import { FilamentOverride } from './FilamentOverride';
import { useFilamentPresetNames } from './useFilamentLabels';
import { buildQueuedFilamentOverrides, fixedPrinterFilamentOverrides } from './filamentOverrides';
import type { FilamentOverrideChoice } from './types';
import { PlateSelector } from './PlateSelector';
import { SelectedPlatesSummary } from './SelectedPlatesSummary';
import { PrinterSelector } from './PrinterSelector';
import { PrintOptionsPanel } from './PrintOptions';
import { ScheduleOptionsPanel } from './ScheduleOptions';
import { VariantCandidates, type VariantCandidate } from './VariantCandidates';
import { MultiFileModeToggle } from './MultiFileModeToggle';
import {
  commonModel,
  defaultMultiFileMode,
  duplicateModel,
  filesIncompatibleWith,
  filesNotSlicedFor,
  type MultiFileMode,
} from './multiFile';
import { fileHasQueuedPair, queueSeparateJobs, runAsapTail } from './separateJobs';
import type {
  AssignmentMode,
  PrintModalProps,
  PrintOptions,
  ScheduleOptions,
  ScheduleType,
} from './types';
import { DEFAULT_PRINT_OPTIONS, DEFAULT_SCHEDULE_OPTIONS } from './types';
import { computeFilamentWarnings } from './filamentWarnings';

/**
 * Unified PrintModal component that handles queue item creation and editing.
 * - 'create': Create a print queue item from an archive or library file
 * - 'edit-queue-item': Edit existing queue item
 *
 * Both archiveId and libraryFileId are supported. Library files are archived at
 * print start time by the scheduler, not when queued.
 */
export function PrintModal({
  mode,
  archiveId,
  libraryFileId,
  archiveName,
  queueItem,
  initialSelectedPrinterIds,
  preselectPlateId,
  onClose,
  onSuccess,
  projectId,
  cleanupLibraryAfterDispatch,
  variantFiles,
  separateJobsAllowed,
  resumeSeparateJobs,
  onSeparateJobsProgress,
}: PrintModalProps) {
  const { t: translateInterface } = useTranslation();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { hasPermission } = useAuth();

  // Determine if we're printing a library file
  const isLibraryFile = !!libraryFileId && !archiveId;
  const isEditing = mode === 'edit-queue-item';

  // The rest of a separate-jobs run closed after a refusal (#3471 review).
  const resumed = mode === 'create' && !!separateJobsAllowed && !!resumeSeparateJobs && (variantFiles?.length ?? 0) > 0;
  // What that run was submitted with: the reopened dialog starts from it, so
  // a quick Print finishes the run the way it began (#3471 review).
  const resumedSettings = resumed ? resumeSeparateJobs!.settings : undefined;
  // Several sliced files at once. One file is not a choice, so a single-entry
  // list behaves exactly like an ordinary print, unless it is the last file of
  // a resumed run: one printer may already have it, and only the separate-jobs
  // path knows to skip that pair.
  const isMultiFile = mode === 'create' && ((variantFiles?.length ?? 0) > 1 || resumed);
  // What those files become (#3462): one job with a candidate per file (#671),
  // or one queue item per file. Only a selection made in the File Manager may
  // be split into separate jobs; a version group is the same job sliced for
  // different printers, so without `separateJobsAllowed` it stays alternatives
  // and the dialog behaves exactly as before.
  const [multiFileMode, setMultiFileMode] = useState<MultiFileMode>(() =>
    resumed ? 'separate' : separateJobsAllowed && isMultiFile ? defaultMultiFileMode(variantFiles!) : 'alternatives',
  );
  // Cross-model alternatives (#671).
  const isCrossModel = isMultiFile && multiFileMode === 'alternatives';
  const isSeparateJobs = isMultiFile && multiFileMode === 'separate';
  // Set once separate jobs were partly queued and the rest is still listed.
  // The rest is the remainder of those jobs, so the mode is no longer offered:
  // as alternatives it could be a job of one candidate, or one whose filament
  // panel describes a file that has already been queued and left the list.
  const [partlyQueued, setPartlyQueued] = useState(resumed);
  // File and printer pairs earlier submits of a partly queued run got into the
  // queue. The next submit skips them, so a file one printer took and another
  // refused is not queued on the first printer again.
  const [queuedPairs, setQueuedPairs] = useState<ReadonlySet<string>>(
    () => new Set(resumed ? resumeSeparateJobs!.queuedPairs : []),
  );
  // ASAP positions the run has taken so far. The backend moves everything at
  // or below an inserted position down, so a second submit that restarted at 1
  // would put the rest ahead of what is already queued.
  const [asapPositionsTaken, setAsapPositionsTaken] = useState(resumed ? resumeSeparateJobs!.asapInserted : 0);
  // The run's own queue items and batches, to find where its ASAP items end
  // in the queue as it is at the next submit.
  const [runItemIds, setRunItemIds] = useState<number[]>(() => (resumed ? resumeSeparateJobs!.queuedItemIds ?? [] : []));
  const [runBatchIds, setRunBatchIds] = useState<number[]>(() => (resumed ? resumeSeparateJobs!.queuedBatchIds ?? [] : []));
  const showModeToggle = isMultiFile && !!separateJobsAllowed && !partlyQueued;
  // Editing an already-queued cross-model item. The candidates are shown so the
  // dialog doesn't misrepresent the job as a plain "Any H2D" — which is what it
  // did before, offering a printer picker whose Save would have left a row with
  // both variants and a printer_id. They are not editable here: changing the
  // set after queueing needs a variant-level API that doesn't exist, and the
  // backend refuses the printer/model change either way.
  const editingVariants: VariantCandidate[] =
    mode === 'edit-queue-item' && (queueItem?.variants?.length ?? 0) > 1
      ? queueItem!.variants!.map((v) => ({
          id: v.library_file_id,
          filename: v.filename,
          sliced_for_model: v.target_model,
        }))
      : [];
  const hasEditingVariants = editingVariants.length > 0;
  const [candidates, setCandidates] = useState<VariantCandidate[]>(variantFiles ?? []);
  const [candidatePlates, setCandidatePlates] = useState<Record<number, number | null>>(
    () => resumedSettings?.plateByFile ?? {},
  );
  // Whether every listed file's plates are known and chosen (#3471 review).
  // Before that a quick Print would send plate_id null: the whole file's time
  // and cost, and plate 1 printing.
  const [candidatePlatesReady, setCandidatePlatesReady] = useState(false);

  type FilamentWarningItem = {
    printerId: number;
    printerName: string;
    slotLabel: string;
    requiredGrams: number;
    remainingGrams: number;
    pooled: boolean;
  };

  // Multiple printer selection (used for all modes now)
  const [selectedPrinters, setSelectedPrinters] = useState<number[]>(() => {
    // Initialize with the queue item's printer if editing
    if (mode === 'edit-queue-item' && queueItem?.printer_id) {
      return [queueItem.printer_id];
    }
    if (initialSelectedPrinterIds?.length) {
      return initialSelectedPrinterIds;
    }
    if (resumedSettings) return resumedSettings.printerIds;
    return [];
  });

  // Multi-select plates: create mode users can pick a subset of plates
  const [selectedPlates, setSelectedPlates] = useState<Set<number>>(() => {
    if (mode === 'edit-queue-item' && queueItem?.plate_id != null) {
      return new Set([queueItem.plate_id]);
    }
    // Several files choose their plates in the candidate list, in either mode.
    if (mode === 'create' && !isMultiFile && preselectPlateId != null) {
      return new Set([preselectPlateId]);
    }
    return new Set();
  });

  // Derived single-plate value for filament queries and single-select contexts
  const selectedPlate = selectedPlates.size === 1 ? [...selectedPlates][0] : null;

  // Quantity — number of copies (creates a batch if > 1)
  const [quantity, setQuantity] = useState(() => resumedSettings?.quantity ?? 1);

  // Per-plate quantities for multi-plate files (#342). Keyed by plate index;
  // a plate with no entry means one run. Only used in create mode on a
  // multi-plate file, where it replaces the single global Quantity field.
  const [plateQuantities, setPlateQuantities] = useState<Record<number, number>>({});

  const [printOptions, setPrintOptions] = useState<PrintOptions>(() => {
    if (mode === 'edit-queue-item' && queueItem) {
      return {
        bed_levelling: queueItem.bed_levelling ?? DEFAULT_PRINT_OPTIONS.bed_levelling,
        flow_cali: queueItem.flow_cali ?? DEFAULT_PRINT_OPTIONS.flow_cali,
        vibration_cali: queueItem.vibration_cali ?? DEFAULT_PRINT_OPTIONS.vibration_cali,
        layer_inspect: queueItem.layer_inspect ?? DEFAULT_PRINT_OPTIONS.layer_inspect,
        timelapse: queueItem.timelapse ?? DEFAULT_PRINT_OPTIONS.timelapse,
        nozzle_offset_cali: queueItem.nozzle_offset_cali ?? DEFAULT_PRINT_OPTIONS.nozzle_offset_cali,
        confirm_outcome: queueItem.confirm_outcome ?? false,
        expected_parts: queueItem.expected_parts ?? null,
        preheat_override: queueItem.preheat_override ?? DEFAULT_PRINT_OPTIONS.preheat_override,
        preheat_chamber_target_override: queueItem.preheat_chamber_target_override ?? DEFAULT_PRINT_OPTIONS.preheat_chamber_target_override,
      };
    }
    return resumedSettings?.printOptions ?? DEFAULT_PRINT_OPTIONS;
  });

  const [scheduleOptions, setScheduleOptions] = useState<ScheduleOptions>(() => {
    if (mode === 'edit-queue-item' && queueItem) {
      let scheduleType: ScheduleType = 'queue';
      if (queueItem.scheduled_time && !isPlaceholderDate(queueItem.scheduled_time)) {
        scheduleType = 'scheduled';
      }

      let scheduledTime = '';
      if (queueItem.scheduled_time && !isPlaceholderDate(queueItem.scheduled_time)) {
        const date = parseUTCDate(queueItem.scheduled_time) ?? new Date();
        // Use toDateTimeLocalValue to convert UTC to local time for datetime-local input
        scheduledTime = toDateTimeLocalValue(date);
      }

      return {
        scheduleType,
        scheduledTime,
        requireManualStart: queueItem.manual_start,
        requirePreviousSuccess: queueItem.require_previous_success,
        autoOffAfter: queueItem.auto_off_after,
        gcodeInjection: queueItem.gcode_injection ?? false,
        staggerEnabled: false,
        staggerGroupSize: DEFAULT_SCHEDULE_OPTIONS.staggerGroupSize,
        staggerIntervalMinutes: DEFAULT_SCHEDULE_OPTIONS.staggerIntervalMinutes,
      };
    }
    return resumedSettings?.scheduleOptions ?? DEFAULT_SCHEDULE_OPTIONS;
  });

  // Manual slot overrides: slot_id (1-indexed) -> globalTrayId (default mapping for single printer or all printers)
  const [manualMappings, setManualMappings] = useState<Record<number, number>>(() => {
    if (mode === 'edit-queue-item' && queueItem?.ams_mapping && Array.isArray(queueItem.ams_mapping)) {
      const mappings: Record<number, number> = {};
      queueItem.ams_mapping.forEach((globalTrayId, idx) => {
        if (globalTrayId !== -1) {
          mappings[idx + 1] = globalTrayId;
        }
      });
      return mappings;
    }
    return {};
  });

  // Tray IDs from the shared panel belong only to the printer edited there.
  const [sharedMappingPrinterId, setSharedMappingPrinterId] = useState<number | null>(() =>
    mode === 'edit-queue-item' ? queueItem?.printer_id ?? null : null,
  );

  // Per-printer override configs (for multi-printer selection)
  const [perPrinterConfigs, setPerPrinterConfigs] = useState<Record<number, PerPrinterConfig>>({});

  // Assignment mode: 'printer' (specific) or 'model' (any of model)
  const [assignmentMode, setAssignmentMode] = useState<AssignmentMode>(() => {
    // Cross-model alternatives are model-based by definition — naming one
    // printer would defeat the point of offering the other file.
    if (isCrossModel) {
      return 'model';
    }
    // Initialize from queue item if editing with target_model
    if (mode === 'edit-queue-item' && queueItem?.target_model) {
      return 'model';
    }
    return resumedSettings?.assignmentMode ?? 'printer';
  });

  // Target model for model-based assignment
  const [targetModel, setTargetModel] = useState<string | null>(() => {
    if (mode === 'edit-queue-item' && queueItem?.target_model) {
      return queueItem.target_model;
    }
    return resumedSettings?.targetModel ?? null;
  });

  // Target location for model-based assignment (optional filter)
  const [targetLocation, setTargetLocation] = useState<string | null>(() => {
    if (mode === 'edit-queue-item' && queueItem?.target_location) {
      return queueItem.target_location;
    }
    return resumedSettings?.targetLocation ?? null;
  });

  // Filament overrides for model-based assignment: slot_id -> {type, color}
  const [filamentOverrides, setFilamentOverrides] = useState<Record<number, FilamentOverrideChoice>>(() => {
    if (mode === 'edit-queue-item' && queueItem?.filament_overrides) {
      const overrides: Record<number, FilamentOverrideChoice> = {};
      for (const o of queueItem.filament_overrides) {
        overrides[o.slot_id] = { type: o.type, color: o.color, tray_info_idx: o.tray_info_idx };
      }
      return overrides;
    }
    return {};
  });

  // Per-slot force color match flags. Default is false (opt-in).
  const [forceColorMatch, setForceColorMatch] = useState<Record<number, boolean>>(() => {
    if (mode === 'edit-queue-item' && queueItem?.filament_overrides) {
      const flags: Record<number, boolean> = {};
      for (const o of queueItem.filament_overrides) {
        flags[o.slot_id] = o.force_color_match === true;
      }
      return flags;
    }
    return {};
  });

  // Track initial values for clearing mappings on change (edit mode only)
  const [initialPrinterIds] = useState(() => (mode === 'edit-queue-item' && queueItem?.printer_id ? [queueItem.printer_id] : []));
  const [initialPlateId] = useState(() => (mode === 'edit-queue-item' && queueItem ? queueItem.plate_id : null));

  // Submission state for multi-printer
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitProgress, setSubmitProgress] = useState({ current: 0, total: 0 });

  const [filamentWarningItems, setFilamentWarningItems] = useState<FilamentWarningItem[] | null>(null);

  // Track which printers have had the "Expand custom mapping by default" setting applied
  // This ensures the setting only affects initial state, not preventing unchecking
  const [initialExpandApplied, setInitialExpandApplied] = useState<Set<number>>(new Set());

  // Printer counts and effective printer for filament mapping
  const effectivePrinterCount = selectedPrinters.length;
  // For filament mapping, use first selected printer (mapping applies to all)
  const effectivePrinterId = selectedPrinters.length > 0 ? selectedPrinters[0] : null;

  // Queries
  const { data: settings } = useQuery({
    queryKey: ['settings', 'ui-flags'],
    queryFn: api.getUiFlags,
  });

  // Sync print option defaults from settings once available
  const printDefaultsApplied = useRef(false);
  useEffect(() => {
    // A resumed run keeps the options it was submitted with.
    if (!settings || printDefaultsApplied.current || mode === 'edit-queue-item' || resumedSettings) return;
    printDefaultsApplied.current = true;
    setPrintOptions((current) => ({
      ...current,
      bed_levelling: settings.default_bed_levelling ?? DEFAULT_PRINT_OPTIONS.bed_levelling,
      flow_cali: settings.default_flow_cali ?? DEFAULT_PRINT_OPTIONS.flow_cali,
      vibration_cali: settings.default_vibration_cali ?? DEFAULT_PRINT_OPTIONS.vibration_cali,
      layer_inspect: settings.default_layer_inspect ?? DEFAULT_PRINT_OPTIONS.layer_inspect,
      timelapse: settings.default_timelapse ?? DEFAULT_PRINT_OPTIONS.timelapse,
      nozzle_offset_cali: settings.default_nozzle_offset_cali ?? DEFAULT_PRINT_OPTIONS.nozzle_offset_cali,
      preheat_override: DEFAULT_PRINT_OPTIONS.preheat_override,
      preheat_chamber_target_override: DEFAULT_PRINT_OPTIONS.preheat_chamber_target_override,
    }));
  }, [settings, mode, resumedSettings]);

  // Sync stagger defaults from settings once available
  const staggerDefaultsApplied = useRef(false);
  useEffect(() => {
    if (!settings || staggerDefaultsApplied.current || mode === 'edit-queue-item' || resumedSettings) return;
    staggerDefaultsApplied.current = true;
    setScheduleOptions((prev) => ({
      ...prev,
      staggerGroupSize: settings.stagger_group_size ?? prev.staggerGroupSize,
      staggerIntervalMinutes: settings.stagger_interval_minutes ?? prev.staggerIntervalMinutes,
    }));
  }, [settings, mode, resumedSettings]);

  const { currencySymbol } = useDisplayCurrency(settings?.currency);
  const defaultCostPerKg = settings?.default_filament_cost ?? 0;
  const filamentPresetNames = useFilamentPresetNames();

  const { data: printers, isLoading: loadingPrinters } = useQuery({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  });

  // Fetch per-printer Map<globalTrayId, gramsRemaining> via the dedicated
  // backend endpoint (#1766). Server-side mirrors `_build_inventory_remain_overrides`
  // so internal and Spoolman modes both work uniformly, VT/external slots are
  // excluded, and negative grams are clamped — single source of truth between
  // the client-side preview and dispatch-time picks.
  const inventoryRemainQueries = useQueries({
    queries: selectedPrinters.map((printerId) => ({
      queryKey: ['printer-inventory-remain', printerId],
      queryFn: () => api.getInventoryRemain(printerId),
      staleTime: 30 * 1000,
      enabled: selectedPrinters.length > 0,
    })),
  });
  const inventoryByTrayIdPerPrinter = useMemo(() => {
    const result = new Map<number, Map<number, number>>();
    selectedPrinters.forEach((printerId, idx) => {
      const data = inventoryRemainQueries[idx]?.data?.inventory_remain_g;
      if (!data) return;
      const printerMap = new Map<number, number>();
      Object.entries(data).forEach(([key, grams]) => {
        const gtid = Number(key);
        if (!Number.isNaN(gtid)) printerMap.set(gtid, grams);
      });
      result.set(printerId, printerMap);
    });
    return result;
  }, [selectedPrinters, inventoryRemainQueries]);

  const slotMaterialsPerPrinter = useMemo(() => {
    const result = new Map<number, SlotMaterial[]>();
    selectedPrinters.forEach((printerId, idx) => {
      const slots = inventoryRemainQueries[idx]?.data?.slot_materials;
      if (slots) result.set(printerId, slots);
    });
    return result;
  }, [selectedPrinters, inventoryRemainQueries]);

  // Fetch archive details to get sliced_for_model
  const { data: archiveDetails, isPending: archiveDetailsPending } = useQuery({
    queryKey: ['archive', archiveId],
    queryFn: () => api.getArchive(archiveId!),
    enabled: !!archiveId && !isLibraryFile,
  });

  // Fetch library file details to get sliced_for_model
  const { data: libraryFileDetails, isPending: libraryDetailsPending } = useQuery({
    queryKey: ['library-file', libraryFileId],
    queryFn: () => api.getLibraryFile(libraryFileId!),
    enabled: isLibraryFile && !!libraryFileId,
  });

  // Get sliced_for_model from archive or library file
  const slicedForModel = archiveDetails?.sliced_for_model || libraryFileDetails?.sliced_for_model || null;
  // The model the printer picker filters on, pre-selects and offers as "Any X".
  // Separate jobs print every listed file, not just the first one the dialog
  // was opened with (which may already be queued and gone from the list after
  // a refusal), so they offer the model all of them share, or none.
  const selectorModel = isSeparateJobs ? commonModel(candidates) : slicedForModel;
  // The model gate (#2578) per file: each separate job runs its own file, and
  // the backend refuses each one sliced for an incompatible model. A file that
  // names no model passes, as a single file does.
  const separateJobsIncompatible = useMemo(
    () => (isSeparateJobs && assignmentMode === 'model' ? filesIncompatibleWith(candidates, targetModel) : []),
    [isSeparateJobs, assignmentMode, candidates, targetModel],
  );

  // Each mode starts from the assignment it is built on, as when the dialog
  // opens in it: the alternatives job is model-based with no printer chosen
  // (#671), separate jobs start at the printer picker. Nothing picked for one
  // mode rides along unseen into the other; the alternatives request always
  // carries target_location, and no control in that mode shows it.
  const handleMultiFileModeChange = (next: MultiFileMode) => {
    if (next === multiFileMode) return;
    // Not while the files are being queued: a refusal mid-run hides the
    // toggle, and the rest would then be queued in a mode nobody chose for it.
    // The toggle is disabled meanwhile; this keeps the mode in step with it.
    if (isSubmitting) return;
    // Two files for one model can't be alternatives; the toggle disables the
    // choice, and this keeps the mode from ever disagreeing with it.
    if (next === 'alternatives' && duplicateModel(candidates) != null) return;
    setMultiFileMode(next);
    setAssignmentMode(next === 'alternatives' ? 'model' : 'printer');
    setTargetModel(null);
    setTargetLocation(null);
    if (next === 'alternatives') setSelectedPrinters([]);
  };



  // Fetch plates for archives
  const { data: archivePlatesData, isError: archivePlatesError } = useQuery({
    queryKey: ['archive-plates', archiveId],
    queryFn: () => api.getArchivePlates(archiveId!),
    enabled: !!archiveId && !isLibraryFile,
    retry: false,
  });

  // Fetch plates for library files
  const { data: libraryPlatesData } = useQuery({
    queryKey: ['library-file-plates', libraryFileId],
    queryFn: () => api.getLibraryFilePlates(libraryFileId!),
    enabled: isLibraryFile && !!libraryFileId,
  });

  // Combine plates data from either source
  const platesData = isLibraryFile ? libraryPlatesData : archivePlatesData;

  // Fetch filament requirements for archives
  const { data: archiveFilamentReqs, isError: archiveFilamentReqsError } = useQuery({
    queryKey: ['archive-filaments', archiveId, selectedPlate],
    queryFn: () => api.getArchiveFilamentRequirements(archiveId!, selectedPlate ?? undefined),
    enabled: !!archiveId && !isLibraryFile && (selectedPlate !== null || !platesData?.is_multi_plate),
    retry: false,
  });

  // Fetch filament requirements for library files (with plate support)
  const { data: libraryFilamentReqs } = useQuery({
    queryKey: ['library-file-filaments', libraryFileId, selectedPlate],
    queryFn: () => api.getLibraryFileFilamentRequirements(libraryFileId!, selectedPlate ?? undefined),
    enabled: isLibraryFile && !!libraryFileId && (selectedPlate !== null || !platesData?.is_multi_plate),
  });

  // Track if archive data couldn't be loaded (archive deleted or file missing)
  const archiveDataMissing = !isLibraryFile && (archivePlatesError || archiveFilamentReqsError);

  // Combine filament requirements from either source
  const effectiveFilamentReqs = isLibraryFile ? libraryFilamentReqs : archiveFilamentReqs;

  // Fetch available filaments for model-based assignment (for filament override UI)
  const { data: availableFilaments } = useQuery({
    queryKey: ['available-filaments', targetModel, targetLocation],
    queryFn: () => api.getAvailableFilaments(targetModel!, targetLocation ?? undefined),
    enabled: assignmentMode === 'model' && !!targetModel,
  });

  // A cross-model job (#671) has no single target model, so the query above is
  // disabled and the override UI would silently vanish — leaving less control
  // than the ordinary "Any X1C" flow offers. Ask each candidate's model instead
  // and offer the union: the job can land on any of them, so anything loaded on
  // any of them is a legitimate choice. Picking one only some models have is
  // allowed and meaningful — it narrows which candidates can match.
  const candidateModels = useMemo(
    () => Array.from(new Set(candidates.map((c) => c.sliced_for_model).filter((m): m is string => !!m))),
    [candidates],
  );
  const candidateFilamentQueries = useQueries({
    queries: isCrossModel
      ? candidateModels.map((model) => ({
          queryKey: ['available-filaments', model, targetLocation],
          queryFn: () => api.getAvailableFilaments(model, targetLocation ?? undefined),
        }))
      : [],
  });
  const crossModelFilaments = useMemo(() => {
    const seen = new Set<string>();
    const merged: NonNullable<typeof availableFilaments> = [];
    for (const query of candidateFilamentQueries) {
      for (const filament of query.data ?? []) {
        // Same type+colour loaded on two models is one choice, not two.
        const key = `${filament.type}|${filament.color}|${filament.tray_info_idx}`;
        if (!seen.has(key)) {
          seen.add(key);
          merged.push(filament);
        }
      }
    }
    return merged;
  }, [candidateFilamentQueries]);

  const effectiveAvailableFilaments = isCrossModel ? crossModelFilaments : availableFilaments;

  // Only fetch printer status when single printer selected (for filament mapping)
  const { data: printerStatus, isLoading: printerStatusLoading } = useQuery({
    queryKey: ['printer-status', effectivePrinterId],
    queryFn: () => api.getPrinterStatus(effectivePrinterId!),
    enabled: !!effectivePrinterId,
  });

  // Single-printer flow: gate prefer_lowest on this printer's backup state.
  // Multi-printer flow gates per-printer inside the hook (different printers
  // may have different backup states), so we pass the raw setting down.
  const singlePrinterPreferLowest = effectivePreferLowest(
    settings?.prefer_lowest_filament,
    printerStatus?.ams_filament_backup,
  );

  const isPrinterCurrentlyDispatchable = (status: PrinterStatus | undefined): boolean => {
    if (!status?.connected) return false;
    if (status.awaiting_plate_clear) return false;
    if (status.ams?.some((ams) => ams.dry_time > 0)) return false;
    return ['IDLE', 'FINISH', 'FAILED'].includes(status.state ?? '');
  };

  const asapToastShouldPromiseLaterStart = async (): Promise<boolean> => {
    if (scheduleOptions.scheduleType !== 'asap' || assignmentMode !== 'printer') return false;
    if (selectedPrinters.length === 0) return false;

    try {
      const statuses = await Promise.all(
        selectedPrinters.map((printerId) =>
          queryClient.fetchQuery({
            queryKey: ['printer-status', printerId],
            queryFn: () => api.getPrinterStatus(printerId),
            staleTime: 0,
          }),
        ),
      );
      return statuses.some((status) => !isPrinterCurrentlyDispatchable(status));
    } catch {
      return true;
    }
  };

  /** The success toast of a create submit that queued `count` items. */
  const showQueuedToast = async (count: number) => {
    const waitForIdleToast = await asapToastShouldPromiseLaterStart();
    if (waitForIdleToast) {
      showToast(t('queue.printQueuedWillStartWhenIdle'));
    } else if (count === 1) {
      showToast(assignmentMode === 'model' ? `Queued for any ${targetModel}` : t('queue.printQueued'));
    } else {
      showToast(t('queue.itemsQueued', { count }));
    }
  };

  // Get AMS mapping from hook (only when single printer selected)
  const { amsMapping } = useFilamentMapping(
    effectiveFilamentReqs,
    printerStatus,
    manualMappings,
    singlePrinterPreferLowest,
    effectivePrinterId ? inventoryByTrayIdPerPrinter.get(effectivePrinterId) : undefined,
  );

  // Multi-printer filament mapping (for per-printer configuration)
  const multiPrinterMapping = useMultiPrinterFilamentMapping(
    selectedPrinters,
    printers,
    effectiveFilamentReqs,
    manualMappings,
    perPrinterConfigs,
    setPerPrinterConfigs,
    settings?.prefer_lowest_filament,
    inventoryByTrayIdPerPrinter,
    sharedMappingPrinterId,
  );

  // Auto-select first plate when plates load (single or multi-plate)
  useEffect(() => {
    const list = platesData?.plates;
    if (!list?.length) return;
    setSelectedPlates((previous) => {
      const kept = [...previous].filter((index) => list.some((plate) => plate.index === index));
      if (kept.length > 0 && kept.length === previous.size) return previous;
      return new Set(kept.length > 0 ? kept : [list[0].index]);
    });
  }, [platesData, selectedPlates.size]);

  const initialPrinterChosen = useRef(false);
  const sourcePending = (isLibraryFile && !!libraryFileId && libraryDetailsPending) || (!!archiveId && !isLibraryFile && archiveDetailsPending);
  useEffect(() => {
    if (mode === 'edit-queue-item' || isCrossModel || assignmentMode !== 'printer') return;
    if (selectedPrinters.length) initialPrinterChosen.current = true;
    if (initialPrinterChosen.current || sourcePending) return;
    const active = printers?.filter(printer => printer.is_active) ?? [];
    const preferred = active.find(printer => printer.id === settings?.default_printer_id
      && (!selectorModel || printer.model === selectorModel));
    const initial = preferred ?? (active.length === 1 ? active[0] : undefined);
    if (initial) {
      initialPrinterChosen.current = true;
      setSelectedPrinters([initial.id]);
    }
  }, [mode, isCrossModel, assignmentMode, selectedPrinters.length, sourcePending, printers, settings?.default_printer_id, selectorModel]);

  // Clear manual mappings and per-printer configs when printer or plate changes
  useEffect(() => {
    if (mode === 'edit-queue-item') {
      // For edit mode, clear mappings if printer selection or plate changed from initial
      const printersChanged = JSON.stringify(selectedPrinters.sort()) !== JSON.stringify(initialPrinterIds.sort());
      if (printersChanged || selectedPlate !== initialPlateId) {
        setManualMappings({});
        setPerPrinterConfigs({});
        setInitialExpandApplied(new Set());
      }
    } else {
      setManualMappings({});
      setPerPrinterConfigs({});
      setInitialExpandApplied(new Set());
    }
  }, [mode, selectedPrinters, selectedPlate, initialPrinterIds, initialPlateId]);

  // Clear filament overrides when target model or plate changes (but not on initial mount for edit mode)
  const [prevTargetModel, setPrevTargetModel] = useState(targetModel);
  const [prevPlateForOverrides, setPrevPlateForOverrides] = useState(selectedPlate);
  useEffect(() => {
    if (targetModel !== prevTargetModel || selectedPlate !== prevPlateForOverrides) {
      setPrevTargetModel(targetModel);
      setPrevPlateForOverrides(selectedPlate);
      // Don't clear on initial render in edit mode (values are initialized from queueItem)
      if (mode !== 'edit-queue-item' || prevTargetModel !== null) {
        setFilamentOverrides({});
        setForceColorMatch({});
      }
    }
  }, [targetModel, selectedPlate, prevTargetModel, prevPlateForOverrides, mode]);

  // Auto-expand per-printer mapping when setting is enabled and multiple printers selected
  // Only applies once per printer on initial selection, not when user unchecks
  useEffect(() => {
    if (!settings?.per_printer_mapping_expanded) return;
    if (selectedPrinters.length <= 1) return;

    // Only auto-configure printers that:
    // 1. Haven't had initial expand applied yet
    // 2. Have their status loaded (so auto-configure will actually work)
    const printersReadyForExpand = selectedPrinters.filter(printerId => {
      if (initialExpandApplied.has(printerId)) return false;

      // Check if this printer has status loaded
      const result = multiPrinterMapping.printerResults.find(r => r.printerId === printerId);
      return result && result.status && !result.isLoading;
    });

    if (printersReadyForExpand.length > 0) {
      // Mark these printers as having been initially expanded
      setInitialExpandApplied(prev => {
        const next = new Set(prev);
        printersReadyForExpand.forEach(id => next.add(id));
        return next;
      });

      // Auto-configure printers
      printersReadyForExpand.forEach(printerId => {
        multiPrinterMapping.autoConfigurePrinter(printerId);
      });
    }
  }, [settings?.per_printer_mapping_expanded, selectedPrinters, initialExpandApplied, multiPrinterMapping]);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isSubmitting) onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, isSubmitting]);

  const isMultiPlate = platesData?.is_multi_plate ?? false;
  const plates = platesData?.plates ?? [];


  const filamentWarningMessage = useMemo(() => {
    if (!filamentWarningItems || filamentWarningItems.length === 0) return '';
    const lines = filamentWarningItems.map((item) =>
      t(item.pooled ? 'printModal.insufficientFilamentLinePooled' : 'printModal.insufficientFilamentLine', {
        printer: item.printerName,
        slot: item.slotLabel,
        required: Math.round(item.requiredGrams),
        remaining: Math.round(item.remainingGrams),
      })
    );
    return [t('printModal.insufficientFilamentMessage'), ...lines].join('\n');
  }, [filamentWarningItems, t]);

  // Add to queue mutation (single printer)
  const addToQueueMutation = useMutation({
    mutationFn: (data: PrintQueueItemCreate) => api.addToQueue(data),
  });

  // The submit handler reports the outcome after all requested updates finish.
  const updateQueueMutation = useMutation({
    mutationFn: (data: PrintQueueItemUpdate) => api.updateQueueItem(queueItem!.id, data),
  });

  const handleSubmit = async (e?: React.FormEvent, options?: { skipFilamentCheck?: boolean; acknowledgedPrinters?: number[] }) => {
    e?.preventDefault();

    // Separate jobs skip it: it weighs the filaments of the dialog's one file,
    // and each job prints its own. The scheduler's check at dispatch (#1496)
    // still holds any of them back that is short of filament.
    if (
      !options?.skipFilamentCheck &&
      !settings?.disable_filament_warnings &&
      !isEditing &&
      !isSeparateJobs &&
      assignmentMode === 'printer'
    ) {
      const warningItems: FilamentWarningItem[] = [];
      const filamentReqs = effectiveFilamentReqs?.filaments ?? [];

      if (filamentReqs.length > 0 && slotMaterialsPerPrinter.size > 0) {
        for (const printerId of selectedPrinters) {
          const printerMapping = selectedPrinters.length > 1
            ? multiPrinterMapping.getFinalMapping(printerId)
            : amsMapping;
          if (!printerMapping) continue;

          const printerStatusForWarning = selectedPrinters.length > 1
            ? multiPrinterMapping.printerResults.find((result) => result.printerId === printerId)?.status
            : printerStatus;

          const loadedFilaments = buildLoadedFilaments(printerStatusForWarning);
          const slotLabelByTray = new Map(loadedFilaments.map((f) => [f.globalTrayId, f.label]));
          const slotMaterials = slotMaterialsPerPrinter.get(printerId);
          const printerName = printers?.find((p) => p.id === printerId)?.name ?? `Printer ${printerId}`;

          if (!slotMaterials) continue;
          computeFilamentWarnings(
            filamentReqs,
            printerMapping,
            slotMaterials,
            printerStatusForWarning?.ams_filament_backup === true,
          ).forEach((warning) => {
            warningItems.push({
              printerId,
              printerName,
              slotLabel: slotLabelByTray.get(warning.globalTrayId) ?? `Tray ${warning.globalTrayId}`,
              requiredGrams: warning.requiredGrams,
              remainingGrams: warning.remainingGrams,
              pooled: warning.pooled,
            });
          });
        }
      }

      if (warningItems.length > 0) {
        setFilamentWarningItems(warningItems);
        return;
      }
    }

    if (separateJobsIncompatible.length > 0) {
      showToast(
        t('printModal.multiFile.incompatible', {
          model: targetModel,
          files: separateJobsIncompatible.map((f) => f.filename).join(', '),
        }),
        'error',
      );
      return;
    }

    // Validate printer/model selection
    if (assignmentMode === 'printer' && selectedPrinters.length === 0) {
      showToast('Please select at least one printer', 'error');
      return;
    }
    // A cross-model job has no single target model — each candidate carries its
    // own, and the backend gates each of them separately. Both checks below are
    // about the one-model case only.
    if (!isCrossModel && assignmentMode === 'model' && !targetModel) {
      showToast('Please select a target printer model', 'error');
      return;
    }
    setIsSubmitting(true);
    // Calculate total API calls: plates × printers (or 1 for model-based)
    const platesToQueue = selectedPlates.size > 1
      ? plates.filter(p => selectedPlates.has(p.index))
      : [null];
    const totalCount = assignmentMode === 'model'
      ? platesToQueue.length
      : selectedPrinters.length * platesToQueue.length;
    setSubmitProgress({ current: 0, total: totalCount });

    const results: { success: number; failed: number; errors: string[] } = {
      success: 0,
      failed: 0,
      errors: [],
    };

    const getMappingForPrinter = (printerId: number): number[] | undefined => {
      if (selectedPrinters.length > 1 ||
          (sharedMappingPrinterId !== null && sharedMappingPrinterId !== printerId)) {
        return multiPrinterMapping.getFinalMapping(printerId);
      }
      return amsMapping;
    };

    // A new material substitution is an explicit operator choice. Preserve an
    // unchanged stored mapping for dispatch revalidation against live trays.
    const mappingSubstitutesMaterial = (printerId: number, plateId: number | null, mapping: number[] | undefined): boolean => {
      if (!mapping) return false;
      const status = selectedPrinters.length > 1
        ? multiPrinterMapping.printerResults.find((result) => result.printerId === printerId)?.status
        : printerStatus;
      const loaded = buildLoadedFilaments(status);
      return (effectiveFilamentReqs?.filaments ?? []).some((req) => {
        const tray = mapping[req.slot_id - 1];
        if (tray == null || tray < 0) return false;
        if (mode === 'edit-queue-item' && printerId === queueItem?.printer_id &&
            plateId === initialPlateId && queueItem?.ams_mapping?.[req.slot_id - 1] === tray) return false;
        const filament = loaded.find((f) => f.globalTrayId === tray);
        return !!filament?.type && !!req.type && !filamentTypesCompatible(filament.type, req.type);
      });
    };

    const filamentOverridesArray = buildQueuedFilamentOverrides(
      effectiveFilamentReqs?.filaments, filamentOverrides, forceColorMatch, filamentPresetNames,
    );
    const printerOverridesForPlate = (printerId: number | null, plateId: number | null) => {
      if (plateId !== selectedPlate || printerId == null) return undefined;
      const sameTarget = isEditing && queueItem?.printer_id === printerId && initialPlateId === plateId;
      return fixedPrinterFilamentOverrides({
        entries: filamentOverridesArray,
        changes: filamentOverrides,
        forceVisible: selectedPrinters.length === 1 && (Boolean(showFilamentMapping) || sameTarget),
        chosenTrays: sharedMappingPrinterId == null || sharedMappingPrinterId === printerId ? manualMappings : undefined,
        status: printerId === effectivePrinterId ? printerStatus : undefined,
        saved: sameTarget ? queueItem : undefined,
      });
    };

    // Cross-model alternatives (#671): ONE item carrying a candidate per file,
    // in the order the user arranged. This returns before the plate/printer
    // fan-out below because it deliberately fans out to nothing — the whole
    // point is that exactly one of these candidates ever runs.
    //
    // Filament overrides are shared rather than per-candidate, matching how
    // single-model assignment already behaves: the printer is unknown at queue
    // time, so what is expressed here is "this job needs PETG", which is true of
    // every slice of the same job. The AMS mapping is likewise absent — the
    // scheduler computes it against the printer it actually picks.
    if (isCrossModel) {
      try {
        let crossModelBatchId: number | undefined;
        if (quantity > 1) {
          const baseName = (archiveName || '').replace(/\.gcode\.3mf$/i, '').replace(/\.3mf$/i, '');
          const batch = await api.createBatch({
            name: `${baseName || 'Batch'} ×${quantity}`,
            // A variant's physical plate number can differ between slices.
            // NULL means "this logical job", independent of which candidate
            // the scheduler resolves for a particular copy.
            plates: [{ plate_id: null, plate_name: null, quantity_target: quantity, sort_order: 0 }],
            project_id: projectId ?? undefined,
          });
          crossModelBatchId = batch.id;
        }
        await api.addToQueue({
          variants: candidates.map((c) => ({
            library_file_id: c.id,
            plate_id: candidatePlates[c.id] ?? null,
            filament_overrides: filamentOverridesArray,
          })),
          target_location: targetLocation,
          require_previous_success: scheduleOptions.requirePreviousSuccess,
          auto_off_after: scheduleOptions.autoOffAfter,
          gcode_injection: scheduleOptions.gcodeInjection,
          manual_start: scheduleOptions.scheduleType === 'queue' && scheduleOptions.requireManualStart,
          scheduled_time: scheduleOptions.scheduleType === 'scheduled' && scheduleOptions.scheduledTime
            ? new Date(scheduleOptions.scheduledTime).toISOString()
            : undefined,
          quantity,
          batch_id: crossModelBatchId,
          ...printOptions,
          project_id: projectId ?? undefined,
        });
        showToast(t('printModal.variants.queued', { count: candidates.length }), 'success');
        queryClient.invalidateQueries({ queryKey: ['queue'] });
        onSuccess?.();
        onClose();
      } catch (error) {
        showToast(error instanceof Error ? error.message : String(error), 'error');
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // Separate jobs (#3462): one ordinary queue item per listed file, files in
    // list order and the selected printers inside each, through the same
    // POST /queue/ the multi-plate fan-out below uses. Returns before that
    // fan-out, which is built around the dialog's one file (its batch, its
    // per-plate quantities and mappings).
    //
    // Each item carries only what is true of every file: printer or model,
    // schedule, options, cost centre. No ams_mapping and no filament_overrides:
    // the mapping and override panels describe the first file's filaments,
    // which are not the others'. Without a mapping the scheduler resolves one at
    // dispatch from the item's own 3MF and the printer's loaded trays
    // (`_ensure_ams_mapping`), as it already does for model-based items. Also
    // left out: estimated_cost (a display hint, the server prices each item
    // itself), skip_filament_check (the spool warning was never shown),
    // nozzle_rack_choice (picked against the first file's filament groups) and
    // batch_id (a batch belongs to one source file; quantity > 1 still makes
    // the server batch each file on its own).
    //
    // The first refused file stops the run: queueing the rest would put them
    // ahead of it, and stopping lets a resubmit carry on from that file
    // without queueing anything twice. What did go in leaves the list, so the
    // list is always exactly what is still to be queued.
    if (isSeparateJobs) {
      const printerIds = assignmentMode === 'printer' ? selectedPrinters : [null];
      // The stagger of the printer fan-out below, per file.
      const useStagger = assignmentMode === 'printer' && scheduleOptions.staggerEnabled && selectedPrinters.length > 1;
      const staggerBaseTime = useStagger
        ? (scheduleOptions.scheduleType === 'scheduled' && scheduleOptions.scheduledTime
          ? new Date(scheduleOptions.scheduledTime).getTime()
          : Date.now())
        : 0;
      const asap = scheduleOptions.scheduleType === 'asap';
      setSubmitProgress({ current: 0, total: candidates.length * printerIds.length });
      try {
        // The rest of a partly queued run goes in right behind the run's own
        // ASAP items as the queue stands now: since the refusal, items may have
        // been added, moved or started, and the count of positions taken would
        // then point somewhere else (#3471 review). The count is the fallback
        // when the queue can't be read.
        let asapInsertedBefore = asapPositionsTaken;
        if (asap && (runItemIds.length > 0 || runBatchIds.length > 0)) {
          try {
            const pending = await api.getQueue(undefined, 'pending');
            asapInsertedBefore = runAsapTail(pending, runItemIds, runBatchIds);
          } catch {
            // Keep the count.
          }
        }
        const outcome = await queueSeparateJobs({
          files: candidates,
          plateByFile: candidatePlates,
          printerIds,
          alreadyQueued: queuedPairs,
          asapInsertedBefore,
          quantity: effectiveQuantity,
          asap,
          buildItem: (file, plateId, printerId, printerIndex) => {
            const item: PrintQueueItemCreate = {
              library_file_id: file.id,
              plate_id: plateId,
              printer_id: assignmentMode === 'printer' ? printerId : null,
              target_model: assignmentMode === 'model' ? targetModel : null,
              target_location: assignmentMode === 'model' ? targetLocation : null,
              require_previous_success: scheduleOptions.requirePreviousSuccess,
              auto_off_after: scheduleOptions.autoOffAfter,
              gcode_injection: scheduleOptions.gcodeInjection,
              manual_start: (scheduleOptions.scheduleType === 'queue' && scheduleOptions.requireManualStart),
              scheduled_time: scheduleOptions.scheduleType === 'scheduled' && scheduleOptions.scheduledTime
                ? new Date(scheduleOptions.scheduledTime).toISOString()
                : undefined,
              ...printOptions,
              project_id: projectId ?? undefined,
              cleanup_library_after_dispatch: cleanupLibraryAfterDispatch,
            };
            if (useStagger) {
              const groupIndex = Math.floor(printerIndex / scheduleOptions.staggerGroupSize);
              if (groupIndex > 0) {
                const offsetMs = groupIndex * scheduleOptions.staggerIntervalMinutes * 60_000;
                item.scheduled_time = new Date(staggerBaseTime + offsetMs).toISOString();
              }
            }
            return item;
          },
          addToQueue: (data) => addToQueueMutation.mutateAsync(data),
          onProgress: (current, total) => setSubmitProgress({ current, total }),
        });

        setAsapPositionsTaken(outcome.asapInserted);
        const allItemIds = [...runItemIds, ...outcome.queuedItemIds];
        const allBatchIds = [...runBatchIds, ...outcome.queuedBatchIds];
        setRunItemIds(allItemIds);
        setRunBatchIds(allBatchIds);
        if (outcome.failure) {
          const allQueued = new Set([...queuedPairs, ...outcome.queuedPairs]);
          setQueuedPairs(allQueued);
          // What is in the queue: the files queued on every printer, and the
          // refused file itself when a printer took it, in this submit or an
          // earlier one, also on a printer that has been deselected since.
          const refusedId = outcome.failure.file.id;
          const refusedFileQueued = fileHasQueuedPair(allQueued, refusedId);
          const queuedIds = refusedFileQueued
            ? [...outcome.queuedFileIds, refusedId]
            : outcome.queuedFileIds;
          const queued = candidates.filter((c) => queuedIds.includes(c.id)).map((c) => c.filename);
          showToast(
            t('printModal.multiFile.failed', {
              filename: outcome.failure.file.filename,
              message: outcome.failure.message,
              queued: queued.length > 0 ? queued.join(', ') : t('common.none'),
            }),
            'error',
          );
          // Only files queued on every printer leave the list; the refused one
          // stays, even if a printer before the refusal took it.
          const remaining = candidates.filter((c) => !outcome.queuedFileIds.includes(c.id));
          setCandidates(remaining);
          // Any item in the queue makes this run partly queued, also one of
          // the refused file on an earlier printer.
          if (outcome.itemsCreated > 0) setPartlyQueued(true);
          // The opener keeps this if the dialog is closed now: without it the
          // same selection would open empty-handed and queue them again.
          if (allQueued.size > 0) {
            const remainingIds = remaining.map((c) => c.id);
            onSeparateJobsProgress?.({
              queuedPairs: [...allQueued],
              asapInserted: outcome.asapInserted,
              queuedItemIds: allItemIds,
              queuedBatchIds: allBatchIds,
              settings: {
                plateByFile: candidatePlates,
                assignmentMode,
                printerIds: selectedPrinters,
                targetModel,
                targetLocation,
                quantity,
                printOptions,
                scheduleOptions,
              },
              queuedFileIds: (variantFiles ?? []).map((f) => f.id).filter((id) => !remainingIds.includes(id)),
              remainingFileIds: remainingIds,
            });
          }
          queryClient.invalidateQueries({ queryKey: ['queue'] });
          return;
        }

        // Nothing posted means every remaining pair was already queued (a
        // refusing printer deselected since): a success, but "0 items queued"
        // would say otherwise.
        if (outcome.itemsCreated > 0) await showQueuedToast(outcome.itemsCreated);
        queryClient.invalidateQueries({ queryKey: ['queue'] });
        onSuccess?.();
        onClose();
      } catch (error) {
        // queueSeparateJobs reports refusals itself; this is anything else.
        showToast(error instanceof Error ? error.message : String(error), 'error');
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // Batch order (#342): a create submission that produces more than one run
    // from one source is pre-created as a batch carrying per-plate targets,
    // and its id is passed to each subsequent addToQueue call. The targets are
    // what make the order able to say a failed run is still owed — without
    // them the batch only knows what it happened to queue. Only for
    // single-target submissions; multi-printer fan-out keeps the old per-item
    // shape, where "how many" is answered by the printer count.
    const plateTargets = platesToQueue.map((plate, index) => {
      const plateIndex = plate ? plate.index : selectedPlate;
      return {
        plate_id: plateIndex,
        plate_name: plate ? (plate.name || null) : null,
        quantity_target: quantityForPlate(plateIndex),
        sort_order: index,
      };
    });
    const totalRuns = plateTargets.reduce((sum, target) => sum + target.quantity_target, 0);
    const shouldAutoBatch =
      mode === 'create'
      && (platesToQueue.length > 1 || totalRuns > 1)
      && (assignmentMode === 'model' || selectedPrinters.length === 1);
    let autoBatchId: number | null = null;
    if (shouldAutoBatch) {
      try {
        const baseName = (archiveName || '').replace(/\.gcode\.3mf$/i, '').replace(/\.3mf$/i, '');
        const batchName = platesToQueue.length > 1
          ? `${baseName || 'Batch'} · ${platesToQueue.length} plates`
          : `${baseName || 'Batch'} ×${totalRuns}`;
        const batch = await api.createBatch({
          name: batchName,
          archive_id: isLibraryFile ? undefined : archiveId,
          library_file_id: isLibraryFile ? libraryFileId : undefined,
          plates: plateTargets,
        });
        autoBatchId = batch.id;
      } catch {
        // Non-fatal: fall back to ungrouped items so the queue still works.
        // The server still creates a plain batch when quantity > 1, so the
        // queue grouping survives even when the order layer doesn't.
        autoBatchId = null;
      }
    }

    let asapInserted = 0;
    const applyAsapInsertion = (queueData: PrintQueueItemCreate, itemCount = 1) => {
      if (scheduleOptions.scheduleType !== 'asap') return;
      queueData.insert_at_top = true;
      queueData.insert_position = asapInserted + 1;
      asapInserted += itemCount;
    };

    // Common queue data for create and edit modes
    const getQueueData = (printerId: number | null, plateOverride?: number | null): PrintQueueItemCreate => ({
      printer_id: assignmentMode === 'printer' ? printerId : null,
      target_model: assignmentMode === 'model' ? targetModel : null,
      target_location: assignmentMode === 'model' ? targetLocation : null,
      filament_overrides: assignmentMode === 'model'
        ? filamentOverridesArray
        : printerOverridesForPlate(printerId, plateOverride ?? selectedPlate),
      // Use library_file_id for library files, archive_id for archives
      archive_id: isLibraryFile ? undefined : archiveId,
      library_file_id: isLibraryFile ? libraryFileId : undefined,
      require_previous_success: scheduleOptions.requirePreviousSuccess,
      auto_off_after: scheduleOptions.autoOffAfter,
      gcode_injection: scheduleOptions.gcodeInjection,
      manual_start: scheduleOptions.scheduleType === 'queue' && scheduleOptions.requireManualStart,
      // When the user clicks "Print Anyway" on the frontend deficit warning,
      // persist that acknowledgement so the scheduler doesn't immediately
      // re-flag the item on its first dispatch tick (#1698-followup).
      skip_filament_check: printerId != null && (
        options?.acknowledgedPrinters?.includes(printerId) ||
        mappingSubstitutesMaterial(printerId, plateOverride ?? selectedPlate, getMappingForPrinter(printerId))
      ) ? true : undefined,
      ams_mapping: printerId ? getMappingForPrinter(printerId) : undefined,
      plate_id: plateOverride !== undefined ? plateOverride : selectedPlate,
      scheduled_time: scheduleOptions.scheduleType === 'scheduled' && scheduleOptions.scheduledTime
        ? new Date(scheduleOptions.scheduledTime).toISOString()
        : undefined,
      ...printOptions,
      project_id: projectId ?? undefined,
      batch_id: autoBatchId ?? undefined,
      cleanup_library_after_dispatch: cleanupLibraryAfterDispatch,
    });

    // Model-based assignment
    if (assignmentMode === 'model') {
      let progressCounter = 0;
      for (const plate of platesToQueue) {
        progressCounter++;
        setSubmitProgress({ current: progressCounter, total: totalCount });
        const plateId = plate ? plate.index : selectedPlate;

        try {
          if (mode === 'edit-queue-item' && !plate) {
            // Edit mode - update with target_model (only for single plate)
            const updateData: PrintQueueItemUpdate = {
              printer_id: null,
              target_model: targetModel,
              target_location: targetLocation,
              filament_overrides: filamentOverridesArray || null,
              require_previous_success: scheduleOptions.requirePreviousSuccess,
              auto_off_after: scheduleOptions.autoOffAfter,
              gcode_injection: scheduleOptions.gcodeInjection,
              manual_start: scheduleOptions.scheduleType === 'queue' && scheduleOptions.requireManualStart,
              ams_mapping: undefined,
              plate_id: plateId,
              scheduled_time: scheduleOptions.scheduleType === 'scheduled' && scheduleOptions.scheduledTime
                ? new Date(scheduleOptions.scheduledTime).toISOString()
                : null,
              ...printOptions,
            };
            await updateQueueMutation.mutateAsync(updateData);
          } else {
            // Add-to-queue mode with model-based assignment
            const queueData = getQueueData(null, plateId);
            const plateQuantity = quantityForPlate(plateId);
            if (plateQuantity > 1) queueData.quantity = plateQuantity;
            applyAsapInsertion(queueData, plateQuantity);
            await addToQueueMutation.mutateAsync(queueData);
          }
          results.success++;
        } catch (error) {
          results.failed++;
          const plateName = plate ? (plate.name || `Plate ${plate.index}`) : '';
          results.errors.push(plateName ? `${plateName}: ${(error as Error).message}` : (error as Error).message);
        }
      }
    } else {
      // Printer-based assignment: loop through plates × printers
      // Compute stagger base time once before the loop
      const useStagger = scheduleOptions.staggerEnabled
        && !isEditing
        && selectedPrinters.length > 1;
      const staggerBaseTime = useStagger
        ? (scheduleOptions.scheduleType === 'scheduled' && scheduleOptions.scheduledTime
          ? new Date(scheduleOptions.scheduledTime).getTime()
          : Date.now())
        : 0;

      let progressCounter = 0;
      for (const plate of platesToQueue) {
        const plateId = plate ? plate.index : selectedPlate;

        for (let i = 0; i < selectedPrinters.length; i++) {
          const printerId = selectedPrinters[i];
          progressCounter++;
          setSubmitProgress({ current: progressCounter, total: totalCount });

          try {
            if (isEditing && progressCounter === 1) {
              // Edit mode - update the original queue item for the first entry
              const printerMapping = getMappingForPrinter(printerId);
              const updateData: PrintQueueItemUpdate = {
                printer_id: printerId,
                target_model: null,
                target_location: null,
                filament_overrides: printerOverridesForPlate(printerId, plateId) ?? null,
                require_previous_success: scheduleOptions.requirePreviousSuccess,
                auto_off_after: scheduleOptions.autoOffAfter,
                gcode_injection: scheduleOptions.gcodeInjection,
                manual_start: scheduleOptions.scheduleType === 'queue' && scheduleOptions.requireManualStart,
                ams_mapping: printerMapping,
                skip_filament_check: mappingSubstitutesMaterial(printerId, plateId, printerMapping) ? true : undefined,
                plate_id: plateId,
                scheduled_time: scheduleOptions.scheduleType === 'scheduled' && scheduleOptions.scheduledTime
                  ? new Date(scheduleOptions.scheduledTime).toISOString()
                  : null,
                ...printOptions,
              };
              await updateQueueMutation.mutateAsync(updateData);
            } else {
              // New print mode, staggered print, or edit mode with additional entries
              const queueData = getQueueData(printerId, plateId);
              const plateQuantity = quantityForPlate(plateId);
              if (plateQuantity > 1) queueData.quantity = plateQuantity;
              applyAsapInsertion(queueData, plateQuantity);
              // Apply stagger offset for groups after the first
              if (useStagger) {
                const groupIndex = Math.floor(i / scheduleOptions.staggerGroupSize);
                if (groupIndex > 0) {
                  const offsetMs = groupIndex * scheduleOptions.staggerIntervalMinutes * 60_000;
                  queueData.scheduled_time = new Date(staggerBaseTime + offsetMs).toISOString();
                }
                // Group 0 with ASAP: no scheduled_time (start immediately)
                // Group 0 with scheduled: keeps the scheduled_time from getQueueData
              }
              await addToQueueMutation.mutateAsync(queueData);
            }
            results.success++;
          } catch (error) {
            results.failed++;
            const printerName = printers?.find(p => p.id === printerId)?.name || `Printer ${printerId}`;
            const plateName = plate ? (plate.name || `Plate ${plate.index}`) : '';
            const label = plateName ? `${printerName} (${plateName})` : printerName;
            results.errors.push(`${label}: ${(error as Error).message}`);
          }
        }
      }
    }

    setIsSubmitting(false);

    // Show result toast
    if (results.failed === 0) {
      if (isEditing) {
        if (mode === 'edit-queue-item') {
          showToast(t('queue.editSuccess'));
        }
      } else {
        await showQueuedToast(results.success);
      }
      queryClient.invalidateQueries({ queryKey: ['queue'] });
      onSuccess?.();
      onClose();
    } else if (results.success === 0) {
      showToast(`Failed: ${results.errors[0]}`, 'error');
    } else {
      showToast(`${results.success} succeeded, ${results.failed} failed`, 'error');
      queryClient.invalidateQueries({ queryKey: ['queue'] });
    }
  };

  const isPending = isSubmitting || updateQueueMutation.isPending;

  // A single-printer AMS job must wait for the printer's live status before it
  // can resolve the filament mapping. Submitting mid-load matched against zero
  // known trays and serialized an all-[-1] mapping, which dispatched the print
  // to the empty external feed (#2589). Separate jobs send no mapping at all
  // (the scheduler maps each against its own file at dispatch), so they have
  // nothing to wait for.
  const waitingForAmsStatus =
    !isSeparateJobs && assignmentMode === 'printer' && selectedPrinters.length === 1 && printerStatusLoading;

  const canSubmit = useMemo(() => {
    if (waitingForAmsStatus || separateJobsIncompatible.length || (isMultiFile && !candidatePlatesReady)) return false;
    if (isPending) return false;

    // Need valid printer/model selection
    if (assignmentMode === 'printer' && selectedPrinters.length === 0) return false;
    // Both are about the single-model case. A cross-model job has no one target
    // model, and each candidate is gated against its own by the backend (#671).
    if (!isCrossModel && assignmentMode === 'model' && !targetModel) return false;

    // For multi-plate files, need at least one plate selected. Separate jobs
    // take each file's plate from the candidate list, not from this selection.
    if (!isSeparateJobs && isMultiPlate && selectedPlates.size === 0) return false;

    return true;
  }, [
    selectedPrinters.length,
    assignmentMode,
    targetModel,
    isMultiPlate,
    selectedPlates.size,
    isPending,
    isMultiFile, isSeparateJobs, separateJobsIncompatible, candidatePlatesReady, waitingForAmsStatus,
    isCrossModel,
  ]);

  // Quantity only applies for single-printer or model-based assignment (not multi-printer)
  const effectiveQuantity = (assignmentMode === 'printer' && selectedPrinters.length > 1) ? 1 : quantity;

  // On a multi-plate file the per-plate steppers own the quantity and the
  // global field is hidden (#342) — the reporter's case is "plate 1 once,
  // plate 2 twice", which one shared number cannot express. Single-plate
  // files, and edit mode, keep the single field exactly as before.
  const usePerPlateQuantities = mode === 'create' && !isMultiFile && isMultiPlate && plates.length > 1;

  /** Runs to queue for one plate. `null` = the single-plate / whole-file case. */
  const quantityForPlate = (plateIndex: number | null): number => {
    if (!usePerPlateQuantities || plateIndex == null) return effectiveQuantity;
    // Multi-printer fan-out already means one copy per printer; multiplying by
    // a per-plate count on top would silently produce plates × printers × n.
    if (assignmentMode === 'printer' && selectedPrinters.length > 1) return 1;
    return Math.max(1, plateQuantities[plateIndex] ?? 1);
  };

  // Clear gcode_injection if the admin removes all snippets while the modal
  // is open — the checkbox itself hides via hasGcodeSnippets in
  // ScheduleOptions, but the boolean would otherwise stay true and ship to
  // the API. The previous gate also reset the flag whenever effectiveQuantity
  // dropped to <= 1, which silently un-ticked the checkbox on every single-
  // print create flow (#1852). The scheduler reads item.gcode_injection per
  // queue item regardless of batch size, so there's no underlying reason for
  // the quantity-1 case to be blocked.
  useEffect(() => {
    if (mode === 'create' && scheduleOptions.gcodeInjection && !settings?.has_gcode_snippets) {
      setScheduleOptions((opts) => ({ ...opts, gcodeInjection: false }));
    }
  }, [mode, settings?.has_gcode_snippets, scheduleOptions.gcodeInjection]);

  // Modal title and action button text based on mode
  const getModalConfig = () => {
    if (!isEditing) {
      return {
        title: t('common.print'),
        icon: Printer,
        submitText: t('common.print'),
        submitIcon: Printer,
        loadingText: submitProgress.total > 1
          ? t('queue.addingProgress', { current: submitProgress.current, total: submitProgress.total })
          : t('queue.adding'),
      };
    }
    // edit-queue-item mode
    return {
      title: t('queue.editQueueItem'),
      icon: Pencil,
      submitText: t('common.save'),
      submitIcon: Pencil,
      loadingText: submitProgress.total > 1
        ? t('queue.savingProgress', { current: submitProgress.current, total: submitProgress.total })
        : t('common.saving'),
    };
  };

  const modalConfig = getModalConfig();
  const TitleIcon = modalConfig.icon;
  const SubmitIcon = modalConfig.submitIcon;

  // Show filament mapping when:
  // - Single printer selected
  // - For archives: plate is selected (for multi-plate) or not required (single-plate)
  // - For library files: always show (no plate selection)
  // Never for separate jobs: the panel maps the first file's filaments, and
  // each job is mapped against its own file at dispatch.
  const showFilamentMapping = !isSeparateJobs && effectivePrinterId && selectedPlates.size <= 1 && (
    isLibraryFile || (isMultiPlate ? selectedPlate !== null : true)
  );

  // Model mode has no printer and so no trays to map onto; what it offers instead
  // is the filament each slot must be printed in, which the scheduler matches
  // against whatever printer of the model it picks. Needs the model's loaded
  // filaments to offer as alternatives.
  // Cross-model items have no targetModel by design — their candidates each
  // carry their own — so gate on having somewhere to source choices from.
  // Separate jobs send no overrides: the slots listed are the first file's.
  const showFilamentOverride =
    assignmentMode === 'model'
    && !isSeparateJobs
    && (isCrossModel || !!targetModel)
    && !!effectiveAvailableFilaments
    && effectiveAvailableFilaments.length > 0;
  // Dual-nozzle gate for the Nozzle Offset Calibration toggle (#1682).
  // Mirrors backend `DUAL_NOZZLE_MODELS` so model-based assignment can show
  // the toggle without a specific printer selected. For printer-mode we rely
  // on the canonical `nozzle_count` field auto-detected from MQTT.
  const DUAL_NOZZLE_MODELS = useMemo(
    () => new Set(['H2D', 'H2DPRO', 'H2C', 'X2D']),
    [],
  );
  const showDualNozzleOptions = useMemo(() => {
    if (assignmentMode === 'model') {
      if (!targetModel) return false;
      return DUAL_NOZZLE_MODELS.has(targetModel.toUpperCase().replace(/[\s-]/g, ''));
    }
    if (!printers || selectedPrinters.length === 0) return false;
    return selectedPrinters.some(id => printers.find(p => p.id === id)?.nozzle_count === 2);
  }, [assignmentMode, targetModel, printers, selectedPrinters, DUAL_NOZZLE_MODELS]);

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      onClick={isSubmitting ? undefined : onClose}
    >
      <Card
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <CardContent className="p-0">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-bambu-dark-tertiary">
            <div className="flex items-center gap-2">
              <TitleIcon className="w-5 h-5 text-bambu-green" />
              <h2 className="text-lg font-semibold text-white">{modalConfig.title}</h2>
            </div>
            <Button variant="ghost" size="sm" onClick={onClose} disabled={isSubmitting}>
              <X className="w-5 h-5" />
            </Button>
          </div>

          <form onSubmit={handleSubmit} className="p-4 space-y-4">
            {/* Archive name */}
            <p className="text-sm text-bambu-gray">
              <span className="block text-bambu-gray mb-1">{translateInterface("orders.runtimeInterface.printJob")}</span>
              <span className="text-white font-medium truncate block">{archiveName}</span>
            </p>

            {/* Build-plate badge for the selected (or sole) plate — surfaced
                early so the user knows which plate to mount before scheduling
                (#1281). PlateSelector renders its own per-plate badges for
                multi-plate files; this badge covers the single-plate case and
                the multi-plate case where exactly one plate is selected.
                Not for separate jobs: it would name the first file's plate. */}
            {(() => {
              if (isSeparateJobs || !plates.length) return null;
              const target = selectedPlate != null
                ? plates.find(p => p.index === selectedPlate)
                : plates[0];
              const bed = getBedTypeInfo(target?.bed_type);
              if (!bed) return null;
              return (
                <p className="flex items-center gap-1.5 text-xs text-bambu-gray -mt-2" title={bed.label}>
                  <img src={bed.icon} alt="" className="w-4 h-4 object-contain flex-shrink-0" />
                  <span className="truncate">{bed.label}</span>
                </p>
              );
            })()}

            {/* Plate selection - first so users know filament requirements before selecting printers */}
            <PlateSelector
              plates={plates}
              isMultiPlate={isMultiPlate}
              selectedPlates={selectedPlates}
              onToggle={(plateIndex) => {
                setSelectedPlates(prev => {
                  const next = new Set(prev);
                  if (!isEditing) {
                    // Multi-select: toggle the plate
                    if (next.has(plateIndex)) {
                      next.delete(plateIndex);
                    } else {
                      next.add(plateIndex);
                    }
                  } else {
                    // Single-select: replace selection
                    next.clear();
                    next.add(plateIndex);
                  }
                  return next;
                });
              }}
              onSelectAll={!isEditing ? () => setSelectedPlates(new Set(plates.map(p => p.index))) : undefined}
              onDeselectAll={!isEditing ? () => setSelectedPlates(new Set()) : undefined}
              multiSelect={!isEditing}
              quantities={usePerPlateQuantities ? plateQuantities : undefined}
              onQuantityChange={usePerPlateQuantities
                ? (plateIndex, value) => setPlateQuantities(prev => ({ ...prev, [plateIndex]: value }))
                : undefined}
            />

            {/* What the marked files become (#3462). Only for a selection made
                in the File Manager: a version group is one job sliced for
                different printers, for which only alternatives make sense.
                Its hint, or why Alternatives is blocked, is the one
                explanation of the mode, so the list below shows none. */}
            {showModeToggle && (
              <MultiFileModeToggle
                value={multiFileMode}
                onChange={handleMultiFileModeChange}
                blockedModel={duplicateModel(candidates)}
                disabled={isPending}
              />
            )}

            {/* Cross-model alternatives (#671) replace the printer picker entirely:
                the user already answered "which printer" by choosing these files,
                and the remaining question is only which they'd rather have.
                Separate jobs use the same list for their queue order and keep
                the printer picker below. */}
            {isMultiFile && (
              <VariantCandidates
                candidates={candidates}
                onReorder={setCandidates}
                plateByFile={candidatePlates}
                onPlateChange={(fileId, plateId) =>
                  setCandidatePlates((prev) => ({ ...prev, [fileId]: plateId }))
                }
                onPlatesReadyChange={setCandidatePlatesReady}
                title={isSeparateJobs ? t('printModal.multiFile.orderTitle') : undefined}
                help={showModeToggle ? '' : isSeparateJobs ? t('printModal.multiFile.separateHint') : undefined}
              />
            )}

            {hasEditingVariants && (
              <VariantCandidates
                candidates={editingVariants}
                readOnly
                readOnlyNote={t('printModal.variants.editNote')}
                onReorder={() => {}}
                plateByFile={{}}
                onPlateChange={() => {}}
              />
            )}

            {/* Printer selection with per-printer mapping — hidden when printer is pre-selected via props */}
            {!isCrossModel && !hasEditingVariants && !initialSelectedPrinterIds?.length && (
              <PrinterSelector
                printers={printers || []}
                selectedPrinterIds={selectedPrinters}
                onMultiSelect={setSelectedPrinters}
                isLoading={loadingPrinters}
                allowMultiple={true}
                showInactive={mode === 'edit-queue-item'}
                disableBusy={false}
                printerMappingResults={multiPrinterMapping.printerResults}
                filamentReqs={effectiveFilamentReqs}
                onAutoConfigurePrinter={multiPrinterMapping.autoConfigurePrinter}
                onUpdatePrinterConfig={multiPrinterMapping.updatePrinterConfig}
                assignmentMode={assignmentMode}
                onAssignmentModeChange={setAssignmentMode}
                targetModel={targetModel}
                onTargetModelChange={setTargetModel}
                targetLocation={targetLocation}
                onTargetLocationChange={setTargetLocation}
                slicedForModel={selectorModel}
              />
            )}

            {/* "Any X" for separate jobs: each file is gated on its own (#2578),
                and the backend would refuse these one by one. */}
            {separateJobsIncompatible.length > 0 && (
              <div className="p-3 mb-2 bg-red-50 dark:bg-red-500/10 border border-red-300 dark:border-red-500/30 rounded-lg flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0" />
                <span className="text-sm text-red-700 dark:text-red-400">
                  {t('printModal.multiFile.incompatible', {
                    model: targetModel,
                    files: separateJobsIncompatible.map((f) => f.filename).join(', '),
                  })}
                </span>
              </div>
            )}

            {/* Filament override - shown in model mode when filament requirements are available */}
            {showFilamentOverride && effectiveFilamentReqs && (
              <FilamentOverride
                filamentReqs={effectiveFilamentReqs}
                availableFilaments={effectiveAvailableFilaments!}
                overrides={filamentOverrides}
                onChange={setFilamentOverrides}
                forceColorMatch={forceColorMatch}
                onForceColorMatchChange={(slotId, value) =>
                  setForceColorMatch((prev) => ({ ...prev, [slotId]: value }))
                }
              />
            )}

            {/* Compatibility warning when sliced model doesn't match selected printer */}
            {!isSeparateJobs && slicedForModel && assignmentMode === 'printer' && selectedPrinters.length === 1 && (() => {
              const selectedPrinter = printers?.find(p => p.id === selectedPrinters[0]);
              if (selectedPrinter && selectedPrinter.model && slicedForModel !== selectedPrinter.model) {
                return (
                  <div className="p-3 mb-2 bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-300 dark:border-yellow-500/30 rounded-lg flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-yellow-600 dark:text-yellow-400 flex-shrink-0" />
                    <span className="text-sm text-yellow-700 dark:text-yellow-400">
                      {translateInterface("orders.runtimeInterface.fileWasSlicedFor")} {slicedForModel}{translateInterface("orders.runtimeInterface.butPrintingOn")} {selectedPrinter.model}
                    </span>
                  </div>
                );
              }
              return null;
            })()}

            {/* The same warning for separate jobs, naming each file that was
                sliced for another model. Every selected printer gets every
                file, so there is one line per model among them; with mixed
                files the picker shows all printers unfiltered. A warning, not
                a block, as for one file. */}
            {isSeparateJobs && assignmentMode === 'printer' && (() => {
              const printerModels = new Set(
                selectedPrinters
                  .map((id) => printers?.find((p) => p.id === id)?.model)
                  .filter((model): model is string => !!model),
              );
              return [...printerModels].map((printerModel) => {
                const mismatched = filesNotSlicedFor(candidates, printerModel);
                if (mismatched.length === 0) return null;
                return (
                  <div
                    key={printerModel}
                    className="p-3 mb-2 bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-300 dark:border-yellow-500/30 rounded-lg flex items-center gap-2"
                  >
                    <AlertTriangle className="w-4 h-4 text-yellow-600 dark:text-yellow-400 flex-shrink-0" />
                    <span className="text-sm text-yellow-700 dark:text-yellow-400">
                      {t('printModal.multiFile.notSlicedFor', {
                        model: printerModel,
                        files: mismatched.map((f) => f.filename).join(', '),
                      })}
                    </span>
                  </div>
                );
              });
            })()}

            {/* Warning when archive data couldn't be loaded */}
            {archiveDataMissing && (
              <div className="flex items-start gap-2 p-3 mb-2 bg-orange-50 dark:bg-orange-500/10 border border-orange-300 dark:border-orange-500/30 rounded-lg text-sm">
                <AlertCircle className="w-4 h-4 text-orange-600 dark:text-orange-400 mt-0.5 flex-shrink-0" />
                <p className="text-orange-700 dark:text-orange-400">
                  {translateInterface("orders.runtimeInterface.archiveDataUnavailableTheSourceFileMayHaveBeenDeletedFilamentMappingIs")}
                </p>
              </div>
            )}

            {/* Filament mapping - only show when single printer selected */}
            {showFilamentMapping && !archiveDataMissing && selectedPrinters.length === 1 && (
              <FilamentMapping
                printerId={effectivePrinterId!}
                filamentReqs={effectiveFilamentReqs}
                manualMappings={manualMappings}
                onManualMappingChange={(next) => {
                  setSharedMappingPrinterId(effectivePrinterId!);
                  setManualMappings(next);
                }}
                defaultExpanded={!!initialSelectedPrinterIds?.length || (settings?.per_printer_mapping_expanded ?? false)}
                currencySymbol={currencySymbol}
                defaultCostPerKg={defaultCostPerKg}
                forceColorMatch={forceColorMatch}
                onForceColorMatchChange={(slotId, value) =>
                  setForceColorMatch((prev) => ({ ...prev, [slotId]: value }))
                }
              />
            )}

            {/* Print options */}
            {(mode === 'create' || effectivePrinterCount > 0 || (assignmentMode === 'model' && targetModel)) && (
              <PrintOptionsPanel
                options={printOptions}
                onChange={setPrintOptions}
                defaultExpanded={!!initialSelectedPrinterIds?.length}
                showDualNozzleOptions={showDualNozzleOptions}
              />
            )}

            {/* Quantity — create multiple copies (batch). Hidden for multi-printer
                selection, and for multi-plate files where the per-plate steppers
                in PlateSelector own the number instead (#342). */}
            {mode !== 'edit-queue-item' && !usePerPlateQuantities
              && (assignmentMode === 'model' || selectedPrinters.length <= 1) && (
              <div className="flex items-center gap-3">
                <label htmlFor="printQuantity" className="text-sm text-bambu-gray whitespace-nowrap">
                  {t('queue.quantity', 'Quantity')}
                </label>
                <NumberField
                  id="printQuantity"
                  min={1}
                  max={999}
                  value={quantity}
                  onChange={(e) => setQuantity(Math.max(1, Math.min(999, parseInt(e.target.value) || 1)))}
                  className="w-20 px-2 py-1 text-sm bg-bambu-dark border border-bambu-dark-tertiary rounded text-white focus:outline-none focus:ring-1 focus:ring-bambu-green"
                />
                {quantity > 1 && (
                  <span className="text-xs text-bambu-gray">
                    {/* Separate jobs post the quantity once per listed file. */}
                    {t('queue.quantityHint', 'Creates {{count}} queue items', {
                      count: isSeparateJobs ? quantity * candidates.length : quantity,
                    })}
                  </span>
                )}
              </div>
            )}

            {/* Schedule options */}
            <ScheduleOptionsPanel
              options={scheduleOptions}
              onChange={setScheduleOptions}
              dateFormat={settings?.date_format || 'system'}
              timeFormat={settings?.time_format || 'system'}
              canControlPrinter={hasPermission('printers:control')}
              showStagger={!isEditing && assignmentMode === 'printer' && selectedPrinters.length > 1}
              printerCount={selectedPrinters.length}
              hasGcodeSnippets={!!settings?.has_gcode_snippets}
            />

            {/* Error message */}
            {updateQueueMutation.isError && (
              <div className="mb-4 p-3 bg-red-100 dark:bg-red-500/20 border border-red-500/50 rounded-lg text-sm text-red-700 dark:text-red-400">
                {(updateQueueMutation.error as Error)?.message || translateInterface("orders.runtimeInterface.failedToCompleteOperation")}
              </div>
            )}

            {!isMultiFile && isMultiPlate && plates.length > 1 && (
              <SelectedPlatesSummary plates={plates} selected={selectedPlates} />
            )}

            {waitingForAmsStatus && (
              <div className="mb-4 p-3 bg-blue-100 dark:bg-blue-500/20 border border-blue-500/50 rounded-lg text-sm text-blue-700 dark:text-blue-400 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                {t('printModal.waitingForAmsStatus', {
                  printer: printers?.find((p) => p.id === effectivePrinterId)?.name ?? '',
                })}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-2">
              <Button type="button" variant="secondary" onClick={onClose} className="flex-1" disabled={isSubmitting}>
                {translateInterface("common.cancel")}
              </Button>
              <Button
                type="submit"
                disabled={!canSubmit}
                className="flex-1"
              >
                {isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {modalConfig.loadingText}
                  </>
                ) : (
                  <>
                    <SubmitIcon className="w-4 h-4" />
                    {modalConfig.submitText}
                  </>
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {filamentWarningItems && filamentWarningItems.length > 0 && (
        <ConfirmModal
          title={t('printModal.insufficientFilamentTitle')}
          message={filamentWarningMessage}
          confirmText={t('printModal.printAnyway')}
          cancelText={t('common.cancel')}
          variant="warning"
          onConfirm={() => {
            const acknowledgedPrinters = [...new Set(filamentWarningItems.map(item => item.printerId))];
            setFilamentWarningItems(null);
            void handleSubmit(undefined, { skipFilamentCheck: true, acknowledgedPrinters });
          }}
          onCancel={() => setFilamentWarningItems(null)}
        />
      )}
    </div>
  );
}

// Re-export types for convenience
export type { PrintModalMode, PrintModalProps } from './types';
