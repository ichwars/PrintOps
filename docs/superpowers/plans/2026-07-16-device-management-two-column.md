# Device Management Two-Column Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the upper Devices settings surface as a responsive two-column layout with separate, visually consistent printer and dryer cards while leaving the full-width Virtual Printers section unchanged.

**Architecture:** `SettingsPage` owns the responsive page composition and places existing settings cards into two independent desktop columns. `frontend/src/components/settings/DeviceManagement.tsx` continues to own printer/dryer queries and mutations, but exposes focused `PrinterManagementCard` and `DryerManagementCard` components so each card can be placed in the correct column without duplicate visual nesting. Existing API contracts and Virtual Printer components remain unchanged.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, TanStack Query, Testing Library, Vitest, MSW, Vite, Chromium browser QA.

## Global Constraints

- The complete `VirtualPrinterList` area remains unchanged and full width.
- Large desktop layout uses two independent columns: left = FTP Retry then Printers; right = Default Printer then Dryers then Camera.
- Below the large desktop breakpoint, order is FTP Retry, Default Printer, Printers, Dryers, Camera, Virtual Printers.
- Printer accent is PrintOps green.
- Dryer accent is restrained blue/cyan.
- Primary add/save actions are PrintOps green; orange is removed from printer/dryer actions.
- Inactive states are gray, destructive actions are red, and warnings remain yellow.
- No API, data-model, calculation, FTP, camera, sidebar, or Virtual Printer behavior changes.
- Preserve the existing dark backgrounds, borders, radii, typography, and control heights.
- Do not overwrite unrelated working-tree changes; inspect generated `static/` output before staging it.

---

### Task 1: Lock Printer and Dryer Card Behavior with Component Tests

**Files:**
- Create: `frontend/src/__tests__/components/DeviceManagement.test.tsx`
- Test: `frontend/src/__tests__/components/DeviceManagement.test.tsx`

**Interfaces:**
- Consumes: `PrinterManagementCard({ locale }: { locale: string })` and `DryerManagementCard({ locale }: { locale: string })` from `frontend/src/components/settings/DeviceManagement.tsx`.
- Produces: Regression coverage for card separation, approved accents, add-form behavior, and preserved cost data.

- [ ] **Step 1: Write the printer/dryer fixtures and API handlers**

```tsx
import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import {
  DryerManagementCard,
  PrinterManagementCard,
} from '../../components/settings/DeviceManagement';

const printer = {
  id: 1,
  name: 'X1 Carbon',
  serial_number: '01S00A000000001',
  ip_address: '192.168.1.40',
  model: 'X1C',
  location: null,
  nozzle_count: 1,
  is_active: true,
  auto_archive: true,
  external_camera_url: null,
  external_camera_type: null,
  external_camera_enabled: false,
  external_camera_snapshot_url: null,
  camera_rotation: 0,
  plate_detection_enabled: false,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
  acquisition_date: '2025-01-15',
  acquisition_value: '1400.00',
  service_years: '5.00',
  annual_hours: '1200.00',
  maintenance_rate: '0.10',
  nominal_power_watts: '350.00',
  residual_value: '1120.00',
  hourly_rate: '0.48',
};

const dryer = {
  id: 7,
  equipment_type: 'dryer' as const,
  name: 'Filament Dryer Pro',
  is_active: true,
  acquisition_date: '2025-02-01',
  acquisition_value: '190.00',
  service_years: '4.00',
  annual_hours: '500.00',
  maintenance_rate: '0.10',
  nominal_power_watts: '250.00',
  residual_value: '142.50',
  hourly_rate: '0.12',
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

function useDeviceHandlers() {
  server.use(
    http.get('/api/v1/printers/', () => HttpResponse.json([printer])),
    http.get('/api/v1/equipment/', () => HttpResponse.json([dryer])),
  );
}
```

- [ ] **Step 2: Write the failing card-separation and color test**

```tsx
it('renders separate printer and dryer cards with approved accents', async () => {
  useDeviceHandlers();
  const { container } = render(
    <>
      <PrinterManagementCard locale="de" />
      <DryerManagementCard locale="de" />
    </>,
  );

  expect(await screen.findByRole('heading', { name: 'Drucker' })).toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: 'Trockner' })).toBeInTheDocument();
  expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
  expect(screen.getByText('Filament Dryer Pro')).toBeInTheDocument();
  expect(screen.getByText('1.120,00 €')).toBeInTheDocument();
  expect(screen.getByText('142,50 €')).toBeInTheDocument();

  expect(container.querySelector('[data-device-card="printers"]')).toHaveClass('border-bambu-dark-tertiary');
  expect(container.querySelector('[data-device-accent="printer"]')).toHaveClass('text-bambu-green');
  expect(container.querySelector('[data-device-accent="dryer"]')).toHaveClass('text-cyan-400');
  expect(container.querySelector('.bg-bambu-orange')).toBeNull();
});
```

- [ ] **Step 3: Write the failing non-destructive interaction test**

```tsx
it('opens and closes both inline add forms without submitting', async () => {
  useDeviceHandlers();
  const user = userEvent.setup();
  render(
    <>
      <PrinterManagementCard locale="de" />
      <DryerManagementCard locale="de" />
    </>,
  );

  await user.click(await screen.findByRole('button', { name: 'Drucker hinzufügen' }));
  expect(screen.getByLabelText('Seriennummer')).toBeInTheDocument();
  await user.click(screen.getAllByRole('button', { name: 'Abbrechen' })[0]);
  expect(screen.queryByLabelText('Seriennummer')).not.toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'Trockner hinzufügen' }));
  expect(screen.getByLabelText('Bezeichnung')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Abbrechen' }));
  expect(screen.queryByLabelText('Bezeichnung')).not.toBeInTheDocument();
});
```

- [ ] **Step 4: Run the focused test and verify it fails**

Run:

```bash
cd frontend
npx vitest run src/__tests__/components/DeviceManagement.test.tsx
```

Expected: FAIL because `PrinterManagementCard` and `DryerManagementCard` are not exported and the approved card structure does not exist.

- [ ] **Step 5: Commit the regression test**

```bash
git add frontend/src/__tests__/components/DeviceManagement.test.tsx
git commit -m "test(settings): cover device management cards"
```

---

### Task 2: Split and Restyle Printer and Dryer Management Cards

**Files:**
- Modify: `frontend/src/components/settings/DeviceManagement.tsx`
- Test: `frontend/src/__tests__/components/DeviceManagement.test.tsx`

**Interfaces:**
- Consumes: Existing `api.getPrinters`, `api.createPrinter`, `api.updatePrinter`, `api.getEquipment`, `api.createEquipment`, `api.updateEquipment`, and `api.deleteEquipment`.
- Produces:
  - `PrinterManagementCard({ locale }: { locale: string }): JSX.Element`
  - `DryerManagementCard({ locale }: { locale: string }): JSX.Element`
  - Shared local primitives `DeviceSectionHeader` and `DeviceMetric`.

- [ ] **Step 1: Update imports and shared state factories**

```tsx
import { useEffect, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
import { Button } from '../Button';

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
```

- [ ] **Step 2: Add shared section primitives and approved colors**

```tsx
const inputClass =
  'mt-1 h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-sm text-white outline-none transition-colors focus:border-bambu-green';

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
      {action}
    </header>
  );
}

function DeviceMetric({ label, value, accent = 'neutral' }: {
  label: string;
  value: string;
  accent?: 'neutral' | 'printer' | 'dryer';
}) {
  const valueClass = accent === 'printer'
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
```

- [ ] **Step 3: Implement the complete printer card state and mutations**

```tsx
export function PrinterManagementCard({ locale }: { locale: string }) {
  const de = locale.startsWith('de');
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
      className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary"
    >
      <DeviceSectionHeader
        icon={<PrinterIcon data-device-accent="printer" className="mt-0.5 h-5 w-5 text-bambu-green" />}
        title={de ? 'Drucker' : 'Printers'}
        description={de
          ? 'Verbindung, Betrieb und kaufmännische Kostenbasis zentral verwalten.'
          : 'Manage connectivity, operation, and commercial cost basis centrally.'}
        action={
          <Button size="sm" onClick={() => setPrinterDraft(initialPrinter())}>
            <Plus className="h-4 w-4" />
            {de ? 'Drucker hinzufügen' : 'Add printer'}
          </Button>
        }
      />
      <div className="space-y-4 p-4">
        {printerDraft && (
          <div className="grid gap-3 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-4 sm:grid-cols-2">
            {([
              ['name', de ? 'Bezeichnung' : 'Name'],
              ['serial_number', de ? 'Seriennummer' : 'Serial number'],
              ['ip_address', 'IP / Hostname'],
              ['access_code', de ? 'Zugriffscode' : 'Access code'],
            ] as Array<[keyof PrinterCreate, string]>).map(([key, label]) => (
              <label key={key} className="text-xs text-bambu-gray">
                {label}
                <input
                  type={key === 'access_code' ? 'password' : 'text'}
                  value={String(printerDraft[key] ?? '')}
                  onChange={(event) => setPrinterDraft({
                    ...printerDraft,
                    [key]: event.target.value,
                  })}
                  className={inputClass}
                />
              </label>
            ))}
            <div className="flex flex-wrap items-end justify-end gap-2 sm:col-span-2">
              <Button
                size="sm"
                onClick={() => createPrinter.mutate(printerDraft)}
                disabled={!printerDraft.name
                  || !printerDraft.serial_number
                  || !printerDraft.ip_address
                  || !printerDraft.access_code
                  || createPrinter.isPending}
              >
                {de ? 'Drucker speichern' : 'Save printer'}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setPrinterDraft(null)}>
                {de ? 'Abbrechen' : 'Cancel'}
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
          <p className="text-sm text-bambu-gray">
            {de ? 'Noch keine Drucker vorhanden.' : 'No printers configured.'}
          </p>
        )}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Replace the printer cost editor with the complete restyled implementation**

```tsx
function PrinterCostEditor({
  printer,
  locale,
  onSaved,
}: {
  printer: Printer;
  locale: string;
  onSaved: () => void;
}) {
  const de = locale.startsWith('de');
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
    mutationFn: () => api.updatePrinter(
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
    ['acquisition_date', de ? 'Anschaffungsdatum' : 'Acquisition date', 'date'],
    ['acquisition_value', de ? 'Anschaffungswert' : 'Acquisition value', 'number'],
    ['service_years', de ? 'Nutzungsdauer Jahre' : 'Service life years', 'number'],
    ['annual_hours', de ? 'Betriebsstunden/Jahr' : 'Operating hours/year', 'number'],
    ['maintenance_rate', de ? 'Wartung (0–1)' : 'Maintenance (0–1)', 'number'],
    ['nominal_power_watts', de ? 'Leistung Watt' : 'Power watts', 'number'],
  ];

  return (
    <article className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="font-semibold text-white">{printer.name}</h3>
          <p className="mt-0.5 text-xs text-bambu-gray">
            {printer.model || (de ? 'Modell nicht erkannt' : 'Model not detected')}
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-2 sm:min-w-64">
          <DeviceMetric
            label={de ? 'Restwert' : 'Residual value'}
            value={money(printer.residual_value)}
            accent="printer"
          />
          <DeviceMetric
            label={de ? 'Stundensatz' : 'Hourly rate'}
            value={`${money(printer.hourly_rate)}/h`}
            accent="printer"
          />
        </dl>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {fields.map(([key, label, type]) => (
          <label key={key} className="text-xs text-bambu-gray">
            {label}
            <input
              type={type}
              min={type === 'number' ? '0' : undefined}
              step="0.01"
              value={draft[key]}
              onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
              className={inputClass}
            />
          </label>
        ))}
      </div>
      <div className="mt-4 flex justify-end">
        <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
          {de ? 'Kostenwerte speichern' : 'Save cost values'}
        </Button>
      </div>
    </article>
  );
}
```

- [ ] **Step 5: Implement the complete dryer card state and mutations**

```tsx
export function DryerManagementCard({ locale }: { locale: string }) {
  const de = locale.startsWith('de');
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
    if (editingId) {
      update.mutate({ id: editingId, data: draft }, {
        onSuccess: () => {
          setDraft(null);
          setEditingId(null);
        },
      });
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
      className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary"
    >
      <DeviceSectionHeader
        icon={<Wind data-device-accent="dryer" className="mt-0.5 h-5 w-5 text-cyan-400" />}
        title={de ? 'Trockner' : 'Dryers'}
        description={de
          ? 'Zentrale Stammdaten für Trocknungs- und Kalkulationskosten.'
          : 'Central master data for drying and calculation costs.'}
        action={
          <Button size="sm" onClick={() => { setEditingId(null); setDraft(initialDryer()); }}>
            <Plus className="h-4 w-4" />
            {de ? 'Trockner hinzufügen' : 'Add dryer'}
          </Button>
        }
      />
      <div className="space-y-4 p-4">
        {draft && (
          <DryerForm
            draft={draft}
            de={de}
            pending={create.isPending || update.isPending}
            onChange={setDraft}
            onSave={saveDryer}
            onCancel={() => { setDraft(null); setEditingId(null); }}
          />
        )}
        {dryers.map((dryer) => (
          <DryerPanel
            key={dryer.id}
            dryer={dryer}
            locale={locale}
            de={de}
            onEdit={() => editDryer(dryer)}
            onToggle={() => update.mutate({ id: dryer.id, data: { is_active: !dryer.is_active } })}
            onDelete={() => remove.mutate(dryer.id)}
          />
        ))}
        {dryers.length === 0 && (
          <p className="text-sm text-bambu-gray">
            {de ? 'Noch keine Trockner angelegt.' : 'No dryers configured.'}
          </p>
        )}
      </div>
    </section>
  );
}
```

- [ ] **Step 6: Implement the complete dryer form**

```tsx
function DryerForm({
  draft,
  de,
  pending,
  onChange,
  onSave,
  onCancel,
}: {
  draft: EquipmentInput;
  de: boolean;
  pending: boolean;
  onChange: (draft: EquipmentInput) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  type DryerNumericField =
    | 'acquisition_value'
    | 'service_years'
    | 'annual_hours'
    | 'maintenance_rate'
    | 'nominal_power_watts';
  const fields: Array<[DryerNumericField, string]> = [
    ['acquisition_value', de ? 'Anschaffungswert' : 'Acquisition value'],
    ['service_years', de ? 'Nutzungsdauer Jahre' : 'Service life years'],
    ['annual_hours', de ? 'Betriebsstunden/Jahr' : 'Operating hours/year'],
    ['maintenance_rate', de ? 'Wartung (0–1)' : 'Maintenance (0–1)'],
    ['nominal_power_watts', de ? 'Leistung Watt' : 'Power watts'],
  ];

  return (
    <div className="grid gap-3 rounded-lg border border-cyan-500/20 bg-bambu-dark p-4 sm:grid-cols-2">
      <label className="text-xs text-bambu-gray">
        {de ? 'Bezeichnung' : 'Name'}
        <input
          value={draft.name}
          onChange={(event) => onChange({ ...draft, name: event.target.value })}
          className={inputClass}
        />
      </label>
      <label className="text-xs text-bambu-gray">
        {de ? 'Anschaffungsdatum' : 'Acquisition date'}
        <input
          type="date"
          value={draft.acquisition_date}
          onChange={(event) => onChange({ ...draft, acquisition_date: event.target.value })}
          className={inputClass}
        />
      </label>
      {fields.map(([key, label]) => (
        <label key={key} className="text-xs text-bambu-gray">
          {label}
          <input
            type="number"
            min="0"
            step="0.01"
            value={String(draft[key])}
            onChange={(event) => onChange({ ...draft, [key]: event.target.value })}
            className={inputClass}
          />
        </label>
      ))}
      <div className="flex flex-wrap items-end justify-end gap-2 sm:col-span-2">
        <Button size="sm" onClick={onSave} disabled={!draft.name || pending}>
          {de ? 'Speichern' : 'Save'}
        </Button>
        <Button size="sm" variant="secondary" onClick={onCancel}>
          {de ? 'Abbrechen' : 'Cancel'}
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Implement the dryer panel actions and metrics**

```tsx
function DryerPanel({
  dryer,
  locale,
  de,
  onEdit,
  onToggle,
  onDelete,
}: {
  dryer: Equipment;
  locale: string;
  de: boolean;
  onEdit: () => void;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const money = (value: string) =>
    new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR' }).format(Number(value));

  return (
    <article className="rounded-lg border border-cyan-500/20 bg-bambu-dark p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-white">{dryer.name}</h3>
            <span className={dryer.is_active
              ? 'rounded-full bg-bambu-green/15 px-2 py-0.5 text-xs text-bambu-green-light'
              : 'rounded-full bg-bambu-dark-tertiary px-2 py-0.5 text-xs text-bambu-gray'}
            >
              {dryer.is_active ? (de ? 'Aktiv' : 'Active') : (de ? 'Inaktiv' : 'Inactive')}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            aria-label={de ? 'Trockner bearbeiten' : 'Edit dryer'}
            onClick={onEdit}
            className="rounded-lg p-2 text-bambu-gray transition-colors hover:bg-bambu-dark-tertiary hover:text-white"
          >
            <Pencil className="h-4 w-4" />
          </button>
          <button
            type="button"
            aria-label={de ? 'Aktivstatus ändern' : 'Toggle active'}
            onClick={onToggle}
            className="rounded-lg p-2 text-bambu-gray transition-colors hover:bg-bambu-dark-tertiary hover:text-white"
          >
            <Power className="h-4 w-4" />
          </button>
          <button
            type="button"
            aria-label={de ? 'Trockner löschen' : 'Delete dryer'}
            onClick={onDelete}
            className="rounded-lg p-2 text-red-300 transition-colors hover:bg-red-500/10 hover:text-red-200"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-2">
        <DeviceMetric label={de ? 'Restwert' : 'Residual value'} value={money(dryer.residual_value)} accent="dryer" />
        <DeviceMetric label={de ? 'Stundensatz' : 'Hourly rate'} value={`${money(dryer.hourly_rate)}/h`} accent="dryer" />
        <DeviceMetric label={de ? 'Leistung' : 'Power'} value={`${Number(dryer.nominal_power_watts)} W`} />
        <DeviceMetric label={de ? 'Anschaffung' : 'Acquisition'} value={money(dryer.acquisition_value)} />
      </dl>
    </article>
  );
}
```

- [ ] **Step 8: Run the component tests**

Run:

```bash
cd frontend
npx vitest run src/__tests__/components/DeviceManagement.test.tsx
```

Expected: PASS, including add-form open/close behavior and absence of orange action styles.

- [ ] **Step 9: Commit the component refactor**

```bash
git add frontend/src/components/settings/DeviceManagement.tsx frontend/src/__tests__/components/DeviceManagement.test.tsx
git commit -m "feat(settings): restyle printer and dryer cards"
```

---

### Task 3: Compose the Responsive Two-Column Settings Layout

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx:4432-4436`
- Modify: `frontend/src/pages/SettingsPage.tsx:5324-5340`
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`
- Test: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

**Interfaces:**
- Consumes: `PrinterManagementCard` and `DryerManagementCard` from Task 2 plus existing `ftpRetryCard`, `defaultPrinterCard`, and `cameraSettingsCard`.
- Produces: `data-testid="device-settings-grid"` with two independent `xl` columns; `#card-vp` remains a following full-width sibling.

- [ ] **Step 1: Write the failing page-composition test**

Add a test to the SettingsPage rendering block:

```tsx
it('composes device settings in two desktop columns before the full-width virtual printers area', async () => {
  setSettingsTabUrl('printers-production');
  server.use(
    http.get('/api/v1/equipment/', () => HttpResponse.json([])),
  );

  render(<SettingsPage />);

  const grid = await screen.findByTestId('device-settings-grid');
  const left = within(grid).getByTestId('device-settings-left-column');
  const right = within(grid).getByTestId('device-settings-right-column');
  const virtualPrinters = document.getElementById('card-vp');

  expect(grid).toHaveClass('xl:grid-cols-2');
  expect(within(left).getByText('FTP Retry')).toBeInTheDocument();
  expect(within(left).getByRole('heading', { name: 'Printers' })).toBeInTheDocument();
  expect(within(right).getAllByText('Default Printer').length).toBeGreaterThan(0);
  expect(within(right).getByRole('heading', { name: 'Dryers' })).toBeInTheDocument();
  expect(within(right).getByText('External Cameras')).toBeInTheDocument();
  expect(within(grid).getByTestId('device-layout-ftp')).toHaveClass('order-1');
  expect(within(grid).getByTestId('device-layout-default-printer')).toHaveClass('order-2');
  expect(within(grid).getByTestId('device-layout-printers')).toHaveClass('order-3');
  expect(within(grid).getByTestId('device-layout-dryers')).toHaveClass('order-4');
  expect(within(grid).getByTestId('device-layout-camera')).toHaveClass('order-5');
  expect(virtualPrinters).not.toBeNull();
  expect(grid.compareDocumentPosition(virtualPrinters as Node) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(grid.contains(virtualPrinters)).toBe(false);
});
```

- [ ] **Step 2: Run the focused page test and verify it fails**

Run:

```bash
cd frontend
npx vitest run src/__tests__/pages/SettingsPage.test.tsx -t "composes device settings"
```

Expected: FAIL because the layout test IDs and separate management cards do not exist.

- [ ] **Step 3: Update imports and remove the old duplicate device blocks**

Replace:

```tsx
import { DeviceManagement } from '../components/settings/DeviceManagement';
```

with:

```tsx
import {
  DryerManagementCard,
  PrinterManagementCard,
} from '../components/settings/DeviceManagement';
```

Remove the earlier standalone `ftpRetryCard` rendering block and the later old `defaultPrinterCard` / `DeviceManagement` / `cameraSettingsCard` stack so each surface is rendered exactly once.

- [ ] **Step 4: Add the approved responsive composition**

Insert before `#card-vp`:

```tsx
{activeTab === 'printers-production' && printerProductionSubTab === 'devices' && (
  <div
    data-testid="device-settings-grid"
    className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-2 xl:items-start"
  >
    <div
      data-testid="device-settings-left-column"
      className="contents xl:block xl:space-y-4"
    >
      <div data-testid="device-layout-ftp" className="order-1">{ftpRetryCard}</div>
      <div data-testid="device-layout-printers" className="order-3 xl:order-none">
        <PrinterManagementCard locale={i18n.resolvedLanguage ?? 'en'} />
      </div>
    </div>

    <div
      data-testid="device-settings-right-column"
      className="contents xl:block xl:space-y-4"
    >
      <div data-testid="device-layout-default-printer" className="order-2">{defaultPrinterCard}</div>
      <div data-testid="device-layout-dryers" className="order-4 xl:order-none">
        <DryerManagementCard locale={i18n.resolvedLanguage ?? 'en'} />
      </div>
      <div data-testid="device-layout-camera" className="order-5 xl:order-none">{cameraSettingsCard}</div>
    </div>
  </div>
)}
```

The `contents` behavior preserves the approved mobile order while `xl:block` creates independent desktop columns. Do not move or modify:

```tsx
<div id="card-vp">
  <VirtualPrinterList />
</div>
```

- [ ] **Step 5: Run focused settings and component tests**

Run:

```bash
cd frontend
npx vitest run \
  src/__tests__/components/DeviceManagement.test.tsx \
  src/__tests__/pages/SettingsPage.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit the layout**

```bash
git add frontend/src/pages/SettingsPage.tsx frontend/src/__tests__/pages/SettingsPage.test.tsx
git commit -m "feat(settings): add two-column device layout"
```

---

### Task 4: Build, Browser-Verify, and Inspect Generated Assets

**Files:**
- Modify through build: `static/index.html`
- Modify through build: `static/assets/index-*.css`
- Modify through build: `static/assets/index-*.js`
- Verify: `frontend/src/components/settings/DeviceManagement.tsx`
- Verify: `frontend/src/pages/SettingsPage.tsx`
- Verify unchanged: `frontend/src/components/VirtualPrinterList.tsx`

**Interfaces:**
- Consumes: The completed UI from Tasks 2–3.
- Produces: Fresh production build and browser evidence for desktop, mobile, interactions, console health, and unchanged Virtual Printers layout.

- [ ] **Step 1: Run lint, targeted tests, and production build**

Run:

```bash
cd frontend
npx eslint src/components/settings/DeviceManagement.tsx src/pages/SettingsPage.tsx \
  src/__tests__/components/DeviceManagement.test.tsx src/__tests__/pages/SettingsPage.test.tsx
npx vitest run src/__tests__/components/DeviceManagement.test.tsx src/__tests__/pages/SettingsPage.test.tsx
npm run build
```

Expected:

- ESLint exit 0.
- Focused tests PASS.
- TypeScript and Vite build exit 0.
- Vite writes the current production bundle to `static/`.

- [ ] **Step 2: Inspect generated output without discarding prior user changes**

Run:

```bash
git status --short
git diff --stat
git diff -- static/index.html
```

Expected: Generated asset hash changes correspond to the new build. Do not delete, reset, or overwrite unrelated files. Confirm `docs/session-handoff-2026-07-16.md` remains untouched.

- [ ] **Step 3: Verify the live page in the Browser plugin**

The flow under test is:

```text
/settings?tab=printers-production
→ Devices subtab
→ two-column upper settings area
→ open and close printer/dryer add forms
→ unchanged full-width Virtual Printers section
```

Use the in-app Browser runtime:

```js
agent.browser.nameSession("PrintOps device management QA");
const tab = await browser.tabs.selected();
await tab.goto("http://127.0.0.1:8000/settings?tab=printers-production");
await tab.playwright.domSnapshot();
await tab.dev.logs({ levels: ["error", "warn"], limit: 50 });
await display(await tab.playwright.screenshot({ fullPage: false }));
```

Verify:

- URL and title identify PrintOps Devices settings.
- Page is not blank and no framework error overlay is visible.
- At a desktop viewport, FTP/Printers are left and Default Printer/Dryers/Camera are right.
- Printer green and dryer cyan accents are visually distinct.
- No orange printer/dryer action remains.
- Add Printer opens and Cancel restores the card.
- Add Dryer opens and Cancel restores the card.
- Virtual Printers remains outside the grid and spans the full content width.

- [ ] **Step 4: Verify responsive behavior**

Set a mobile-sized viewport supported by the Browser API, reload, and capture a screenshot. Confirm the order:

```text
FTP Retry
Default Printer
Printers
Dryers
Camera
Virtual Printers
```

Confirm no horizontal overflow, clipped fields, overlapping actions, or unreadable labels.

- [ ] **Step 5: Compare implementation screenshots with the approved references**

Use `view_image` on:

- `C:/Users/droth/AppData/Local/Temp/codex-clipboard-fb4e3bff-447d-4cd0-8441-e1b3f45ce1ca.png`
- `C:/Users/droth/AppData/Local/Temp/codex-clipboard-9b8c5647-899a-4c0a-84ab-a5e80b52c223.png`
- Latest desktop implementation screenshot
- Latest mobile implementation screenshot

Record a fidelity ledger covering at least:

1. Two-column composition.
2. Independent column heights.
3. Printer/dryer card hierarchy.
4. Green/cyan action and accent colors.
5. Virtual Printers full-width preservation.
6. Mobile order and overflow.

- [ ] **Step 6: Run final verification and commit**

Run:

```bash
cd frontend
npm run test:run
npm run build
```

Expected: Full frontend tests, i18n parity, TypeScript, and Vite build pass.

After inspecting the diff, stage only the intended source, tests, and generated build output:

```bash
git add \
  frontend/src/components/settings/DeviceManagement.tsx \
  frontend/src/pages/SettingsPage.tsx \
  frontend/src/__tests__/components/DeviceManagement.test.tsx \
  frontend/src/__tests__/pages/SettingsPage.test.tsx \
  static/index.html \
  static/assets
git commit -m "feat(settings): redesign device management"
```
