import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api, type InventorySpool, type PrinterStatus } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { canonicalFilamentType, formatSlotLabel } from '../utils/amsHelpers';
import { invalidateSpoolAndLocationQueries, inventoryLocationsQueryKey } from '../utils/inventoryQueries';
import { Button } from './Button';
import { QrSpoolScanner } from './QrSpoolScanner';
import { LegacySelect, Modal } from './ui';

type Slot = { id: string; amsId: number; trayId: number; label: string; material: string | null };

function printerSlots(status: PrinterStatus): Slot[] {
  const slots = status.ams.flatMap(unit => {
    const amsId = Number(unit.id);
    return unit.tray.map(tray => {
      const trayId = Number(tray.id);
      return {
        id: `${amsId}:${trayId}`, amsId, trayId,
        label: formatSlotLabel(amsId, trayId, amsId >= 128, false), material: tray.tray_type,
      };
    });
  });
  return [...slots, ...status.vt_tray.flatMap(tray => {
    const trayId = Number(tray.id) - 254;
    if (trayId !== 0 && trayId !== 1) return [];
    const label = status.vt_tray.length > 1 ? (trayId === 0 ? 'Ext-L' : 'Ext-R') : 'Ext';
    return [{ id: `255:${trayId}`, amsId: 255, trayId, label, material: tray.tray_type }];
  })];
}

interface Props {
  spoolmanMode: boolean;
  onClose: () => void;
  onAssigned?: () => void;
  fixedSlot?: { printerId: number; amsId: number; trayId: number; label: string; material: string | null };
}

export function QrAssignTargetModal({ spoolmanMode, onClose, onAssigned, fixedSlot }: Props) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const canUseAms = hasPermission('printers:read') && (!spoolmanMode || hasPermission('printers:ams_rfid'));
  const [kind, setKind] = useState<'location' | 'ams'>('location');
  const [locationId, setLocationId] = useState(0);
  const [printerId, setPrinterId] = useState(0);
  const [slotId, setSlotId] = useState('');
  const [spool, setSpool] = useState<InventorySpool | null>(null);
  const [scanNumber, setScanNumber] = useState(0);

  const locations = useQuery({ queryKey: inventoryLocationsQueryKey, queryFn: api.getLocations, enabled: !fixedSlot });
  const printers = useQuery({ queryKey: ['printers'], queryFn: api.getPrinters, enabled: canUseAms && kind === 'ams' });
  const status = useQuery({
    queryKey: ['printerStatus', printerId], queryFn: () => api.getPrinterStatus(printerId),
    enabled: canUseAms && kind === 'ams' && printerId > 0,
  });
  const slots = status.data?.connected ? printerSlots(status.data) : [];
  const location = locations.data?.find(row => row.id === locationId);
  const slot = slots.find(row => row.id === slotId);
  const printer = printers.data?.find(row => row.id === printerId);
  const target = fixedSlot && canUseAms
    ? { kind: 'ams' as const, slot: fixedSlot, printer: { id: fixedSlot.printerId, name: '' } }
    : kind === 'ams' && canUseAms && slot && printer
    ? { kind: 'ams' as const, slot, printer }
    : kind === 'location' && location ? { kind: 'location' as const, location } : null;
  const targetName = target?.kind === 'ams' ? [target.printer.name, target.slot.label].filter(Boolean).join(' · ') : target?.location.name;

  const read = useMutation({
    mutationFn: async (payload: string) => {
      const resolved = await api.resolveSpoolLabel(payload);
      if ((resolved.source === 'spoolman') !== spoolmanMode) throw new Error(t('inventory.qrAssign.wrongInventory'));
      const result = await (spoolmanMode
        ? api.getSpoolmanInventorySpool(resolved.spool_id)
        : api.getSpool(resolved.spool_id));
      if (result.archived_at) throw new Error(t('inventory.qrAssign.archived'));
      return result;
    },
    onSuccess: setSpool,
  });
  const assign = useMutation({
    mutationFn: async ({ selected, destination }: { selected: InventorySpool; destination: NonNullable<typeof target> }) => {
      if (destination.kind === 'location') {
        const data = { location_id: destination.location.id };
        if (spoolmanMode) await api.updateSpoolmanInventorySpool(selected.id, data);
        else await api.updateSpool(selected.id, data);
        return false;
      }
      const data = {
        printer_id: destination.printer.id, ams_id: destination.slot.amsId, tray_id: destination.slot.trayId, move: true,
      };
      if (spoolmanMode) {
        await api.assignSpoolmanSlot({ spoolman_spool_id: selected.id, ...data });
        return false;
      }
      const result = await api.assignSpool({ spool_id: selected.id, ...data });
      return result.pending_config;
    },
    onSuccess: (pending, variables) => {
      const destination = variables.destination;
      const cache = spoolmanMode ? 'spoolman-inventory-spools' : 'inventory-spools';
      const detail = spoolmanMode ? 'spoolman-inventory-spool' : 'inventory-spool';
      void invalidateSpoolAndLocationQueries(queryClient, [cache]);
      void queryClient.invalidateQueries({ queryKey: [detail, variables.selected.id] });
      if (destination.kind === 'ams') {
        void queryClient.invalidateQueries({ queryKey: ['spool-assignments'] });
        void queryClient.invalidateQueries({ queryKey: ['spoolman-slot-assignments'] });
        void queryClient.invalidateQueries({ queryKey: ['printerStatus', destination.printer.id] });
      }
      const name = destination.kind === 'ams'
        ? [destination.printer.name, destination.slot.label].filter(Boolean).join(' · ') : destination.location.name;
      showToast(pending ? t('inventory.assignPendingInsert') : t('inventory.qrAssign.assigned', { target: name }), 'success');
      setSpool(null);
      setScanNumber(value => value + 1);
      onAssigned?.();
    },
  });
  const busy = read.isPending || assign.isPending;
  const error = read.error ?? assign.error ?? locations.error ?? (kind === 'ams' ? printers.error ?? status.error : null);
  const slotMaterial = target?.kind === 'ams' ? target.slot.material : null;
  const materialMismatch = slotMaterial && spool?.material
    && canonicalFilamentType(slotMaterial) !== canonicalFilamentType(spool.material);

  return <Modal open title={t('inventory.qrAssign.title')} closeLabel={t('common.close')}
    onClose={() => { if (!busy) onClose(); }} closeDisabled={busy}>
    <div className="space-y-4">
      {!fixedSlot && canUseAms && <label className="block text-sm text-white">
        {t('inventory.qrAssign.target')}
        <LegacySelect className="mt-1 w-full" aria-label={t('inventory.qrAssign.target')} value={kind} disabled={busy}
          onChange={event => { setKind(event.target.value === 'ams' ? 'ams' : 'location'); assign.reset(); }}>
          <option value="location">{t('inventory.storageLocation')}</option>
          <option value="ams">{t('inventory.qrAssign.ams')}</option>
        </LegacySelect>
      </label>}
      {!fixedSlot && kind === 'location' && <label className="block text-sm text-white">
        {t('inventory.storageLocation')}
        <LegacySelect className="mt-1 w-full" aria-label={t('inventory.storageLocation')} value={locationId}
          disabled={busy || locations.isPending} onChange={event => { setLocationId(Number(event.target.value)); assign.reset(); }}>
          <option value="0">{t('inventory.qrAssign.chooseLocation')}</option>
          {locations.data?.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
        </LegacySelect>
      </label>}
      {kind === 'ams' && canUseAms && <>
        <label className="block text-sm text-white">
          {t('inventory.qrAssign.printer')}
          <LegacySelect className="mt-1 w-full" aria-label={t('inventory.qrAssign.printer')} value={printerId}
            disabled={busy || printers.isPending} onChange={event => {
              setPrinterId(Number(event.target.value)); setSlotId(''); assign.reset();
            }}>
            <option value="0">{t('inventory.qrAssign.choosePrinter')}</option>
            {printers.data?.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
          </LegacySelect>
        </label>
        {printer && <label className="block text-sm text-white">
          {t('inventory.qrAssign.ams')}
          <LegacySelect className="mt-1 w-full" aria-label={t('inventory.qrAssign.ams')} value={slotId}
            disabled={busy || status.isPending} onChange={event => { setSlotId(event.target.value); assign.reset(); }}>
            <option value="">{t('inventory.qrAssign.chooseSlot')}</option>
            {slots.map(row => <option key={row.id} value={row.id}>{row.label}</option>)}
          </LegacySelect>
        </label>}
      </>}
      {target && !spool && <QrSpoolScanner key={scanNumber} disabled={busy}
        onPayload={payload => { assign.reset(); read.mutate(payload); }} />}
      {spool && <div className="space-y-2">
        <p className="text-sm text-white">#{spool.id} · {[spool.brand, spool.material, spool.subtype, spool.color_name].filter(Boolean).join(' ')}</p>
        {target?.kind === 'ams' && materialMismatch && <p className="text-sm text-amber-400">
          {t('inventory.qrAssign.mismatch', { spool: spool.material, slot: target.slot.material })}
        </p>}
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy || !target} onClick={() => target && assign.mutate({ selected: spool, destination: target })}>
            {t('inventory.qrAssign.assign', { target: targetName ?? '' })}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => { setSpool(null); assign.reset(); }}>
            {t('inventory.qrAssign.scanAgain')}
          </Button>
        </div>
      </div>}
      {read.isPending && <p role="status" className="text-sm text-bambu-gray">{t('common.loading')}</p>}
      {error && <p role="status" className="text-sm text-red-400">{error.message}</p>}
    </div>
  </Modal>;
}
