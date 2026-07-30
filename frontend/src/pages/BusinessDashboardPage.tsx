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
import { documentManagementApi, type CommercialDocument } from '../api/documentManagement';
import { offersApi, ordersApi, type CustomerOrder, type Offer, type StockReservation } from '../api/offers';
import {
  procurementOffersApi,
  suppliersApi,
  type ProcurementOffer,
  type ProcurementResource,
  type Supplier,
} from '../api/procurement';
import { Select } from '../components/ui';
import { useDisplayCurrency } from '../hooks/useDisplayCurrency';
import { formatMoney } from '../utils/calculationFormatting';

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
  grams: number;
  value: number;
  remaining: number;
  days: number;
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
  { value: 'overview', label: 'Übersicht', icon: BarChart3 },
  { value: 'revenue', label: 'Einnahmen', icon: Receipt },
  { value: 'margin', label: 'Kosten & Marge', icon: CircleDollarSign },
  { value: 'inventory', label: 'Lager & Verbrauch', icon: Warehouse },
  { value: 'energy', label: 'Energie', icon: Zap },
];

const dateRangeOptions: Array<{ value: DateRangeValue; days: number; label: string }> = [
  { value: '7', days: 7, label: 'letzte 7 Tage' },
  { value: '30', days: 30, label: 'letzte 30 Tage' },
  { value: '90', days: 90, label: 'letzte 90 Tage' },
  { value: '365', days: 365, label: 'letzte 12 Monate' },
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
  [spool.material, spool.subtype].filter(Boolean).join(' ') || 'Unbekannt';

const spoolItemLabel = (spool: InventorySpool) =>
  [spool.material, spool.subtype, spool.color_name].filter(Boolean).join(' ') || `Spule #${spool.id}`;

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
  if (unique.length === 0) return 'nicht zugeordnet';
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

function createMaterialCostMap(spools: InventorySpool[]) {
  const costs = new Map<string, { grams: number; value: number }>();
  spools.forEach((spool) => {
    const key = materialKey(spool.material);
    if (!key || spool.archived_at) return;
    const grams = spoolRemainingGrams(spool);
    const value = (grams / 1000) * (spool.cost_per_kg ?? 0);
    const current = costs.get(key) ?? { grams: 0, value: 0 };
    costs.set(key, { grams: current.grams + grams, value: current.value + value });
  });
  return costs;
}

function reservationValue(reservation: StockReservation, materialCosts: Map<string, { grams: number; value: number }>) {
  const grams = reservationQuantityGrams(reservation);
  if (grams <= 0) return 0;
  const cost = materialCosts.get(materialKey(reservation.material_code));
  if (!cost || cost.grams <= 0) return 0;
  return grams * (cost.value / cost.grams);
}

const snapshotPart = (snapshot: Record<string, unknown> | undefined, key: string): Record<string, unknown> => {
  const value = snapshot?.[key];
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
};

const readRevisionValue = (offer: Offer, key: string): number => asNumber(snapshotPart(offer.snapshot, 'revision')[key]);
const readAcceptedRevisionValue = (order: CustomerOrder, key: string): number => asNumber(snapshotPart(order.accepted_snapshot, 'revision')[key]);
const readRevisionText = (snapshot: Record<string, unknown> | undefined, key: string): string => {
  const revision = snapshotPart(snapshot, 'revision');
  const calculation = snapshotPart(snapshot, 'calculation');
  const value = revision[key] ?? calculation[key];
  return typeof value === 'string' && value.trim() ? value : '';
};

const displayCustomer = (customerId: number | null | undefined) => (customerId ? `Kunde #${customerId}` : 'Ohne Kunde');

const formatPercent = (value: number, locale: string) =>
  `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value)} %`;

const formatKwh = (value: number, locale: string) =>
  `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)} kWh`;

const formatWeightKg = (grams: number, locale: string) =>
  `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(grams / 1000)} kg`;

function createMetricTrend(
  current: number,
  previous: number,
  formatter: (value: number) => string,
  higherIsPositive = true,
): MetricTrend {
  const delta = current - previous;
  if (Math.abs(delta) < 0.005) {
    return { label: 'unverändert vs vorher', direction: 'flat', positive: true };
  }
  const direction = delta > 0 ? 'up' : 'down';
  const positive = higherIsPositive ? delta > 0 : delta < 0;
  const sign = delta > 0 ? '+' : '-';
  return {
    label: `${sign}${formatter(Math.abs(delta))} vs vorher`,
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
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  return date.getTime() >= start.getTime() && date.getTime() <= end.getTime();
}

const daysSince = (value: string | null | undefined, today: Date) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
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
): TrendPoint[] {
  const bucketCount = 7;
  const rangeMs = Math.max(rangeEnd.getTime() - rangeStart.getTime(), 86400000);
  const bucketMs = rangeMs / bucketCount;
  const useDailyLabels = rangeMs <= 31 * 86400000;
  const buckets = Array.from({ length: bucketCount }, (_, index) => {
    const bucketDate = new Date(rangeStart.getTime() + bucketMs * index + bucketMs / 2);
    return {
      label: useDailyLabels
        ? new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit' }).format(bucketDate)
        : `KW ${getIsoWeek(bucketDate)}`,
      revenue: 0,
      costs: 0,
      energy: 0,
      margin: 0,
    };
  });
  orders
    .filter((order) => order.status !== 'cancelled' && isInDateRange(order.updated_at || order.created_at, rangeStart, rangeEnd))
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
): RevenueRow[] {
  const documentRows = documents
    .filter(isPaymentDocument)
    .map((document) => {
      const openAmount = asNumber(document.open_amount);
      const dueDate = document.due_date ? new Date(document.due_date) : null;
      const overdue = openAmount > 0 && dueDate !== null && dueDate.getTime() < today.getTime();
      const documentFilter = openAmount > 0 ? 'open' : 'paid';
      return {
        number: document.number ?? `Dokument #${document.id}`,
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
    .map((order) => ({
      number: order.number,
      customer: displayCustomer(order.customer_id),
      status: order.status === 'completed' ? 'completed' as const : 'active' as const,
      amount: readAcceptedRevisionValue(order, 'selling_price'),
      due: new Date(order.updated_at || order.created_at).toLocaleDateString('de-DE'),
      to: `/orders/${order.id}`,
    }));
  const offerRows = offers
    .filter((offer) => offer.status === 'sent' || offer.status === 'draft')
    .map((offer) => ({
      number: offer.number,
      customer: displayCustomer(offer.customer_id),
      status: 'offer' as const,
      amount: readRevisionValue(offer, 'selling_price'),
      due: new Date(offer.updated_at || offer.created_at).toLocaleDateString('de-DE'),
      to: '/orders/offers',
    }));
  return [...documentRows, ...orderRows, ...offerRows]
    .filter((row) => row.amount > 0)
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 8);
}

function deriveMaterialUsage(spools: InventorySpool[]): MaterialUsage[] {
  const grouped = new Map<string, MaterialUsage>();
  spools.forEach((spool) => {
    const label = spoolMaterialLabel(spool);
    const used = Math.max(0, spool.weight_used - (spool.weight_used_baseline ?? 0));
    const remaining = Math.max(0, spool.label_weight - spool.weight_used);
    const value = (remaining / 1000) * (spool.cost_per_kg ?? 0);
    const days = Math.max(3, Math.round((remaining / Math.max(used / 30, 12)) || 0));
    const current = grouped.get(label) ?? { label, grams: 0, value: 0, remaining: 0, days };
    current.grams += used;
    current.value += value;
    current.remaining += remaining;
    current.days = Math.min(current.days, days);
    grouped.set(label, current);
  });
  const values = Array.from(grouped.values()).sort((a, b) => b.grams - a.grams);
  return values.slice(0, 6);
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
                  { label: 'Auftragswert', value: formatMoney(item.revenue, locale, currency) },
                  { label: 'Kosten', value: formatMoney(item.costs, locale, currency) },
                  { label: 'Energie', value: formatMoney(item.energy, locale, currency) },
                  { label: 'Marge', value: formatPercent(item.margin, locale) },
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
        grün = Auftragswert, orange = Kosten, blau = Energie, Linie = Marge
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
          <span className="text-xs text-bambu-gray">Kosten</span>
          <strong className="text-sm text-white">{center}</strong>
        </div>
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        {slices.map((slice) => (
          <ChartTooltip
            key={slice.label}
            title={slice.label}
            lines={[
              { label: 'Wert', value: formatValue(slice.value) },
              { label: 'Anteil', value: `${Math.round((slice.value / total) * 100)}%` },
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
                { label: 'Wert', value: formatMoney(stage.value, locale, currency) },
                { label: 'Anteil max.', value: `${Math.round((stage.value / max) * 100)}%` },
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
          { label: 'Wert', value: suffix },
          { label: 'Anteil', value: `${Math.round((value / Math.max(max, 1)) * 100)}%` },
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
  const days = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
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
      const current = cells.get(key) ?? { kwh: 0, cost: 0, runs: 0, source: 'Smart-Plug History' };
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
      const current = cells.get(key) ?? { kwh: 0, cost: 0, runs: 0, source: measuredKwh > 0 ? 'Print-Log' : 'Zeitanteil aus Zeitraumssumme' };
      current.kwh += kwh;
      current.cost += cost;
      current.runs += 1;
      cells.set(key, current);
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
                const cell = cells.get(`${days.indexOf(day)}-${hour}`) ?? { kwh: 0, cost: 0, runs: 0, source: 'keine Daten' };
                const value = cell.kwh > 0 ? clamp((cell.kwh / maxKwh) * 100, 12, 100) : 0;
                return (
                  <ChartTooltip
                    key={`${day}-${hour}`}
                    title={`${day} ${hour}:00`}
                    lines={[
                      { label: 'Verbrauch', value: formatKwh(cell.kwh, locale) },
                      { label: 'Kosten', value: formatMoney(cell.cost, locale, currency) },
                      { label: 'Samples/Drucke', value: String(cell.runs) },
                      { label: 'Quelle', value: cell.source },
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
    paid: 'Bezahlt',
    partially_paid: 'Teilbezahlt',
    unpaid: 'Offen',
    overdue: 'Überfällig',
    completed: 'Abgeschlossen',
    active: 'Aktiver Auftrag',
    offer: 'Angebot',
    missing_payment_source: 'Zahlungsquelle fehlt',
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
            className={`${surface.tile} flex min-h-[76px] items-center gap-3 px-4 py-3 transition-colors hover:border-bambu-green/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green`}
          >
            <Icon className={`h-4 w-4 shrink-0 ${toneClasses[action.tone].text}`} />
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
        : leftText.localeCompare(rightText, 'de', { numeric: true, sensitivity: 'base' });
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
  const completedStage = pipelineStages.find((stage) => stage.label === 'Abgeschlossen')?.value ?? 0;
  const revenueRowsForTable = revenueRows.slice(0, 4).map((row) => [
    <EntityLink to={row.to}>{row.number}</EntityLink>,
    row.customer,
    <RevenueStatus status={row.status} />,
    formatMoney(row.amount, locale, currency),
  ]);

  return (
    <div className="mt-5 space-y-5">
      <div className="grid gap-5 xl:grid-cols-[1.12fr_1.18fr_1fr]">
        <Panel icon={BarChart3} title="Finanztrend mit Kosten, Energie und Marge" subtitle="Auftragswerte, Kosten und Energiekosten aus vorhandenen Quellen">
          <FinanceTrendChart data={trend} currency={currency} locale={locale} />
        </Panel>

        <Panel icon={Zap} title="Energie & Stromkosten" subtitle="Smart-Plug / Print-Log Quelle mit Hinweis, falls Daten fehlen">
          <div className="mb-4 grid grid-cols-3 gap-3">
            <MiniMetric icon={Zap} label="Verbrauch" value={formatKwh(stats?.total_energy_kwh ?? 0, locale)} tone="cyan" />
            <MiniMetric icon={CircleDollarSign} label="Kosten" value={formatMoney(stats?.total_energy_cost ?? 0, locale, currency)} tone="amber" />
            <MiniMetric icon={BatteryCharging} label="kWh/h" value={energyPerHour.toFixed(2)} tone="green" />
          </div>
          <div className="grid gap-4 min-[1500px]:grid-cols-[1.05fr_1fr]">
            <Donut
              size="small"
              center={String(Math.round(stats?.total_energy_kwh ?? 0))}
              valueFormatter={(value) => formatKwh(value, locale)}
              slices={(stats?.total_energy_kwh ?? 0) > 0
                ? [{ label: stats?.energy_source ?? 'Archiv', value: stats?.total_energy_kwh ?? 0, color: '#21b7cf' }]
                : []}
            />
            <div className={`${surface.panelQuiet} text-sm`}>
              <strong className="block text-white">Energie-Signale</strong>
              <p className="mt-3 text-bambu-gray">Zeitraum: {formatKwh(stats?.total_energy_kwh ?? 0, locale)}</p>
              <p className="mt-2 text-bambu-gray">Kosten: {formatMoney(stats?.total_energy_cost ?? 0, locale, currency)}</p>
              <p className="mt-2 text-bambu-gray">Quelle: {stats?.energy_source ?? 'Archivstatistik'}</p>
            </div>
          </div>
        </Panel>

        <Panel icon={TrendingUp} title="Pipeline ohne Einnahmen-Verwechslung" subtitle="Angebote, aktive Aufträge und abgeschlossene Aufträge getrennt">
          <PipelineChart stages={pipelineStages} currency={currency} locale={locale} />
          <div className={`${surface.panelQuiet} text-sm`}>
            <div className="flex items-center justify-between gap-3">
              <strong className="text-white">Erwarteter Umsatz</strong>
              <span className="text-bambu-gray">{formatMoney(pipelineTotal, locale, currency)}</span>
            </div>
            <div className="mt-2 flex items-center justify-between gap-3 text-bambu-gray">
              <span>davon abgeschlossen</span>
              <span>{formatMoney(completedStage, locale, currency)}</span>
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr_0.9fr]">
        <Panel icon={Lightbulb} title="Prioritäten" subtitle="Nächste Schritte aus Einnahmen, Marge, Lager und Energie">
          <CompactTable columns={['Bereich', 'Signal', 'Wert', 'Aktion']} rows={priorityRows} />
        </Panel>
        <Panel icon={TrendingUp} title="30-Tage-Vorschau" subtitle="Hochrechnung aus dem gewählten Zeitraum">
          <CompactTable columns={['Kennzahl', '30 Tage', 'Basis', 'Nächster Schritt']} rows={forecastRows} />
        </Panel>
        <Panel icon={Gauge} title="Datenqualität" subtitle="Welche Datenbasis aktuell belastbar ist">
          <CompactTable columns={['Quelle', 'Abdeckung', 'Auswirkung', 'Nächster Schritt']} rows={dataQualityRows} />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-4">
        <Panel icon={Receipt} title="Umsatz kompakt" subtitle="Echte Auftrags- und Angebotswerte">
          {revenueRows.length > 0 ? (
            <>
              <div className="flex h-24 items-end gap-3 border-b border-bambu-dark-tertiary pb-1">
                {revenueRows.map((row) => (
                  <ChartTooltip
                    key={row.number}
                    title={row.number}
                    lines={[
                      { label: 'Kunde', value: row.customer },
                      { label: 'Status', value: textFromNode(<RevenueStatus status={row.status} />) },
                      { label: 'Betrag', value: formatMoney(row.amount, locale, currency) },
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
                Bezahlt {formatMoney(revenueRows.filter((row) => row.status === 'paid').reduce((sum, row) => sum + row.amount, 0), locale, currency)} · offen {formatMoney(revenueRows.filter((row) => row.status === 'unpaid' || row.status === 'partially_paid' || row.status === 'overdue').reduce((sum, row) => sum + row.amount, 0), locale, currency)}
              </p>
            </>
          ) : <EmptyState label="Noch keine Angebots- oder Auftragswerte vorhanden." />}
        </Panel>

        <Panel icon={CircleDollarSign} title="Kosten & Marge kompakt" subtitle="Kostenarten inkl. Energie">
          <Donut size="small" slices={costSlices} center="Kosten" valueFormatter={(value) => formatMoney(value, locale, currency)} />
        </Panel>

        <Panel icon={Warehouse} title="Lager & Verbrauch kompakt" subtitle="Wert, Reservierung, Reichweite">
          {materialUsage.length > 0 ? (
            <div className="space-y-4">
              {materialUsage.slice(0, 4).map((item, index) => (
                <ProgressRow
                  key={item.label}
                  label={`${item.label} ${item.days} Tage`}
                  value={item.remaining}
                  max={materialMax}
                  suffix=""
                  tone={index === 1 ? 'red' : index === 2 ? 'amber' : 'green'}
                />
              ))}
            </div>
          ) : <EmptyState label="Keine aktiven Spulen im Lager gefunden." />}
          <p className="mt-5 text-xs text-bambu-gray">
            Lagerwert {formatMoney(stockValue, locale, currency)} · reserviert {formatMoney(reservedValue, locale, currency)}
          </p>
        </Panel>

        <Panel icon={BatteryCharging} title="Energieprofil kompakt" subtitle="Stundenmuster aus Print-Logs oder zeitanteilig aus Zeitraumssumme">
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
        <Panel icon={Receipt} title="Aufträge und Angebote">
          <CompactTable columns={['Beleg', 'Kunde', 'Status', 'Betrag']} rows={revenueRowsForTable} />
        </Panel>
        <Panel icon={ClipboardList} title="Aufträge nach Marge">
          {orderMarginRows.length > 0 ? (
            <CompactTable
              columns={['Auftrag', 'Umsatz / Titel', 'Kosten', 'Marge', 'Signal']}
              rows={orderMarginRows}
            />
          ) : <EmptyState label="Noch keine kalkulierten Aufträge vorhanden." />}
        </Panel>
        <Panel icon={AlertTriangle} title="Lager- und Energierisiken">
          {riskRows.length > 0 ? (
            <CompactTable columns={['Ressource', 'Bestand', 'Ort / Quelle', 'Signal']} rows={riskRows} />
          ) : <EmptyState label="Keine kritischen Lager- oder Energiesignale im aktuellen Zeitraum." />}
        </Panel>
      </div>
    </div>
  );
}

export function BusinessDashboardPage() {
  const { i18n } = useTranslation();
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
  const statsQuery = useQuery<ArchiveStats>({
    queryKey: ['business-dashboard', 'archive-stats', dateFrom, dateTo],
    queryFn: () => api.getArchiveStats({ dateFrom, dateTo }),
  });
  const previousStatsQuery = useQuery<ArchiveStats>({
    queryKey: ['business-dashboard', 'archive-stats-previous', previousDateFrom, previousDateTo],
    queryFn: () => api.getArchiveStats({ dateFrom: previousDateFrom, dateTo: previousDateTo }),
  });
  const archiveEventsQuery = useQuery<ArchiveSlim[]>({
    queryKey: ['business-dashboard', 'archive-events', dateFrom, dateTo],
    queryFn: () => api.getArchivesSlim(dateFrom, dateTo),
  });
  const energyHistoryQuery = useQuery<ArchiveEnergyHistoryPoint[]>({
    queryKey: ['business-dashboard', 'energy-history', dateFrom, dateTo],
    queryFn: () => api.getArchiveEnergyHistory({ dateFrom, dateTo, bucket: 'hour' }),
  });
  const spoolsQuery = useQuery<InventorySpool[]>({
    queryKey: ['business-dashboard', 'spools'],
    queryFn: () => api.getSpools(false),
  });
  const skuSettingsQuery = useQuery<FilamentSkuSettings[]>({
    queryKey: ['business-dashboard', 'sku-settings'],
    queryFn: () => api.getSkuSettings(),
  });
  const suppliersQuery = useQuery({
    queryKey: ['business-dashboard', 'suppliers'],
    queryFn: () => suppliersApi.list({ active: true, limit: 200 }),
  });
  const offersQuery = useQuery<Offer[]>({
    queryKey: ['business-dashboard', 'offers'],
    queryFn: () => offersApi.list(),
  });
  const ordersQuery = useQuery<CustomerOrder[]>({
    queryKey: ['business-dashboard', 'orders'],
    queryFn: () => ordersApi.list(),
  });
  const documentsQuery = useQuery<CommercialDocument[]>({
    queryKey: ['business-dashboard', 'commercial-documents'],
    queryFn: () => documentManagementApi.listDocuments(),
  });
  const { currencyCode } = useDisplayCurrency(settingsQuery.data?.currency);
  const stats = statsQuery.data;
  const previousStats = previousStatsQuery.data;
  const archiveEvents = useMemo(() => archiveEventsQuery.data ?? [], [archiveEventsQuery.data]);
  const energyHistory = useMemo(() => energyHistoryQuery.data ?? [], [energyHistoryQuery.data]);
  const spools = useMemo(() => spoolsQuery.data ?? [], [spoolsQuery.data]);
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
    enabled: procurementResources.length > 0,
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
  const previousPeriodDocuments = useMemo(
    () => documents.filter((document) =>
      isInDateRange(document.issue_date || document.created_at, previousRangeStart, previousRangeEnd)
      || document.payments.some((payment) => isInDateRange(payment.paid_at, previousRangeStart, previousRangeEnd)),
    ),
    [documents, previousRangeEnd, previousRangeStart],
  );

  const derived = useMemo(() => {
    const activeOrders = periodOrders.filter((order) => order.status !== 'cancelled');
    const currentOpenOrders = orders.filter((order) => order.status === 'active');
    const completedOrders = activeOrders.filter((order) => order.status === 'completed');
    const runningOrders = activeOrders.filter((order) => order.status === 'active');
    const completedRevenue = completedOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'selling_price'), 0);
    const activeOrderRevenue = runningOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'selling_price'), 0);
    const acceptedRevenue = activeOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'selling_price'), 0);
    const acceptedCost = activeOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'production_cost'), 0);
    const quoteValue = periodOffers.reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const draftRevenue = periodOffers
      .filter((offer) => offer.status === 'draft')
      .reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const sentRevenue = periodOffers
      .filter((offer) => offer.status === 'sent')
      .reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const acceptedOfferRevenue = periodOffers
      .filter((offer) => offer.status === 'accepted')
      .reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const pipelineRevenue = periodOffers
      .filter((offer) => offer.status === 'draft' || offer.status === 'sent' || offer.status === 'accepted')
      .reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const materialUsage = deriveMaterialUsage(spools);
    const materialCosts = createMaterialCostMap(spools);
    const stockValue = spools.reduce((sum, spool) => {
      const remaining = Math.max(0, spool.label_weight - spool.weight_used);
      return sum + (remaining / 1000) * (spool.cost_per_kg ?? 0);
    }, 0);
    const lowStockCount = spools.filter((spool) => {
      const threshold = spool.low_stock_threshold_pct ?? 20;
      if (spool.label_weight <= 0) return false;
      return ((spool.label_weight - spool.weight_used) / spool.label_weight) * 100 <= threshold;
    }).length;
    const reservedLines = currentOpenOrders.reduce((sum, order) => sum + order.reservations.length, 0);
    const consumedGrams = materialUsage.reduce((sum, item) => sum + item.grams, 0);
    const margin = acceptedRevenue > 0 ? ((acceptedRevenue - acceptedCost - (stats?.total_energy_cost ?? 0)) / acceptedRevenue) * 100 : 0;
    const paymentDocuments = periodDocuments.filter(isPaymentDocument);
    const revenueRows = createRevenueRows(periodOrders, periodOffers, periodDocuments, today);
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
        return new Date(document.due_date).getTime() < today.getTime();
      })
      .reduce((sum, document) => sum + asNumber(document.open_amount), 0);
    const missingPaymentSource = paymentDocuments.length === 0 && (activeOrders.length > 0 || offers.length > 0);
    const productionCost = acceptedCost + (stats?.total_cost ?? 0) + (stats?.total_energy_cost ?? 0);
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
          value > 0 ? formatMoney(value, locale, currencyCode) : <span className="text-bambu-gray">nicht bewertbar</span>,
          reservation.status === 'fulfilled' || reservation.status === 'allocated' ? 'OK' : <span className="text-amber-300">prüfen</span>,
        ] as Array<ReactNode>;
      }))
      .slice(0, 6);

    const costSlices: CostSlice[] = [
      { label: 'Material', value: stats?.total_cost ?? 0, color: '#00a14a' },
      { label: 'Produktion', value: Math.max(acceptedCost - (stats?.total_cost ?? 0), 0), color: '#38a8d5' },
      { label: 'Energie', value: energyCost, color: '#21b7cf' },
      { label: 'Reservierung', value: reservedValue, color: '#8d73d9' },
    ];

    const pipelineStages: PipelineStage[] = [
      { label: 'Entwurf', value: draftRevenue, color: '#00a14a' },
      { label: 'Versendet', value: sentRevenue, color: '#38a8d5' },
      { label: 'Angenommen', value: acceptedOfferRevenue, color: '#d89a18' },
      { label: 'Aktiv', value: activeOrderRevenue, color: '#8d73d9' },
      { label: 'Abgeschlossen', value: completedRevenue, color: '#dc5b64' },
    ];

    return {
      activeOrders,
      completedOrders,
      runningOrders,
      completedRevenue,
      activeOrderRevenue,
      paymentDocuments,
      acceptedRevenue,
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
  }, [currencyCode, locale, offers, orders, periodDocuments, periodOffers, periodOrders, rangeEnd, rangeStart, spools, stats, today]);

  const previousDerived = useMemo(() => {
    const activeOrders = previousPeriodOrders.filter((order) => order.status !== 'cancelled');
    const completedOrders = activeOrders.filter((order) => order.status === 'completed');
    const acceptedRevenue = activeOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'selling_price'), 0);
    const acceptedCost = activeOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'production_cost'), 0);
    const completedRevenue = completedOrders.reduce((sum, order) => sum + readAcceptedRevisionValue(order, 'selling_price'), 0);
    const pipelineRevenue = previousPeriodOffers
      .filter((offer) => offer.status === 'draft' || offer.status === 'sent' || offer.status === 'accepted')
      .reduce((sum, offer) => sum + readRevisionValue(offer, 'selling_price'), 0);
    const paymentDocuments = previousPeriodDocuments.filter(isPaymentDocument);
    const paymentEffectiveRevenue = paymentDocuments.reduce(
      (sum, document) => sum + document.payments
        .filter((payment) => isInDateRange(payment.paid_at, previousRangeStart, previousRangeEnd))
        .reduce((paymentSum, payment) => paymentSum + asNumber(payment.amount), 0),
      0,
    );
    const productionCost = acceptedCost + (previousStats?.total_cost ?? 0) + (previousStats?.total_energy_cost ?? 0);
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
  }, [previousPeriodDocuments, previousPeriodOffers, previousPeriodOrders, previousRangeEnd, previousRangeStart, previousStats]);

  const trend = useMemo(
    () => createTrend(periodOrders, archiveEvents, energyHistory, stats, rangeStart, rangeEnd),
    [archiveEvents, energyHistory, periodOrders, rangeEnd, rangeStart, stats],
  );
  const energyPerHour = (stats?.total_print_time_hours ?? 0) > 0
    ? (stats?.total_energy_kwh ?? 0) / (stats?.total_print_time_hours ?? 1)
    : 0;
  const completionRate = derived.acceptedRevenue > 0
    ? (derived.completedRevenue / derived.acceptedRevenue) * 100
    : 0;
  const energyMode = settingsQuery.data?.energy_tracking_mode === 'total' ? 'Gesamtverbrauch' : 'Druckverbrauch';
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
  const spoolsWithLocationCount = spools.filter((spool) => spool.storage_location || spool.location_id).length;
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
      row.idleDays === null ? 'unbekannt' : `${row.idleDays} Tage`,
      row.spool.storage_location ?? 'ohne Ort',
      row.value > 25 ? <span className="text-amber-300">Bestand prüfen</span> : 'beobachten',
    ] as Array<ReactNode>);
  const procurementReadinessRows = [
    ['Kostenbasis', `${spools.length - spoolsWithoutCostCount}/${spools.length || 0} Spulen`, spoolsWithoutCostCount > 0 ? <span className="text-amber-300">Marge unvollständig</span> : 'OK', spoolsWithoutCostCount > 0 ? <EntityLink to={inventoryFocusUrl('missing-cost')}>Kosten pflegen</EntityLink> : 'keine Aktion'],
    ['SKU-Lieferant', `${directSupplierAssignedSpoolCount}/${spools.length || 0} Spulen`, directSupplierAssignedSpoolCount < spools.length ? <span className="text-amber-300">Zuordnung fehlt</span> : 'OK', <EntityLink to={supplierListUrl()}>Lieferanten prüfen</EntityLink>],
    ['Lieferantenbezug gesamt', `${supplierAssignedSpoolCount}/${spools.length || 0} Spulen`, supplierAssignedSpoolCount < spools.length ? <span className="text-amber-300">Angebote fehlen</span> : 'OK', <EntityLink to={supplierListUrl()}>Angebote prüfen</EntityLink>],
    ['Lagerort', `${spoolsWithLocationCount}/${spools.length || 0} Spulen`, spoolsWithLocationCount < spools.length ? <span className="text-amber-300">Suche erschwert</span> : 'OK', <EntityLink to={inventoryFocusUrl('missing-location')}>Orte pflegen</EntityLink>],
    ['Engpassquote', `${derived.lowStockCount}/${spools.length || 0} Artikel`, derived.lowStockCount > 0 ? <span className="text-red-300">Nachbestellen</span> : 'OK', derived.lowStockCount > 0 ? <EntityLink to={inventoryFocusUrl('low-stock')}>Bestellvorschläge</EntityLink> : 'keine Aktion'],
    ['Reservierungsdruck', `${derived.reservedLines} Positionen`, formatMoney(derived.reservedValue, locale, currencyCode), derived.reservedLines > 0 ? <EntityLink to="/orders">Aufträge prüfen</EntityLink> : 'OK'],
  ] as Array<Array<ReactNode>>;
  const riskRows = [
    ...lowStockSpools.slice(0, 4).map((spool) => {
      const label = [spool.material, spool.subtype, spool.color_name].filter(Boolean).join(' ');
      const remaining = Math.max(0, spool.label_weight - spool.weight_used);
      const pct = spool.label_weight > 0 ? (remaining / spool.label_weight) * 100 : 0;
      return [
        <EntityLink to={spoolDetailUrl(spool)}>{label || `Spule #${spool.id}`}</EntityLink>,
        `${Math.round(remaining)} g`,
        spool.storage_location ?? 'Lager',
        pct < 8 ? <span className="text-red-300">kritisch</span> : <span className="text-amber-300">knapp</span>,
      ] as Array<ReactNode>;
    }),
    ...((stats?.total_energy_kwh ?? 0) > 0 ? [[
      <EntityLink to="/settings?tab=operations">Energiequelle</EntityLink>,
      formatKwh(stats?.total_energy_kwh ?? 0, locale),
      stats?.energy_source ?? 'Archiv',
      stats?.energy_data_warming_up ? <span className="text-amber-300">wärmt auf</span> : 'OK',
    ] as Array<ReactNode>] : []),
  ];
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
        `${shortestLeadTime} Tage`,
        group.supplier.email || group.supplier.phone || group.supplier.website || 'kein Kontakt',
        group.skuCount > 0
          ? <span className="text-[#35c46f]">{group.skuCount} SKU direkt</span>
          : `${group.fallbackCount} Angebots-Fallback`,
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
      '1 Rolle',
      supplier ? <EntityLink to={supplierListUrl(supplier.name)}>{supplier.name}</EntityLink> : <EntityLink to={supplierListUrl(spool.brand ?? '')}>{spool.brand || 'Lieferant zuordnen'}</EntityLink>,
      assignment.leadTimeDays > 0 ? `${assignment.leadTimeDays} Tage` : `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(pct)} % Rest`,
      pct < 8 ? <span className="text-red-300">heute prüfen</span> : <span className="text-amber-300">einplanen</span>,
    ] as Array<ReactNode>;
  });
  const materialPlanningRows = derived.materialUsage
    .map((item) => {
      const materialSpools = spools.filter((spool) => spoolMaterialLabel(spool) === item.label);
      const assignment = materialSpools
        .map((spool) => supplierAssignmentForSpool(spool))
        .find((candidate) => candidate.supplier !== null) ?? null;
      const supplier = assignment?.supplier ?? null;
      const leadTimeDays = assignment?.leadTimeDays ?? 0;
      const dailyUse = item.grams / Math.max(selectedDateRange.days, 1);
      const targetDays = Math.max(leadTimeDays + 14, 30);
      const reorderGrams = item.days < targetDays
        ? Math.max(1000, Math.ceil(((targetDays - item.days) * Math.max(dailyUse, 25)) / 100) * 100)
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
      `${item.days} Tage`,
      item.supplier ? <EntityLink to={supplierListUrl(item.supplier.name)}>{item.supplier.name}</EntityLink> : 'Lieferant zuordnen',
      item.supplier ? `${item.leadTimeDays} Tage` : '-',
      item.reorderGrams > 0 ? `${formatWeightKg(item.reorderGrams, locale)} nachziehen` : 'Bestand reicht',
      item.days <= Math.max(item.leadTimeDays + 7, 14)
        ? <span className="text-red-300">kritisch</span>
        : item.reorderGrams > 0
          ? <span className="text-amber-300">einplanen</span>
        : 'OK',
    ] as Array<ReactNode>);
  const openReceivableDocuments = [...derived.paymentDocuments]
    .filter((document) => asNumber(document.open_amount) > 0)
    .sort((left, right) => {
      const leftDue = left.due_date ? new Date(left.due_date).getTime() : Number.MAX_SAFE_INTEGER;
      const rightDue = right.due_date ? new Date(right.due_date).getTime() : Number.MAX_SAFE_INTEGER;
      return leftDue - rightDue;
    });
  const overdueDocuments = openReceivableDocuments.filter((document) =>
    document.due_date ? new Date(document.due_date).getTime() < today.getTime() : false,
  );
  const dueSoonDocuments = openReceivableDocuments.filter((document) => {
    if (!document.due_date) return false;
    const due = new Date(document.due_date).getTime();
    const days = Math.ceil((due - today.getTime()) / 86400000);
    return days >= 0 && days <= 7;
  });
  const paymentRows = derived.paymentDocuments
    .flatMap((document) => document.payments
      .filter((payment) => isInDateRange(payment.paid_at, rangeStart, rangeEnd))
      .map((payment) => ({ document, payment })))
    .sort((left, right) => new Date(right.payment.paid_at).getTime() - new Date(left.payment.paid_at).getTime())
    .slice(0, 8)
    .map(({ document, payment }) => [
      new Date(payment.paid_at).toLocaleDateString(locale),
      <EntityLink to={invoiceListUrl('paid')}>{document.number ?? `Dokument #${document.id}`}</EntityLink>,
      displayCustomer(document.customer_id),
      formatMoney(asNumber(payment.amount), locale, payment.currency || currencyCode),
      payment.method,
    ] as Array<ReactNode>);
  const receivableRows = openReceivableDocuments.slice(0, 8).map((document) => {
    const dueDate = document.due_date ? new Date(document.due_date) : null;
    const daysUntilDue = dueDate ? Math.ceil((dueDate.getTime() - today.getTime()) / 86400000) : null;
    return [
      <EntityLink to={invoicePaymentUrl(document.id)}>{document.number ?? `Dokument #${document.id}`}</EntityLink>,
      displayCustomer(document.customer_id),
      dueDate ? dueDate.toLocaleDateString(locale) : <span className="text-bambu-gray">ohne Fälligkeit</span>,
      formatMoney(asNumber(document.open_amount), locale, document.currency || currencyCode),
      daysUntilDue === null
        ? <span className="text-amber-300">Fälligkeit pflegen</span>
        : daysUntilDue < 0
          ? <span className="text-red-300">{Math.abs(daysUntilDue)} Tage überfällig</span>
          : daysUntilDue <= 7
            ? <span className="text-amber-300">fällig in {daysUntilDue} Tagen</span>
            : 'OK',
      <EntityLink to={invoicePaymentUrl(document.id)}>Zahlung erfassen</EntityLink>,
    ] as Array<ReactNode>;
  });
  const nextPaymentDocument = overdueDocuments[0] ?? dueSoonDocuments[0] ?? openReceivableDocuments[0] ?? null;
  const paymentStatusRows = [
    ['Zahlungswirksam', formatMoney(derived.paymentEffectiveRevenue, locale, currencyCode), `${paymentRows.length} Buchungen`, derived.paymentEffectiveRevenue > 0 ? 'OK' : <span className="text-bambu-gray">keine Buchungen</span>],
    ['Offene Forderungen', formatMoney(derived.openRevenue, locale, currencyCode), `${openReceivableDocuments.length} Belege`, nextPaymentDocument ? <EntityLink to={invoicePaymentUrl(nextPaymentDocument.id)}>Zahlung erfassen</EntityLink> : <EntityLink to={invoiceListUrl('open')}>prüfen</EntityLink>],
    ['Überfällig', formatMoney(derived.overdueRevenue, locale, currencyCode), `${overdueDocuments.length} Belege`, overdueDocuments.length > 0 ? <EntityLink to={invoiceListUrl('overdue')}>Mahnlauf</EntityLink> : 'OK'],
    ['Demnächst fällig', formatMoney(dueSoonDocuments.reduce((sum, document) => sum + asNumber(document.open_amount), 0), locale, currencyCode), `${dueSoonDocuments.length} Belege`, dueSoonDocuments.length > 0 ? <EntityLink to={invoiceListUrl('open')}>erinnern</EntityLink> : 'OK'],
  ] as Array<Array<ReactNode>>;
  const revenueActionRows = [
    ['Zahlung erfassen', `${openReceivableDocuments.length} offene Belege`, nextPaymentDocument ? <EntityLink to={invoicePaymentUrl(nextPaymentDocument.id)}>nächsten Beleg öffnen</EntityLink> : <EntityLink to={invoiceListUrl('open')}>Rechnungen öffnen</EntityLink>, openReceivableDocuments.length > 0 ? 'manuell bestätigen' : 'keine Aktion'],
    ['Mahnlauf vorbereiten', `${overdueDocuments.length} überfällig`, formatMoney(derived.overdueRevenue, locale, currencyCode), overdueDocuments.length > 0 ? <EntityLink to={invoiceListUrl('overdue')}>prüfen</EntityLink> : 'OK'],
    ['Pipeline trennen', formatMoney(derived.pipelineRevenue, locale, currencyCode), <EntityLink to="/orders/offers">Angebote</EntityLink>, 'nicht als Einnahme zählen'],
    ['Kontoabgleich später', derived.missingPaymentSource ? 'Quelle fehlt' : 'Quelle vorhanden', 'Roadmap', 'optional anbinden'],
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
      `${row.runs} Drucke`,
      row.kwh > 0 && row.kwh >= (stats?.total_energy_kwh ?? 0) * 0.2 ? <span className="text-amber-300">Peak prüfen</span> : 'OK',
    ] as Array<ReactNode>);
  const energyActionRows = [
    ['Zeitraumssumme', formatKwh(stats?.total_energy_kwh ?? 0, locale), selectedDateRange.label, <EntityLink to={archiveEnergyUrl('measured')}>{stats?.energy_source ?? 'Archiv'}</EntityLink>],
    ['Energiekosten', formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode), selectedDateRange.label, (stats?.total_energy_cost ?? 0) > 0 ? <EntityLink to={archiveEnergyUrl('measured')}>Kosten prüfen</EntityLink> : <span className="text-bambu-gray">keine Kosten</span>],
    ['Kosten/kWh', formatMoney(settingsQuery.data?.energy_cost_per_kwh ?? 0, locale, currencyCode), 'Einstellung', <EntityLink to={energyCostSettingsUrl}>öffnen</EntityLink>],
    ['Druckintensität', `${energyPerHour.toFixed(2)} kWh/h`, `${formatWeightKg((stats?.total_filament_grams ?? 0), locale)} Filament`, energyPerHour > 0 ? 'OK' : <span className="text-amber-300">keine Stunden</span>],
    ['Messabdeckung', formatPercent(energyDataCoverage, locale), `${measuredEnergyEvents.length}/${archiveEvents.length || 0} Ereignisse`, energyDataCoverage >= 80 ? <EntityLink to={archiveEnergyUrl('measured')}>Messwerte</EntityLink> : <EntityLink to={archiveEnergyUrl('missing')}>Datenlücke</EntityLink>],
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
      <EntityLink to={archiveEnergyUrl(undefined, 'log', event.print_name || '')}>{event.print_name || 'Druck ohne Namen'}</EntityLink>,
      event.printer_id ? <EntityLink to="/printers">{`Drucker #${event.printer_id}`}</EntityLink> : 'unbekannt',
      asNumber(event.energy_kwh) > 0 ? formatKwh(asNumber(event.energy_kwh), locale) : <span className="text-bambu-gray">aus Zeitraum</span>,
      asNumber(event.energy_cost) > 0 ? formatMoney(asNumber(event.energy_cost), locale, currencyCode) : <span className="text-bambu-gray">anteilig</span>,
    ] as Array<ReactNode>);
  const energyQualityRows = [
    ['Print-Log Messwerte', `${measuredEnergyEvents.length}/${archiveEvents.length || 0}`, formatPercent(energyDataCoverage, locale), energyDataCoverage >= 80 ? <EntityLink to={archiveEnergyUrl('measured')}>stabil</EntityLink> : <EntityLink to={archiveEnergyUrl('missing')}>Messwerte ergänzen</EntityLink>],
    ['Zeitanteilige Schätzung', archiveEvents.length > measuredEnergyEvents.length ? `${archiveEvents.length - measuredEnergyEvents.length} Drucke` : '0 Drucke', stats?.energy_source ?? 'Archiv', archiveEvents.length > measuredEnergyEvents.length ? <EntityLink to={archiveEnergyUrl('missing')}>transparent markieren</EntityLink> : 'OK'],
    ['Smart-Plug Verlauf', stats?.energy_data_warming_up ? 'wärmt auf' : 'bereit', selectedDateRange.label, stats?.energy_data_warming_up ? <span className="text-amber-300">Historie sammeln</span> : 'OK'],
    ['Kostenbasis', formatMoney(settingsQuery.data?.energy_cost_per_kwh ?? 0, locale, currencyCode), 'Einstellungen', (settingsQuery.data?.energy_cost_per_kwh ?? 0) > 0 ? 'OK' : <EntityLink to={energyCostSettingsUrl}>pflegen</EntityLink>],
  ];
  const energyRecommendationRows = [
    ['Peak-Fenster', peakHourRows.length > 0 ? peakHourRows[0][0] : 'keine Daten', peakHourRows.length > 0 ? peakHourRows[0][1] : '-', peakHourRows.length > 0 ? 'Druckplanung bündeln' : 'Daten sammeln'],
    ['Kosten je kg', energyPerKg > 0 ? `${energyPerKg.toFixed(2)} kWh/kg` : 'keine Daten', formatWeightKg(stats?.total_filament_grams ?? 0, locale), energyPerKg > 0 ? 'Materialmix beobachten' : 'Archiv abwarten'],
    ['Kosten je Druck', (stats?.total_prints ?? 0) > 0 ? formatMoney((stats?.total_energy_cost ?? 0) / (stats?.total_prints ?? 1), locale, currencyCode) : 'keine Daten', `${stats?.total_prints ?? 0} Drucke`, (stats?.total_prints ?? 0) > 0 ? 'Kalkulation prüfen' : 'keine Aktion'],
    ['Abdeckung verbessern', formatPercent(energyDataCoverage, locale), stats?.energy_source ?? 'Archiv', energyDataCoverage < 80 ? <EntityLink to={archiveEnergyUrl('missing')}>Smart-Plug/Logs prüfen</EntityLink> : 'OK'],
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
      row.margin < 20 ? <span className="text-red-300">Marge Risiko</span> : row.margin < 35 ? <span className="text-amber-300">Prüfen</span> : 'OK',
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
    ['Auftragswert', formatMoney(derived.acceptedRevenue, locale, currencyCode), `${derived.activeOrders.length} Aufträge`, 'Basis'],
    ['Produktionskosten', formatMoney(derived.productionCost, locale, currencyCode), 'Material, Produktion, Energie', derived.productionCost > derived.acceptedRevenue && derived.acceptedRevenue > 0 ? <span className="text-red-300">zu hoch</span> : 'OK'],
    ['Deckungsbeitrag', formatMoney(Math.max(derived.acceptedRevenue - derived.productionCost, 0), locale, currencyCode), formatPercent(derived.margin, locale), derived.margin < 25 && derived.acceptedRevenue > 0 ? <span className="text-amber-300">prüfen</span> : 'OK'],
    ['Reservierter Lagerwert', formatMoney(derived.reservedValue, locale, currencyCode), `${derived.reservedLines} Reservierungen`, derived.reservedValue > 0 ? 'gebunden' : 'frei'],
  ] as Array<Array<ReactNode>>;
  const costControlRows = [
    ['Archivkosten', formatMoney(stats?.total_cost ?? 0, locale, currencyCode), stats?.total_prints ? `${stats.total_prints} Drucke` : 'keine Drucke', (stats?.total_cost ?? 0) > 0 ? <EntityLink to="/archives">prüfen</EntityLink> : 'OK'],
    ['Auftragskalkulation', formatMoney(derived.acceptedRevenue > 0 ? Math.max(derived.productionCost - (stats?.total_cost ?? 0) - (stats?.total_energy_cost ?? 0), 0) : 0, locale, currencyCode), <EntityLink to="/orders/calculation">Kalkulation</EntityLink>, 'Kostenbasis'],
    ['Energieanteil', formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode), formatKwh(stats?.total_energy_kwh ?? 0, locale), (stats?.total_energy_cost ?? 0) > 0 ? <EntityLink to={dashboardTabUrl('energy')}>Energie ansehen</EntityLink> : 'keine Kosten'],
    ['Lagerbindung', formatMoney(derived.reservedValue, locale, currencyCode), `${derived.reservedLines} Positionen`, derived.reservedLines > 0 ? <EntityLink to={dashboardTabUrl('inventory')}>Reservierungen prüfen</EntityLink> : 'OK'],
  ] as Array<Array<ReactNode>>;
  const marginActionRows = [
    ['Marge unter 25 %', `${lowMarginOrders.length} Aufträge`, lowMarginOrders.length > 0 ? formatMoney(lowMarginOrders.reduce((sum, row) => sum + row.revenue, 0), locale, currencyCode) : '-', lowMarginOrders.length > 0 ? <span className="text-amber-300">neu kalkulieren</span> : 'OK'],
    ['Kosten ohne Umsatz', derived.acceptedRevenue <= 0 && derived.productionCost > 0 ? formatMoney(derived.productionCost, locale, currencyCode) : '0,00 €', 'Zeitraum', derived.acceptedRevenue <= 0 && derived.productionCost > 0 ? <span className="text-red-300">prüfen</span> : 'OK'],
    ['Energie in Kalkulation', formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode), settingsQuery.data?.energy_tracking_mode ?? 'Archiv', (stats?.total_energy_cost ?? 0) > 0 ? 'berücksichtigt' : <span className="text-amber-300">keine Daten</span>],
    ['Materialkosten pflegen', `${spoolsWithoutCostCount} Spulen`, <EntityLink to={inventoryFocusUrl('missing-cost')}>Lager öffnen</EntityLink>, spoolsWithoutCostCount > 0 ? <span className="text-amber-300">ergänzen</span> : 'OK'],
  ] as Array<Array<ReactNode>>;
  const overviewPriorityRows = [
    [
      'Einnahmen',
      overdueDocuments.length > 0 ? <span className="text-red-300">überfällig</span> : openReceivableDocuments.length > 0 ? <span className="text-amber-300">offen</span> : 'OK',
      overdueDocuments.length > 0 ? formatMoney(derived.overdueRevenue, locale, currencyCode) : formatMoney(derived.openRevenue, locale, currencyCode),
      openReceivableDocuments.length > 0 ? <EntityLink to={dashboardTabUrl('revenue')}>Forderungen prüfen</EntityLink> : 'keine Aktion',
    ],
    [
      'Marge',
      lowMarginOrders.length > 0 ? <span className="text-amber-300">Risiko</span> : 'OK',
      `${lowMarginOrders.length} Aufträge`,
      lowMarginOrders.length > 0 ? <EntityLink to={dashboardTabUrl('margin')}>Kalkulation prüfen</EntityLink> : 'keine Aktion',
    ],
    [
      'Lager',
      derived.lowStockCount > 0 ? <span className="text-red-300">Nachschub</span> : 'OK',
      `${derived.lowStockCount} Artikel`,
      derived.lowStockCount > 0 ? <EntityLink to={dashboardTabUrl('inventory')}>Bestellvorschläge</EntityLink> : 'Bestand stabil',
    ],
    [
      'Energie',
      energyDataCoverage < 80 ? <span className="text-amber-300">Datenlücke</span> : 'OK',
      formatPercent(energyDataCoverage, locale),
      energyDataCoverage < 80 ? <EntityLink to={dashboardTabUrl('energy')}>Messbasis prüfen</EntityLink> : 'Messbasis stabil',
    ],
    [
      'Pipeline',
      derived.pipelineRevenue > derived.paymentEffectiveRevenue && derived.paymentEffectiveRevenue <= 0 ? <span className="text-amber-300">nicht zahlungswirksam</span> : 'OK',
      formatMoney(derived.pipelineRevenue, locale, currencyCode),
      <EntityLink to="/orders/offers">Angebote öffnen</EntityLink>,
    ],
  ] as Array<Array<ReactNode>>;
  const overviewDataQualityRows = [
    [
      'Zahlungen',
      paymentRows.length > 0 ? `${paymentRows.length} Buchungen` : 'keine Buchungen',
      derived.missingPaymentSource ? <span className="text-amber-300">manuelle Bestätigung fehlt</span> : 'Forderungen auswertbar',
      <EntityLink to={invoiceListUrl(derived.openRevenue > 0 ? 'open' : undefined)}>Rechnungen</EntityLink>,
    ],
    [
      'Materialkosten',
      `${spools.length - spoolsWithoutCostCount}/${spools.length || 0} Spulen`,
      spoolsWithoutCostCount > 0 ? <span className="text-amber-300">Marge unvollständig</span> : 'Kostenbasis OK',
      spoolsWithoutCostCount > 0 ? <EntityLink to={inventoryFocusUrl('missing-cost')}>Kosten/kg pflegen</EntityLink> : 'keine Aktion',
    ],
    [
      'Lieferanten',
      `${directSupplierAssignedSpoolCount}/${spools.length || 0} direkt · ${supplierAssignedSpoolCount} gesamt`,
      directSupplierAssignedSpoolCount < spools.length ? <span className="text-amber-300">SKU-Zuordnung fehlt</span> : 'Nachschub gut ableitbar',
      <EntityLink to={supplierListUrl()}>Lieferanten</EntityLink>,
    ],
    [
      'Energie',
      formatPercent(energyDataCoverage, locale),
      energyDataCoverage < 80 ? <span className="text-amber-300">teilweise geschätzt</span> : 'Messwerte belastbar',
      <EntityLink to="/settings?tab=operations">Einstellungen</EntityLink>,
    ],
    [
      'Kalkulation',
      `${marginSourceRows.length}/${derived.activeOrders.length || 0} Aufträge`,
      marginSourceRows.length < derived.activeOrders.length ? <span className="text-amber-300">nicht alle Aufträge bewertet</span> : 'Margen ableitbar',
      <EntityLink to="/orders/calculation">Kalkulation</EntityLink>,
    ],
  ] as Array<Array<ReactNode>>;
  const forecastScale30 = 30 / Math.max(selectedDateRange.days, 1);
  const forecastPaymentRevenue = derived.paymentEffectiveRevenue * forecastScale30;
  const forecastProductionCost = derived.productionCost * forecastScale30;
  const forecastEnergyKwh = (stats?.total_energy_kwh ?? 0) * forecastScale30;
  const forecastEnergyCost = (stats?.total_energy_cost ?? 0) * forecastScale30;
  const forecastMaterialGrams = derived.consumedGrams * forecastScale30;
  const openDueSoonValue = dueSoonDocuments.reduce((sum, document) => sum + asNumber(document.open_amount), 0);
  const overviewForecastRows = [
    [
      'Zahlungseingang',
      formatMoney(forecastPaymentRevenue, locale, currencyCode),
      `${paymentRows.length} Buchungen`,
      forecastPaymentRevenue > 0 ? 'Liquidität einplanen' : <EntityLink to={invoiceListUrl('open')}>Zahlungen buchen</EntityLink>,
    ],
    [
      'Kostenlauf',
      formatMoney(forecastProductionCost, locale, currencyCode),
      'Produktion inkl. Energie',
      forecastProductionCost > derived.acceptedRevenue && derived.acceptedRevenue > 0 ? <span className="text-amber-300">Deckung prüfen</span> : <EntityLink to={dashboardTabUrl('margin')}>Kosten ansehen</EntityLink>,
    ],
    [
      'Energiebedarf',
      formatKwh(forecastEnergyKwh, locale),
      formatMoney(forecastEnergyCost, locale, currencyCode),
      forecastEnergyKwh > 0 ? <EntityLink to={dashboardTabUrl('energy')}>Peak-Zeiten prüfen</EntityLink> : <EntityLink to="/settings?tab=operations">Messung pflegen</EntityLink>,
    ],
    [
      'Materialverbrauch',
      formatWeightKg(forecastMaterialGrams, locale),
      'seit Verbrauchs-Reset',
      forecastMaterialGrams > 0 ? <EntityLink to={inventoryFocusUrl('low-stock')}>Nachschub planen</EntityLink> : <EntityLink to={inventoryFocusUrl('used')}>Verbrauch pflegen</EntityLink>,
    ],
    [
      'Forderungen',
      formatMoney(derived.openRevenue, locale, currencyCode),
      openDueSoonValue > 0 ? `${formatMoney(openDueSoonValue, locale, currencyCode)} bald fällig` : 'aktueller Stand',
      derived.openRevenue > 0 ? <EntityLink to={invoiceListUrl(overdueDocuments.length > 0 ? 'overdue' : 'open')}>Fälligkeiten öffnen</EntityLink> : 'keine Aktion',
    ],
    [
      'Nachschubrisiko',
      `${derived.lowStockCount} Artikel`,
      lowStockValue > 0 ? formatMoney(lowStockValue, locale, currencyCode) : 'kein Wert gebunden',
      derived.lowStockCount > 0 ? <EntityLink to={inventoryFocusUrl('low-stock')}>Bestellvorschläge</EntityLink> : 'Bestand stabil',
    ],
  ] as Array<Array<ReactNode>>;
  const revenueShortcuts: ActionShortcut[] = [
    {
      label: 'Zahlung erfassen',
      detail: nextPaymentDocument
        ? `${nextPaymentDocument.number ?? `Dokument #${nextPaymentDocument.id}`} · ${formatMoney(asNumber(nextPaymentDocument.open_amount), locale, nextPaymentDocument.currency || currencyCode)} offen`
        : 'keine offenen Belege',
      to: nextPaymentDocument ? invoicePaymentUrl(nextPaymentDocument.id) : invoiceListUrl('open'),
      icon: Receipt,
      tone: nextPaymentDocument ? 'green' : 'neutral',
    },
    {
      label: 'Fälligkeiten prüfen',
      detail: `${overdueDocuments.length} überfällig · ${dueSoonDocuments.length} bald fällig`,
      to: invoiceListUrl(overdueDocuments.length > 0 ? 'overdue' : 'open'),
      icon: AlertTriangle,
      tone: overdueDocuments.length > 0 ? 'red' : dueSoonDocuments.length > 0 ? 'amber' : 'neutral',
    },
    {
      label: 'Angebote öffnen',
      detail: formatMoney(derived.pipelineRevenue, locale, currencyCode),
      to: '/orders/offers',
      icon: TrendingUp,
      tone: 'blue',
    },
    {
      label: 'Rechnungsliste',
      detail: `${derived.paymentDocuments.length} Rechnungen mit Zahlungsdaten`,
      to: invoiceListUrl(),
      icon: ClipboardList,
      tone: 'green',
    },
  ];
  const marginShortcuts: ActionShortcut[] = [
    {
      label: 'Kalkulation öffnen',
      detail: `${marginSourceRows.length} bewertete Aufträge`,
      to: '/orders/calculation',
      icon: Factory,
      tone: 'green',
    },
    {
      label: 'Niedrige Marge',
      detail: `${lowMarginOrders.length} Aufträge unter 25 %`,
      to: lowMarginOrders[0] ? `/orders/${lowMarginOrders[0].order.id}` : '/orders',
      icon: AlertTriangle,
      tone: lowMarginOrders.length > 0 ? 'amber' : 'neutral',
    },
    {
      label: 'Energieanteil prüfen',
      detail: formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode),
      to: dashboardTabUrl('energy'),
      icon: Zap,
      tone: (stats?.total_energy_cost ?? 0) > 0 ? 'cyan' : 'neutral',
    },
    {
      label: 'Materialkosten pflegen',
      detail: `${spoolsWithoutCostCount} Spulen ohne Kosten/kg`,
      to: inventoryFocusUrl(),
      icon: Package,
      tone: spoolsWithoutCostCount > 0 ? 'amber' : 'neutral',
    },
  ];
  const inventoryShortcuts: ActionShortcut[] = [
    {
      label: 'Bestellvorschläge',
      detail: `${derived.lowStockCount} Engpass-Signale`,
      to: inventoryFocusUrl('low-stock'),
      icon: AlertTriangle,
      tone: derived.lowStockCount > 0 ? 'red' : 'neutral',
    },
    {
      label: 'Lieferanten pflegen',
      detail: `${directSupplierAssignedSpoolCount}/${spools.length || 0} direkt · ${supplierAssignedSpoolCount} mit Bezug`,
      to: supplierListUrl(),
      icon: Truck,
      tone: directSupplierAssignedSpoolCount < spools.length ? 'amber' : 'green',
    },
    {
      label: 'Filament öffnen',
      detail: `${spools.length} Spulen · ${formatMoney(derived.stockValue, locale, currencyCode)}`,
      to: inventoryFocusUrl('used'),
      icon: Warehouse,
      tone: 'green',
    },
    {
      label: 'Reservierungen',
      detail: `${derived.reservedLines} Positionen · ${formatMoney(derived.reservedValue, locale, currencyCode)}`,
      to: '/orders',
      icon: ClipboardList,
      tone: derived.reservedLines > 0 ? 'blue' : 'neutral',
    },
  ];
  const energyShortcuts: ActionShortcut[] = [
    {
      label: 'Energie einstellen',
      detail: `${formatMoney(settingsQuery.data?.energy_cost_per_kwh ?? 0, locale, currencyCode)} pro kWh`,
      to: energyCostSettingsUrl,
      icon: BatteryCharging,
      tone: (settingsQuery.data?.energy_cost_per_kwh ?? 0) > 0 ? 'green' : 'amber',
    },
    {
      label: 'Archiv prüfen',
      detail: `${archiveEvents.length} Druckereignisse`,
      to: archiveEnergyUrl(undefined, 'log'),
      icon: BarChart3,
      tone: archiveEvents.length > 0 ? 'cyan' : 'neutral',
    },
    {
      label: 'Drucker ansehen',
      detail: `${printerRows.length} Quellen im Mix`,
      to: '/printers',
      icon: Factory,
      tone: printerRows.length > 0 ? 'blue' : 'neutral',
    },
    {
      label: 'Kostenwirkung',
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
          { title: 'Zahlungsstatus', columns: ['Status', 'Wert', 'Umfang', 'Aktion'], rows: paymentStatusRows },
          { title: 'Offene Forderungen', columns: ['Beleg', 'Kunde', 'Fällig', 'Offen', 'Signal', 'Aktion'], rows: receivableRows },
          { title: 'Zahlungseingänge', columns: ['Datum', 'Beleg', 'Kunde', 'Betrag', 'Methode'], rows: paymentRows },
          { title: 'Einnahmen-Aktionen', columns: ['Thema', 'Umfang', 'Ziel', 'Aktion'], rows: revenueActionRows },
        ];
      case 'margin':
        return [
          { title: 'Deckungsbeitrag kompakt', columns: ['Kennzahl', 'Wert', 'Basis', 'Signal'], rows: contributionRows },
          { title: 'Kostenkontrolle', columns: ['Treiber', 'Wert', 'Quelle', 'Aktion'], rows: costControlRows },
          { title: 'Margen-Aktionen', columns: ['Thema', 'Umfang', 'Wert / Ziel', 'Aktion'], rows: marginActionRows },
          { title: 'Aufträge nach Marge', columns: ['Auftrag', 'Umsatz / Titel', 'Kosten', 'Marge', 'Signal'], rows: orderMarginRows },
        ];
      case 'inventory':
        return [
          { title: 'Nachbestellen und Reservierung', columns: ['Ressource', 'Bestand', 'Ort / Quelle', 'Signal'], rows: riskRows },
          { title: 'Lieferanten-Cockpit', columns: ['Lieferant', 'Materialbezug', 'Lieferzeit', 'Kontakt', 'Status'], rows: supplierRows },
          { title: 'Bestellvorschläge', columns: ['Artikel', 'Bestand', 'Vorschlag', 'Lieferant', 'Lieferzeit', 'Aktion'], rows: reorderRows },
          { title: 'Material- & Lieferantenplanung', columns: ['Material', 'Reichweite', 'Lieferant', 'Lieferzeit', 'Vorschlag', 'Signal'], rows: materialPlanningRows },
          { title: 'Beschaffungsreife', columns: ['Prüfpunkt', 'Abdeckung', 'Signal', 'Aktion'], rows: procurementReadinessRows },
          { title: 'Langsamdreher & Kapitalbindung', columns: ['Spule', 'Wert', 'Ruhezeit', 'Ort', 'Aktion'], rows: staleSpoolRows },
        ];
      case 'energy':
        return [
          { title: 'Energie-Signale', columns: ['Signal', 'Wert', 'Zeitfenster', 'Aktion'], rows: energyActionRows },
          { title: 'Energie je Druck', columns: ['Datum', 'Druck', 'Drucker', 'kWh', 'Kosten'], rows: energyEventRows },
          { title: 'Peak-Fenster', columns: ['Zeitfenster', 'kWh', 'Kosten', 'Drucke', 'Signal'], rows: peakHourRows },
          { title: 'Datenqualität & Kostenbasis', columns: ['Prüfpunkt', 'Wert', 'Quelle', 'Aktion'], rows: energyQualityRows },
          { title: 'Energie-Optimierung', columns: ['Hebel', 'Wert', 'Basis', 'Nächster Schritt'], rows: energyRecommendationRows },
          { title: 'Drucker- und Quellenmix', columns: ['Drucker', 'Drucke', 'kWh anteilig', 'Anteil'], rows: printerRows },
        ];
      case 'overview':
      default:
        return [
          { title: 'Prioritäten', columns: ['Bereich', 'Signal', 'Wert', 'Aktion'], rows: overviewPriorityRows },
          { title: '30-Tage-Vorschau', columns: ['Kennzahl', '30 Tage', 'Basis', 'Nächster Schritt'], rows: overviewForecastRows },
          { title: 'Datenqualität', columns: ['Quelle', 'Abdeckung', 'Auswirkung', 'Nächster Schritt'], rows: overviewDataQualityRows },
          { title: 'Aufträge und Angebote', columns: ['Beleg', 'Kunde', 'Status', 'Betrag'], rows: derived.revenueRows.slice(0, 4).map((row) => [row.number, row.customer, <RevenueStatus status={row.status} />, formatMoney(row.amount, locale, currencyCode)] as Array<ReactNode>) },
          { title: 'Lager- und Energierisiken', columns: ['Ressource', 'Bestand', 'Ort / Quelle', 'Signal'], rows: riskRows },
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
        <MetricCard icon={Receipt} label="Zahlungswirksam" value={formatMoney(derived.paymentEffectiveRevenue, locale, currencyCode)} detail={derived.paymentDocuments.length > 0 ? `${derived.paymentDocuments.length} Rechnungen` : derived.missingPaymentSource ? 'Zahlungsquelle fehlt' : 'keine Buchungen'} tone={derived.paymentEffectiveRevenue > 0 ? 'green' : 'neutral'} to={invoiceListUrl(derived.paymentEffectiveRevenue > 0 ? 'paid' : undefined)} trend={trendLabels.paymentEffectiveRevenue} />
        <MetricCard icon={AlertTriangle} label="Offen / Überfällig" value={formatMoney(derived.openRevenue, locale, currencyCode)} detail={`${formatMoney(derived.overdueRevenue, locale, currencyCode)} überfällig`} tone={derived.overdueRevenue > 0 ? 'red' : 'amber'} to={invoiceListUrl(overdueDocuments.length > 0 ? 'overdue' : 'open')} />
        <MetricCard icon={Clock} label="Aktive Aufträge" value={formatMoney(derived.activeOrderRevenue, locale, currencyCode)} detail={`${derived.runningOrders.length} laufend`} tone="amber" to="/orders" />
        <MetricCard icon={TrendingUp} label="Pipeline" value={formatMoney(derived.pipelineRevenue, locale, currencyCode)} detail="Angebote und Aufträge" tone="blue" to="/orders/offers" trend={trendLabels.pipelineRevenue} />
      </div>
      <ActionStrip actions={revenueShortcuts} />

      <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <Panel icon={Receipt} title="Aufträge, Angebote und Zahlungsquelle" subtitle="Echte Einnahmen bleiben 0, bis Rechnungszahlungen oder Kontoabgleich angebunden sind">
          {derived.revenueRows.length > 0 ? (
            <CompactTable
              columns={['Beleg', 'Kunde', 'Status', 'Betrag']}
              rows={derived.revenueRows.map((row) => [<EntityLink to={row.to}>{row.number}</EntityLink>, row.customer, <RevenueStatus status={row.status} />, formatMoney(row.amount, locale, currencyCode)])}
            />
          ) : <EmptyState label="Noch keine Angebote oder Aufträge vorhanden." />}
        </Panel>
        <Panel icon={CircleDollarSign} title="Abschlussquote und offene Werte">
          <div className="flex items-end gap-4">
            <strong className="text-6xl font-semibold text-white">{formatPercent(completionRate, locale)}</strong>
            <span className="pb-2 text-sm text-bambu-gray">aus Auftragsstatus</span>
          </div>
          <div className="mt-5 h-3 rounded bg-bambu-dark-tertiary">
            <div className="h-3 rounded bg-[#00a14a]" style={{ width: `${clamp(completionRate, 0, 100)}%` }} />
          </div>
          <div className="mt-5 space-y-4">
            <ProgressRow label="Abgeschlossen" value={derived.completedRevenue} max={Math.max(derived.acceptedRevenue, derived.pipelineRevenue, 1)} suffix={formatMoney(derived.completedRevenue, locale, currencyCode)} tone="green" />
            <ProgressRow label="Offene Rechnungen" value={derived.openRevenue} max={Math.max(derived.openRevenue, derived.acceptedRevenue, derived.pipelineRevenue, 1)} suffix={formatMoney(derived.openRevenue, locale, currencyCode)} tone="amber" />
            <ProgressRow label="Überfällig" value={derived.overdueRevenue} max={Math.max(derived.openRevenue, 1)} suffix={formatMoney(derived.overdueRevenue, locale, currencyCode)} tone="red" />
            <ProgressRow label="Angebote" value={derived.pipelineRevenue} max={Math.max(derived.acceptedRevenue, derived.pipelineRevenue, 1)} suffix={formatMoney(derived.pipelineRevenue, locale, currencyCode)} tone="blue" />
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel icon={TrendingUp} title="Pipeline ist Erwartung" subtitle="Nicht mit zahlungswirksamen Einnahmen vermischen">
          <PipelineChart stages={derived.pipelineStages} currency={currencyCode} locale={locale} />
        </Panel>
        <Panel icon={BarChart3} title="Einnahmen, Kosten und Marge im Verlauf">
          <FinanceTrendChart data={trend} currency={currencyCode} locale={locale} />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <Panel icon={AlertTriangle} title="Offene Forderungen" subtitle="Fälligkeit, Restbetrag und nächster manueller Schritt">
          {receivableRows.length > 0 ? (
            <CompactTable columns={['Beleg', 'Kunde', 'Fällig', 'Offen', 'Signal', 'Aktion']} rows={receivableRows} />
          ) : <EmptyState label="Keine offenen Forderungen im gewählten Zeitraum." />}
        </Panel>
        <Panel icon={Receipt} title="Zahlungsstatus" subtitle="Aus tatsächlich erfassten Zahlungen und offenen Rechnungen">
          <CompactTable columns={['Status', 'Wert', 'Umfang', 'Aktion']} rows={paymentStatusRows} />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Panel icon={CircleDollarSign} title="Zahlungseingänge" subtitle="Manuell bestätigte Zahlungen im Zeitraum">
          {paymentRows.length > 0 ? (
            <CompactTable columns={['Datum', 'Beleg', 'Kunde', 'Betrag', 'Methode']} rows={paymentRows} />
          ) : <EmptyState label="Noch keine Zahlungseingänge im gewählten Zeitraum erfasst." />}
        </Panel>
        <Panel icon={Lightbulb} title="Einnahmen-Aktionen" subtitle="Was als nächstes manuell zu prüfen ist">
          <CompactTable columns={['Thema', 'Umfang', 'Ziel', 'Aktion']} rows={revenueActionRows} />
        </Panel>
      </div>
    </div>
  );

  const marginTab = (
    <div className="mt-5 space-y-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Factory} label="Produktionskosten" value={formatMoney(derived.productionCost, locale, currencyCode)} detail="Material, Produktion, Energie" tone="violet" to="/orders/calculation" trend={trendLabels.productionCost} />
        <MetricCard icon={Zap} label="Energieanteil" value={formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode)} detail="separat auswertbar" tone="cyan" to={dashboardTabUrl('energy')} trend={trendLabels.energyCost} />
        <MetricCard icon={CircleDollarSign} label="Deckungsbeitrag" value={formatMoney(Math.max(derived.acceptedRevenue - derived.productionCost, 0), locale, currencyCode)} detail="vor Gemeinkosten" tone="green" to="/orders" trend={trendLabels.contribution} />
        <MetricCard icon={Gauge} label="Marge" value={formatPercent(derived.margin, locale)} detail="effektiv" tone="green" to="/orders/calculation" trend={trendLabels.margin} />
      </div>
      <ActionStrip actions={marginShortcuts} />

      <div className="grid gap-5 xl:grid-cols-[0.78fr_1.22fr]">
        <Panel icon={CircleDollarSign} title="Kostenstruktur im Detail" subtitle="Archivkosten, Auftragskalkulation, Energie und Reservierung">
          <Donut slices={derived.costSlices} center={formatMoney(derived.productionCost, locale, currencyCode)} valueFormatter={(value) => formatMoney(value, locale, currencyCode)} />
        </Panel>
        <Panel icon={ClipboardList} title="Aufträge nach Marge">
          {orderMarginRows.length > 0 ? (
            <CompactTable
              columns={['Auftrag', 'Umsatz / Titel', 'Kosten', 'Marge', 'Signal']}
              rows={orderMarginRows}
            />
          ) : <EmptyState label="Noch keine kalkulierten Aufträge vorhanden." />}
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Panel icon={BarChart3} title="Kostenentwicklung">
          <FinanceTrendChart data={trend} currency={currencyCode} locale={locale} />
        </Panel>
        <Panel icon={Factory} title="Kostentreiber">
          <div className="space-y-4">
            <ProgressRow label="Archivkosten" value={stats?.total_cost ?? 0} max={Math.max(derived.productionCost, 1)} suffix={formatMoney(stats?.total_cost ?? 0, locale, currencyCode)} tone="green" />
            <ProgressRow label="Auftragskalkulation" value={derived.acceptedRevenue > 0 ? Math.max(derived.productionCost - (stats?.total_cost ?? 0) - (stats?.total_energy_cost ?? 0), 0) : 0} max={Math.max(derived.productionCost, 1)} suffix={formatMoney(derived.acceptedRevenue > 0 ? Math.max(derived.productionCost - (stats?.total_cost ?? 0) - (stats?.total_energy_cost ?? 0), 0) : 0, locale, currencyCode)} tone="blue" />
            <ProgressRow label="Energie" value={stats?.total_energy_cost ?? 0} max={Math.max(derived.productionCost, 1)} suffix={formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode)} tone="cyan" />
            <ProgressRow label="Reservierter Lagerwert" value={derived.reservedValue} max={Math.max(derived.stockValue, derived.productionCost, 1)} suffix={formatMoney(derived.reservedValue, locale, currencyCode)} tone="amber" />
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel icon={CircleDollarSign} title="Deckungsbeitrag kompakt" subtitle="Auftragswert gegen Kosten und gebundenes Lager">
          <CompactTable columns={['Kennzahl', 'Wert', 'Basis', 'Signal']} rows={contributionRows} />
        </Panel>
        <Panel icon={ClipboardList} title="Kostenkontrolle" subtitle="Wo die Kosten herkommen und wohin der nächste Klick führt">
          <CompactTable columns={['Treiber', 'Wert', 'Quelle', 'Aktion']} rows={costControlRows} />
        </Panel>
      </div>

      <Panel icon={Lightbulb} title="Margen-Aktionen" subtitle="Konkrete Prüfungen für Kalkulation, Energie und Materialdaten">
        <CompactTable columns={['Thema', 'Umfang', 'Wert / Ziel', 'Aktion']} rows={marginActionRows} />
      </Panel>
    </div>
  );

  const inventoryTab = (
    <div className="mt-5 space-y-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Warehouse} label="Lagerwert" value={formatMoney(derived.stockValue, locale, currencyCode)} detail={`${formatMoney(derived.reservedValue, locale, currencyCode)} reserviert`} tone="green" to={inventoryFocusUrl()} />
        <MetricCard icon={AlertTriangle} label="Nachbestellen" value={`${derived.lowStockCount} Artikel`} detail="unter Schwellwert" tone={derived.lowStockCount > 0 ? 'red' : 'neutral'} to={inventoryFocusUrl('low-stock')} />
        <MetricCard icon={ClipboardList} label="Reservierungen" value={`${derived.reservedLines}`} detail="aus offenen Aufträgen" tone="blue" to="/orders" />
        <MetricCard icon={Package} label="Verbrauch" value={formatWeightKg(derived.consumedGrams, locale)} detail="seit Verbrauchs-Reset" tone="amber" to={inventoryFocusUrl('used')} />
      </div>
      <ActionStrip actions={inventoryShortcuts} />

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel icon={Warehouse} title="Lagerreichweite und Verbrauch" subtitle="Lagerverwaltung bleibt eigener Schwerpunkt">
          {derived.materialUsage.length > 0 ? (
            <div className="space-y-4">
              {derived.materialUsage.map((item, index) => (
                <ProgressRow
                  key={item.label}
                  label={`${item.label} · ${item.days} Tage Reichweite`}
                  value={item.remaining}
                  max={Math.max(...derived.materialUsage.map((material) => material.remaining), 1)}
                  suffix={formatWeightKg(item.remaining, locale)}
                  tone={index === 1 ? 'red' : index === 2 ? 'amber' : 'green'}
                />
              ))}
            </div>
          ) : <EmptyState label="Keine aktiven Spulen im Lager gefunden." />}
        </Panel>
        <Panel icon={AlertTriangle} title="Nachbestellen und Reservierung">
          {riskRows.length > 0 ? (
            <CompactTable columns={['Ressource', 'Bestand', 'Ort / Quelle', 'Signal']} rows={riskRows} />
          ) : <EmptyState label="Keine kritischen Lager- oder Energiesignale im aktuellen Zeitraum." />}
        </Panel>

        <Panel icon={Package} title="Lagerwert nach Material">
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
          ) : <EmptyState label="Keine Materialwerte berechenbar." />}
        </Panel>
        <Panel icon={ClipboardList} title="Reservierungsdruck">
          {derived.reservationRows.length > 0 ? (
            <CompactTable
              columns={['Auftrag', 'Material', 'Reserviert', 'Wert', 'Status']}
              rows={derived.reservationRows}
            />
          ) : <EmptyState label="Keine offenen Reservierungen gefunden." />}
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr_1fr]">
        <Panel icon={Truck} title="Lieferanten-Cockpit" subtitle="Bezugsquelle, Materialabdeckung und Zuverlässigkeit">
          {supplierRows.length > 0 ? (
            <CompactTable columns={['Lieferant', 'Materialbezug', 'Lieferzeit', 'Kontakt', 'Status']} rows={supplierRows} />
          ) : <EmptyState label="Noch keine aktiven Lieferanten hinterlegt." />}
        </Panel>
        <Panel icon={ClipboardList} title="Bestellvorschläge" subtitle="Nachschub nach Reichweite und Reservierung">
          {reorderRows.length > 0 ? (
            <CompactTable columns={['Artikel', 'Bestand', 'Vorschlag', 'Lieferant', 'Lieferzeit', 'Aktion']} rows={reorderRows} />
          ) : <EmptyState label="Aktuell keine Bestellvorschläge aus niedrigen Spulenbeständen." />}
        </Panel>
        <Panel icon={Gauge} title="Materialfluss" subtitle="Was blockiert, was bindet Kapital?">
          <div className="space-y-4">
            <ProgressRow label="Verfügbar" value={Math.max(derived.stockValue - derived.reservedValue, 0)} max={Math.max(derived.stockValue, 1)} suffix={formatMoney(Math.max(derived.stockValue - derived.reservedValue, 0), locale, currencyCode)} tone="green" />
            <ProgressRow label="Reserviert" value={derived.reservedValue} max={Math.max(derived.stockValue, 1)} suffix={formatMoney(derived.reservedValue, locale, currencyCode)} tone="blue" />
            <ProgressRow label="Kritisch gebunden" value={lowStockValue} max={Math.max(derived.stockValue, 1)} suffix={`${derived.lowStockCount} Positionen · ${formatMoney(lowStockValue, locale, currencyCode)}`} tone={derived.lowStockCount > 0 ? 'red' : 'neutral'} />
            <ProgressRow label="Verbrauchsdynamik" value={derived.consumedGrams} max={Math.max(derived.consumedGrams * 1.35, 1)} suffix={formatWeightKg(derived.consumedGrams, locale)} tone="amber" />
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel icon={Lightbulb} title="Material- & Lieferantenplanung" subtitle="Reichweite gegen Lieferzeit und Verbrauch gespiegelt">
          {materialPlanningRows.length > 0 ? (
            <CompactTable columns={['Material', 'Reichweite', 'Lieferant', 'Lieferzeit', 'Vorschlag', 'Signal']} rows={materialPlanningRows} />
          ) : <EmptyState label="Keine Materialplanung berechenbar." />}
        </Panel>
        <Panel icon={Gauge} title="Lagerqualität" subtitle="Wert, Engpass und Datenpflege auf einen Blick">
          <div className="space-y-4">
            <ProgressRow label="SKU-Lieferanten" value={directSupplierAssignedSpoolCount} max={Math.max(spools.length, 1)} suffix={`${directSupplierAssignedSpoolCount} von ${spools.length}`} tone={directSupplierAssignedSpoolCount < spools.length ? 'amber' : 'green'} />
            <ProgressRow label="Angebotsabdeckung" value={supplierAssignedSpoolCount} max={Math.max(spools.length, 1)} suffix={`${supplierAssignedSpoolCount} von ${spools.length}`} tone="green" />
            <ProgressRow label="Ohne Kosten/kg" value={spoolsWithoutCostCount} max={Math.max(spools.length, 1)} suffix={`${spoolsWithoutCostCount} Spulen`} tone={spoolsWithoutCostCount > 0 ? 'amber' : 'neutral'} />
            <ProgressRow label="Kritischer Bestand" value={derived.lowStockCount} max={Math.max(spools.length, 1)} suffix={`${derived.lowStockCount} Artikel`} tone={derived.lowStockCount > 0 ? 'red' : 'green'} />
            <ProgressRow label="Mit Lagerort" value={spoolsWithLocationCount} max={Math.max(spools.length, 1)} suffix={`${spoolsWithLocationCount} Spulen`} tone="blue" />
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel icon={Gauge} title="Beschaffungsreife" subtitle="Wie vollständig Nachbestellung und Kalkulation ableitbar sind">
          <CompactTable columns={['Prüfpunkt', 'Abdeckung', 'Signal', 'Aktion']} rows={procurementReadinessRows} />
        </Panel>
        <Panel icon={Package} title="Langsamdreher & Kapitalbindung" subtitle="Bestand mit langer Ruhezeit und vorhandenem Restwert">
          {staleSpoolRows.length > 0 ? (
            <CompactTable columns={['Spule', 'Wert', 'Ruhezeit', 'Ort', 'Aktion']} rows={staleSpoolRows} />
          ) : <EmptyState label="Keine langsam drehenden Bestände mit Restwert gefunden." />}
        </Panel>
      </div>
    </div>
  );

  const energyTab = (
    <div className="mt-5 space-y-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Zap} label="Verbrauch" value={formatKwh(stats?.total_energy_kwh ?? 0, locale)} detail={energyMode} tone="cyan" to="/dashboard" trend={trendLabels.energyKwh} />
        <MetricCard icon={CircleDollarSign} label="Energiekosten" value={formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode)} detail="im Zeitraum" tone="amber" to={energyCostSettingsUrl} trend={trendLabels.energyCost} />
        <MetricCard icon={BatteryCharging} label="Kosten/kWh" value={formatMoney(settingsQuery.data?.energy_cost_per_kwh ?? 0, locale, currencyCode)} detail="aus Einstellungen" tone="neutral" to={energyCostSettingsUrl} />
        <MetricCard icon={Gauge} label="Intensität" value={`${energyPerHour.toFixed(2)} kWh/h`} detail="je Druckstunde" tone="green" to={archiveEnergyUrl(undefined, 'log')} />
      </div>
      <ActionStrip actions={energyShortcuts} />

      <div className="grid gap-5 xl:grid-cols-[0.85fr_1.15fr]">
        <Panel icon={Zap} title="Energie-Kennzahlen" subtitle={energyMode}>
          <div className="grid gap-3 sm:grid-cols-2">
            <MiniMetric icon={Zap} label="Verbrauch" value={formatKwh(stats?.total_energy_kwh ?? 0, locale)} tone="cyan" />
            <MiniMetric icon={CircleDollarSign} label="Energiekosten" value={formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode)} tone="amber" />
            <MiniMetric icon={BatteryCharging} label="Kosten/kWh" value={formatMoney(settingsQuery.data?.energy_cost_per_kwh ?? 0, locale, currencyCode)} tone="neutral" />
            <MiniMetric icon={Factory} label="kWh / Druckstunde" value={energyPerHour.toFixed(2)} tone="green" />
          </div>
          <div className={`${surface.panelQuiet} mt-5 text-sm text-bambu-gray`}>
            Quelle: <span className="font-medium text-white">{stats?.energy_source ?? 'Archivstatistik'}</span>
          </div>
        </Panel>
        <Panel icon={BatteryCharging} title="Stundenprofil" subtitle="Print-Log-Energie, sonst nach realer Druckdauer aus der Zeitraumssumme verteilt">
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
            : <EmptyState label="Keine Energiedaten im Zeitraum." />}
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Panel icon={BarChart3} title="Energie je Druck" subtitle="Letzte Ereignisse aus dem gewählten Zeitraum">
          {energyEventRows.length > 0 ? (
            <CompactTable columns={['Datum', 'Druck', 'Drucker', 'kWh', 'Kosten']} rows={energyEventRows} />
          ) : <EmptyState label="Noch keine Druckereignisse im Zeitraum vorhanden." />}
        </Panel>
        <Panel icon={AlertTriangle} title="Energie-Signale">
          <CompactTable
            columns={['Signal', 'Wert', 'Zeitfenster', 'Aktion']}
            rows={energyActionRows}
          />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Panel icon={Clock} title="Peak-Fenster" subtitle="Stunden mit höchstem Energiebedarf im Zeitraum">
          {peakHourRows.length > 0 ? (
            <CompactTable columns={['Zeitfenster', 'kWh', 'Kosten', 'Drucke', 'Signal']} rows={peakHourRows} />
          ) : <EmptyState label="Noch keine Zeitfenster aus Druckereignissen berechenbar." />}
        </Panel>
        <Panel icon={Gauge} title="Datenqualität & Kostenbasis" subtitle="Was gemessen ist und was geschätzt werden muss">
          <CompactTable columns={['Prüfpunkt', 'Wert', 'Quelle', 'Aktion']} rows={energyQualityRows} />
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr_1fr]">
        <Panel icon={Lightbulb} title="Energie-Optimierung" subtitle="Konkrete Hebel aus vorhandenen Kennzahlen">
          <CompactTable columns={['Hebel', 'Wert', 'Basis', 'Nächster Schritt']} rows={energyRecommendationRows} />
        </Panel>
        <Panel icon={Clock} title="Archivkennzahlen" subtitle="Reale Summen aus dem gewählten Zeitraum">
          <CompactTable
            columns={['Kennzahl', 'Wert', 'Quelle', 'Signal']}
            rows={[
              ['Druckstunden', `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(stats?.total_print_time_hours ?? 0)} h`, 'Archiv', 'OK'],
              ['Filament', formatWeightKg(stats?.total_filament_grams ?? 0, locale), 'Archiv', 'OK'],
              ['Energiequelle', stats?.energy_source ?? 'keine', energyMode, (stats?.total_energy_kwh ?? 0) > 0 ? 'OK' : <span className="text-amber-300">fehlt</span>],
              ['Aufwärmphase', stats?.energy_data_warming_up ? 'aktiv' : 'nein', 'Archiv', stats?.energy_data_warming_up ? <span className="text-amber-300">warten</span> : 'OK'],
            ]}
          />
        </Panel>
        <Panel icon={Factory} title="Drucker- und Quellenmix" subtitle="Druckanteile aus der Archivstatistik">
          {printerRows.length > 0 ? (
            <CompactTable columns={['Drucker', 'Drucke', 'kWh anteilig', 'Anteil']} rows={printerRows} />
          ) : <EmptyState label="Keine Druckeranteile im Zeitraum vorhanden." />}
          <p className="mt-5 text-xs text-bambu-gray">Quelle: {stats?.energy_source ?? 'Archivstatistik'} · Modus: {energyMode}</p>
        </Panel>
      </div>
    </div>
  );

  return (
    <div className="w-full p-4 sm:p-6">
      <div className="w-full">
        <header className="space-y-4">
          <div>
            <h1 className="text-[1.75rem] font-semibold leading-tight text-white sm:text-[2rem]">Business Dashboard</h1>
            <p className="mt-1 text-sm leading-5 text-bambu-gray">
              Kosten, Einnahmen, Lager und Energieverbrauch als eigene betriebliche Übersicht.
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
                CSV Export
              </button>
              <Select
                ariaLabel="Zeitraum"
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
                    <span className="text-bambu-gray">Zeitraum:</span>
                    <span className="font-medium text-white">{option?.label}</span>
                  </span>
                )}
              />
            </div>
          </div>
        </header>

        {activeTab === 'overview' ? (
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-8">
            <MetricCard icon={Receipt} label="Zahlungswirksam" value={formatMoney(derived.paymentEffectiveRevenue, locale, currencyCode)} detail={derived.paymentDocuments.length > 0 ? `${derived.paymentDocuments.length} Rechnungen` : derived.missingPaymentSource ? 'Zahlungsquelle fehlt' : 'keine Buchungen'} tone={derived.paymentEffectiveRevenue > 0 ? 'green' : 'neutral'} to={dashboardTabUrl('revenue')} trend={trendLabels.paymentEffectiveRevenue} />
            <MetricCard icon={TrendingUp} label="Auftragswert" value={formatMoney(derived.acceptedRevenue, locale, currencyCode)} detail={`${derived.activeOrders.length} Aufträge`} tone="green" to={dashboardTabUrl('revenue')} trend={trendLabels.acceptedRevenue} />
            <MetricCard icon={CircleDollarSign} label="Deckungsbeitrag" value={formatMoney(Math.max(derived.acceptedRevenue - derived.productionCost, 0), locale, currencyCode)} detail={`${formatPercent(derived.margin, locale)} effektive Marge`} tone="green" to={dashboardTabUrl('margin')} trend={trendLabels.contribution} />
            <MetricCard icon={Warehouse} label="Lagerwert" value={formatMoney(derived.stockValue, locale, currencyCode)} detail={`${formatMoney(derived.reservedValue, locale, currencyCode)} reserviert`} tone="cyan" to={dashboardTabUrl('inventory')} />
            <MetricCard icon={Zap} label="Energieverbrauch" value={formatKwh(stats?.total_energy_kwh ?? 0, locale)} detail={`${formatMoney(stats?.total_energy_cost ?? 0, locale, currencyCode)} Strom`} tone="cyan" to={dashboardTabUrl('energy')} trend={trendLabels.energyKwh} />
            <MetricCard icon={AlertTriangle} label="Nachbestellen" value={`${derived.lowStockCount} Artikel`} detail={`${riskRows.length} Signale`} tone={derived.lowStockCount > 0 ? 'red' : 'neutral'} to={dashboardTabUrl('inventory')} />
            <MetricCard icon={Factory} label="Produktionskosten" value={formatMoney(derived.productionCost, locale, currencyCode)} detail="Material, Produktion, Energie" tone="violet" to={dashboardTabUrl('margin')} trend={trendLabels.productionCost} />
            <MetricCard icon={Gauge} label="Abschlussquote" value={formatPercent(completionRate, locale)} detail="aus Auftragsstatus" tone="green" to={dashboardTabUrl('revenue')} trend={trendLabels.completionRate} />
          </div>
        ) : null}

        {activeTab === 'overview' ? (
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
        {activeTab === 'revenue' ? revenueTab : null}
        {activeTab === 'margin' ? marginTab : null}
        {activeTab === 'inventory' ? inventoryTab : null}
        {activeTab === 'energy' ? energyTab : null}
      </div>
    </div>
  );
}
