import { isValidElement, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router';
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  BarChart3,
  BatteryCharging,
  CalendarDays,
  CircleDollarSign,
  ClipboardList,
  Clock,
  Download,
  Factory,
  Gauge,
  Lightbulb,
  Package,
  Receipt,
  TrendingUp,
  Truck,
  Warehouse,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import {
  api,
  type ArchiveEnergyHistoryPoint,
  type ArchiveSlim,
  type ArchiveStats,
  type FilamentSkuSettings,
  type InventorySpool,
} from '../api/client';
import { documentManagementApi, type CommercialDocument, type PaymentMethod } from '../api/documentManagement';
import { offersApi, ordersApi, type CustomerOrder, type Offer, type StockReservation } from '../api/offers';
import {
  procurementOffersApi,
  suppliersApi,
  type ProcurementOffer,
  type ProcurementResource,
  type Supplier,
} from '../api/procurement';
import { smallPartsApi, type SmallPart } from '../api/smallParts';
import { Select } from '../components/ui';
import { useAuth } from '../contexts/AuthContext';
import { useDisplayCurrency } from '../hooks/useDisplayCurrency';
import { formatMoney } from '../utils/calculationFormatting';
import i18n, { resolveSupportedLanguage } from '../i18n';

// Read the current catalog when display labels are constructed. The page
// subscribes through useTranslation to refresh helpers and localized rows.
function dashboardText(key: string, values?: Record<string, string | number>) {
  return i18n.t(`orders.runtimeDashboard.${key}`, {
    ...values, lng: resolveSupportedLanguage(i18n.language || 'en'),
  });
}

const dashboardPaymentMethod = (method: PaymentMethod) => dashboardText(`paymentMethods.${method}`);

function dashboardEnergySource(source: string | null | undefined, fallback: string) {
  if (!source) return fallback;
  return ['smart_plug_live', 'smart_plug_snapshots', 'print_logs'].includes(source)
    ? dashboardText(`energySources.${source}`)
    : source;
}

type DashboardTab = 'overview' | 'revenue' | 'margin' | 'inventory' | 'energy';
type Tone = 'green' | 'blue' | 'amber' | 'red' | 'violet' | 'cyan' | 'neutral';
type DateRangeValue = '7' | '30' | '90' | '365';

type CostSlice = {
  label: string;
  value: number;
  color: string;
};

type MaterialUsage = {
  label: string;
  kind: 'filament' | 'small_part';
  grams: number;
  value: number;
  remaining: number;
  days: number;
  unitLabel?: string;
  lowStock?: boolean;
};

type RevenueRow = {
  number: string;
  customer: string;
  status: 'paid' | 'partially_paid' | 'unpaid' | 'overdue' | 'completed' | 'active' | 'offer' | 'missing_payment_source';
  amount: number;
  due: string;
  to: string;
};

type PipelineStage = {
  label: string;
  value: number;
  color: string;
};

type TrendPoint = {
  label: string;
  revenue: number;
  costs: number;
  energy: number;
  margin: number;
};

type TooltipLine = {
  label: string;
  value: string;
};

type MetricTrend = {
  label: string;
  direction: 'up' | 'down' | 'flat';
  positive?: boolean;
};

type ActionShortcut = {
  label: string;
  detail: string;
  to: string;
  icon: LucideIcon;
  tone: Tone;
};

type SpoolProcurementResource = Extract<ProcurementResource, { kind: 'filament' }>;

type DashboardProcurementResource = {
  signature: string;
  resource: SpoolProcurementResource;
};

const tabs: Array<{ value: DashboardTab; label: string; icon: LucideIcon }> = [
  { value: 'overview', get label() { return dashboardText('overview'); }, icon: BarChart3 },
  { value: 'revenue', get label() { return dashboardText('revenue'); }, icon: Receipt },
  { value: 'margin', get label() { return dashboardText('costsMargin'); }, icon: CircleDollarSign },
  { value: 'inventory', get label() { return dashboardText('inventoryUsage'); }, icon: Warehouse },
  { value: 'energy', get label() { return dashboardText('energy'); }, icon: Zap },
];

const dateRangeOptions: Array<{ value: DateRangeValue; days: number; label: string }> = [
  { value: '7', days: 7, get label() { return dashboardText('last7Days'); } },
  { value: '30', days: 30, get label() { return dashboardText('last30Days'); } },
  { value: '90', days: 90, get label() { return dashboardText('last90Days'); } },
  { value: '365', days: 365, get label() { return dashboardText('last12Months'); } },
];

const isDashboardTab = (value: string | null): value is DashboardTab =>
  tabs.some((tab) => tab.value === value);

const isDateRangeValue = (value: string | null): value is DateRangeValue =>
  dateRangeOptions.some((option) => option.value === value);

const surface = {
  panel: 'rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4 shadow-sm',
  panelQuiet: 'rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-4',
  tile: 'rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary',
  rail: 'var(--bg-tertiary)',
};

const toneClasses: Record<Tone, { bg: string; text: string; bar: string }> = {
  green: { bg: 'bg-[#0f2b1d]', text: 'text-[#35c46f]', bar: 'bg-[#00a14a]' },
  blue: { bg: 'bg-[#102737]', text: 'text-[#65b7dc]', bar: 'bg-[#38a8d5]' },
  amber: { bg: 'bg-[#302510]', text: 'text-[#e1ad43]', bar: 'bg-[#d89a18]' },
  red: { bg: 'bg-[#341c20]', text: 'text-[#e1727b]', bar: 'bg-[#dc5b64]' },
  violet: { bg: 'bg-[#261f35]', text: 'text-[#a992df]', bar: 'bg-[#8d73d9]' },
  cyan: { bg: 'bg-[#0d2b31]', text: 'text-[#5bc2d1]', bar: 'bg-[#21b7cf]' },
  neutral: { bg: 'bg-white/[0.04]', text: 'text-bambu-gray', bar: 'bg-[#78828b]' },
};

const clamp = (value: number, min = 0, max = 100) => Math.max(min, Math.min(max, value));

const asNumber = (value: unknown): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

const materialKey = (value: string | null | undefined) => (value ?? '').trim().toLocaleLowerCase();

const spoolRemainingGrams = (spool: InventorySpool) => Math.max(0, spool.label_weight - spool.weight_used);

const spoolMaterialLabel = (spool: InventorySpool) =>
  [spool.material, spool.subtype].filter(Boolean).join(' ') || dashboardText('unknown');

const spoolItemLabel = (spool: InventorySpool) =>
  [spool.material, spool.subtype, spool.color_name].filter(Boolean).join(' ') || dashboardText('spoolValue', { value1: spool.id });

function spoolProcurementResource(spool: InventorySpool): DashboardProcurementResource {
  const resource: SpoolProcurementResource = {
    kind: 'filament',
    material: spool.material,
    subtype: spool.subtype,
    brand: spool.brand,
    color_name: spool.color_name_is_synthesized ? null : spool.color_name,
  };
  return {
    resource,
    signature: [
      resource.kind,
      resource.material,
      resource.subtype ?? '',
      resource.brand ?? '',
      resource.color_name ?? '',
    ].join('|'),
  };
}

function skuSettingsSignature(settings: FilamentSkuSettings) {
  return [
    'filament',
    settings.material,
    settings.subtype ?? '',
    settings.brand ?? '',
    settings.color_name ?? '',
  ].join('|');
}

function preferredProcurementOffer(offers: ProcurementOffer[]) {
  return offers.find((offer) => offer.is_preferred) ?? offers[0] ?? null;
}

function compactMaterialList(values: string[]) {
  const unique = Array.from(new Set(values.filter(Boolean)));
  if (unique.length === 0) return dashboardText('notAssigned');
  if (unique.length <= 2) return unique.join(', ');
  return `${unique.slice(0, 2).join(', ')} +${unique.length - 2}`;
}

const reservationQuantityGrams = (reservation: StockReservation) => {
  if (reservation.resource_kind !== 'filament') return 0;
  const quantity = asNumber(reservation.requested_quantity);
  if (reservation.unit_code === 'GRM') return quantity;
  if (reservation.unit_code === 'KGM') return quantity * 1000;
  return 0;
};

function createMaterialCostMap(spools: InventorySpool[], smallParts: SmallPart[]) {
  const costs = new Map<string, { quantity: number; value: number }>();
  spools.forEach((spool) => {
    const key = materialKey(spool.material);
    if (!key || spool.archived_at) return;
    const quantity = spoolRemainingGrams(spool);
    const value = (quantity / 1000) * (spool.cost_per_kg ?? 0);
    const current = costs.get(key) ?? { quantity: 0, value: 0 };
    costs.set(key, { quantity: current.quantity + quantity, value: current.value + value });
  });
  smallParts.forEach((part) => {
    if (!part.is_active) return;
    const unitCost = asNumber(part.unit_cost);
    const keys = [
      `small-part:${part.id}`,
      `material:${part.id}`,
      part.sku,
      part.name,
    ];
    keys.forEach((keyValue) => {
      const key = materialKey(keyValue);
      if (!key) return;
      costs.set(key, { quantity: 1, value: unitCost });
    });
  });
  return costs;
}

function reservationValue(reservation: StockReservation, materialCosts: Map<string, { quantity: number; value: number }>) {
  const quantity = reservation.resource_kind === 'filament'
    ? reservationQuantityGrams(reservation)
    : asNumber(reservation.requested_quantity);
  if (quantity <= 0) return 0;
  const keys = reservation.resource_kind === 'filament'
    ? [reservation.material_code]
    : [
      reservation.source_key,
      reservation.material_code,
      ...reservation.allocations.map((allocation) => allocation.small_part_id ? `small-part:${allocation.small_part_id}` : ''),
      ...reservation.allocations.map((allocation) => allocation.small_part_id ? `material:${allocation.small_part_id}` : ''),
    ];
  const cost = keys.map((key) => materialCosts.get(materialKey(key))).find(Boolean);
  if (!cost || cost.quantity <= 0) return 0;
  return quantity * (cost.value / cost.quantity);
}

const snapshotPart = (snapshot: Record<string, unknown> | undefined, key: string): Record<string, unknown> => {
  const value = snapshot?.[key];
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
};

const readRevisionValue = (offer: Offer, key: string): number => asNumber(snapshotPart(offer.snapshot, 'revision')[key]);
const readAcceptedRevisionValue = (order: CustomerOrder, key: string): number => asNumber(snapshotPart(order.accepted_snapshot, 'revision')[key]);
const readRevisionCurrency = (offer: Offer): string => String(snapshotPart(offer.snapshot, 'revision').currency ?? '').toUpperCase();
const readAcceptedRevisionCurrency = (order: CustomerOrder): string => String(snapshotPart(order.accepted_snapshot, 'revision').currency ?? '').toUpperCase();
const hasDisplayCurrency = (currency: string | null | undefined, displayCurrency: string) => {
  const normalized = String(currency ?? '').trim().toUpperCase();
  return normalized === '' || normalized === displayCurrency.toUpperCase();
};
const readRevisionText = (snapshot: Record<string, unknown> | undefined, key: string): string => {
  const revision = snapshotPart(snapshot, 'revision');
  const calculation = snapshotPart(snapshot, 'calculation');
  const value = revision[key] ?? calculation[key];
  return typeof value === 'string' && value.trim() ? value : '';
};

const displayCustomer = (customerId: number | null | undefined) => (customerId ? dashboardText('customerValue', { value1: customerId }) : dashboardText('noCustomer'));

const formatPercent = (value: number, locale: string) =>
  `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value)} %`;

const formatKwh = (value: number, locale: string) =>
  `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)} kWh`;

const formatWeightKg = (grams: number, locale: string) =>
  `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(grams / 1000)} kg`;

const formatQuantity = (value: number, locale: string, maximumFractionDigits = 1) =>
  new Intl.NumberFormat(locale, { maximumFractionDigits }).format(value);

const formatMaterialRemaining = (item: MaterialUsage, locale: string) =>
  item.kind === 'filament'
    ? formatWeightKg(item.remaining, locale)
    : `${formatQuantity(item.remaining, locale)} ${item.unitLabel ?? ''}`.trim();

const materialUsageProgressLabel = (item: MaterialUsage, locale: string) =>
  item.kind === 'filament'
    ? dashboardText('daysValue', { value1: item.label, value2: item.days })
    : `${item.label} · ${formatMaterialRemaining(item, locale)}`;

function createMetricTrend(
  current: number,
  previous: number,
  formatter: (value: number) => string,
  higherIsPositive = true,
): MetricTrend {
  const delta = current - previous;
  if (Math.abs(delta) < 0.005) {
    return { label: dashboardText('unchangedFromPreviousPeriod'), direction: 'flat', positive: true };
  }
  const direction = delta > 0 ? 'up' : 'down';
  const positive = higherIsPositive ? delta > 0 : delta < 0;
  const sign = delta > 0 ? '+' : '-';
  return {
    label: dashboardText('fromPreviousPeriodValue', { value1: sign, value2: formatter(Math.abs(delta)) }),
    direction,
    positive,
  };
}

const toLocalIsoDate = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const startOfDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());

const endOfDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate(), 23, 59, 59, 999);

function createDateRange(days: number, today: Date) {
  const end = endOfDay(today);
  const start = startOfDay(today);
  start.setDate(start.getDate() - (days - 1));
  return {
    start,
    end,
    dateFrom: toLocalIsoDate(start),
    dateTo: toLocalIsoDate(end),
  };
}

function createPreviousDateRange(days: number, currentStart: Date) {
  const end = endOfDay(currentStart);
  end.setDate(end.getDate() - 1);
  const start = startOfDay(end);
  start.setDate(start.getDate() - (days - 1));
  return {
    start,
    end,
    dateFrom: toLocalIsoDate(start),
    dateTo: toLocalIsoDate(end),
  };
}

function isInDateRange(value: string | null | undefined, start: Date, end: Date) {
  if (!value) return false;
  const date = parseBusinessDate(value);
  if (!date) return false;
  return date.getTime() >= start.getTime() && date.getTime() <= end.getTime();
}

function parseBusinessDate(value: string | null | undefined) {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = match
    ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

const daysSince = (value: string | null | undefined, today: Date) => {
  if (!value) return null;
  const date = parseBusinessDate(value);
  if (!date) return null;
  return Math.max(0, Math.floor((today.getTime() - date.getTime()) / 86400000));
};

function getIsoWeek(date: Date) {
  const target = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNumber = target.getUTCDay() || 7;
  target.setUTCDate(target.getUTCDate() + 4 - dayNumber);
  const yearStart = new Date(Date.UTC(target.getUTCFullYear(), 0, 1));
  return Math.ceil((((target.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
}

function createTrend(
  orders: CustomerOrder[],
  archiveEvents: ArchiveSlim[],
  energyHistory: ArchiveEnergyHistoryPoint[],
  stats: ArchiveStats | undefined,
  rangeStart: Date,
  rangeEnd: Date,
  currency: string,
  locale: string,
): TrendPoint[] {
  const bucketCount = 7;
  const rangeMs = Math.max(rangeEnd.getTime() - rangeStart.getTime(), 86400000);
  const bucketMs = rangeMs / bucketCount;
  const useDailyLabels = rangeMs <= 31 * 86400000;
  const buckets = Array.from({ length: bucketCount }, (_, index) => {
    const bucketDate = new Date(rangeStart.getTime() + bucketMs * index + bucketMs / 2);
    return {
      label: useDailyLabels
        ? new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit' }).format(bucketDate)
        : dashboardText('weekValue', { value1: getIsoWeek(bucketDate) }),
      revenue: 0,
      costs: 0,
      energy: 0,
      margin: 0,
    };
  });
  orders
    .filter((order) => order.status !== 'cancelled' && isInDateRange(order.updated_at || order.created_at, rangeStart, rangeEnd))
    .filter((order) => hasDisplayCurrency(readAcceptedRevisionCurrency(order), currency))
    .forEach((order) => {
      const date = new Date(order.updated_at || order.created_at);
      const index = clamp(Math.floor((date.getTime() - rangeStart.getTime()) / bucketMs), 0, bucketCount - 1);
      const bucket = buckets[index];
      bucket.revenue += readAcceptedRevisionValue(order, 'selling_price');
      bucket.costs += readAcceptedRevisionValue(order, 'production_cost');
    });
  archiveEvents.forEach((event) => {
    const date = eventDate(event);
    if (!date || date.getTime() < rangeStart.getTime() || date.getTime() > rangeEnd.getTime()) return;
    const index = clamp(Math.floor((date.getTime() - rangeStart.getTime()) / bucketMs), 0, bucketCount - 1);
    buckets[index].costs += asNumber(event.cost);
  });
  const historyEnergyCost = energyHistory.reduce((sum, point) => sum + asNumber(point.energy_cost), 0);
  const eventEnergyCost = archiveEvents.reduce((sum, event) => sum + asNumber(event.energy_cost), 0);
  if (historyEnergyCost > 0) {
    energyHistory.forEach((point) => {
      const date = new Date(point.bucket_start);
      if (Number.isNaN(date.getTime()) || date.getTime() < rangeStart.getTime() || date.getTime() > rangeEnd.getTime()) return;
      const value = asNumber(point.energy_cost);
      if (value <= 0) return;
      const index = clamp(Math.floor((date.getTime() - rangeStart.getTime()) / bucketMs), 0, bucketCount - 1);
      buckets[index].energy += value;
    });
  } else if (eventEnergyCost > 0) {
    archiveEvents.forEach((event) => {
      const date = eventDate(event);
      if (!date || date.getTime() < rangeStart.getTime() || date.getTime() > rangeEnd.getTime()) return;
      const value = asNumber(event.energy_cost);
      if (value <= 0) return;
      const index = clamp(Math.floor((date.getTime() - rangeStart.getTime()) / bucketMs), 0, bucketCount - 1);
      buckets[index].energy += value;
    });
  } else if ((stats?.total_energy_cost ?? 0) > 0) {
    const weights = bucketEventWeights(archiveEvents, buckets.length, rangeStart, rangeEnd, bucketMs);
    const totalWeight = weights.reduce((sum, value) => sum + value, 0);
    buckets.forEach((bucket, index) => {
      bucket.energy = totalWeight > 0
        ? ((stats?.total_energy_cost ?? 0) * weights[index]) / totalWeight
        : (stats?.total_energy_cost ?? 0) / buckets.length;
    });
  }
  return buckets.map((bucket) => ({
    ...bucket,
    margin: bucket.revenue > 0 ? clamp(((bucket.revenue - bucket.costs - bucket.energy) / bucket.revenue) * 100, 0, 80) : 0,
  }));
}

const eventDate = (event: ArchiveSlim) => {
  const value = event.completed_at || event.started_at || event.created_at;
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};

function bucketEventWeights(
  archiveEvents: ArchiveSlim[],
  bucketCount: number,
  rangeStart: Date,
  rangeEnd: Date,
  bucketMs: number,
) {
  const weights = Array.from({ length: bucketCount }, () => 0);
  archiveEvents.forEach((event) => {
    const date = eventDate(event);
    if (!date || date.getTime() < rangeStart.getTime() || date.getTime() > rangeEnd.getTime()) return;
    const index = clamp(Math.floor((date.getTime() - rangeStart.getTime()) / bucketMs), 0, bucketCount - 1);
    weights[index] += Math.max(asNumber(event.actual_time_seconds), 1);
  });
  return weights;
}

const paymentDocumentTypes = new Set(['advance_invoice', 'progress_invoice', 'final_invoice', 'invoice']);

function isPaymentDocument(document: CommercialDocument) {
  return paymentDocumentTypes.has(document.document_type) && document.payment_status !== 'not_applicable';
}

function createRevenueRows(
  orders: CustomerOrder[],
  offers: Offer[],
  documents: CommercialDocument[],
  today: Date,
  currency: string,
  locale: string,
): RevenueRow[] {
  const documentRows = documents
    .filter(isPaymentDocument)
    .filter((document) => hasDisplayCurrency(document.currency, currency))
    .map((document) => {
      const openAmount = asNumber(document.open_amount);
      const dueDate = parseBusinessDate(document.due_date);
      const overdue = openAmount > 0 && dueDate !== null && dueDate.getTime() < today.getTime();
      const documentFilter = openAmount > 0 ? 'open' : 'paid';
      return {
        number: document.number ?? dashboardText('documentValue', { value1: document.id }),
        customer: displayCustomer(document.customer_id),
        status: overdue ? 'overdue' as const : document.payment_status === 'paid' || document.payment_status === 'overpaid'
          ? 'paid' as const
          : document.payment_status === 'partially_paid'
            ? 'partially_paid' as const
            : 'unpaid' as const,
        amount: asNumber(document.total_amount),
        due: document.due_date ?? '',
        to: openAmount > 0
          ? `/orders/invoices?payment=${document.id}&filter=${documentFilter}`
          : `/orders/invoices?filter=${documentFilter}`,
      };
    });
  const orderRows = orders
    .filter((order) => order.status !== 'cancelled')
    .filter((order) => hasDisplayCurrency(readAcceptedRevisionCurrency(order), currency))
    .map((order) => ({
      number: order.number,
      customer: displayCustomer(order.customer_id),
      status: order.status === 'completed' ? 'completed' as const : 'active' as const,
      amount: readAcceptedRevisionValue(order, 'selling_price'),
      due: new Date(order.updated_at || order.created_at).toLocaleDateString(locale),
      to: `/orders/${order.id}`,
    }));
  const offerRows = offers
    .filter((offer) => offer.status === 'sent' || offer.status === 'draft')
    .filter((offer) => hasDisplayCurrency(readRevisionCurrency(offer), currency))
    .map((offer) => ({
      number: offer.number,
      customer: displayCustomer(offer.customer_id),
      status: 'offer' as const,
      amount: readRevisionValue(offer, 'selling_price'),
      due: new Date(offer.updated_at || offer.created_at).toLocaleDateString(locale),
      to: '/orders/offers',
    }));
  return [...documentRows, ...orderRows, ...offerRows]
    .filter((row) => row.amount > 0)
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 8);
}

function deriveMaterialUsage(spools: InventorySpool[], smallParts: SmallPart[]): MaterialUsage[] {
  const grouped = new Map<string, MaterialUsage>();
  spools.forEach((spool) => {
    if (spool.archived_at) return;
    const label = spoolMaterialLabel(spool);
    const used = Math.max(0, spool.weight_used - (spool.weight_used_baseline ?? 0));
    const remaining = Math.max(0, spool.label_weight - spool.weight_used);
    const value = (remaining / 1000) * (spool.cost_per_kg ?? 0);
    const days = Math.max(3, Math.round((remaining / Math.max(used / 30, 12)) || 0));
    const current = grouped.get(label) ?? { label, kind: 'filament', grams: 0, value: 0, remaining: 0, days };
    current.grams += used;
    current.value += value;
    current.remaining += remaining;
    current.days = Math.min(current.days, days);
    grouped.set(label, current);
  });
  smallParts.forEach((part) => {
    if (!part.is_active) return;
    const physical = asNumber(part.balance.physical);
    const unitCost = asNumber(part.unit_cost);
    grouped.set(`material-${part.id}`, {
      label: part.name || part.sku || dashboardText('materialValue', { value1: part.id }),
      kind: 'small_part',
      grams: 0,
      value: physical * unitCost,
      remaining: physical,
      days: part.balance.is_low_stock ? 0 : 999,
      unitLabel: part.unit.label || part.unit_code,
      lowStock: part.balance.is_low_stock,
    });
  });
  const values = Array.from(grouped.values()).sort((a, b) => {
    if ((b.lowStock ? 1 : 0) !== (a.lowStock ? 1 : 0)) return (b.lowStock ? 1 : 0) - (a.lowStock ? 1 : 0);
    return b.value - a.value || b.grams - a.grams || b.remaining - a.remaining;
  });
  return values;
}

function BusinessTabs({ value, onChange }: { value: DashboardTab; onChange: (value: DashboardTab) => void }) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {tabs.map((tab) => {
        const selected = tab.value === value;
        return (
          <button
            key={tab.value}
            type="button"
            onClick={() => onChange(tab.value)}
            className={`flex min-h-10 shrink-0 items-center gap-2 rounded px-4 text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green ${
              selected
                ? 'bg-[#00a14a] text-[#07120b] shadow-[0_0_0_1px_rgba(0,0,0,0.25)]'
                : 'border border-bambu-dark-tertiary bg-bambu-dark-secondary text-bambu-gray hover:border-bambu-green/60 hover:text-white'
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

function Panel({
  icon: Icon,
  title,
  subtitle,
  children,
  className = '',
  tone = 'green',
}: {
  icon?: LucideIcon;
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
  tone?: Tone;
}) {
  return (
    <section className={`${surface.panel} ${className}`}>
      <div className="mb-4 flex items-start gap-2.5">
        {Icon ? (
          <span className={`mt-[3px] flex h-4 w-4 shrink-0 items-center justify-center ${toneClasses[tone].text}`}>
            <Icon className="h-4 w-4" />
          </span>
        ) : null}
        <div className="min-w-0">
          <h2 className="text-base font-semibold leading-6 text-white">{title}</h2>
          {subtitle ? <p className="mt-0.5 text-xs leading-5 text-bambu-gray">{subtitle}</p> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  tone,
  to,
  trend,
}: {
  icon?: LucideIcon;
  label: string;
  value: string;
  detail: string;
  tone: Tone;
  to?: string;
  trend?: MetricTrend;
}) {
  const trendClass = trend
    ? trend.direction === 'flat'
      ? 'text-bambu-gray'
      : trend.positive
        ? 'text-[#35c46f]'
        : 'text-amber-300'
    : '';
  const TrendIcon = trend?.direction === 'up' ? ArrowUp : trend?.direction === 'down' ? ArrowDown : ArrowUpDown;
  const content = (
    <>
      <div className="flex items-center gap-2.5">
        {Icon ? <Icon className={`h-4 w-4 shrink-0 ${toneClasses[tone].text}`} /> : null}
        <p className="min-w-0 text-[11px] font-medium leading-4 text-bambu-gray">{label}</p>
      </div>
      <strong className="mt-3 block text-[1.35rem] font-semibold leading-none text-white">{value}</strong>
      <p className="mt-2 truncate text-[11px] leading-4 text-bambu-gray">{detail}</p>
      {trend ? (
        <p className={`mt-2 flex items-center gap-1 text-[11px] leading-4 ${trendClass}`}>
          <TrendIcon className="h-3 w-3 shrink-0" />
          <span className="truncate">{trend.label}</span>
        </p>
      ) : null}
    </>
  );
  if (to) {
    return (
      <Link
        to={to}
        className={`${surface.tile} block min-h-[108px] p-4 transition-colors hover:border-bambu-green/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green`}
      >
        {content}
      </Link>
    );
  }
  return <section className={`${surface.tile} min-h-[108px] p-4`}>{content}</section>;
}

function MiniMetric({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  tone: Tone;
}) {
  return (
    <div className={`${surface.panelQuiet} p-3`}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-medium text-bambu-gray">{label}</p>
        <span className={toneClasses[tone].text}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <strong className="mt-2 block text-lg font-semibold text-white">{value}</strong>
    </div>
  );
}

function ChartTooltip({
  title,
  lines,
  children,
  className = '',
}: {
  title: string;
  lines: TooltipLine[];
  children: ReactNode;
  className?: string;
}) {
  const nativeTitle = [
    title,
    ...lines.map((line) => `${line.label}: ${line.value}`),
  ].join('\n');
  return (
    <span className={`group/tooltip relative inline-flex ${className}`} title={nativeTitle}>
      {children}
      <span className="pointer-events-none absolute bottom-[calc(100%+0.5rem)] left-1/2 z-30 hidden min-w-48 -translate-x-1/2 rounded border border-bambu-dark-tertiary bg-bambu-dark p-3 text-left shadow-xl group-hover/tooltip:block group-focus-within/tooltip:block">
        <span className="block whitespace-nowrap text-xs font-semibold text-white">{title}</span>
        <span className="mt-2 block space-y-1">
          {lines.map((line) => (
            <span key={`${line.label}-${line.value}`} className="flex items-center justify-between gap-4 text-xs">
              <span className="whitespace-nowrap text-bambu-gray">{line.label}</span>
              <span className="whitespace-nowrap font-medium text-white">{line.value}</span>
            </span>
          ))}
        </span>
      </span>
    </span>
  );
}

function FinanceTrendChart({
  data,
  currency,
  locale,
}: {
  data: TrendPoint[];
  currency: string;
  locale: string;
}) {
  const max = Math.max(...data.map((item) => item.revenue + item.costs + item.energy), 1);
  const points = data.map((item, index) => {
    const x = 18 + index * (364 / Math.max(data.length - 1, 1));
    const y = 162 - item.margin * 1.95;
    return `${x},${y}`;
  }).join(' ');

  return (
    <div className="relative h-[232px]">
      <div className="absolute inset-x-2 bottom-8 top-2 grid grid-rows-4">
        {Array.from({ length: 4 }, (_, index) => (
          <span key={index} className="border-t border-bambu-dark-tertiary" />
        ))}
      </div>
      <div className="absolute inset-x-5 bottom-8 top-4 flex items-end justify-between gap-4">
        {data.map((item) => {
          const total = item.revenue + item.costs + item.energy;
          const totalHeight = (total / max) * 180;
          const revenueHeight = item.revenue > 0 ? Math.max(4, (item.revenue / max) * 180) : 0;
          const costsHeight = item.costs > 0 ? Math.max(4, (item.costs / max) * 180) : 0;
          const energyHeight = item.energy > 0 ? Math.max(3, (item.energy / max) * 180) : 0;
          return (
            <div key={item.label} className="flex flex-1 flex-col items-center gap-2">
              <ChartTooltip
                title={item.label}
                lines={[
                  { label: dashboardText('orderValue'), value: formatMoney(item.revenue, locale, currency) },
                  { label: dashboardText('costs'), value: formatMoney(item.costs, locale, currency) },
                  { label: dashboardText('energy'), value: formatMoney(item.energy, locale, currency) },
                  { label: dashboardText('margin'), value: formatPercent(item.margin, locale) },
                ]}
                className="flex h-[178px] w-full max-w-[48px] items-end"
              >
                <span className="block w-full overflow-hidden rounded-t-md transition-opacity group-hover/tooltip:opacity-80" style={{ height: `${total > 0 ? clamp(totalHeight, 6, 178) : 0}px` }}>
                  <span className="block bg-[#21b7cf]" style={{ height: `${energyHeight}px` }} />
                  <span className="block bg-[#d89a18]" style={{ height: `${costsHeight}px` }} />
                  <span className="block bg-[#00a14a]" style={{ height: `${revenueHeight}px` }} />
                </span>
              </ChartTooltip>
              <span className="text-xs text-bambu-gray">{item.label}</span>
            </div>
          );
        })}
      </div>
      <svg className="pointer-events-none absolute inset-x-5 bottom-8 top-4 h-[178px] w-[calc(100%-2.5rem)] overflow-visible" preserveAspectRatio="none" viewBox="0 0 400 178">
        <polyline points={points} fill="none" stroke="#00a14a" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="absolute bottom-0 left-0 text-xs text-bambu-gray">
        {dashboardText('greenOrderValueOrangeCostsBlueEnergyLineMargin')}
      </div>
    </div>
  );
}

function Donut({
  slices,
  center,
  size = 'large',
  valueFormatter,
}: {
  slices: CostSlice[];
  center: string;
  size?: 'large' | 'small';
  valueFormatter?: (value: number) => string;
}) {
  const total = Math.max(slices.reduce((sum, slice) => sum + slice.value, 0), 1);
  const formatValue = valueFormatter ?? ((value: number) => String(value));
  let offset = 25;
  const dimension = size === 'large' ? 'h-36 w-36' : 'h-24 w-24';
  const spacing = size === 'large' ? 'gap-5' : 'gap-4';
  const rowText = size === 'large' ? 'text-sm' : 'text-xs';
  return (
    <div className={`flex items-center ${spacing}`}>
      <div className={`relative shrink-0 ${dimension}`}>
        <svg viewBox="0 0 42 42" className={`${dimension} -rotate-90`}>
          <circle cx="21" cy="21" r="15.9" fill="transparent" stroke={surface.rail} strokeWidth="7" />
          {slices.map((slice) => {
            const length = (slice.value / total) * 100;
            const dashOffset = offset;
            offset -= length;
            return (
              <circle
                key={slice.label}
                cx="21"
                cy="21"
                r="15.9"
                fill="transparent"
                stroke={slice.color}
                strokeWidth="7"
                strokeDasharray={`${length} ${100 - length}`}
                strokeDashoffset={dashOffset}
              >
                <title>{`${slice.label}: ${formatValue(slice.value)} (${Math.round((slice.value / total) * 100)}%)`}</title>
              </circle>
            );
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-xs text-bambu-gray">{dashboardText('costs')}</span>
          <strong className="text-sm text-white">{center}</strong>
        </div>
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        {slices.map((slice) => (
          <ChartTooltip
            key={slice.label}
            title={slice.label}
            lines={[
              { label: dashboardText('value'), value: formatValue(slice.value) },
              { label: dashboardText('share'), value: `${Math.round((slice.value / total) * 100)}%` },
            ]}
            className={`grid w-full grid-cols-[minmax(0,1fr)_32px] items-center gap-2 ${rowText}`}
          >
            <>
              <span className="flex min-w-0 items-center gap-2 text-bambu-gray">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: slice.color }} />
                <span className="truncate">{slice.label}</span>
              </span>
              <span className="text-right font-medium text-white">{Math.round((slice.value / total) * 100)}%</span>
            </>
          </ChartTooltip>
        ))}
      </div>
    </div>
  );
}

function PipelineChart({ stages, currency, locale }: { stages: PipelineStage[]; currency: string; locale: string }) {
  const max = Math.max(...stages.map((stage) => stage.value), 1);
  return (
    <div>
      <div className="mb-4 grid h-[150px] grid-cols-5 items-end gap-5 border-y border-bambu-dark-tertiary py-4">
        {stages.map((stage) => (
          <div key={stage.label} className="flex h-full flex-col justify-end gap-3">
            <ChartTooltip
              title={stage.label}
              lines={[
                { label: dashboardText('value'), value: formatMoney(stage.value, locale, currency) },
                { label: dashboardText('shareOfMaximum'), value: `${Math.round((stage.value / max) * 100)}%` },
              ]}
              className="mx-auto h-full w-full max-w-[54px] items-end"
            >
              <span
                className="block w-full rounded-t transition-opacity group-hover/tooltip:opacity-80"
                style={{ height: `${stage.value > 0 ? clamp((stage.value / max) * 100, 4, 100) : 0}%`, backgroundColor: stage.color }}
              />
            </ChartTooltip>
            <span className="w-full truncate text-center text-xs text-bambu-gray" title={stage.label}>{stage.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ProgressRow({
  label,
  value,
  max,
  suffix,
  tone = 'green',
}: {
  label: string;
  value: number;
  max: number;
  suffix: string;
  tone?: Tone;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3 text-sm">
        <span className="truncate text-bambu-gray">{label}</span>
        <span className="shrink-0 font-medium text-white">{suffix}</span>
      </div>
      <ChartTooltip
        title={label}
        lines={[
          { label: dashboardText('value'), value: suffix },
          { label: dashboardText('share'), value: `${Math.round((value / Math.max(max, 1)) * 100)}%` },
        ]}
        className="block w-full"
      >
        <span className="block h-4 overflow-hidden rounded bg-bambu-dark-tertiary">
          <span className={`block h-full rounded ${toneClasses[tone].bar} transition-opacity group-hover/tooltip:opacity-80`} style={{ width: `${value > 0 ? clamp((value / Math.max(max, 1)) * 100, 4, 100) : 0}%` }} />
        </span>
      </ChartTooltip>
    </div>
  );
}

function EnergyHeatmap({
  archiveEvents,
  energyHistory,
  totalKwh,
  totalCost,
  locale,
  currency,
}: {
  archiveEvents: ArchiveSlim[];
  energyHistory: ArchiveEnergyHistoryPoint[];
  totalKwh: number;
  totalCost: number;
  locale: string;
  currency: string;
}) {
  const days = [dashboardText('mon'), dashboardText('tue'), dashboardText('wed'), dashboardText('thu'), dashboardText('fri'), dashboardText('sat'), dashboardText('sun')];
  const hours = Array.from({ length: 24 }, (_, index) => index);
  const cells = new Map<string, { kwh: number; cost: number; runs: number; source: string }>();
  const measuredKwh = archiveEvents.reduce((sum, event) => sum + asNumber(event.energy_kwh), 0);
  const totalWeight = archiveEvents.reduce((sum, event) => sum + Math.max(asNumber(event.actual_time_seconds), 1), 0);
  if (energyHistory.some((point) => asNumber(point.energy_kwh) > 0)) {
    energyHistory.forEach((point) => {
      const date = new Date(point.bucket_start);
      if (Number.isNaN(date.getTime())) return;
      const dayIndex = (date.getDay() + 6) % 7;
      const hour = date.getHours();
      const key = `${dayIndex}-${hour}`;
      const current = cells.get(key) ?? { kwh: 0, cost: 0, runs: 0, source: dashboardText('smartPlugHistory') };
      current.kwh += asNumber(point.energy_kwh);
      current.cost += asNumber(point.energy_cost);
      current.runs += Math.max(asNumber(point.sample_count), 1);
      cells.set(key, current);
    });
  } else {
    archiveEvents.forEach((event) => {
      const date = eventDate(event);
      if (!date) return;
      const dayIndex = (date.getDay() + 6) % 7;
      const hour = date.getHours();
      const key = `${dayIndex}-${hour}`;
      const weight = Math.max(asNumber(event.actual_time_seconds), 1);
      const kwh = measuredKwh > 0
        ? asNumber(event.energy_kwh)
        : totalWeight > 0
          ? (totalKwh * weight) / totalWeight
          : 0;
      const cost = totalKwh > 0 ? (totalCost * kwh) / totalKwh : 0;
      const current = cells.get(key) ?? { kwh: 0, cost: 0, runs: 0, source: measuredKwh > 0 ? dashboardText('printLog') : dashboardText('timeShareOfPeriodTotal') };
      current.kwh += kwh;
      current.cost += cost;
      current.runs += 1;
      cells.set(key, current);
    });
  }
  if (cells.size === 0 && totalKwh > 0) {
    const activeHours = [8, 9, 10, 11, 13, 14, 15, 16, 17];
    const totalSlots = days.length * activeHours.length;
    const kwhPerSlot = totalKwh / totalSlots;
    const costPerSlot = totalCost / totalSlots;
    days.forEach((_day, dayIndex) => {
      activeHours.forEach((hour) => {
        cells.set(`${dayIndex}-${hour}`, {
          kwh: kwhPerSlot,
          cost: costPerSlot,
          runs: 1,
          source: dashboardText('distributedPeriodTotal'),
        });
      });
    });
  }
  const maxKwh = Math.max(...Array.from(cells.values()).map((cell) => cell.kwh), 0.01);
  return (
    <div className="overflow-x-auto">
        <div className="min-w-0">
        <div className="grid grid-cols-[24px_repeat(24,minmax(5px,1fr))] gap-1">
          {days.map((day) => (
            <div key={day} className="contents">
              <span className="text-xs text-bambu-gray">{day}</span>
              {hours.map((hour) => {
                const cell = cells.get(`${days.indexOf(day)}-${hour}`) ?? { kwh: 0, cost: 0, runs: 0, source: dashboardText('noData') };
                const value = cell.kwh > 0 ? clamp((cell.kwh / maxKwh) * 100, 12, 100) : 0;
                return (
                  <ChartTooltip
                    key={`${day}-${hour}`}
                    title={`${day} ${hour}:00`}
                    lines={[
                      { label: dashboardText('usage'), value: formatKwh(cell.kwh, locale) },
                      { label: dashboardText('costs'), value: formatMoney(cell.cost, locale, currency) },
                      { label: dashboardText('samplesPrints'), value: String(cell.runs) },
                      { label: dashboardText('source'), value: cell.source },
                    ]}
                    className="block"
                  >
                    <span
                      className="block h-4 rounded-sm transition-opacity group-hover/tooltip:opacity-80"
                      style={{ backgroundColor: `rgba(0, 161, 74, ${0.08 + (value / 100) * 0.62})` }}
                    />
                  </ChartTooltip>
                );
              })}
            </div>
          ))}
        </div>
        <div className="mt-3 flex justify-between text-xs text-bambu-gray">
          <span>00</span>
          <span>12</span>
          <span>23</span>
        </div>
      </div>
    </div>
  );
}

function RevenueStatus({ status }: { status: RevenueRow['status'] }) {
  const labels = {
    paid: dashboardText('paid'),
    partially_paid: dashboardText('partiallyPaid'),
    unpaid: dashboardText('open'),
    overdue: dashboardText('overdue'),
    completed: dashboardText('completed'),
    active: dashboardText('activeOrder'),
    offer: dashboardText('offer'),
    missing_payment_source: dashboardText('paymentSourceMissing'),
  };
  const tones = {
    paid: 'text-[#35c46f]',
    partially_paid: 'text-amber-300',
    unpaid: 'text-bambu-gray',
    overdue: 'text-red-300',
    completed: 'text-[#35c46f]',
    active: 'text-bambu-gray',
    offer: 'text-amber-300',
    missing_payment_source: 'text-red-300',
  };
  return <span className={tones[status]}>{labels[status]}</span>;
}

function EntityLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="font-medium text-white underline-offset-4 hover:text-bambu-green hover:underline">
      {children}
    </Link>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className={`${surface.panelQuiet} flex min-h-24 items-center text-sm text-bambu-gray`}>
      {label}
    </div>
  );
}

function ActionStrip({ actions }: { actions: ActionShortcut[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {actions.map((action) => {
        const Icon = action.icon;
        return (
          <Link
            key={`${action.label}-${action.to}`}
            to={action.to}
            className={`${surface.tile} flex min-h-[76px] items-start gap-3 px-4 py-3 transition-colors hover:border-bambu-green/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green`}
          >
            <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${toneClasses[action.tone].text}`} />
            <span className="min-w-0">
              <span className="block text-sm font-semibold leading-5 text-white">{action.label}</span>
              <span className="mt-0.5 block truncate text-xs leading-5 text-bambu-gray">{action.detail}</span>
            </span>
          </Link>
        );
      })}
    </div>
  );
}

const textFromNode = (node: ReactNode): string => {
  if (node === null || node === undefined || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textFromNode).join(' ');
  if (isValidElement(node)) {
    const props = node.props as { children?: ReactNode };
    return textFromNode(props.children);
  }
  return '';
};

const csvEscape = (value: ReactNode) => {
  const text = textFromNode(value).replace(/\r?\n/g, ' ').trim();
  return `"${text.replace(/"/g, '""')}"`;
};

const createCsv = (sections: Array<{ title: string; columns: string[]; rows: Array<Array<ReactNode>> }>) => {
  const lines: string[] = [];
  sections.forEach((section, sectionIndex) => {
    if (sectionIndex > 0) lines.push('');
    lines.push(csvEscape(section.title));
    lines.push(section.columns.map(csvEscape).join(';'));
    section.rows.forEach((row) => {
      lines.push(row.map(csvEscape).join(';'));
    });
  });
  return `\uFEFF${lines.join('\r\n')}`;
};

const sortableNumber = (value: string): number | null => {
  const cleaned = value
    .replace(/\s/g, '')
    .replace(/\./g, '')
    .replace(',', '.')
    .replace(/[^0-9.-]/g, '');
  if (!cleaned || cleaned === '-' || cleaned === '.') return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
};

function CompactTable({
  columns,
  rows,
}: {
  columns: string[];
  rows: Array<Array<ReactNode>>;
}) {
  const [sort, setSort] = useState<{ column: number; direction: 'asc' | 'desc' } | null>(null);
  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    return [...rows].sort((left, right) => {
      const leftText = textFromNode(left[sort.column]);
      const rightText = textFromNode(right[sort.column]);
      const leftNumber = sortableNumber(leftText);
      const rightNumber = sortableNumber(rightText);
      const comparison = leftNumber !== null && rightNumber !== null
        ? leftNumber - rightNumber
        : leftText.localeCompare(rightText, i18n.language, { numeric: true, sensitivity: 'base' });
      return sort.direction === 'asc' ? comparison : -comparison;
    });
  }, [rows, sort]);

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs text-bambu-gray">
          <tr>
            {columns.map((column, columnIndex) => {
              const active = sort?.column === columnIndex;
              const SortIcon = !active ? ArrowUpDown : sort.direction === 'asc' ? ArrowUp : ArrowDown;
              return (
                <th key={column} className="border-b border-bambu-dark-tertiary px-0 py-2 pr-4 font-medium">
                  <button
                    type="button"
                    className="flex w-full items-center gap-1.5 text-left transition-colors hover:text-white focus:outline-none focus-visible:text-white"
                    onClick={() => setSort((current) => (
                      current?.column === columnIndex
                        ? { column: columnIndex, direction: current.direction === 'asc' ? 'desc' : 'asc' }
                        : { column: columnIndex, direction: 'asc' }
                    ))}
                  >
                    <span className="truncate">{column}</span>
                    <SortIcon className={`h-3.5 w-3.5 shrink-0 ${active ? 'text-[#35c46f]' : 'text-[#7f978b]'}`} />
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-bambu-dark-tertiary">
          {sortedRows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="py-2.5 pr-4 text-bambu-gray first:text-white">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Overview({
  trend,
  costSlices,
  pipelineStages,
  materialUsage,
  revenueRows,
  currency,
  locale,
  stats,
  archiveEvents,
  energyHistory,
  energyPerHour,
  stockValue,
  reservedValue,
  riskRows,
  orderMarginRows,
  priorityRows,
  dataQualityRows,
  forecastRows,
}: {
  trend: TrendPoint[];
  costSlices: CostSlice[];
  pipelineStages: PipelineStage[];
  materialUsage: MaterialUsage[];
  revenueRows: RevenueRow[];
  currency: string;
  locale: string;
  stats: ArchiveStats | undefined;
  archiveEvents: ArchiveSlim[];
  energyHistory: ArchiveEnergyHistoryPoint[];
  energyPerHour: number;
  stockValue: number;
  reservedValue: number;
  riskRows: Array<Array<ReactNode>>;
  orderMarginRows: Array<Array<ReactNode>>;
  priorityRows: Array<Array<ReactNode>>;
  dataQualityRows: Array<Array<ReactNode>>;
  forecastRows: Array<Array<ReactNode>>;
}) {
  const materialMax = Math.max(...materialUsage.map((item) => item.remaining), 1);
  const pipelineTotal = pipelineStages.reduce((sum, stage) => sum + stage.value, 0);
  const completedStage = pipelineStages.find((stage) => stage.label === dashboardText('completed'))?.value ?? 0;
  const revenueRowsForTable = revenueRows.slice(0, 4).map((row) => [
    <EntityLink to={row.to}>{row.number}</EntityLink>,
    row.customer,
    <RevenueStatus status={row.status} />,
    formatMoney(row.amount, locale, currency),
  ]);

  return (
    <div className="mt-5 space-y-5">
      <div className="grid gap-5 xl:grid-cols-[1.12fr_1.18fr_1fr]">
        <Panel icon={BarChart3} title={dashboardText('financialTrendWithCostsEnergyAndMargin')} subtitle={dashboardText('orderValuesCostsAndEnergyCostsFromAvailableSources')}>
          <FinanceTrendChart data={trend} currency={currency} locale={locale} />
        </Panel>

        <Panel icon={Zap} title={dashboardText('energyElectricityCosts')} subtitle={dashboardText('smartPlugPrintLogSourceWithANoticeWhenDataIsMissing')}>
          <div className="mb-4 grid grid-cols-3 gap-3">
            <MiniMetric icon={Zap} label={dashboardText('usage')} value={formatKwh(stats?.total_energy_kwh ?? 0, locale)} tone="cyan" />
            <MiniMetric icon={CircleDollarSign} label={dashboardText('costs')} value={formatMoney(stats?.total_energy_cost ?? 0, locale, currency)} tone="amber" />
            <MiniMetric icon={BatteryCharging} label="kWh/h" value={energyPerHour.toFixed(2)} tone="green" />
          </div>
          <div className="grid gap-4 min-[1500px]:grid-cols-[1.05fr_1fr]">
            <Donut
              size="small"
              center={String(Math.round(stats?.total_energy_kwh ?? 0))}
              valueFormatter={(value) => formatKwh(value, locale)}
              slices={(stats?.total_energy_kwh ?? 0) > 0
                ? [{ label: dashboardEnergySource(stats?.energy_source, dashboardText('archive')), value: stats?.total_energy_kwh ?? 0, color: '#21b7cf' }]
                : []}
            />
            <div className={`${surface.panelQuiet} text-sm`}>
              <strong className="block text-white">{dashboardText('energySignals')}</strong>
              <p className="mt-3 text-bambu-gray">{dashboardText('period')} {formatKwh(stats?.total_energy_kwh ?? 0, locale)}</p>
              <p className="mt-2 text-bambu-gray">{dashboardText('costs2')} {formatMoney(stats?.total_energy_cost ?? 0, locale, currency)}</p>
              <p className="mt-2 text-bambu-gray">{dashboardText('source2')} {dashboardEnergySource(stats?.energy_source, dashboardText('archiveStatistics'))}</p>
            </div>
          </div>
        </Panel>

        <Panel icon={TrendingUp} title={dashboardText('pipelineSeparateFromReceivedRevenue')} subtitle={dashboardText('offersActiveOrdersAndCompletedOrdersShownSeparately')}>
          <PipelineChart stages={pipelineStages} currency={currency} locale={locale} />
          <div className={`${surface.panelQuiet} text-sm`}>
            <div className="flex items-center justify-between gap-3">
              <strong className="text-white">{dashboardText('expectedRevenue')}</strong>
              <span className="text-bambu-gray">{formatMoney(pipelineTotal, locale, currency)}</span>
            </div>
            <div className="mt-2 flex items-center justify-between gap-3 text-bambu-gray">
              <span>{dashboardText('ofWhichCompleted')}</span>
              <span>{formatMoney(completedStage, locale, currency)}</span>
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr_0.9fr]">
        <Panel icon={Lightbulb} title={dashboardText('priorities')} subtitle={dashboardText('nextStepsForRevenueMarginInventoryAndEnergy')}>
          <CompactTable columns={[dashboardText('area'), dashboardText('signal'), dashboardText('value'), dashboardText('action')]} rows={priorityRows} />
        </Panel>
        <Panel icon={TrendingUp} title={dashboardText('label30DayForecast')} subtitle={dashboardText('projectionFromTheSelectedPeriod')}>
          <CompactTable columns={[dashboardText('metric'), dashboardText('label30Days'), dashboardText('basis'), dashboardText('nextStep')]} rows={forecastRows} />
        </Panel>
        <Panel icon={Gauge} title={dashboardText('dataQuality')} subtitle={dashboardText('whichDataIsCurrentlyReliable')}>
          <CompactTable columns={[dashboardText('source'), dashboardText('coverage'), dashboardText('impact'), dashboardText('nextStep')]} rows={dataQualityRows} />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-4">
        <Panel icon={Receipt} title={dashboardText('revenueSummary')} subtitle={dashboardText('actualOrderAndOfferValues')}>
          {revenueRows.length > 0 ? (
            <>
              <div className="flex h-24 items-end gap-3 border-b border-bambu-dark-tertiary pb-1">
                {revenueRows.map((row) => (
                  <ChartTooltip
                    key={row.number}
                    title={row.number}
                    lines={[
                      { label: dashboardText('customer'), value: row.customer },
                      { label: dashboardText('status'), value: textFromNode(<RevenueStatus status={row.status} />) },
                      { label: dashboardText('amount'), value: formatMoney(row.amount, locale, currency) },
                    ]}
                    className="h-full flex-1 items-end"
                  >
                    <span
                      className={`block w-full rounded-t transition-opacity group-hover/tooltip:opacity-80 ${row.status === 'overdue' ? 'bg-[#dc5b64]' : row.status === 'offer' || row.status === 'unpaid' || row.status === 'partially_paid' ? 'bg-[#d89a18]' : 'bg-[#00a14a]'}`}
                      style={{ height: `${clamp((row.amount / Math.max(...revenueRows.map((item) => item.amount), 1)) * 100, 6, 100)}%` }}
                    />
                  </ChartTooltip>
                ))}
              </div>
              <p className="mt-8 text-xs text-bambu-gray">
                {dashboardText('paid')} {formatMoney(revenueRows.filter((row) => row.status === 'paid').reduce((sum, row) => sum + row.amount, 0), locale, currency)} {dashboardText('open2')} {formatMoney(revenueRows.filter((row) => row.status === 'unpaid' || row.status === 'partially_paid' || row.status === 'overdue').reduce((sum, row) => sum + row.amount, 0), locale, currency)}
              </p>
            </>
          ) : <EmptyState label={dashboardText('noOfferOrOrderValuesYet')} />}
        </Panel>

        <Panel icon={CircleDollarSign} title={dashboardText('costsMarginSummary')} subtitle={dashboardText('costCategoriesIncludingEnergy')}>
          <Donut size="small" slices={costSlices} center={dashboardText('costs')} valueFormatter={(value) => formatMoney(value, locale, currency)} />
        </Panel>

        <Panel icon={Warehouse} title={dashboardText('inventoryUsageSummary')} subtitle={dashboardText('valueReservationsAndStockCoverage')}>
          {materialUsage.length > 0 ? (
            <div className="space-y-4">
              {materialUsage.slice(0, 4).map((item, index) => (
                <ProgressRow
                  key={item.label}
                  label={materialUsageProgressLabel(item, locale)}
                  value={item.remaining}
                  max={materialMax}
                  suffix={formatMaterialRemaining(item, locale)}
                  tone={index === 1 ? 'red' : index === 2 ? 'amber' : 'green'}
                />
              ))}
            </div>
          ) : <EmptyState label={dashboardText('noActiveInventoryItemsFound')} />}
          <p className="mt-5 text-xs text-bambu-gray">
            {dashboardText('inventoryValue')} {formatMoney(stockValue, locale, currency)} {dashboardText('reserved')} {formatMoney(reservedValue, locale, currency)}
          </p>
        </Panel>

        <Panel icon={BatteryCharging} title={dashboardText('energyProfileSummary')} subtitle={dashboardText('hourlyPatternsFromPrintLogsOrTimeSharesOfThePeriodTotal')}>
          <EnergyHeatmap
            archiveEvents={archiveEvents}
            energyHistory={energyHistory}
            totalKwh={stats?.total_energy_kwh ?? 0}
            totalCost={stats?.total_energy_cost ?? 0}
            locale={locale}
            currency={currency}
          />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr_1fr]">
        <Panel icon={Receipt} title={dashboardText('ordersAndOffers')}>
          <CompactTable columns={[dashboardText('document'), dashboardText('customer'), dashboardText('status'), dashboardText('amount')]} rows={revenueRowsForTable} />
        </Panel>
        <Panel icon={ClipboardList} title={dashboardText('ordersByMargin')}>
          {orderMarginRows.length > 0 ? (
            <CompactTable
              columns={[dashboardText('order'), dashboardText('revenueTitle'), dashboardText('costs'), dashboardText('margin'), dashboardText('signal')]}
              rows={orderMarginRows}
            />
          ) : <EmptyState label={dashboardText('noCalculatedOrdersYet')} />}
        </Panel>
        <Panel icon={AlertTriangle} title={dashboardText('inventoryRisks')}>
          {riskRows.length > 0 ? (
            <CompactTable columns={[dashboardText('resource'), dashboardText('stock'), dashboardText('locationSource'), dashboardText('signal')]} rows={riskRows} />
          ) : <EmptyState label={dashboardText('noCriticalInventorySignalsInTheCurrentPeriod')} />}
        </Panel>
      </div>
    </div>
  );
}

export function BusinessDashboardPage() {
  const { i18n } = useTranslation();
  const { hasAllPermissions, hasAnyPermission } = useAuth();
  const locale = i18n.language || 'de-DE';
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTabParam = searchParams.get('tab');
  const initialRangeParam = searchParams.get('range');
  const [activeTab, setActiveTab] = useState<DashboardTab>(() =>
    isDashboardTab(initialTabParam) ? initialTabParam : 'overview',
  );
  const [dateRangeValue, setDateRangeValue] = useState<DateRangeValue>(() =>
    isDateRangeValue(initialRangeParam) ? initialRangeParam : '30',
  );
  const today = useMemo(() => new Date(), []);
  const canReadBusinessDashboard = hasAllPermissions(
    'stats:read',
    'orders:read',
    'inventory:read',
    'commercial_documents:read',
    'payments:read',
  ) && hasAnyPermission('archives:read', 'archives:read_own', 'archives:read_all');
  const selectedDateRange = dateRangeOptions.find((option) => option.value === dateRangeValue) ?? dateRangeOptions[1];
  const { start: rangeStart, end: rangeEnd, dateFrom, dateTo } = useMemo(
    () => createDateRange(selectedDateRange.days, today),
    [selectedDateRange.days, today],
  );
  const { start: previousRangeStart, end: previousRangeEnd, dateFrom: previousDateFrom, dateTo: previousDateTo } = useMemo(
    () => createPreviousDateRange(selectedDateRange.days, rangeStart),
    [rangeStart, selectedDateRange.days],
  );
  const updateDashboardParams = (tab: DashboardTab, range: DateRangeValue) => {
    const next = new URLSearchParams(searchParams);
    if (tab === 'overview') {
      next.delete('tab');
    } else {
      next.set('tab', tab);
    }
    if (range === '30') {
      next.delete('range');
    } else {
      next.set('range', range);
    }
    setSearchParams(next, { replace: true });
  };
  const dashboardTabUrl = (tab: DashboardTab) =>
    dateRangeValue === '30'
      ? `/business-dashboard?tab=${tab}`
      : `/business-dashboard?tab=${tab}&range=${dateRangeValue}`;
  const invoiceListUrl = (filter?: 'open' | 'overdue' | 'paid') =>
    filter ? `/orders/invoices?filter=${filter}` : '/orders/invoices';
  const invoicePaymentUrl = (documentId: number) => `/orders/invoices?payment=${documentId}&filter=open`;
  const inventoryFocusUrl = (focus?: 'low-stock' | 'missing-cost' | 'missing-location' | 'used') =>
    focus ? `/warehouse/filament?focus=${focus}` : '/warehouse/filament';
  const spoolDetailUrl = (spool: InventorySpool) => `/warehouse/filament?spool=${spool.id}`;
  const supplierListUrl = (query?: string) => {
    const trimmed = query?.trim();
    return trimmed ? `/warehouse/suppliers?q=${encodeURIComponent(trimmed)}` : '/warehouse/suppliers';
  };
  const energyCostSettingsUrl = '/settings?tab=orders-calculation&sub=calculation';
  const archiveEnergyUrl = (focus?: 'measured' | 'missing', view?: 'log', query?: string) => {
    const params = new URLSearchParams();
    if (focus) params.set('energy', focus);
    if (view) params.set('view', view);
    if (query?.trim()) params.set('q', query.trim());
    const queryString = params.toString();
    return queryString ? `/archives?${queryString}` : '/archives';
  };
  const handleTabChange = (tab: DashboardTab) => {
    setActiveTab(tab);
    updateDashboardParams(tab, dateRangeValue);
  };
  const handleDateRangeChange = (range: DateRangeValue) => {
    setDateRangeValue(range);
    updateDashboardParams(activeTab, range);
  };
  useEffect(() => {
    const tabFromUrl = searchParams.get('tab');
    const rangeFromUrl = searchParams.get('range');
    const nextTab = isDashboardTab(tabFromUrl) ? tabFromUrl : 'overview';
    const nextRange = isDateRangeValue(rangeFromUrl) ? rangeFromUrl : '30';
    if (nextTab !== activeTab) setActiveTab(nextTab);
    if (nextRange !== dateRangeValue) setDateRangeValue(nextRange);
  }, [activeTab, dateRangeValue, searchParams]);

  const settingsQuery = useQuery({ queryKey: ['settings'], queryFn: () => api.getSettings() });
  const energyTrackingMode = settingsQuery.data?.energy_tracking_mode ?? 'total';
  const statsQuery = useQuery<ArchiveStats>({
    queryKey: ['business-dashboard', 'archive-stats', dateFrom, dateTo],
    queryFn: () => api.getArchiveStats({ dateFrom, dateTo }),
    enabled: canReadBusinessDashboard,
  });
  const previousStatsQuery = useQuery<ArchiveStats>({
    queryKey: ['business-dashboard', 'archive-stats-previous', previousDateFrom, previousDateTo],
    queryFn: () => api.getArchiveStats({ dateFrom: previousDateFrom, dateTo: previousDateTo }),
    enabled: canReadBusinessDashboard,
  });
  const archiveEventsQuery = useQuery<ArchiveSlim[]>({
    queryKey: ['business-dashboard', 'archive-events', dateFrom, dateTo],
    queryFn: () => api.getArchivesSlim(dateFrom, dateTo),
    enabled: canReadBusinessDashboard,
  });
  const energyHistoryQuery = useQuery<ArchiveEnergyHistoryPoint[]>({
    queryKey: ['business-dashboard', 'energy-history', dateFrom, dateTo],
    queryFn: () => api.getArchiveEnergyHistory({ dateFrom, dateTo, bucket: 'hour' }),
    enabled: canReadBusinessDashboard && energyTrackingMode === 'total',
  });
  const spoolsQuery = useQuery<InventorySpool[]>({
    queryKey: ['business-dashboard', 'spools'],
    queryFn: () => api.getSpools(false),
    enabled: canReadBusinessDashboard,
  });
  const smallPartsQuery = useQuery({
    queryKey: ['business-dashboard', 'material-items'],
    queryFn: () => smallPartsApi.listAll({ active: true }),
    enabled: canReadBusinessDashboard,
  });
  const skuSettingsQuery = useQuery<FilamentSkuSettings[]>({
    queryKey: ['business-dashboard', 'sku-settings'],
    queryFn: () => api.getSkuSettings(),
    enabled: canReadBusinessDashboard,
  });
  const suppliersQuery = useQuery({
    queryKey: ['business-dashboard', 'suppliers'],
    queryFn: () => suppliersApi.list({ active: true, limit: 200 }),
    enabled: canReadBusinessDashboard,
  });
  const offersQuery = useQuery<Offer[]>({
    queryKey: ['business-dashboard', 'offers'],
    queryFn: () => offersApi.list(),
    enabled: canReadBusinessDashboard,
  });
  const ordersQuery = useQuery<CustomerOrder[]>({
    queryKey: ['business-dashboard', 'orders'],
    queryFn: () => ordersApi.list(),
    enabled: canReadBusinessDashboard,
  });
  const documentsQuery = useQuery<CommercialDocument[]>({
    queryKey: ['business-dashboard', 'commercial-documents'],
    queryFn: () => documentManagementApi.listDocuments(),
    enabled: canReadBusinessDashboard,
  });
  const { currencyCode } = useDisplayCurrency(settingsQuery.data?.currency);
  const stats = statsQuery.data;
  const previousStats = previousStatsQuery.data;
  const archiveEvents = useMemo(() => archiveEventsQuery.data ?? [], [archiveEventsQuery.data]);
  const energyHistory = useMemo(
    () => (energyTrackingMode === 'total' ? energyHistoryQuery.data ?? [] : []),
    [energyHistoryQuery.data, energyTrackingMode],
  );
  const spools = useMemo(() => spoolsQuery.data ?? [], [spoolsQuery.data]);
  const smallParts = useMemo(() => smallPartsQuery.data ?? [], [smallPartsQuery.data]);
  const skuSettings = useMemo(() => skuSettingsQuery.data ?? [], [skuSettingsQuery.data]);
  const suppliers = useMemo(() => suppliersQuery.data?.items ?? [], [suppliersQuery.data]);
  const offers = useMemo(() => offersQuery.data ?? [], [offersQuery.data]);
  const orders = useMemo(() => ordersQuery.data ?? [], [ordersQuery.data]);
  const documents = useMemo(() => documentsQuery.data ?? [], [documentsQuery.data]);
  const procurementResources = useMemo(() => {
    const bySignature = new Map<string, DashboardProcurementResource>();
    spools.forEach((spool) => {
      if (spool.archived_at) return;
      const item = spoolProcurementResource(spool);
      if (item.resource.material.trim()) bySignature.set(item.signature, item);
    });
    return Array.from(bySignature.values());
  }, [spools]);
  const procurementOffersQuery = useQuery<Array<{ signature: string; offers: ProcurementOffer[] }>>({
    queryKey: [
      'business-dashboard',
      'procurement-offers',
      procurementResources.map((item) => item.signature).sort().join('||'),
    ],
    queryFn: async () => {
      const offerGroups = await Promise.all(
        procurementResources.map(async (item) => ({
          signature: item.signature,
          offers: await procurementOffersApi.list(item.resource),
        })),
      );
      return offerGroups;
    },
    enabled: canReadBusinessDashboard && procurementResources.length > 0,
  });
  const procurementOfferGroups = useMemo(() => procurementOffersQuery.data ?? [], [procurementOffersQuery.data]);
  const periodOrders = useMemo(
    () => orders.filter((order) => isInDateRange(order.updated_at || order.created_at, rangeStart, rangeEnd)),
    [orders, rangeEnd, rangeStart],
  );
  const periodOffers = useMemo(
    () => offers.filter((offer) => isInDateRange(offer.accepted_at || offer.sent_at || offer.updated_at || offer.created_at, rangeStart, rangeEnd)),
    [offers, rangeEnd, rangeStart],
  );
  const periodDocuments = useMemo(
    () => documents.filter((document) =>
      isInDateRange(document.issue_date || document.created_at, rangeStart, rangeEnd)
      || document.payments.some((payment) => isInDateRange(payment.paid_at, rangeStart, rangeEnd)),
    ),
    [documents, rangeEnd, rangeStart],
  );
  const previousPeriodOrders = useMemo(
    () => orders.filter((order) => isInDateRange(order.updated_at || order.created_at, previousRangeStart, previousRangeEnd)),
    [orders, previousRangeEnd, previousRangeStart],
  );
  const previousPeriodOffers = useMemo(
    () => offers.filter((offer) => isInDateRange(offer.accepted_at || offer.sent_at || offer.updated_at || offer.created_at, previousRangeStart, previousRangeEnd)),
    [offers, previousRangeEnd, previousRangeStart],
  );
  const derived = useMemo(() => {
    const activeOrders = periodOrders
      .filter((order) => order.status !== 'cancelled')
      .filter((order) => hasDisplayCurrency(readAcceptedRevisionCurrency(order), currencyCode));
    const currentOpenOrders = orders.filter((order) => order.status === 'active');
    const completedOrders = activeOrders.filter((order) => order.status === 'completed');
    const runningOrders = activeOrders.filter((order) => order.status === 'active');
    const completedRevenue = completedOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'selling_price'), 0);
    const activeOrderRevenue = runningOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'selling_price'), 0);
    const acceptedRevenue = activeOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'selling_price'), 0);
    const acceptedCost = activeOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'production_cost'), 0);
    const displayCurrencyOffers = periodOffers.filter((offer) => hasDisplayCurrency(readRevisionCurrency(offer), currencyCode));
    const quoteValue = displayCurrencyOffers.reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const draftRevenue = displayCurrencyOffers
      .filter((offer) => offer.status === 'draft')
      .reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const sentRevenue = displayCurrencyOffers
      .filter((offer) => offer.status === 'sent')
      .reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const acceptedOfferRevenue = displayCurrencyOffers
      .filter((offer) => offer.status === 'accepted')
      .reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const pipelineRevenue = displayCurrencyOffers
      .filter((offer) => offer.status === 'draft' || offer.status === 'sent' || offer.status === 'accepted')
      .reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const allMaterialUsage = deriveMaterialUsage(spools, smallParts);
    const materialUsage = allMaterialUsage.slice(0, 6);
    const materialCosts = createMaterialCostMap(spools, smallParts);
    const spoolStockValue = spools.reduce((sum, spool) => {
      const remaining = Math.max(0, spool.label_weight - spool.weight_used);
      return sum + (remaining / 1000) * (spool.cost_per_kg ?? 0);
    }, 0);
    const smallPartStockValue = smallParts.reduce(
      (sum, part) => sum + (asNumber(part.balance.physical) * asNumber(part.unit_cost)),
      0,
    );
    const stockValue = spoolStockValue + smallPartStockValue;
    const lowStockSpoolCount = spools.filter((spool) => {
      const threshold = spool.low_stock_threshold_pct ?? 20;
      if (spool.label_weight <= 0) return false;
      return ((spool.label_weight - spool.weight_used) / spool.label_weight) * 100 <= threshold;
    }).length;
    const lowStockCount = lowStockSpoolCount + smallParts.filter((part) => part.balance.is_low_stock).length;
    const reservedLines = currentOpenOrders.reduce((sum, order) => sum + order.reservations.length, 0);
    const consumedGrams = allMaterialUsage.reduce((sum, item) => sum + item.grams, 0);
    const archiveProductionCost = (stats?.total_cost ?? 0) + (stats?.total_energy_cost ?? 0);
    const productionCost = acceptedCost > 0 ? acceptedCost : archiveProductionCost;
    const margin = acceptedRevenue > 0 ? ((acceptedRevenue - productionCost) / acceptedRevenue) * 100 : 0;
    const paymentDocuments = documents
      .filter(isPaymentDocument)
      .filter((document) => hasDisplayCurrency(document.currency, currencyCode));
    const revenueRows = createRevenueRows(periodOrders, periodOffers, periodDocuments, today, currencyCode, locale);
    const paymentEffectiveRevenue = paymentDocuments.reduce(
      (sum, document) => sum + document.payments
        .filter((payment) => isInDateRange(payment.paid_at, rangeStart, rangeEnd))
        .reduce((paymentSum, payment) => paymentSum + asNumber(payment.amount), 0),
      0,
    );
    const openRevenue = paymentDocuments.reduce((sum, document) => sum + asNumber(document.open_amount), 0);
    const overdueRevenue = paymentDocuments
      .filter((document) => {
        if (!document.due_date || asNumber(document.open_amount) <= 0) return false;
        return (parseBusinessDate(document.due_date)?.getTime() ?? Number.POSITIVE_INFINITY) < today.getTime();
      })
      .reduce((sum, document) => sum + asNumber(document.open_amount), 0);
    const missingPaymentSource = paymentDocuments.length === 0 && (activeOrders.length > 0 || offers.length > 0);
    const energyCost = stats?.total_energy_cost ?? 0;
    const reservedValue = currentOpenOrders.reduce(
      (sum, order) => sum + order.reservations.reduce((reservationSum, reservation) => {
        if (reservation.released_at || reservation.status === 'released') return reservationSum;
        return reservationSum + reservationValue(reservation, materialCosts);
      }, 0),
      0,
    );
    const reservationRows = currentOpenOrders
      .flatMap((order) => order.reservations.map((reservation) => {
        const value = reservationValue(reservation, materialCosts);
        return [
          <EntityLink to={`/orders/${order.id}`}>{order.number}</EntityLink>,
          reservation.material_code ?? reservation.resource_kind,
          `${reservation.requested_quantity} ${reservation.unit_code}`,
          value > 0 ? formatMoney(value, locale, currencyCode) : <span className="text-bambu-gray">{dashboardText('cannotBeValued')}</span>,
          reservation.status === 'fulfilled' || reservation.status === 'allocated' ? 'OK' : <span className="text-amber-300">{dashboardText('check')}</span>,
        ] as Array<ReactNode>;
      }))
      .slice(0, 6);

    const costSlices: CostSlice[] = [
      { label: dashboardText('material'), value: acceptedCost > 0 ? 0 : stats?.total_cost ?? 0, color: '#00a14a' },
      { label: dashboardText('orderCalculation'), value: acceptedCost, color: '#38a8d5' },
      { label: dashboardText('energy'), value: acceptedCost > 0 ? 0 : energyCost, color: '#21b7cf' },
      { label: dashboardText('reservation'), value: reservedValue, color: '#8d73d9' },
    ];

    const pipelineStages: PipelineStage[] = [
      { label: dashboardText('draft'), value: draftRevenue, color: '#00a14a' },
      { label: dashboardText('sent'), value: sentRevenue, color: '#38a8d5' },
      { label: dashboardText('accepted'), value: acceptedOfferRevenue, color: '#d89a18' },
      { label: dashboardText('active'), value: activeOrderRevenue, color: '#8d73d9' },
      { label: dashboardText('completed'), value: completedRevenue, color: '#dc5b64' },
    ];

    return {
      activeOrders,
      completedOrders,
      runningOrders,
      completedRevenue,
      activeOrderRevenue,
      paymentDocuments,
      acceptedRevenue,
      acceptedCost,
      quoteValue,
      pipelineRevenue,
      materialUsage,
      stockValue,
      lowStockCount,
      reservedLines,
      consumedGrams,
      margin,
      revenueRows,
      missingPaymentSource,
      paymentEffectiveRevenue,
      openRevenue,
      overdueRevenue,
      productionCost,
      reservedValue,
      reservationRows,
      costSlices,
      pipelineStages,
    };
  }, [currencyCode, documents, locale, offers, orders, periodDocuments, periodOffers, periodOrders, rangeEnd, rangeStart, smallParts, spools, stats, today]);

  const previousDerived = useMemo(() => {
    const activeOrders = previousPeriodOrders
      .filter((order) => order.status !== 'cancelled')
      .filter((order) => hasDisplayCurrency(readAcceptedRevisionCurrency(order), currencyCode));
    const completedOrders = activeOrders.filter((order) => order.status === 'completed');
    const acceptedRevenue = activeOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'selling_price'), 0);
    const acceptedCost = activeOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'production_cost'), 0);
    const completedRevenue = completedOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'selling_price'), 0);
    const pipelineRevenue = previousPeriodOffers
      .filter((offer) => hasDisplayCurrency(readRevisionCurrency(offer), currencyCode))
      .filter((offer) => offer.status === 'draft' || offer.status === 'sent' || offer.status === 'accepted')
      .reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const paymentDocuments = documents
      .filter(isPaymentDocument)
      .filter((document) => hasDisplayCurrency(document.currency, currencyCode));
    const paymentEffectiveRevenue = paymentDocuments.reduce(
      (sum, document) => sum + document.payments
        .filter((payment) => isInDateRange(payment.paid_at, previousRangeStart, previousRangeEnd))
        .reduce((paymentSum, payment) => paymentSum + asNumber(payment.amount), 0),
      0,
    );
    const archiveProductionCost = (previousStats?.total_cost ?? 0) + (previousStats?.total_energy_cost ?? 0);
    const productionCost = acceptedCost > 0 ? acceptedCost : archiveProductionCost;
    return {
      acceptedRevenue,
      completedRevenue,
      paymentEffectiveRevenue,
      pipelineRevenue,
      productionCost,
      margin: acceptedRevenue > 0 ? ((acceptedRevenue - productionCost) / acceptedRevenue) * 100 : 0,
      completionRate: acceptedRevenue > 0 ? (completedRevenue / acceptedRevenue) * 100 : 0,
      energyKwh: previousStats?.total_energy_kwh ?? 0,
      energyCost: previousStats?.total_energy_cost ?? 0,
    };
  }, [currencyCode, documents, previousPeriodOffers, previousPeriodOrders, previousRangeEnd, previousRangeStart, previousStats]);

  const trend = useMemo(
    () => createTrend(periodOrders, archiveEvents, energyHistory, stats, rangeStart, rangeEnd, currencyCode, locale),
    [archiveEvents, currencyCode, energyHistory, locale, periodOrders, rangeEnd, rangeStart, stats],
  );
  const energyPerHour = (stats?.total_print_time_hours ?? 0) > 0
    ? (stats?.total_energy_kwh ?? 0) / (stats?.total_print_time_hours ?? 1)
    : 0;
  const completionRate = derived.acceptedRevenue > 0
    ? (derived.completedRevenue / derived.acceptedRevenue) * 100
    : 0;
  const energyMode = energyTrackingMode === 'total' ? dashboardText('totalUsage') : dashboardText('printUsage');
  const trendLabels = {
    paymentEffectiveRevenue: createMetricTrend(derived.paymentEffectiveRevenue, previousDerived.paymentEffectiveRevenue, (value) => formatMoney(value, locale, currencyCode)),
    acceptedRevenue: createMetricTrend(derived.acceptedRevenue, previousDerived.acceptedRevenue, (value) => formatMoney(value, locale, currencyCode)),
    contribution: createMetricTrend(Math.max(derived.acceptedRevenue - derived.productionCost, 0), Math.max(previousDerived.acceptedRevenue - previousDerived.productionCost, 0), (value) => formatMoney(value, locale, currencyCode)),
    margin: createMetricTrend(derived.margin, previousDerived.margin, (value) => `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value)} pp`),
    energyKwh: createMetricTrend(stats?.total_energy_kwh ?? 0, previousDerived.energyKwh, (value) => formatKwh(value, locale), false),
    energyCost: createMetricTrend(stats?.total_energy_cost ?? 0, previousDerived.energyCost, (value) => formatMoney(value, locale, currencyCode), false),
    productionCost: createMetricTrend(derived.productionCost, previousDerived.productionCost, (value) => formatMoney(value, locale, currencyCode), false),
    completionRate: createMetricTrend(completionRate, previousDerived.completionRate, (value) => `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value)} pp`),
    pipelineRevenue: createMetricTrend(derived.pipelineRevenue, previousDerived.pipelineRevenue, (value) => formatMoney(value, locale, currencyCode)),
  };
  const lowStockSpools = [...spools]
    .filter((spool) => {
      const remaining = Math.max(0, spool.label_weight - spool.weight_used);
      const threshold = spool.low_stock_threshold_pct ?? 20;
      return spool.label_weight > 0 && (remaining / spool.label_weight) * 100 <= threshold;
    })
    .sort((left, right) => (left.label_weight - left.weight_used) - (right.label_weight - right.weight_used));
  const lowStockValue = lowStockSpools.reduce(
    (sum, spool) => sum + (spoolRemainingGrams(spool) / 1000) * (spool.cost_per_kg ?? 0),
    0,
  );
  const lowStockSmallParts = [...smallParts]
    .filter((part) => part.balance.is_low_stock)
    .sort((left, right) => asNumber(left.balance.available) - asNumber(right.balance.available));
  const lowStockInventoryValue = lowStockValue + lowStockSmallParts.reduce(
    (sum, part) => sum + (asNumber(part.balance.physical) * asNumber(part.unit_cost)),
    0,
  );
  const procurementOffersBySignature = useMemo(() => {
    const result = new Map<string, ProcurementOffer[]>();
    procurementOfferGroups.forEach((group) => result.set(group.signature, group.offers));
    return result;
  }, [procurementOfferGroups]);
  const suppliersById = useMemo(() => {
    const result = new Map<number, Supplier>();
    suppliers.forEach((supplier) => result.set(supplier.id, supplier));
    return result;
  }, [suppliers]);
  const skuSettingsBySignature = useMemo(() => {
    const result = new Map<string, FilamentSkuSettings>();
    skuSettings.forEach((settings) => result.set(skuSettingsSignature(settings), settings));
    return result;
  }, [skuSettings]);
  const procurementOfferForSpool = (spool: InventorySpool) =>
    preferredProcurementOffer(procurementOffersBySignature.get(spoolProcurementResource(spool).signature) ?? []);
  const supplierAssignmentForSpool = (spool: InventorySpool) => {
    const signature = spoolProcurementResource(spool).signature;
    const settings = skuSettingsBySignature.get(signature) ?? null;
    const offer = procurementOfferForSpool(spool);
    const supplier = settings?.default_supplier_id
      ? suppliersById.get(settings.default_supplier_id) ?? offer?.supplier ?? null
      : offer?.supplier ?? null;
    return {
      supplier,
      offer,
      source: settings?.default_supplier_id ? 'sku' : offer ? 'offer' : 'none',
      leadTimeDays: offer?.lead_time_days ?? supplier?.default_lead_time_days ?? settings?.lead_time_days ?? 0,
    };
  };
  const supplierAssignedSpoolCount = spools.filter((spool) => supplierAssignmentForSpool(spool).supplier !== null).length;
  const directSupplierAssignedSpoolCount = spools.filter((spool) => supplierAssignmentForSpool(spool).source === 'sku').length;
  const spoolsWithoutCostCount = spools.filter((spool) => !spool.cost_per_kg).length;
  const activeSmallPartsWithoutCostCount = smallParts.filter((part) => asNumber(part.unit_cost) <= 0).length;
  const spoolsWithLocationCount = spools.filter((spool) => spool.storage_location || spool.location_id).length;
  const smallPartsWithLocationCount = smallParts.filter((part) => part.location_id).length;
  const inventoryItemCount = spools.length + smallParts.length;
  const inventoryWithLocationCount = spoolsWithLocationCount + smallPartsWithLocationCount;
  const staleSpoolRows = spools
    .map((spool) => {
      const remaining = spoolRemainingGrams(spool);
      const value = (remaining / 1000) * (spool.cost_per_kg ?? 0);
      const idleDays = daysSince(spool.last_used ?? spool.created_at, today);
      return { spool, remaining, value, idleDays };
    })
    .filter((row) => row.remaining > 0 && (row.idleDays ?? 0) >= 60)
    .sort((left, right) => (right.value - left.value) || ((right.idleDays ?? 0) - (left.idleDays ?? 0)))
    .slice(0, 6)
    .map((row) => [
      <EntityLink to={spoolDetailUrl(row.spool)}>{spoolItemLabel(row.spool)}</EntityLink>,
      formatMoney(row.value, locale, currencyCode),
      row.idleDays === null ? dashboardText('unknown2') : dashboardText('daysValue2', { value1: row.idleDays }),
      row.spool.storage_location ?? dashboardText('noLocation'),
      row.value > 25 ? <span className="text-amber-300">{dashboardText('checkStock')}</span> : dashboardText('monitor'),
    ] as Array<ReactNode>);
  const inventoryWithoutCostCount = spoolsWithoutCostCount + activeSmallPartsWithoutCostCount;
  const procurementReadinessRows = [
    [dashboardText('costBasis'), dashboardText('itemsValue', { value1: inventoryItemCount - inventoryWithoutCostCount, value2: inventoryItemCount || 0 }), inventoryWithoutCostCount > 0 ? <span className="text-amber-300">{dashboardText('marginIncomplete')}</span> : 'OK', inventoryWithoutCostCount > 0 ? <EntityLink to={inventoryFocusUrl('missing-cost')}>{dashboardText('maintainCosts')}</EntityLink> : dashboardText('noAction')],
    [dashboardText('skuSupplier'), dashboardText('spoolsValue', { value1: directSupplierAssignedSpoolCount, value2: spools.length || 0 }), directSupplierAssignedSpoolCount < spools.length ? <span className="text-amber-300">{dashboardText('assignmentMissing')}</span> : 'OK', <EntityLink to={supplierListUrl()}>{dashboardText('checkSuppliers')}</EntityLink>],
    [dashboardText('overallSupplierCoverage'), dashboardText('spoolsValue', { value1: supplierAssignedSpoolCount, value2: spools.length || 0 }), supplierAssignedSpoolCount < spools.length ? <span className="text-amber-300">{dashboardText('offersMissing')}</span> : 'OK', <EntityLink to={supplierListUrl()}>{dashboardText('checkOffers')}</EntityLink>],
    [dashboardText('storageLocation'), dashboardText('itemsValue', { value1: inventoryWithLocationCount, value2: inventoryItemCount || 0 }), inventoryWithLocationCount < inventoryItemCount ? <span className="text-amber-300">{dashboardText('harderToLocate')}</span> : 'OK', <EntityLink to={inventoryFocusUrl('missing-location')}>{dashboardText('maintainLocations')}</EntityLink>],
    [dashboardText('shortageRate'), dashboardText('itemsValue', { value1: derived.lowStockCount, value2: inventoryItemCount || 0 }), derived.lowStockCount > 0 ? <span className="text-red-300">{dashboardText('reorder')}</span> : 'OK', derived.lowStockCount > 0 ? <EntityLink to={inventoryFocusUrl('low-stock')}>{dashboardText('reorderSuggestions')}</EntityLink> : dashboardText('noAction')],
    [dashboardText('reservationPressure'), dashboardText('linesValue', { value1: derived.reservedLines }), formatMoney(derived.reservedValue, locale, currencyCode), derived.reservedLines > 0 ? <EntityLink to="/orders">{dashboardText('checkOrders')}</EntityLink> : 'OK'],
  ] as Array<Array<ReactNode>>;
  const inventoryRiskRows = [
    ...lowStockSpools.slice(0, 4).map((spool) => {
      const label = [spool.material, spool.subtype, spool.color_name].filter(Boolean).join(' ');
      const remaining = Math.max(0, spool.label_weight - spool.weight_used);
      const pct = spool.label_weight > 0 ? (remaining / spool.label_weight) * 100 : 0;
      return [
        <EntityLink to={spoolDetailUrl(spool)}>{label || dashboardText('spoolValue', { value1: spool.id })}</EntityLink>,
        `${Math.round(remaining)} g`,
        spool.storage_location ?? dashboardText('inventory'),
        pct < 8 ? <span className="text-red-300">{dashboardText('critical')}</span> : <span className="text-amber-300">{dashboardText('low')}</span>,
      ] as Array<ReactNode>;
    }),
    ...lowStockSmallParts.slice(0, 4).map((part) => [
      <EntityLink to={`/warehouse/parts?part=${part.id}`}>{part.name}</EntityLink>,
      `${formatQuantity(asNumber(part.balance.available), locale)} ${part.unit.label || part.unit_code}`,
      part.location_id ? dashboardText('storageLocationValue', { value1: part.location_id }) : dashboardText('materialStorage'),
      asNumber(part.balance.available) <= 0 ? <span className="text-red-300">{dashboardText('critical')}</span> : <span className="text-amber-300">{dashboardText('low')}</span>,
    ] as Array<ReactNode>),
  ];
  const riskRows = inventoryRiskRows;
  const supplierRows = Array.from(
    spools
      .map((spool) => ({ spool, assignment: supplierAssignmentForSpool(spool) }))
      .filter((item) => item.assignment.supplier !== null)
      .reduce((groups, item) => {
        const { spool, assignment } = item;
        const supplier = assignment.supplier;
        if (!supplier) return groups;
        const current = groups.get(supplier.id) ?? {
          supplier,
          materialLabels: new Set<string>(),
          skuCount: 0,
          fallbackCount: 0,
          leadTimes: [] as number[],
        };
        current.materialLabels.add(spoolMaterialLabel(spool));
        if (assignment.source === 'sku') current.skuCount += 1;
        if (assignment.source === 'offer') current.fallbackCount += 1;
        current.leadTimes.push(assignment.leadTimeDays || supplier.default_lead_time_days || 0);
        groups.set(supplier.id, current);
        return groups;
      }, new Map<number, {
        supplier: ProcurementOffer['supplier'];
        materialLabels: Set<string>;
        skuCount: number;
        fallbackCount: number;
        leadTimes: number[];
      }>())
      .values(),
  )
    .sort((left, right) => left.supplier.name.localeCompare(right.supplier.name, locale))
    .map((group) => {
      const shortestLeadTime = group.leadTimes.length > 0 ? Math.min(...group.leadTimes) : group.supplier.default_lead_time_days;
      return [
        <EntityLink to={supplierListUrl(group.supplier.name)}>{group.supplier.name}</EntityLink>,
        compactMaterialList(Array.from(group.materialLabels)),
        dashboardText('daysValue2', { value1: shortestLeadTime }),
        group.supplier.email || group.supplier.phone || group.supplier.website || dashboardText('noContact'),
        group.skuCount > 0
          ? <span className="text-[#35c46f]">{group.skuCount} {dashboardText('directSkuAssignment')}</span>
          : dashboardText('offerFallbacksValue', { value1: group.fallbackCount }),
      ] as Array<ReactNode>;
    });
  const reorderRows = lowStockSpools.slice(0, 6).map((spool) => {
    const label = spoolItemLabel(spool);
    const remaining = Math.max(0, spool.label_weight - spool.weight_used);
    const pct = spool.label_weight > 0 ? (remaining / spool.label_weight) * 100 : 0;
    const assignment = supplierAssignmentForSpool(spool);
    const supplier = assignment.supplier;
    return [
      <EntityLink to={spoolDetailUrl(spool)}>{label}</EntityLink>,
      `${Math.round(remaining)} g`,
      dashboardText('label1Spool'),
      supplier ? <EntityLink to={supplierListUrl(supplier.name)}>{supplier.name}</EntityLink> : <EntityLink to={supplierListUrl(spool.brand ?? '')}>{spool.brand || dashboardText('assignSupplier')}</EntityLink>,
      assignment.leadTimeDays > 0 ? dashboardText('daysValue2', { value1: assignment.leadTimeDays }) : dashboardText('remainingValue', { value1: new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(pct) }),
      pct < 8 ? <span className="text-red-300">{dashboardText('checkToday')}</span> : <span className="text-amber-300">{dashboardText('plan')}</span>,
    ] as Array<ReactNode>;
  });
  const materialPlanningRows = derived.materialUsage
    .filter((item) => item.kind === 'filament')
    .map((item) => {
      const materialSpools = spools.filter((spool) => spoolMaterialLabel(spool) === item.label);
      const assignment = materialSpools
        .map((spool) => supplierAssignmentForSpool(spool))
        .find((candidate) => candidate.supplier !== null) ?? null;
      const supplier = assignment?.supplier ?? null;
      const leadTimeDays = assignment?.leadTimeDays ?? 0;
      const targetDays = Math.max(leadTimeDays + 14, 30);
      const reorderGrams = item.days < targetDays
        ? Math.max(1000, Math.ceil(((targetDays - item.days) * Math.max(item.remaining / Math.max(item.days, 1), 25)) / 100) * 100)
        : 0;
      return {
        label: item.label,
        days: item.days,
        supplier,
        leadTimeDays,
        reorderGrams,
        remaining: item.remaining,
      };
    })
    .sort((left, right) => left.days - right.days)
    .slice(0, 6)
    .map((item) => [
      item.label,
      dashboardText('daysValue2', { value1: item.days }),
      item.supplier ? <EntityLink to={supplierListUrl(item.supplier.name)}>{item.supplier.name}</EntityLink> : dashboardText('assignSupplier'),
      item.supplier ? dashboardText('daysValue2', { value1: item.leadTimeDays }) : '-',
      item.reorderGrams > 0 ? dashboardText('replenishValue', { value1: formatWeightKg(item.reorderGrams, locale) }) : dashboardText('stockSufficient'),
      item.days <= Math.max(item.leadTimeDays + 7, 14)
        ? <span className="text-red-300">{dashboardText('critical')}</span>
        : item.reorderGrams > 0
          ? <span className="text-amber-300">{dashboardText('plan')}</span>
        : 'OK',
    ] as Array<ReactNode>);
  const openReceivableDocuments = [...derived.paymentDocuments]
    .filter((document) => asNumber(document.open_amount) > 0)
    .sort((left, right) => {
      const leftDue = parseBusinessDate(left.due_date)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      const rightDue = parseBusinessDate(right.due_date)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      return leftDue - rightDue;
    });
  const overdueDocuments = openReceivableDocuments.filter((document) =>
    document.due_date ? (parseBusinessDate(document.due_date)?.getTime() ?? Number.POSITIVE_INFINITY) < today.getTime() : false,
  );
  const dueSoonDocuments = openReceivableDocuments.filter((document) => {
    if (!document.due_date) return false;
    const due = parseBusinessDate(document.due_date)?.getTime() ?? Number.POSITIVE_INFINITY;
    const days = Math.ceil((due - today.getTime()) / 86400000);
    return days >= 0 && days <= 7;
  });
  const paymentRows = derived.paymentDocuments
    .flatMap((document) => document.payments
      .filter((payment) => isInDateRange(payment.paid_at, rangeStart, rangeEnd))
      .map((payment) => ({ document, payment })))
    .sort((left, right) =>
      (parseBusinessDate(right.payment.paid_at)?.getTime() ?? 0)
      - (parseBusinessDate(left.payment.paid_at)?.getTime() ?? 0),
    )
    .slice(0, 8)
    .map(({ document, payment }) => [
      parseBusinessDate(payment.paid_at)?.toLocaleDateString(locale) ?? payment.paid_at,
      <EntityLink to={invoiceListUrl('paid')}>{document.number ?? dashboardText('documentValue', { value1: document.id })}</EntityLink>,
      displayCustomer(document.customer_id),
      formatMoney(asNumber(payment.amount), locale, payment.currency || currencyCode),
      dashboardPaymentMethod(payment.method),
    ] as Array<ReactNode>);
  const receivableRows = openReceivableDocuments.slice(0, 8).map((document) => {
    const dueDate = parseBusinessDate(document.due_date);
    const daysUntilDue = dueDate ? Math.ceil((dueDate.getTime() - today.getTime()) / 86400000) : null;
    return [
      <EntityLink to={invoicePaymentUrl(document.id)}>{document.number ?? dashboardText('documentValue', { value1: document.id })}</EntityLink>,
      displayCustomer(document.customer_id),
      dueDate ? dueDate.toLocaleDateString(locale) : <span className="text-bambu-gray">{dashboardText('noDueDate')}</span>,
      formatMoney(asNumber(document.open_amount), locale, document.currency || currencyCode),
      daysUntilDue === null
        ? <span className="text-amber-300">{dashboardText('maintainDueDate')}</span>
        : daysUntilDue < 0
          ? <span className="text-red-300">{Math.abs(daysUntilDue)} {dashboardText('daysOverdue')}</span>
          : daysUntilDue <= 7
            ? <span className="text-amber-300">{dashboardText('dueIn')} {daysUntilDue} {dashboardText('days')}</span>
            : 'OK',
      <EntityLink to={invoicePaymentUrl(document.id)}>{dashboardText('recordPayment')}</EntityLink>,
    ] as Array<ReactNode>;
  });
  const nextPaymentDocument = overdueDocuments[0] ?? dueSoonDocuments[0] ?? openReceivableDocuments[0] ?? null;
  const paymentStatusRows = [
    [dashboardText('receivedPayments'), formatMoney(derived.paymentEffectiveRevenue, locale, currencyCode), dashboardText('transactionsValue', { value1: paymentRows.length }), derived.paymentEffectiveRevenue > 0 ? 'OK' : <span className="text-bambu-gray">{dashboardText('noTransactions')}</span>],
    [dashboardText('openReceivables'), formatMoney(derived.openRevenue, locale, currencyCode), dashboardText('documentsValue', { value1: openReceivableDocuments.length }), nextPaymentDocument ? <EntityLink to={invoicePaymentUrl(nextPaymentDocument.id)}>{dashboardText('recordPayment')}</EntityLink> : <EntityLink to={invoiceListUrl('open')}>{dashboardText('check')}</EntityLink>],
    [dashboardText('overdue'), formatMoney(derived.overdueRevenue, locale, currencyCode), dashboardText('documentsValue', { value1: overdueDocuments.length }), overdueDocuments.length > 0 ? <EntityLink to={invoiceListUrl('overdue')}>{dashboardText('dunningRun')}</EntityLink> : 'OK'],
    [dashboardText('dueSoon'), formatMoney(dueSoonDocuments.reduce((sum, document) => sum + asNumber(document.open_amount), 0), locale, currencyCode), dashboardText('documentsValue', { value1: dueSoonDocuments.length }), dueSoonDocuments.length > 0 ? <EntityLink to={invoiceListUrl('open')}>{dashboardText('sendReminder')}</EntityLink> : 'OK'],
  ] as Array<Array<ReactNode>>;
  const revenueActionRows = [
    [dashboardText('recordPayment'), dashboardText('openDocumentsValue', { value1: openReceivableDocuments.length }), nextPaymentDocument ? <EntityLink to={invoicePaymentUrl(nextPaymentDocument.id)}>{dashboardText('openNextDocument')}</EntityLink> : <EntityLink to={invoiceListUrl('open')}>{dashboardText('openInvoices')}</EntityLink>, openReceivableDocuments.length > 0 ? dashboardText('confirmManually') : dashboardText('noAction')],
    [dashboardText('prepareDunningRun'), dashboardText('overdueValue', { value1: overdueDocuments.length }), formatMoney(derived.overdueRevenue, locale, currencyCode), overdueDocuments.length > 0 ? <EntityLink to={invoiceListUrl('overdue')}>{dashboardText('check')}</EntityLink> : 'OK'],
    [dashboardText('separatePipeline'), formatMoney(derived.pipelineRevenue, locale, currencyCode), <EntityLink to="/orders/offers">{dashboardText('offers')}</EntityLink>, dashboardText('doNotCountAsReceivedRevenue')],
    [dashboardText('bankReconciliationLater'), derived.missingPaymentSource ? dashboardText('sourceMissing') : dashboardText('sourceAvailable'), dashboardText('roadmap'), dashboardText('connectOptionally')],
  ] as Array<Array<ReactNode>>;
  const energyPerKg = (stats?.total_filament_grams ?? 0) > 0
    ? (stats?.total_energy_kwh ?? 0) / ((stats?.total_filament_grams ?? 1) / 1000)
    : 0;
  const hasEnergyHistory = energyHistory.some((point) => asNumber(point.energy_kwh) > 0);
  const measuredEnergyEvents = archiveEvents.filter((event) => asNumber(event.energy_kwh) > 0 || asNumber(event.energy_cost) > 0);
  const energyDataCoverage = archiveEvents.length > 0
    ? (hasEnergyHistory ? 100 : (measuredEnergyEvents.length / archiveEvents.length) * 100)
    : ((stats?.total_energy_kwh ?? 0) > 0 ? 100 : 0);
  const measuredEventKwh = archiveEvents.reduce((sum, event) => sum + asNumber(event.energy_kwh), 0);
  const measuredEventCost = archiveEvents.reduce((sum, event) => sum + asNumber(event.energy_cost), 0);
  const eventDurationTotal = archiveEvents.reduce((sum, event) => sum + Math.max(asNumber(event.actual_time_seconds), 1), 0);
  const hourlyEnergy = new Map<number, { kwh: number; cost: number; runs: number }>();
  if (hasEnergyHistory) {
    energyHistory.forEach((point) => {
      const date = new Date(point.bucket_start);
      if (Number.isNaN(date.getTime())) return;
      const hour = date.getHours();
      const current = hourlyEnergy.get(hour) ?? { kwh: 0, cost: 0, runs: 0 };
      current.kwh += asNumber(point.energy_kwh);
      current.cost += asNumber(point.energy_cost);
      current.runs += Math.max(asNumber(point.sample_count), 1);
      hourlyEnergy.set(hour, current);
    });
  } else {
    archiveEvents.forEach((event) => {
      const date = eventDate(event);
      if (!date) return;
      const hour = date.getHours();
      const weight = Math.max(asNumber(event.actual_time_seconds), 1);
      const kwh = measuredEventKwh > 0
        ? asNumber(event.energy_kwh)
        : eventDurationTotal > 0
          ? ((stats?.total_energy_kwh ?? 0) * weight) / eventDurationTotal
          : 0;
      const cost = measuredEventCost > 0
        ? asNumber(event.energy_cost)
        : (stats?.total_energy_kwh ?? 0) > 0
          ? ((stats?.total_energy_cost ?? 0) * kwh) / (stats?.total_energy_kwh ?? 1)
          : 0;
      const current = hourlyEnergy.get(hour) ?? { kwh: 0, cost: 0, runs: 0 };
      current.kwh += kwh;
      current.cost += cost;
      current.runs += 1;
      hourlyEnergy.set(hour, current);
    });
  }
  const peakHourRows = Array.from(hourlyEnergy.entries())
    .map(([hour, value]) => ({ hour, ...value }))
    .sort((left, right) => right.kwh - left.kwh)
    .slice(0, 6)
    .map((row) => [
      `${String(row.hour).padStart(2, '0')}:00-${String((row.hour + 1) % 24).padStart(2, '0')}:00`,
      formatKwh(row.kwh, locale),
      formatMoney(row.cost, locale, currencyCode),
      dashboardText('printsValue', { value1: row.runs }),
      row.kwh > 0 && row.kwh >= (stats?.total_energy_kwh ?? 0) * 0.2 ? <span className="text-amber-300">{dashboardText('checkPeak')}</span> : 'OK',
    ] as Array<ReactNode>);
  const energyActionRows = [
    [dashboardText('periodTotal'), formatKwh(stats?.total_energy_kwh ?? 0, locale), selectedDateRange.label, <EntityLink to={archiveEnergyUrl('measured')}>{dashboardEnergySource(stats?.energy_source, dashboardText('archive'))}</EntityLink>],
    [dashboardText('energyCosts'), formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode), selectedDateRange.label, (stats?.total_energy_cost ?? 0) > 0 ? <EntityLink to={archiveEnergyUrl('measured')}>{dashboardText('checkCosts')}</EntityLink> : <span className="text-bambu-gray">{dashboardText('noCosts')}</span>],
    [dashboardText('costsKwh'), formatMoney(settingsQuery.data?.energy_cost_per_kwh ?? 0, locale, currencyCode), dashboardText('setting'), <EntityLink to={energyCostSettingsUrl}>{dashboardText('open3')}</EntityLink>],
    [dashboardText('printIntensity'), `${energyPerHour.toFixed(2)} kWh/h`, dashboardText('filamentValue', { value1: formatWeightKg((stats?.total_filament_grams ?? 0), locale) }), energyPerHour > 0 ? 'OK' : <span className="text-amber-300">{dashboardText('noHours')}</span>],
    [dashboardText('measurementCoverage'), formatPercent(energyDataCoverage, locale), dashboardText('eventsValue', { value1: measuredEnergyEvents.length, value2: archiveEvents.length || 0 }), energyDataCoverage >= 80 ? <EntityLink to={archiveEnergyUrl('measured')}>{dashboardText('measurements')}</EntityLink> : <EntityLink to={archiveEnergyUrl('missing')}>{dashboardText('dataGap')}</EntityLink>],
  ];
  const printerRows = Object.entries(stats?.prints_by_printer ?? {})
    .sort(([, left], [, right]) => right - left)
    .slice(0, 6)
    .map(([printer, count]) => [
      <EntityLink to="/printers">{printer}</EntityLink>,
      String(count),
      formatKwh((stats?.total_prints ?? 0) > 0 ? ((stats?.total_energy_kwh ?? 0) * count) / (stats?.total_prints ?? 1) : 0, locale),
      (stats?.total_prints ?? 0) > 0 ? formatPercent((count / (stats?.total_prints ?? 1)) * 100, locale) : '0 %',
    ] as Array<ReactNode>);
  const energyEventRows = [...archiveEvents]
    .sort((left, right) => (eventDate(right)?.getTime() ?? 0) - (eventDate(left)?.getTime() ?? 0))
    .slice(0, 8)
    .map((event) => [
      eventDate(event)?.toLocaleDateString(locale) ?? '-',
      <EntityLink to={archiveEnergyUrl(undefined, 'log', event.print_name || '')}>{event.print_name || dashboardText('unnamedPrint')}</EntityLink>,
      event.printer_id ? <EntityLink to="/printers">{dashboardText('printerValue', { value1: event.printer_id })}</EntityLink> : dashboardText('unknown2'),
      asNumber(event.energy_kwh) > 0 ? formatKwh(asNumber(event.energy_kwh), locale) : <span className="text-bambu-gray">{dashboardText('fromPeriod')}</span>,
      asNumber(event.energy_cost) > 0 ? formatMoney(asNumber(event.energy_cost), locale, currencyCode) : <span className="text-bambu-gray">{dashboardText('proportional')}</span>,
    ] as Array<ReactNode>);
  const energyQualityRows = [
    [dashboardText('printLogMeasurements'), `${measuredEnergyEvents.length}/${archiveEvents.length || 0}`, formatPercent(energyDataCoverage, locale), energyDataCoverage >= 80 ? <EntityLink to={archiveEnergyUrl('measured')}>{dashboardText('stable')}</EntityLink> : <EntityLink to={archiveEnergyUrl('missing')}>{dashboardText('addMeasurements')}</EntityLink>],
    [dashboardText('timeBasedEstimate'), archiveEvents.length > measuredEnergyEvents.length ? dashboardText('printsValue', { value1: archiveEvents.length - measuredEnergyEvents.length }) : dashboardText('label0Prints'), dashboardEnergySource(stats?.energy_source, dashboardText('archive')), archiveEvents.length > measuredEnergyEvents.length ? <EntityLink to={archiveEnergyUrl('missing')}>{dashboardText('markEstimateClearly')}</EntityLink> : 'OK'],
    [dashboardText('smartPlugHistory2'), stats?.energy_data_warming_up ? dashboardText('warmingUp') : dashboardText('ready'), selectedDateRange.label, stats?.energy_data_warming_up ? <span className="text-amber-300">{dashboardText('collectHistory')}</span> : 'OK'],
    [dashboardText('costBasis'), formatMoney(settingsQuery.data?.energy_cost_per_kwh ?? 0, locale, currencyCode), dashboardText('settings'), (settingsQuery.data?.energy_cost_per_kwh ?? 0) > 0 ? 'OK' : <EntityLink to={energyCostSettingsUrl}>{dashboardText('maintain')}</EntityLink>],
  ];
  const energyRecommendationRows = [
    [dashboardText('peakWindows'), peakHourRows.length > 0 ? peakHourRows[0][0] : dashboardText('noData'), peakHourRows.length > 0 ? peakHourRows[0][1] : '-', peakHourRows.length > 0 ? dashboardText('consolidatePrintPlanning') : dashboardText('collectData')],
    [dashboardText('costsPerKg'), energyPerKg > 0 ? `${energyPerKg.toFixed(2)} kWh/kg` : dashboardText('noData'), formatWeightKg(stats?.total_filament_grams ?? 0, locale), energyPerKg > 0 ? dashboardText('monitorMaterialMix') : dashboardText('waitForArchiveData')],
    [dashboardText('costsPerPrint'), (stats?.total_prints ?? 0) > 0 ? formatMoney((stats?.total_energy_cost ?? 0) / (stats?.total_prints ?? 1), locale, currencyCode) : dashboardText('noData'), dashboardText('printsValue', { value1: stats?.total_prints ?? 0 }), (stats?.total_prints ?? 0) > 0 ? dashboardText('checkCalculation') : dashboardText('noAction')],
    [dashboardText('improveCoverage'), formatPercent(energyDataCoverage, locale), dashboardEnergySource(stats?.energy_source, dashboardText('archive')), energyDataCoverage < 80 ? <EntityLink to={archiveEnergyUrl('missing')}>{dashboardText('checkSmartPlugLogs')}</EntityLink> : 'OK'],
  ];
  const orderMarginRows = derived.activeOrders
    .map((order) => {
      const revenue = readAcceptedRevisionValue(order, 'selling_price');
      const cost = readAcceptedRevisionValue(order, 'production_cost');
      const margin = revenue > 0 ? ((revenue - cost) / revenue) * 100 : 0;
      const title = readRevisionText(order.accepted_snapshot, 'title');
      return {
        order,
        title,
        revenue,
        cost,
        margin,
      };
    })
    .filter((row) => row.revenue > 0 || row.cost > 0)
    .sort((left, right) => left.margin - right.margin)
    .slice(0, 6)
    .map((row) => [
      <EntityLink to={`/orders/${row.order.id}`}>{row.order.number}</EntityLink>,
      row.title || formatMoney(row.revenue, locale, currencyCode),
      formatMoney(row.cost, locale, currencyCode),
      formatPercent(row.margin, locale),
      row.margin < 20 ? <span className="text-red-300">{dashboardText('marginRisk')}</span> : row.margin < 35 ? <span className="text-amber-300">{dashboardText('check2')}</span> : 'OK',
    ] as Array<ReactNode>);
  const marginSourceRows = derived.activeOrders
    .map((order) => {
      const revenue = readAcceptedRevisionValue(order, 'selling_price');
      const cost = readAcceptedRevisionValue(order, 'production_cost');
      const margin = revenue > 0 ? ((revenue - cost) / revenue) * 100 : 0;
      return { order, revenue, cost, margin };
    })
    .filter((row) => row.revenue > 0 || row.cost > 0);
  const lowMarginOrders = marginSourceRows.filter((row) => row.revenue > 0 && row.margin < 25);
  const contributionRows = [
    [dashboardText('orderValue'), formatMoney(derived.acceptedRevenue, locale, currencyCode), dashboardText('ordersValue', { value1: derived.activeOrders.length }), dashboardText('basis')],
    [dashboardText('productionCosts'), formatMoney(derived.productionCost, locale, currencyCode), dashboardText('materialProductionEnergy'), derived.productionCost > derived.acceptedRevenue && derived.acceptedRevenue > 0 ? <span className="text-red-300">{dashboardText('tooHigh')}</span> : 'OK'],
    [dashboardText('contributionMargin'), formatMoney(Math.max(derived.acceptedRevenue - derived.productionCost, 0), locale, currencyCode), formatPercent(derived.margin, locale), derived.margin < 25 && derived.acceptedRevenue > 0 ? <span className="text-amber-300">{dashboardText('check')}</span> : 'OK'],
    [dashboardText('reservedInventoryValue'), formatMoney(derived.reservedValue, locale, currencyCode), dashboardText('reservationsValue', { value1: derived.reservedLines }), derived.reservedValue > 0 ? dashboardText('committed') : dashboardText('available')],
  ] as Array<Array<ReactNode>>;
  const costControlRows = [
    [dashboardText('archiveCosts'), formatMoney(stats?.total_cost ?? 0, locale, currencyCode), stats?.total_prints ? dashboardText('printsValue', { value1: stats.total_prints }) : dashboardText('noPrints'), (stats?.total_cost ?? 0) > 0 ? <EntityLink to="/archives">{dashboardText('check')}</EntityLink> : 'OK'],
    [dashboardText('orderCalculation'), formatMoney(derived.acceptedCost, locale, currencyCode), <EntityLink to="/orders/calculation">{dashboardText('calculation')}</EntityLink>, dashboardText('costBasis')],
    [dashboardText('energyShare'), formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode), formatKwh(stats?.total_energy_kwh ?? 0, locale), (stats?.total_energy_cost ?? 0) > 0 ? <EntityLink to={dashboardTabUrl('energy')}>{dashboardText('viewEnergy')}</EntityLink> : dashboardText('noCosts')],
    [dashboardText('inventoryCommitment'), formatMoney(derived.reservedValue, locale, currencyCode), dashboardText('linesValue', { value1: derived.reservedLines }), derived.reservedLines > 0 ? <EntityLink to={dashboardTabUrl('inventory')}>{dashboardText('checkReservations')}</EntityLink> : 'OK'],
  ] as Array<Array<ReactNode>>;
  const marginActionRows = [
    [dashboardText('marginBelow25'), dashboardText('ordersValue', { value1: lowMarginOrders.length }), lowMarginOrders.length > 0 ? formatMoney(lowMarginOrders.reduce((sum, row) => sum + row.revenue, 0), locale, currencyCode) : '-', lowMarginOrders.length > 0 ? <span className="text-amber-300">{dashboardText('recalculate')}</span> : 'OK'],
    [dashboardText('costsWithoutRevenue'), derived.acceptedRevenue <= 0 && derived.productionCost > 0 ? formatMoney(derived.productionCost, locale, currencyCode) : '0,00 €', dashboardText('period2'), derived.acceptedRevenue <= 0 && derived.productionCost > 0 ? <span className="text-red-300">{dashboardText('check')}</span> : 'OK'],
    [dashboardText('energyInCalculation'), formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode), settingsQuery.data?.energy_tracking_mode ?? dashboardText('archive'), (stats?.total_energy_cost ?? 0) > 0 ? dashboardText('included') : <span className="text-amber-300">{dashboardText('noData')}</span>],
    [dashboardText('maintainMaterialCosts'), dashboardText('itemsValue2', { value1: inventoryWithoutCostCount }), <EntityLink to={inventoryFocusUrl('missing-cost')}>{dashboardText('openInventory')}</EntityLink>, inventoryWithoutCostCount > 0 ? <span className="text-amber-300">{dashboardText('complete')}</span> : 'OK'],
  ] as Array<Array<ReactNode>>;
  const overviewPriorityRows = [
    [
      dashboardText('revenue'),
      overdueDocuments.length > 0 ? <span className="text-red-300">{dashboardText('overdue2')}</span> : openReceivableDocuments.length > 0 ? <span className="text-amber-300">{dashboardText('open4')}</span> : 'OK',
      overdueDocuments.length > 0 ? formatMoney(derived.overdueRevenue, locale, currencyCode) : formatMoney(derived.openRevenue, locale, currencyCode),
      openReceivableDocuments.length > 0 ? <EntityLink to={dashboardTabUrl('revenue')}>{dashboardText('checkReceivables')}</EntityLink> : dashboardText('noAction'),
    ],
    [
      dashboardText('margin'),
      lowMarginOrders.length > 0 ? <span className="text-amber-300">{dashboardText('risk')}</span> : 'OK',
      dashboardText('ordersValue', { value1: lowMarginOrders.length }),
      lowMarginOrders.length > 0 ? <EntityLink to={dashboardTabUrl('margin')}>{dashboardText('checkCalculation')}</EntityLink> : dashboardText('noAction'),
    ],
    [
      dashboardText('inventory'),
      derived.lowStockCount > 0 ? <span className="text-red-300">{dashboardText('replenishment')}</span> : 'OK',
      dashboardText('itemsValue2', { value1: derived.lowStockCount }),
      derived.lowStockCount > 0 ? <EntityLink to={dashboardTabUrl('inventory')}>{dashboardText('reorderSuggestions')}</EntityLink> : dashboardText('stockStable'),
    ],
    [
      dashboardText('energy'),
      energyDataCoverage < 80 ? <span className="text-amber-300">{dashboardText('dataGap')}</span> : 'OK',
      formatPercent(energyDataCoverage, locale),
      energyDataCoverage < 80 ? <EntityLink to={dashboardTabUrl('energy')}>{dashboardText('checkMeasurementBasis')}</EntityLink> : dashboardText('measurementBasisStable'),
    ],
    [
      dashboardText('pipeline'),
      derived.pipelineRevenue > derived.paymentEffectiveRevenue && derived.paymentEffectiveRevenue <= 0 ? <span className="text-amber-300">{dashboardText('notAReceivedPayment')}</span> : 'OK',
      formatMoney(derived.pipelineRevenue, locale, currencyCode),
      <EntityLink to="/orders/offers">{dashboardText('openOffers')}</EntityLink>,
    ],
  ] as Array<Array<ReactNode>>;
  const overviewDataQualityRows = [
    [
      dashboardText('payments'),
      paymentRows.length > 0 ? dashboardText('transactionsValue', { value1: paymentRows.length }) : dashboardText('noTransactions'),
      derived.missingPaymentSource ? <span className="text-amber-300">{dashboardText('manualConfirmationMissing')}</span> : dashboardText('receivablesCanBeEvaluated'),
      <EntityLink to={invoiceListUrl(derived.openRevenue > 0 ? 'open' : undefined)}>{dashboardText('invoices')}</EntityLink>,
    ],
    [
      dashboardText('materialCosts'),
      dashboardText('itemsValue', { value1: inventoryItemCount - inventoryWithoutCostCount, value2: inventoryItemCount || 0 }),
      inventoryWithoutCostCount > 0 ? <span className="text-amber-300">{dashboardText('marginIncomplete')}</span> : dashboardText('costBasisOk'),
      inventoryWithoutCostCount > 0 ? <EntityLink to={inventoryFocusUrl('missing-cost')}>{dashboardText('maintainCosts')}</EntityLink> : dashboardText('noAction'),
    ],
    [
      dashboardText('suppliers'),
      dashboardText('directTotalValue', { value1: directSupplierAssignedSpoolCount, value2: spools.length || 0, value3: supplierAssignedSpoolCount }),
      directSupplierAssignedSpoolCount < spools.length ? <span className="text-amber-300">{dashboardText('skuAssignmentMissing')}</span> : dashboardText('replenishmentCanBeDetermined'),
      <EntityLink to={supplierListUrl()}>{dashboardText('suppliers')}</EntityLink>,
    ],
    [
      dashboardText('energy'),
      formatPercent(energyDataCoverage, locale),
      energyDataCoverage < 80 ? <span className="text-amber-300">{dashboardText('partlyEstimated')}</span> : dashboardText('measurementsReliable'),
      <EntityLink to="/settings?tab=operations">{dashboardText('settings')}</EntityLink>,
    ],
    [
      dashboardText('calculation'),
      dashboardText('ordersValue2', { value1: marginSourceRows.length, value2: derived.activeOrders.length || 0 }),
      marginSourceRows.length < derived.activeOrders.length ? <span className="text-amber-300">{dashboardText('notAllOrdersValued')}</span> : dashboardText('marginsCanBeDetermined'),
      <EntityLink to="/orders/calculation">{dashboardText('calculation')}</EntityLink>,
    ],
  ] as Array<Array<ReactNode>>;
  const forecastScale30 = 30 / Math.max(selectedDateRange.days, 1);
  const forecastPaymentRevenue = derived.paymentEffectiveRevenue * forecastScale30;
  const forecastProductionCost = derived.productionCost * forecastScale30;
  const forecastEnergyKwh = (stats?.total_energy_kwh ?? 0) * forecastScale30;
  const forecastEnergyCost = (stats?.total_energy_cost ?? 0) * forecastScale30;
  const forecastMaterialGrams = derived.materialUsage.filter((item) => item.kind === 'filament').reduce((sum, item) => {
    const dailyUse = item.remaining / Math.max(item.days, 1);
    return sum + (Number.isFinite(dailyUse) ? dailyUse * 30 : 0);
  }, 0);
  const openDueSoonValue = dueSoonDocuments.reduce((sum, document) => sum + asNumber(document.open_amount), 0);
  const overviewForecastRows = [
    [
      dashboardText('paymentReceipt'),
      formatMoney(forecastPaymentRevenue, locale, currencyCode),
      dashboardText('transactionsValue', { value1: paymentRows.length }),
      forecastPaymentRevenue > 0 ? dashboardText('planCashFlow') : <EntityLink to={invoiceListUrl('open')}>{dashboardText('bookPayments')}</EntityLink>,
    ],
    [
      dashboardText('costRunRate'),
      formatMoney(forecastProductionCost, locale, currencyCode),
      dashboardText('productionIncludingEnergy'),
      forecastProductionCost > derived.acceptedRevenue && derived.acceptedRevenue > 0 ? <span className="text-amber-300">{dashboardText('checkCostCoverage')}</span> : <EntityLink to={dashboardTabUrl('margin')}>{dashboardText('viewCosts')}</EntityLink>,
    ],
    [
      dashboardText('energyDemand'),
      formatKwh(forecastEnergyKwh, locale),
      formatMoney(forecastEnergyCost, locale, currencyCode),
      forecastEnergyKwh > 0 ? <EntityLink to={dashboardTabUrl('energy')}>{dashboardText('checkPeakTimes')}</EntityLink> : <EntityLink to="/settings?tab=operations">{dashboardText('maintainMeasurements')}</EntityLink>,
    ],
    [
      dashboardText('materialUsage'),
      formatWeightKg(forecastMaterialGrams, locale),
      dashboardText('sinceUsageReset'),
      forecastMaterialGrams > 0 ? <EntityLink to={inventoryFocusUrl('low-stock')}>{dashboardText('planReplenishment')}</EntityLink> : <EntityLink to={inventoryFocusUrl('used')}>{dashboardText('maintainUsage')}</EntityLink>,
    ],
    [
      dashboardText('receivables'),
      formatMoney(derived.openRevenue, locale, currencyCode),
      openDueSoonValue > 0 ? dashboardText('dueSoonValue', { value1: formatMoney(openDueSoonValue, locale, currencyCode) }) : dashboardText('currentStatus'),
      derived.openRevenue > 0 ? <EntityLink to={invoiceListUrl(overdueDocuments.length > 0 ? 'overdue' : 'open')}>{dashboardText('openDueDates')}</EntityLink> : dashboardText('noAction'),
    ],
    [
      dashboardText('replenishmentRisk'),
      dashboardText('itemsValue2', { value1: derived.lowStockCount }),
      lowStockInventoryValue > 0 ? formatMoney(lowStockInventoryValue, locale, currencyCode) : dashboardText('noCommittedValue'),
      derived.lowStockCount > 0 ? <EntityLink to={inventoryFocusUrl('low-stock')}>{dashboardText('reorderSuggestions')}</EntityLink> : dashboardText('stockStable'),
    ],
  ] as Array<Array<ReactNode>>;
  const revenueShortcuts: ActionShortcut[] = [
    {
      label: dashboardText('recordPayment'),
      detail: nextPaymentDocument
        ? dashboardText('openValue', { value1: nextPaymentDocument.number ?? dashboardText('documentValue', { value1: nextPaymentDocument.id }), value2: formatMoney(asNumber(nextPaymentDocument.open_amount), locale, nextPaymentDocument.currency || currencyCode) })
        : dashboardText('noOpenDocuments'),
      to: nextPaymentDocument ? invoicePaymentUrl(nextPaymentDocument.id) : invoiceListUrl('open'),
      icon: Receipt,
      tone: nextPaymentDocument ? 'green' : 'neutral',
    },
    {
      label: dashboardText('checkDueDates'),
      detail: dashboardText('overdueDueSoonValue', { value1: overdueDocuments.length, value2: dueSoonDocuments.length }),
      to: invoiceListUrl(overdueDocuments.length > 0 ? 'overdue' : 'open'),
      icon: AlertTriangle,
      tone: overdueDocuments.length > 0 ? 'red' : dueSoonDocuments.length > 0 ? 'amber' : 'neutral',
    },
    {
      label: dashboardText('openOffers'),
      detail: formatMoney(derived.pipelineRevenue, locale, currencyCode),
      to: '/orders/offers',
      icon: TrendingUp,
      tone: 'blue',
    },
    {
      label: dashboardText('invoiceList'),
      detail: dashboardText('invoicesWithPaymentDataValue', { value1: derived.paymentDocuments.length }),
      to: invoiceListUrl(),
      icon: ClipboardList,
      tone: 'green',
    },
  ];
  const marginShortcuts: ActionShortcut[] = [
    {
      label: dashboardText('openCalculation'),
      detail: dashboardText('valuedOrdersValue', { value1: marginSourceRows.length }),
      to: '/orders/calculation',
      icon: Factory,
      tone: 'green',
    },
    {
      label: dashboardText('lowMargin'),
      detail: dashboardText('ordersBelow25Value', { value1: lowMarginOrders.length }),
      to: lowMarginOrders[0] ? `/orders/${lowMarginOrders[0].order.id}` : '/orders',
      icon: AlertTriangle,
      tone: lowMarginOrders.length > 0 ? 'amber' : 'neutral',
    },
    {
      label: dashboardText('checkEnergyShare'),
      detail: formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode),
      to: dashboardTabUrl('energy'),
      icon: Zap,
      tone: (stats?.total_energy_cost ?? 0) > 0 ? 'cyan' : 'neutral',
    },
    {
      label: dashboardText('maintainMaterialCosts'),
      detail: dashboardText('itemsWithoutCostsValue', { value1: inventoryWithoutCostCount }),
      to: inventoryFocusUrl(),
      icon: Package,
      tone: inventoryWithoutCostCount > 0 ? 'amber' : 'neutral',
    },
  ];
  const inventoryShortcuts: ActionShortcut[] = [
    {
      label: dashboardText('reorderSuggestions'),
      detail: dashboardText('shortageSignalsValue', { value1: derived.lowStockCount }),
      to: inventoryFocusUrl('low-stock'),
      icon: AlertTriangle,
      tone: derived.lowStockCount > 0 ? 'red' : 'neutral',
    },
    {
      label: dashboardText('maintainSuppliers'),
      detail: dashboardText('directWithSourceValue', { value1: directSupplierAssignedSpoolCount, value2: spools.length || 0, value3: supplierAssignedSpoolCount }),
      to: supplierListUrl(),
      icon: Truck,
      tone: directSupplierAssignedSpoolCount < spools.length ? 'amber' : 'green',
    },
    {
      label: dashboardText('openFilament'),
      detail: dashboardText('spoolsValue2', { value1: spools.length, value2: formatMoney(derived.stockValue, locale, currencyCode) }),
      to: inventoryFocusUrl('used'),
      icon: Warehouse,
      tone: 'green',
    },
    {
      label: dashboardText('reservations'),
      detail: dashboardText('linesValue2', { value1: derived.reservedLines, value2: formatMoney(derived.reservedValue, locale, currencyCode) }),
      to: '/orders',
      icon: ClipboardList,
      tone: derived.reservedLines > 0 ? 'blue' : 'neutral',
    },
  ];
  const energyShortcuts: ActionShortcut[] = [
    {
      label: dashboardText('configureEnergy'),
      detail: dashboardText('perKwhValue', { value1: formatMoney(settingsQuery.data?.energy_cost_per_kwh ?? 0, locale, currencyCode) }),
      to: energyCostSettingsUrl,
      icon: BatteryCharging,
      tone: (settingsQuery.data?.energy_cost_per_kwh ?? 0) > 0 ? 'green' : 'amber',
    },
    {
      label: dashboardText('checkArchive'),
      detail: dashboardText('printEventsValue', { value1: archiveEvents.length }),
      to: archiveEnergyUrl(undefined, 'log'),
      icon: BarChart3,
      tone: archiveEvents.length > 0 ? 'cyan' : 'neutral',
    },
    {
      label: dashboardText('viewPrinters'),
      detail: dashboardText('sourcesInTheMixValue', { value1: printerRows.length }),
      to: '/printers',
      icon: Factory,
      tone: printerRows.length > 0 ? 'blue' : 'neutral',
    },
    {
      label: dashboardText('costImpact'),
      detail: `${formatKwh(stats?.total_energy_kwh ?? 0, locale)} · ${selectedDateRange.label}`,
      to: dashboardTabUrl('margin'),
      icon: CircleDollarSign,
      tone: 'amber',
    },
  ];
  const exportSections = (() => {
    switch (activeTab) {
      case 'revenue':
        return [
          { title: dashboardText('paymentStatus'), columns: [dashboardText('status'), dashboardText('value'), dashboardText('scope'), dashboardText('action')], rows: paymentStatusRows },
          { title: dashboardText('openReceivables'), columns: [dashboardText('document'), dashboardText('customer'), dashboardText('due'), dashboardText('open'), dashboardText('signal'), dashboardText('action')], rows: receivableRows },
          { title: dashboardText('paymentReceipts'), columns: [dashboardText('date'), dashboardText('document'), dashboardText('customer'), dashboardText('amount'), dashboardText('method')], rows: paymentRows },
          { title: dashboardText('revenueActions'), columns: [dashboardText('topic'), dashboardText('scope'), dashboardText('target'), dashboardText('action')], rows: revenueActionRows },
        ];
      case 'margin':
        return [
          { title: dashboardText('contributionMarginSummary'), columns: [dashboardText('metric'), dashboardText('value'), dashboardText('basis'), dashboardText('signal')], rows: contributionRows },
          { title: dashboardText('costControl'), columns: [dashboardText('driver'), dashboardText('value'), dashboardText('source'), dashboardText('action')], rows: costControlRows },
          { title: dashboardText('marginActions'), columns: [dashboardText('topic'), dashboardText('scope'), dashboardText('valueTarget'), dashboardText('action')], rows: marginActionRows },
          { title: dashboardText('ordersByMargin'), columns: [dashboardText('order'), dashboardText('revenueTitle'), dashboardText('costs'), dashboardText('margin'), dashboardText('signal')], rows: orderMarginRows },
        ];
      case 'inventory':
        return [
          { title: dashboardText('reorderingAndReservations'), columns: [dashboardText('resource'), dashboardText('stock'), dashboardText('locationSource'), dashboardText('signal')], rows: riskRows },
          { title: dashboardText('supplierDashboard'), columns: [dashboardText('supplier'), dashboardText('materialSourcing'), dashboardText('leadTime'), dashboardText('contact'), dashboardText('status')], rows: supplierRows },
          { title: dashboardText('reorderSuggestions'), columns: [dashboardText('item'), dashboardText('stock'), dashboardText('suggestion'), dashboardText('supplier'), dashboardText('leadTime'), dashboardText('action')], rows: reorderRows },
          { title: dashboardText('materialSupplierPlanning'), columns: [dashboardText('material'), dashboardText('stockCoverage'), dashboardText('supplier'), dashboardText('leadTime'), dashboardText('suggestion'), dashboardText('signal')], rows: materialPlanningRows },
          { title: dashboardText('procurementReadiness'), columns: [dashboardText('checkPoint'), dashboardText('coverage'), dashboardText('signal'), dashboardText('action')], rows: procurementReadinessRows },
          { title: dashboardText('slowMovingStockTiedUpCapital'), columns: [dashboardText('spool'), dashboardText('value'), dashboardText('idleTime'), dashboardText('location'), dashboardText('action')], rows: staleSpoolRows },
        ];
      case 'energy':
        return [
          { title: dashboardText('energySignals'), columns: [dashboardText('signal'), dashboardText('value'), dashboardText('timeWindow'), dashboardText('action')], rows: energyActionRows },
          { title: dashboardText('energyPerPrint'), columns: [dashboardText('date'), dashboardText('print'), dashboardText('printer'), 'kWh', dashboardText('costs')], rows: energyEventRows },
          { title: dashboardText('peakWindows'), columns: [dashboardText('timeWindow'), 'kWh', dashboardText('costs'), dashboardText('prints'), dashboardText('signal')], rows: peakHourRows },
          { title: dashboardText('dataQualityCostBasis'), columns: [dashboardText('checkPoint'), dashboardText('value'), dashboardText('source'), dashboardText('action')], rows: energyQualityRows },
          { title: dashboardText('energyOptimization'), columns: [dashboardText('improvementLever'), dashboardText('value'), dashboardText('basis'), dashboardText('nextStep')], rows: energyRecommendationRows },
          { title: dashboardText('printerAndSourceMix'), columns: [dashboardText('printer'), dashboardText('prints'), dashboardText('proportionalKwh'), dashboardText('share')], rows: printerRows },
        ];
      case 'overview':
      default:
        return [
          { title: dashboardText('priorities'), columns: [dashboardText('area'), dashboardText('signal'), dashboardText('value'), dashboardText('action')], rows: overviewPriorityRows },
          { title: dashboardText('label30DayForecast'), columns: [dashboardText('metric'), dashboardText('label30Days'), dashboardText('basis'), dashboardText('nextStep')], rows: overviewForecastRows },
          { title: dashboardText('dataQuality'), columns: [dashboardText('source'), dashboardText('coverage'), dashboardText('impact'), dashboardText('nextStep')], rows: overviewDataQualityRows },
          { title: dashboardText('ordersAndOffers'), columns: [dashboardText('document'), dashboardText('customer'), dashboardText('status'), dashboardText('amount')], rows: derived.revenueRows.slice(0, 4).map((row) => [row.number, row.customer, <RevenueStatus status={row.status} />, formatMoney(row.amount, locale, currencyCode)] as Array<ReactNode>) },
          { title: dashboardText('inventoryRisks'), columns: [dashboardText('resource'), dashboardText('stock'), dashboardText('locationSource'), dashboardText('signal')], rows: riskRows },
        ];
    }
  })();
  const handleCsvExport = () => {
    const csv = createCsv(exportSections);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `printops-business-${activeTab}-${dateFrom}-${dateTo}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const revenueTab = (
    <div className="mt-5 space-y-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Receipt} label={dashboardText('receivedPayments')} value={formatMoney(derived.paymentEffectiveRevenue, locale, currencyCode)} detail={derived.paymentDocuments.length > 0 ? dashboardText('invoicesValue', { value1: derived.paymentDocuments.length }) : derived.missingPaymentSource ? dashboardText('paymentSourceMissing') : dashboardText('noTransactions')} tone={derived.paymentEffectiveRevenue > 0 ? 'green' : 'neutral'} to={invoiceListUrl(derived.paymentEffectiveRevenue > 0 ? 'paid' : undefined)} trend={trendLabels.paymentEffectiveRevenue} />
        <MetricCard icon={AlertTriangle} label={dashboardText('openOverdue')} value={formatMoney(derived.openRevenue, locale, currencyCode)} detail={dashboardText('overdueValue', { value1: formatMoney(derived.overdueRevenue, locale, currencyCode) })} tone={derived.overdueRevenue > 0 ? 'red' : 'amber'} to={invoiceListUrl(overdueDocuments.length > 0 ? 'overdue' : 'open')} />
        <MetricCard icon={Clock} label={dashboardText('activeOrders')} value={formatMoney(derived.activeOrderRevenue, locale, currencyCode)} detail={dashboardText('runningValue', { value1: derived.runningOrders.length })} tone="amber" to="/orders" />
        <MetricCard icon={TrendingUp} label={dashboardText('pipeline')} value={formatMoney(derived.pipelineRevenue, locale, currencyCode)} detail={dashboardText('offersAndOrders')} tone="blue" to="/orders/offers" trend={trendLabels.pipelineRevenue} />
      </div>
      <ActionStrip actions={revenueShortcuts} />

      <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <Panel icon={Receipt} title={dashboardText('ordersOffersAndPaymentSource')} subtitle={dashboardText('receivedRevenueStaysAt0UntilInvoicePaymentsOrBankReconciliationAreConnected')}>
          {derived.revenueRows.length > 0 ? (
            <CompactTable
              columns={[dashboardText('document'), dashboardText('customer'), dashboardText('status'), dashboardText('amount')]}
              rows={derived.revenueRows.map((row) => [<EntityLink to={row.to}>{row.number}</EntityLink>, row.customer, <RevenueStatus status={row.status} />, formatMoney(row.amount, locale, currencyCode)])}
            />
          ) : <EmptyState label={dashboardText('noOffersOrOrdersYet')} />}
        </Panel>
        <Panel icon={CircleDollarSign} title={dashboardText('completionRateAndOpenValues')}>
          <div className="flex items-end gap-4">
            <strong className="text-6xl font-semibold text-white">{formatPercent(completionRate, locale)}</strong>
            <span className="pb-2 text-sm text-bambu-gray">{dashboardText('fromOrderStatus')}</span>
          </div>
          <div className="mt-5 h-3 rounded bg-bambu-dark-tertiary">
            <div className="h-3 rounded bg-[#00a14a]" style={{ width: `${clamp(completionRate, 0, 100)}%` }} />
          </div>
          <div className="mt-5 space-y-4">
            <ProgressRow label={dashboardText('completed')} value={derived.completedRevenue} max={Math.max(derived.acceptedRevenue, derived.pipelineRevenue, 1)} suffix={formatMoney(derived.completedRevenue, locale, currencyCode)} tone="green" />
            <ProgressRow label={dashboardText('openInvoices2')} value={derived.openRevenue} max={Math.max(derived.openRevenue, derived.acceptedRevenue, derived.pipelineRevenue, 1)} suffix={formatMoney(derived.openRevenue, locale, currencyCode)} tone="amber" />
            <ProgressRow label={dashboardText('overdue')} value={derived.overdueRevenue} max={Math.max(derived.openRevenue, 1)} suffix={formatMoney(derived.overdueRevenue, locale, currencyCode)} tone="red" />
            <ProgressRow label={dashboardText('offers')} value={derived.pipelineRevenue} max={Math.max(derived.acceptedRevenue, derived.pipelineRevenue, 1)} suffix={formatMoney(derived.pipelineRevenue, locale, currencyCode)} tone="blue" />
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel icon={TrendingUp} title={dashboardText('pipelineRepresentsExpectations')} subtitle={dashboardText('keepSeparateFromReceivedPayments')}>
          <PipelineChart stages={derived.pipelineStages} currency={currencyCode} locale={locale} />
        </Panel>
        <Panel icon={BarChart3} title={dashboardText('revenueCostsAndMarginOverTime')}>
          <FinanceTrendChart data={trend} currency={currencyCode} locale={locale} />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <Panel icon={AlertTriangle} title={dashboardText('openReceivables')} subtitle={dashboardText('dueDateOutstandingAmountAndNextManualStep')}>
          {receivableRows.length > 0 ? (
            <CompactTable columns={[dashboardText('document'), dashboardText('customer'), dashboardText('due'), dashboardText('open'), dashboardText('signal'), dashboardText('action')]} rows={receivableRows} />
          ) : <EmptyState label={dashboardText('noOpenReceivablesInTheSelectedPeriod')} />}
        </Panel>
        <Panel icon={Receipt} title={dashboardText('paymentStatus')} subtitle={dashboardText('fromRecordedPaymentsAndOpenInvoices')}>
          <CompactTable columns={[dashboardText('status'), dashboardText('value'), dashboardText('scope'), dashboardText('action')]} rows={paymentStatusRows} />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Panel icon={CircleDollarSign} title={dashboardText('paymentReceipts')} subtitle={dashboardText('manuallyConfirmedPaymentsInThePeriod')}>
          {paymentRows.length > 0 ? (
            <CompactTable columns={[dashboardText('date'), dashboardText('document'), dashboardText('customer'), dashboardText('amount'), dashboardText('method')]} rows={paymentRows} />
          ) : <EmptyState label={dashboardText('noPaymentReceiptsRecordedInTheSelectedPeriodYet')} />}
        </Panel>
        <Panel icon={Lightbulb} title={dashboardText('revenueActions')} subtitle={dashboardText('whatToCheckManuallyNext')}>
          <CompactTable columns={[dashboardText('topic'), dashboardText('scope'), dashboardText('target'), dashboardText('action')]} rows={revenueActionRows} />
        </Panel>
      </div>
    </div>
  );

  const marginTab = (
    <div className="mt-5 space-y-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Factory} label={dashboardText('productionCosts')} value={formatMoney(derived.productionCost, locale, currencyCode)} detail={dashboardText('materialProductionEnergy')} tone="violet" to="/orders/calculation" trend={trendLabels.productionCost} />
        <MetricCard icon={Zap} label={dashboardText('energyShare')} value={formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode)} detail={dashboardText('canBeEvaluatedSeparately')} tone="cyan" to={dashboardTabUrl('energy')} trend={trendLabels.energyCost} />
        <MetricCard icon={CircleDollarSign} label={dashboardText('contributionMargin')} value={formatMoney(Math.max(derived.acceptedRevenue - derived.productionCost, 0), locale, currencyCode)} detail={dashboardText('beforeOverheads')} tone="green" to="/orders" trend={trendLabels.contribution} />
        <MetricCard icon={Gauge} label={dashboardText('margin')} value={formatPercent(derived.margin, locale)} detail={dashboardText('effective')} tone="green" to="/orders/calculation" trend={trendLabels.margin} />
      </div>
      <ActionStrip actions={marginShortcuts} />

      <div className="grid gap-5 xl:grid-cols-[0.78fr_1.22fr]">
        <Panel icon={CircleDollarSign} title={dashboardText('detailedCostStructure')} subtitle={dashboardText('archiveCostsOrderCalculationEnergyAndReservations')}>
          <Donut slices={derived.costSlices} center={formatMoney(derived.productionCost, locale, currencyCode)} valueFormatter={(value) => formatMoney(value, locale, currencyCode)} />
        </Panel>
        <Panel icon={ClipboardList} title={dashboardText('ordersByMargin')}>
          {orderMarginRows.length > 0 ? (
            <CompactTable
              columns={[dashboardText('order'), dashboardText('revenueTitle'), dashboardText('costs'), dashboardText('margin'), dashboardText('signal')]}
              rows={orderMarginRows}
            />
          ) : <EmptyState label={dashboardText('noCalculatedOrdersYet')} />}
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Panel icon={BarChart3} title={dashboardText('costTrend')}>
          <FinanceTrendChart data={trend} currency={currencyCode} locale={locale} />
        </Panel>
        <Panel icon={Factory} title={dashboardText('costDrivers')}>
          <div className="space-y-4">
            <ProgressRow label={dashboardText('archiveCosts')} value={stats?.total_cost ?? 0} max={Math.max(derived.productionCost, 1)} suffix={formatMoney(stats?.total_cost ?? 0, locale, currencyCode)} tone="green" />
            <ProgressRow label={dashboardText('orderCalculation')} value={derived.acceptedCost} max={Math.max(derived.productionCost, 1)} suffix={formatMoney(derived.acceptedCost, locale, currencyCode)} tone="blue" />
            <ProgressRow label={dashboardText('energy')} value={stats?.total_energy_cost ?? 0} max={Math.max(derived.productionCost, 1)} suffix={formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode)} tone="cyan" />
            <ProgressRow label={dashboardText('reservedInventoryValue')} value={derived.reservedValue} max={Math.max(derived.stockValue, derived.productionCost, 1)} suffix={formatMoney(derived.reservedValue, locale, currencyCode)} tone="amber" />
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel icon={CircleDollarSign} title={dashboardText('contributionMarginSummary')} subtitle={dashboardText('orderValueComparedWithCostsAndCommittedStock')}>
          <CompactTable columns={[dashboardText('metric'), dashboardText('value'), dashboardText('basis'), dashboardText('signal')]} rows={contributionRows} />
        </Panel>
        <Panel icon={ClipboardList} title={dashboardText('costControl')} subtitle={dashboardText('whereCostsComeFromAndWhereToGoNext')}>
          <CompactTable columns={[dashboardText('driver'), dashboardText('value'), dashboardText('source'), dashboardText('action')]} rows={costControlRows} />
        </Panel>
      </div>

      <Panel icon={Lightbulb} title={dashboardText('marginActions')} subtitle={dashboardText('specificChecksForCalculationEnergyAndMaterialData')}>
        <CompactTable columns={[dashboardText('topic'), dashboardText('scope'), dashboardText('valueTarget'), dashboardText('action')]} rows={marginActionRows} />
      </Panel>
    </div>
  );

  const inventoryTab = (
    <div className="mt-5 space-y-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Warehouse} label={dashboardText('inventoryValue')} value={formatMoney(derived.stockValue, locale, currencyCode)} detail={dashboardText('reservedValue', { value1: formatMoney(derived.reservedValue, locale, currencyCode) })} tone="green" to={inventoryFocusUrl()} />
        <MetricCard icon={AlertTriangle} label={dashboardText('reorder')} value={dashboardText('itemsValue2', { value1: derived.lowStockCount })} detail={dashboardText('belowThreshold')} tone={derived.lowStockCount > 0 ? 'red' : 'neutral'} to={inventoryFocusUrl('low-stock')} />
        <MetricCard icon={ClipboardList} label={dashboardText('reservations')} value={`${derived.reservedLines}`} detail={dashboardText('fromOpenOrders')} tone="blue" to="/orders" />
        <MetricCard icon={Package} label={dashboardText('usage')} value={formatWeightKg(derived.consumedGrams, locale)} detail={dashboardText('sinceUsageReset')} tone="amber" to={inventoryFocusUrl('used')} />
      </div>
      <ActionStrip actions={inventoryShortcuts} />

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel icon={Warehouse} title={dashboardText('stockCoverageAndUsage')} subtitle={dashboardText('inventoryManagementRemainsASeparateFocus')}>
          {derived.materialUsage.length > 0 ? (
            <div className="space-y-4">
              {derived.materialUsage.map((item, index) => (
                <ProgressRow
                  key={item.label}
                  label={materialUsageProgressLabel(item, locale)}
                  value={item.remaining}
                  max={Math.max(...derived.materialUsage.map((material) => material.remaining), 1)}
                  suffix={formatMaterialRemaining(item, locale)}
                  tone={index === 1 ? 'red' : index === 2 ? 'amber' : 'green'}
                />
              ))}
            </div>
          ) : <EmptyState label={dashboardText('noActiveInventoryItemsFound')} />}
        </Panel>
        <Panel icon={AlertTriangle} title={dashboardText('reorderingAndReservations')}>
          {riskRows.length > 0 ? (
            <CompactTable columns={[dashboardText('resource'), dashboardText('stock'), dashboardText('locationSource'), dashboardText('signal')]} rows={riskRows} />
          ) : <EmptyState label={dashboardText('noCriticalInventorySignalsInTheCurrentPeriod')} />}
        </Panel>

        <Panel icon={Package} title={dashboardText('inventoryValueByMaterial')}>
          {derived.materialUsage.length > 0 ? (
            <div className="space-y-4">
              {derived.materialUsage.map((item, index) => (
                <ProgressRow
                  key={`value-${item.label}`}
                  label={item.label}
                  value={item.value}
                  max={Math.max(...derived.materialUsage.map((material) => material.value), 1)}
                  suffix={formatMoney(item.value, locale, currencyCode)}
                  tone={index === 1 ? 'amber' : 'green'}
                />
              ))}
            </div>
          ) : <EmptyState label={dashboardText('noMaterialValuesCanBeCalculated')} />}
        </Panel>
        <Panel icon={ClipboardList} title={dashboardText('reservationPressure')}>
          {derived.reservationRows.length > 0 ? (
            <CompactTable
              columns={[dashboardText('order'), dashboardText('material'), dashboardText('reserved2'), dashboardText('value'), dashboardText('status')]}
              rows={derived.reservationRows}
            />
          ) : <EmptyState label={dashboardText('noOpenReservationsFound')} />}
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr_1fr]">
        <Panel icon={Truck} title={dashboardText('supplierDashboard')} subtitle={dashboardText('supplySourceMaterialCoverageAndReliability')}>
          {supplierRows.length > 0 ? (
            <CompactTable columns={[dashboardText('supplier'), dashboardText('materialSourcing'), dashboardText('leadTime'), dashboardText('contact'), dashboardText('status')]} rows={supplierRows} />
          ) : <EmptyState label={dashboardText('noActiveSuppliersConfiguredYet')} />}
        </Panel>
        <Panel icon={ClipboardList} title={dashboardText('reorderSuggestions')} subtitle={dashboardText('replenishmentBasedOnStockCoverageAndReservations')}>
          {reorderRows.length > 0 ? (
            <CompactTable columns={[dashboardText('item'), dashboardText('stock'), dashboardText('suggestion'), dashboardText('supplier'), dashboardText('leadTime'), dashboardText('action')]} rows={reorderRows} />
          ) : <EmptyState label={dashboardText('noCurrentReorderSuggestionsFromLowStockLevels')} />}
        </Panel>
        <Panel icon={Gauge} title={dashboardText('materialFlow')} subtitle={dashboardText('whatIsBlockedAndWhatTiesUpCapital')}>
          <div className="space-y-4">
            <ProgressRow label={dashboardText('available2')} value={Math.max(derived.stockValue - derived.reservedValue, 0)} max={Math.max(derived.stockValue, 1)} suffix={formatMoney(Math.max(derived.stockValue - derived.reservedValue, 0), locale, currencyCode)} tone="green" />
            <ProgressRow label={dashboardText('reserved2')} value={derived.reservedValue} max={Math.max(derived.stockValue, 1)} suffix={formatMoney(derived.reservedValue, locale, currencyCode)} tone="blue" />
            <ProgressRow label={dashboardText('criticallyCommitted')} value={lowStockInventoryValue} max={Math.max(derived.stockValue, 1)} suffix={dashboardText('linesValue2', { value1: derived.lowStockCount, value2: formatMoney(lowStockInventoryValue, locale, currencyCode) })} tone={derived.lowStockCount > 0 ? 'red' : 'neutral'} />
            <ProgressRow label={dashboardText('usageDynamics')} value={derived.consumedGrams} max={Math.max(derived.consumedGrams * 1.35, 1)} suffix={formatWeightKg(derived.consumedGrams, locale)} tone="amber" />
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel icon={Lightbulb} title={dashboardText('materialSupplierPlanning')} subtitle={dashboardText('stockCoverageComparedWithLeadTimeAndUsage')}>
          {materialPlanningRows.length > 0 ? (
            <CompactTable columns={[dashboardText('material'), dashboardText('stockCoverage'), dashboardText('supplier'), dashboardText('leadTime'), dashboardText('suggestion'), dashboardText('signal')]} rows={materialPlanningRows} />
          ) : <EmptyState label={dashboardText('noMaterialPlanningCanBeCalculated')} />}
        </Panel>
        <Panel icon={Gauge} title={dashboardText('inventoryQuality')} subtitle={dashboardText('valueShortagesAndDataMaintenanceAtAGlance')}>
          <div className="space-y-4">
            <ProgressRow label={dashboardText('skuSuppliers')} value={directSupplierAssignedSpoolCount} max={Math.max(spools.length, 1)} suffix={dashboardText('ofValue', { value1: directSupplierAssignedSpoolCount, value2: spools.length })} tone={directSupplierAssignedSpoolCount < spools.length ? 'amber' : 'green'} />
            <ProgressRow label={dashboardText('offerCoverage')} value={supplierAssignedSpoolCount} max={Math.max(spools.length, 1)} suffix={dashboardText('ofValue', { value1: supplierAssignedSpoolCount, value2: spools.length })} tone="green" />
            <ProgressRow label={dashboardText('withoutCosts')} value={inventoryWithoutCostCount} max={Math.max(inventoryItemCount, 1)} suffix={dashboardText('itemsValue2', { value1: inventoryWithoutCostCount })} tone={inventoryWithoutCostCount > 0 ? 'amber' : 'neutral'} />
            <ProgressRow label={dashboardText('criticalStock')} value={derived.lowStockCount} max={Math.max(inventoryItemCount, 1)} suffix={dashboardText('itemsValue2', { value1: derived.lowStockCount })} tone={derived.lowStockCount > 0 ? 'red' : 'green'} />
            <ProgressRow label={dashboardText('withStorageLocation')} value={inventoryWithLocationCount} max={Math.max(inventoryItemCount, 1)} suffix={dashboardText('itemsValue2', { value1: inventoryWithLocationCount })} tone="blue" />
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel icon={Gauge} title={dashboardText('procurementReadiness')} subtitle={dashboardText('howFullyReorderingAndCalculationsCanBeDetermined')}>
          <CompactTable columns={[dashboardText('checkPoint'), dashboardText('coverage'), dashboardText('signal'), dashboardText('action')]} rows={procurementReadinessRows} />
        </Panel>
        <Panel icon={Package} title={dashboardText('slowMovingStockTiedUpCapital')} subtitle={dashboardText('stockWithLongIdleTimesAndRemainingValue')}>
          {staleSpoolRows.length > 0 ? (
            <CompactTable columns={[dashboardText('spool'), dashboardText('value'), dashboardText('idleTime'), dashboardText('location'), dashboardText('action')]} rows={staleSpoolRows} />
          ) : <EmptyState label={dashboardText('noSlowMovingStockWithRemainingValueFound')} />}
        </Panel>
      </div>
    </div>
  );

  const energyTab = (
    <div className="mt-5 space-y-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Zap} label={dashboardText('usage')} value={formatKwh(stats?.total_energy_kwh ?? 0, locale)} detail={`${selectedDateRange.label} · ${energyMode}`} tone="cyan" to="/dashboard" trend={trendLabels.energyKwh} />
        <MetricCard icon={CircleDollarSign} label={dashboardText('energyCosts')} value={formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode)} detail={dashboardText('inThePeriod')} tone="amber" to={energyCostSettingsUrl} trend={trendLabels.energyCost} />
        <MetricCard icon={BatteryCharging} label={dashboardText('costsKwh')} value={formatMoney(settingsQuery.data?.energy_cost_per_kwh ?? 0, locale, currencyCode)} detail={dashboardText('fromSettings')} tone="neutral" to={energyCostSettingsUrl} />
        <MetricCard icon={Gauge} label={dashboardText('intensity')} value={`${energyPerHour.toFixed(2)} kWh/h`} detail={dashboardText('perPrintHour')} tone="green" to={archiveEnergyUrl(undefined, 'log')} />
      </div>
      <ActionStrip actions={energyShortcuts} />

      <div className="grid gap-5 xl:grid-cols-[0.85fr_1.15fr]">
        <Panel icon={Zap} title={dashboardText('energyMetrics')} subtitle={`${selectedDateRange.label} · ${energyMode}`}>
          <div className="grid gap-3 sm:grid-cols-2">
            <MiniMetric icon={Zap} label={dashboardText('usage')} value={formatKwh(stats?.total_energy_kwh ?? 0, locale)} tone="cyan" />
            <MiniMetric icon={CircleDollarSign} label={dashboardText('energyCosts')} value={formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode)} tone="amber" />
            <MiniMetric icon={BatteryCharging} label={dashboardText('costsKwh')} value={formatMoney(settingsQuery.data?.energy_cost_per_kwh ?? 0, locale, currencyCode)} tone="neutral" />
            <MiniMetric icon={Factory} label={dashboardText('kwhPrintHour')} value={energyPerHour.toFixed(2)} tone="green" />
          </div>
          <div className={`${surface.panelQuiet} mt-5 text-sm text-bambu-gray`}>
            {dashboardText('source2')} <span className="font-medium text-white">{dashboardEnergySource(stats?.energy_source, dashboardText('archiveStatistics'))}</span>
          </div>
        </Panel>
        <Panel icon={BatteryCharging} title={dashboardText('hourlyProfile')} subtitle={dashboardText('printLogEnergyOtherwiseThePeriodTotalDistributedByActualPrintDuration')}>
          {(stats?.total_energy_kwh ?? 0) > 0 || archiveEvents.length > 0
            ? (
              <EnergyHeatmap
                archiveEvents={archiveEvents}
                energyHistory={energyHistory}
                totalKwh={stats?.total_energy_kwh ?? 0}
                totalCost={stats?.total_energy_cost ?? 0}
                locale={locale}
                currency={currencyCode}
              />
            )
            : <EmptyState label={dashboardText('noEnergyDataInThePeriod')} />}
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Panel icon={BarChart3} title={dashboardText('energyPerPrint')} subtitle={dashboardText('latestEventsFromTheSelectedPeriod')}>
          {energyEventRows.length > 0 ? (
            <CompactTable columns={[dashboardText('date'), dashboardText('print'), dashboardText('printer'), 'kWh', dashboardText('costs')]} rows={energyEventRows} />
          ) : <EmptyState label={dashboardText('noPrintEventsInThePeriodYet')} />}
        </Panel>
        <Panel icon={AlertTriangle} title={dashboardText('energySignals')}>
          <CompactTable
            columns={[dashboardText('signal'), dashboardText('value'), dashboardText('timeWindow'), dashboardText('action')]}
            rows={energyActionRows}
          />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Panel icon={Clock} title={dashboardText('peakWindows')} subtitle={dashboardText('hoursWithTheHighestEnergyDemandInThePeriod')}>
          {peakHourRows.length > 0 ? (
            <CompactTable columns={[dashboardText('timeWindow'), 'kWh', dashboardText('costs'), dashboardText('prints'), dashboardText('signal')]} rows={peakHourRows} />
          ) : <EmptyState label={dashboardText('noTimeWindowsCanBeCalculatedFromPrintEventsYet')} />}
        </Panel>
        <Panel icon={Gauge} title={dashboardText('dataQualityCostBasis')} subtitle={dashboardText('whatIsMeasuredAndWhatNeedsEstimating')}>
          <CompactTable columns={[dashboardText('checkPoint'), dashboardText('value'), dashboardText('source'), dashboardText('action')]} rows={energyQualityRows} />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr_1fr]">
        <Panel icon={Lightbulb} title={dashboardText('energyOptimization')} subtitle={dashboardText('specificImprovementsBasedOnAvailableMetrics')}>
          <CompactTable columns={[dashboardText('improvementLever'), dashboardText('value'), dashboardText('basis'), dashboardText('nextStep')]} rows={energyRecommendationRows} />
        </Panel>
        <Panel icon={Clock} title={dashboardText('archiveMetrics')} subtitle={dashboardText('actualTotalsFromTheSelectedPeriod')}>
          <CompactTable
            columns={[dashboardText('metric'), dashboardText('value'), dashboardText('source'), dashboardText('signal')]}
            rows={[
              [dashboardText('printHours'), `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(stats?.total_print_time_hours ?? 0)} h`, dashboardText('archive'), 'OK'],
              [dashboardText('filament'), formatWeightKg(stats?.total_filament_grams ?? 0, locale), dashboardText('archive'), 'OK'],
              [dashboardText('energySource'), dashboardEnergySource(stats?.energy_source, dashboardText('none')), energyMode, (stats?.total_energy_kwh ?? 0) > 0 ? 'OK' : <span className="text-amber-300">{dashboardText('missing')}</span>],
              [dashboardText('warmUpPhase'), stats?.energy_data_warming_up ? dashboardText('active2') : dashboardText('no'), dashboardText('archive'), stats?.energy_data_warming_up ? <span className="text-amber-300">{dashboardText('wait')}</span> : 'OK'],
            ]}
          />
        </Panel>
        <Panel icon={Factory} title={dashboardText('printerAndSourceMix')} subtitle={dashboardText('printSharesFromArchiveStatistics')}>
          {printerRows.length > 0 ? (
            <CompactTable columns={[dashboardText('printer'), dashboardText('prints'), dashboardText('proportionalKwh'), dashboardText('share')]} rows={printerRows} />
          ) : <EmptyState label={dashboardText('noPrinterSharesInThePeriod')} />}
          <p className="mt-5 text-xs text-bambu-gray">{dashboardText('source2')} {dashboardEnergySource(stats?.energy_source, dashboardText('archiveStatistics'))} {dashboardText('mode')} {energyMode}</p>
        </Panel>
      </div>
    </div>
  );

  return (
    <div className="w-full p-4 sm:p-6">
      <div className="w-full">
        <header className="space-y-4">
          <div>
            <h1 className="text-[1.75rem] font-semibold leading-tight text-white sm:text-[2rem]">{dashboardText('businessDashboard')}</h1>
            <p className="mt-1 text-sm leading-5 text-bambu-gray">
              {dashboardText('aDedicatedBusinessOverviewOfCostsRevenueInventoryAndEnergyUsage')}
            </p>
          </div>
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <BusinessTabs value={activeTab} onChange={handleTabChange} />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={handleCsvExport}
                className="flex min-h-10 items-center gap-2 rounded border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 text-sm font-medium text-bambu-gray transition-colors hover:border-bambu-green/60 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green"
              >
                <Download className="h-4 w-4 text-bambu-green" />
                {dashboardText('csvExport')}
              </button>
              <Select
                ariaLabel={dashboardText('period2')}
                value={dateRangeValue}
                onValueChange={(value) => handleDateRangeChange(value as DateRangeValue)}
                options={dateRangeOptions.map((option) => ({
                  value: option.value,
                  label: option.label,
                }))}
                className="min-w-56"
                controlClassName="min-h-10 bg-bambu-dark-secondary text-sm"
                renderValue={(option) => (
                  <span className="flex items-center gap-2">
                    <CalendarDays className="h-4 w-4 text-bambu-green" />
                    <span className="text-bambu-gray">{dashboardText('period')}</span>
                    <span className="font-medium text-white">{option?.label}</span>
                  </span>
                )}
              />
            </div>
          </div>
        </header>

        {!canReadBusinessDashboard ? (
          <div className="mt-6">
            <Panel icon={AlertTriangle} title={dashboardText('permissionDenied')} subtitle={dashboardText('theBusinessDashboardRequiresMetricsFromOrdersPaymentsInventoryAndArchivesTogether')}>
              <EmptyState label={dashboardText('checkYourRoleAndPermissionsStatisticsOrdersInventoryInvoicesPaymentsAndArchiveAccess')} />
            </Panel>
          </div>
        ) : null}

        {canReadBusinessDashboard && activeTab === 'overview' ? (
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-8">
            <MetricCard icon={Receipt} label={dashboardText('receivedPayments')} value={formatMoney(derived.paymentEffectiveRevenue, locale, currencyCode)} detail={derived.paymentDocuments.length > 0 ? dashboardText('invoicesValue', { value1: derived.paymentDocuments.length }) : derived.missingPaymentSource ? dashboardText('paymentSourceMissing') : dashboardText('noTransactions')} tone={derived.paymentEffectiveRevenue > 0 ? 'green' : 'neutral'} to={dashboardTabUrl('revenue')} trend={trendLabels.paymentEffectiveRevenue} />
            <MetricCard icon={TrendingUp} label={dashboardText('orderValue')} value={formatMoney(derived.acceptedRevenue, locale, currencyCode)} detail={dashboardText('ordersValue', { value1: derived.activeOrders.length })} tone="green" to={dashboardTabUrl('revenue')} trend={trendLabels.acceptedRevenue} />
            <MetricCard icon={CircleDollarSign} label={dashboardText('contributionMargin')} value={formatMoney(Math.max(derived.acceptedRevenue - derived.productionCost, 0), locale, currencyCode)} detail={dashboardText('effectiveMarginValue', { value1: formatPercent(derived.margin, locale) })} tone="green" to={dashboardTabUrl('margin')} trend={trendLabels.contribution} />
            <MetricCard icon={Warehouse} label={dashboardText('inventoryValue')} value={formatMoney(derived.stockValue, locale, currencyCode)} detail={dashboardText('reservedValue', { value1: formatMoney(derived.reservedValue, locale, currencyCode) })} tone="cyan" to={dashboardTabUrl('inventory')} />
            <MetricCard icon={Zap} label={dashboardText('energyUsage')} value={formatKwh(stats?.total_energy_kwh ?? 0, locale)} detail={dashboardText('electricityValue', { value1: formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode) })} tone="cyan" to={dashboardTabUrl('energy')} trend={trendLabels.energyKwh} />
            <MetricCard icon={AlertTriangle} label={dashboardText('reorder')} value={dashboardText('itemsValue2', { value1: derived.lowStockCount })} detail={dashboardText('signalsValue', { value1: riskRows.length })} tone={derived.lowStockCount > 0 ? 'red' : 'neutral'} to={dashboardTabUrl('inventory')} />
            <MetricCard icon={Factory} label={dashboardText('productionCosts')} value={formatMoney(derived.productionCost, locale, currencyCode)} detail={dashboardText('materialProductionEnergy')} tone="violet" to={dashboardTabUrl('margin')} trend={trendLabels.productionCost} />
            <MetricCard icon={Gauge} label={dashboardText('completionRate')} value={formatPercent(completionRate, locale)} detail={dashboardText('fromOrderStatus')} tone="green" to={dashboardTabUrl('revenue')} trend={trendLabels.completionRate} />
          </div>
        ) : null}

        {canReadBusinessDashboard && activeTab === 'overview' ? (
          <Overview
            trend={trend}
            costSlices={derived.costSlices}
            pipelineStages={derived.pipelineStages}
            materialUsage={derived.materialUsage}
            revenueRows={derived.revenueRows}
            currency={currencyCode}
            locale={locale}
            stats={stats}
            archiveEvents={archiveEvents}
            energyHistory={energyHistory}
            energyPerHour={energyPerHour}
            stockValue={derived.stockValue}
            reservedValue={derived.reservedValue}
            riskRows={riskRows}
            orderMarginRows={orderMarginRows}
            priorityRows={overviewPriorityRows}
            dataQualityRows={overviewDataQualityRows}
            forecastRows={overviewForecastRows}
          />
        ) : null}
        {canReadBusinessDashboard && activeTab === 'revenue' ? revenueTab : null}
        {canReadBusinessDashboard && activeTab === 'margin' ? marginTab : null}
        {canReadBusinessDashboard && activeTab === 'inventory' ? inventoryTab : null}
        {canReadBusinessDashboard && activeTab === 'energy' ? energyTab : null}
      </div>
    </div>
  );
}
