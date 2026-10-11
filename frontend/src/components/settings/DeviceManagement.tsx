import { useEffect, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Pencil,
  Plus,
  Power,
  Printer as PrinterIcon,
  Trash2,
  Wind,
} from 'lucide-react';
import {
  api,
  type Equipment,
  type EquipmentInput,
  type Printer,
  type PrinterCreate,
} from '../../api/client';
import { Button, DatePicker, IconButton, NumberField, TextField } from '../ui';
import { resolveSupportedLanguage } from '../../i18n';

function useDeviceTranslation(locale: string) {
  const language = resolveSupportedLanguage(locale);
  const { t } = useTranslation(undefined, { lng: language });
  return (key: string) => t(`orders.runtimeDevice.${key}`, { lng: language });
}

const inputClass =
  'mt-1 h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-sm text-white outline-none transition-colors focus:border-bambu-green';
const numberInputClass =
  'h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-sm text-white outline-none transition-colors focus:border-bambu-green';

const initialDryer = (): EquipmentInput => ({
  equipment_type: 'dryer',
  name: '',
  is_active: true,
  acquisition_date: new Date().toISOString().slice(0, 10),
  acquisition_value: '0',
  service_years: '4',
  annual_hours: '500',
  maintenance_rate: '0.10',
  nominal_power_watts: '250',
});

const initialPrinter = (): PrinterCreate => ({
  name: '',
  serial_number: '',
  ip_address: '',
  access_code: '',
  auto_archive: true,
  is_active: true,
});

function DeviceSectionHeader({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  action: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 border-b border-bambu-dark-tertiary px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        {icon}
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-white">{title}</h2>
          <p className="mt-0.5 text-xs leading-5 text-bambu-gray">{description}</p>
        </div>
      </div>
      <div className="shrink-0">{action}</div>
    </header>
  );
}

function DeviceMetric({
  label,
  value,
  accent = 'neutral',
}: {
  label: string;
  value: string;
  accent?: 'neutral' | 'printer' | 'dryer';
}) {
  const valueClass =
    accent === 'printer'
      ? 'text-bambu-green-light'
      : accent === 'dryer'
        ? 'text-cyan-300'
        : 'text-white';

  return (
    <div className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary/70 px-3 py-2">
      <dt className="text-[11px] text-bambu-gray">{label}</dt>
      <dd className={`mt-0.5 text-sm font-semibold ${valueClass}`}>{value}</dd>
    </div>
  );
}

export function PrinterManagementCard({ locale }: { locale: string }) {
  const tr = useDeviceTranslation(locale);
  const queryClient = useQueryClient();
  const { data: printers = [] } = useQuery({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  });
  const [printerDraft, setPrinterDraft] = useState<PrinterCreate | null>(null);
  const createPrinter = useMutation({
    mutationFn: api.createPrinter,
    onSuccess: () => {
      setPrinterDraft(null);
      void queryClient.invalidateQueries({ queryKey: ['printers'] });
    },
  });

  return (
    <section
      data-device-card="printers"
      className="overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary"
    >
      <DeviceSectionHeader
        icon={
          <PrinterIcon
            data-device-accent="printer"
            className="mt-0.5 h-5 w-5 shrink-0 text-bambu-green"
          />
        }
        title={tr('printersTitle')}
        description={tr('printersDescription')}
        action={
          <Button size="sm" onClick={() => setPrinterDraft(initialPrinter())}>
            <Plus className="h-4 w-4" />
            {tr('addPrinter')}
          </Button>
        }
      />

      <div className="space-y-4 p-4">
        {printerDraft && (
          <div className="grid gap-3 rounded-lg border border-bambu-green/20 bg-bambu-dark p-4 sm:grid-cols-2">
            {(
              [
                ['name', tr('name')],
                ['serial_number', tr('serialNumber')],
                ['ip_address', tr('host')],
                ['access_code', tr('accessCode')],
              ] as Array<[keyof PrinterCreate, string]>
            ).map(([key, label]) => (
              <TextField
                  key={key}
                  label={label}
                  type={key === 'access_code' ? 'password' : 'text'}
                  value={String(printerDraft[key] ?? '')}
                  onValueChange={(value) =>
                    setPrinterDraft({
                      ...printerDraft,
                      [key]: value,
                    })
                  }
                  className={inputClass}
                />
            ))}
            <div className="flex flex-wrap items-end justify-end gap-2 sm:col-span-2">
              <Button
                size="sm"
                onClick={() => createPrinter.mutate(printerDraft)}
                disabled={
                  !printerDraft.name ||
                  !printerDraft.serial_number ||
                  !printerDraft.ip_address ||
                  !printerDraft.access_code ||
                  createPrinter.isPending
                }
              >
                {tr('savePrinter')}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setPrinterDraft(null)}>
                {tr('cancel')}
              </Button>
            </div>
          </div>
        )}

        {printers.map((printer) => (
          <PrinterCostEditor
            key={printer.id}
            printer={printer}
            locale={locale}
            onSaved={() => void queryClient.invalidateQueries({ queryKey: ['printers'] })}
          />
        ))}

        {printers.length === 0 && (
          <p className="rounded-lg border border-dashed border-bambu-dark-tertiary px-4 py-6 text-center text-sm text-bambu-gray">
            {tr('printersEmpty')}
          </p>
        )}
      </div>
    </section>
  );
}

function PrinterCostEditor({
  printer,
  locale,
  onSaved,
}: {
  printer: Printer;
  locale: string;
  onSaved: () => void;
}) {
  const tr = useDeviceTranslation(locale);
  const [draft, setDraft] = useState({
    acquisition_date: printer.acquisition_date ?? '',
    acquisition_value: printer.acquisition_value ?? '',
    service_years: printer.service_years ?? '',
    annual_hours: printer.annual_hours ?? '',
    maintenance_rate: printer.maintenance_rate ?? '',
    nominal_power_watts: printer.nominal_power_watts ?? '',
  });

  useEffect(() => {
    setDraft({
      acquisition_date: printer.acquisition_date ?? '',
      acquisition_value: printer.acquisition_value ?? '',
      service_years: printer.service_years ?? '',
      annual_hours: printer.annual_hours ?? '',
      maintenance_rate: printer.maintenance_rate ?? '',
      nominal_power_watts: printer.nominal_power_watts ?? '',
    });
  }, [printer]);

  const save = useMutation({
    mutationFn: () =>
      api.updatePrinter(
        printer.id,
        Object.fromEntries(
          Object.entries(draft).map(([key, value]) => [key, value || null]),
        ),
      ),
    onSuccess: onSaved,
  });

  const money = (value: string | null) =>
    value == null
      ? '–'
      : new Intl.NumberFormat(locale, {
          style: 'currency',
          currency: 'EUR',
        }).format(Number(value));

  const fields: Array<[keyof typeof draft, string, string]> = [
    ['acquisition_date', tr('acquisitionDate'), 'date'],
    ['acquisition_value', tr('acquisitionValue'), 'number'],
    ['service_years', tr('serviceYears'), 'number'],
    ['annual_hours', tr('annualHours'), 'number'],
    ['maintenance_rate', tr('maintenanceRate'), 'number'],
    ['nominal_power_watts', tr('powerWatts'), 'number'],
  ];

  return (
    <article className="rounded-lg border border-bambu-green/15 bg-bambu-dark p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-white">{printer.name}</h3>
          <p className="mt-0.5 text-xs text-bambu-gray">
            {printer.model || tr('modelNotDetected')}
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-2 sm:min-w-64">
          <DeviceMetric
            label={tr('residualValue')}
            value={money(printer.residual_value)}
            accent="printer"
          />
          <DeviceMetric
            label={tr('hourlyRate')}
            value={`${money(printer.hourly_rate)}/h`}
            accent="printer"
          />
        </dl>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {fields.map(([key, label, type]) =>
          type === 'date' ? (
            <DatePicker
              key={key}
              label={label}
              locale={locale}
              value={draft[key]}
              onValueChange={(value) => setDraft({ ...draft, [key]: value })}
            />
          ) : (
            <NumberField
              key={key}
              label={label}
              min="0"
              step="0.01"
              value={draft[key]}
              onValueChange={(value) => setDraft({ ...draft, [key]: value })}
              containerClassName="mt-1"
              className={numberInputClass}
            />
          ),
        )}
      </div>

      <div className="mt-4 flex justify-end">
        <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
          {tr('saveCostValues')}
        </Button>
      </div>
    </article>
  );
}

export function DryerManagementCard({ locale }: { locale: string }) {
  const tr = useDeviceTranslation(locale);
  const queryClient = useQueryClient();
  const { data: dryers = [] } = useQuery({
    queryKey: ['equipment'],
    queryFn: () => api.getEquipment(),
  });
  const [draft, setDraft] = useState<EquipmentInput | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);

  const create = useMutation({
    mutationFn: api.createEquipment,
    onSuccess: () => {
      setDraft(null);
      void queryClient.invalidateQueries({ queryKey: ['equipment'] });
    },
  });
  const update = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<EquipmentInput> }) =>
      api.updateEquipment(id, data),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['equipment'] }),
  });
  const remove = useMutation({
    mutationFn: api.deleteEquipment,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['equipment'] }),
  });

  const saveDryer = () => {
    if (!draft) return;
    if (editingId !== null) {
      update.mutate(
        { id: editingId, data: draft },
        {
          onSuccess: () => {
            setDraft(null);
            setEditingId(null);
          },
        },
      );
      return;
    }
    create.mutate(draft);
  };

  const editDryer = (dryer: Equipment) => {
    setEditingId(dryer.id);
    setDraft({
      equipment_type: 'dryer',
      name: dryer.name,
      is_active: dryer.is_active,
      acquisition_date: dryer.acquisition_date,
      acquisition_value: dryer.acquisition_value,
      service_years: dryer.service_years,
      annual_hours: dryer.annual_hours,
      maintenance_rate: dryer.maintenance_rate,
      nominal_power_watts: dryer.nominal_power_watts,
    });
  };

  return (
    <section
      data-device-card="dryers"
      className="overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary"
    >
      <DeviceSectionHeader
        icon={
          <Wind
            data-device-accent="dryer"
            className="mt-0.5 h-5 w-5 shrink-0 text-cyan-400"
          />
        }
        title={tr('dryersTitle')}
        description={tr('dryersDescription')}
        action={
          <Button
            size="sm"
            onClick={() => {
              setEditingId(null);
              setDraft(initialDryer());
            }}
          >
            <Plus className="h-4 w-4" />
            {tr('addDryer')}
          </Button>
        }
      />

      <div className="space-y-4 p-4">
        {draft && (
          <DryerForm
            draft={draft}
            locale={locale}
            pending={create.isPending || update.isPending}
            onChange={setDraft}
            onSave={saveDryer}
            onCancel={() => {
              setDraft(null);
              setEditingId(null);
            }}
          />
        )}

        {dryers.map((dryer) => (
          <DryerPanel
            key={dryer.id}
            dryer={dryer}
            locale={locale}
            onEdit={() => editDryer(dryer)}
            onToggle={() =>
              update.mutate({
                id: dryer.id,
                data: { is_active: !dryer.is_active },
              })
            }
            onDelete={() => remove.mutate(dryer.id)}
          />
        ))}

        {dryers.length === 0 && (
          <p className="rounded-lg border border-dashed border-cyan-500/20 px-4 py-6 text-center text-sm text-bambu-gray">
            {tr('dryersEmpty')}
          </p>
        )}
      </div>
    </section>
  );
}

function DryerForm({
  draft,
  locale,
  pending,
  onChange,
  onSave,
  onCancel,
}: {
  draft: EquipmentInput;
  locale: string;
  pending: boolean;
  onChange: (draft: EquipmentInput) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const tr = useDeviceTranslation(locale);
  type DryerNumericField =
    | 'acquisition_value'
    | 'service_years'
    | 'annual_hours'
    | 'maintenance_rate'
    | 'nominal_power_watts';

  const fields: Array<[DryerNumericField, string]> = [
    ['acquisition_value', tr('acquisitionValue')],
    ['service_years', tr('serviceYears')],
    ['annual_hours', tr('annualHours')],
    ['maintenance_rate', tr('maintenanceRate')],
    ['nominal_power_watts', tr('powerWatts')],
  ];

  return (
    <div className="grid gap-3 rounded-lg border border-cyan-500/20 bg-bambu-dark p-4 sm:grid-cols-2">
      <TextField
          label={tr('name')}
          value={draft.name}
          onValueChange={(value) => onChange({ ...draft, name: value })}
          className={inputClass}
        />
      <DatePicker
          label={tr('acquisitionDate')}
          locale={locale}
          value={draft.acquisition_date}
          onValueChange={(value) => onChange({ ...draft, acquisition_date: value })}
        />
      {fields.map(([key, label]) => (
          <NumberField
            key={key}
            label={label}
            min="0"
            step="0.01"
            value={String(draft[key])}
            onValueChange={(value) => onChange({ ...draft, [key]: value })}
            containerClassName="mt-1"
            className={numberInputClass}
          />
      ))}
      <div className="flex flex-wrap items-end justify-end gap-2 sm:col-span-2">
        <Button size="sm" onClick={onSave} disabled={!draft.name || pending}>
          {tr('save')}
        </Button>
        <Button size="sm" variant="secondary" onClick={onCancel}>
          {tr('cancel')}
        </Button>
      </div>
    </div>
  );
}

function DryerPanel({
  dryer,
  locale,
  onEdit,
  onToggle,
  onDelete,
}: {
  dryer: Equipment;
  locale: string;
  onEdit: () => void;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const tr = useDeviceTranslation(locale);
  const money = (value: string) =>
    new Intl.NumberFormat(locale, {
      style: 'currency',
      currency: 'EUR',
    }).format(Number(value));

  return (
    <article className="rounded-lg border border-cyan-500/20 bg-bambu-dark p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-white">{dryer.name}</h3>
            <span
              className={
                dryer.is_active
                  ? 'rounded-full bg-bambu-green/15 px-2 py-0.5 text-xs text-bambu-green-light'
                  : 'rounded-full bg-bambu-dark-tertiary px-2 py-0.5 text-xs text-bambu-gray'
              }
            >
              {dryer.is_active ? tr('active') : tr('inactive')}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <IconButton
            label={tr('editDryer')}
            icon={Pencil}
            onClick={onEdit}
          />
          <IconButton
            label={tr('toggleActive')}
            icon={Power}
            onClick={onToggle}
          />
          <IconButton
            label={tr('deleteDryer')}
            icon={Trash2}
            onClick={onDelete}
            className="text-red-300 hover:bg-red-500/10 hover:text-red-200"
          />
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-2">
        <DeviceMetric
          label={tr('residualValue')}
          value={money(dryer.residual_value)}
          accent="dryer"
        />
        <DeviceMetric
          label={tr('hourlyRate')}
          value={`${money(dryer.hourly_rate)}/h`}
          accent="dryer"
        />
        <DeviceMetric
          label={tr('power')}
          value={`${Number(dryer.nominal_power_watts)} W`}
        />
        <DeviceMetric
          label={tr('acquisition')}
          value={money(dryer.acquisition_value)}
        />
      </dl>
    </article>
  );
}

export function DeviceManagement({ locale }: { locale: string }) {
  return (
    <div className="space-y-4">
      <PrinterManagementCard locale={locale} />
      <DryerManagementCard locale={locale} />
    </div>
  );
}
