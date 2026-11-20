import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { SlotMaterial } from '../../api/client';
import { api } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import { useToast } from '../../contexts/ToastContext';
import { type PerPrinterConfig } from '../../hooks/useMultiPrinterFilamentMapping';
import { useDisplayCurrency } from '../../hooks/useDisplayCurrency';
import { toDateTimeLocalValue, parseUTCDate } from '../../utils/date';
import { isPlaceholderDate } from '../../utils/amsHelpers';
import { useFilamentPresetNames } from './useFilamentLabels';
import type { FilamentOverrideChoice } from './types';
import { type VariantCandidate } from './VariantCandidates';
import { commonModel, defaultMultiFileMode, duplicateModel, filesIncompatibleWith, type MultiFileMode } from './multiFile';
import type {
  AssignmentMode,
  PrintModalProps,
  PrintOptions,
  ScheduleOptions,
  ScheduleType,
} from './types';
import { DEFAULT_PRINT_OPTIONS, DEFAULT_SCHEDULE_OPTIONS } from './types';

export type FilamentWarningItem = {
  printerId: number;
  printerName: string;
  slotLabel: string;
  requiredGrams: number;
  remainingGrams: number;
  pooled: boolean;
};

export function usePrintModalSelection({
  mode, archiveId, libraryFileId, queueItem, initialSelectedPrinterIds, preselectPlateId,
  variantFiles, separateJobsAllowed, resumeSeparateJobs,
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

  return {
    translateInterface, t, queryClient, showToast, hasPermission, isLibraryFile, isEditing,
    isMultiFile, multiFileMode, isCrossModel, isSeparateJobs, setPartlyQueued, queuedPairs,
    setQueuedPairs, asapPositionsTaken, setAsapPositionsTaken, runItemIds, setRunItemIds,
    runBatchIds, setRunBatchIds, showModeToggle, editingVariants, hasEditingVariants,
    candidates, setCandidates, candidatePlates, setCandidatePlates, candidatePlatesReady,
    setCandidatePlatesReady, selectedPrinters, setSelectedPrinters, selectedPlates,
    setSelectedPlates, selectedPlate, quantity, setQuantity, plateQuantities,
    setPlateQuantities, printOptions, setPrintOptions, scheduleOptions, setScheduleOptions,
    manualMappings, setManualMappings, sharedMappingPrinterId, setSharedMappingPrinterId,
    perPrinterConfigs, setPerPrinterConfigs, assignmentMode, setAssignmentMode, targetModel,
    setTargetModel, targetLocation, setTargetLocation, filamentOverrides, setFilamentOverrides,
    forceColorMatch, setForceColorMatch, initialPrinterIds, initialPlateId, isSubmitting,
    setIsSubmitting, submitProgress, setSubmitProgress, filamentWarningItems,
    setFilamentWarningItems, initialExpandApplied, setInitialExpandApplied,
    effectivePrinterCount, effectivePrinterId, settings, currencySymbol, defaultCostPerKg,
    filamentPresetNames, printers, loadingPrinters, inventoryByTrayIdPerPrinter,
    slotMaterialsPerPrinter, archiveDetailsPending, libraryDetailsPending, slicedForModel,
    selectorModel, separateJobsIncompatible, handleMultiFileModeChange,
  };
}
