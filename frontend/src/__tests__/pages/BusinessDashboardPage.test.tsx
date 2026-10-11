import { act, cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BusinessDashboardPage } from '../../pages/BusinessDashboardPage';
import i18n from '../../i18n';
import { server } from '../mocks/server';
import { render } from '../utils';

function useDashboardData() {
  const now = new Date().toISOString();
  const dueDate = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
  const order = {
    id: 7, number: 'AU-100', status: 'completed', customer_id: null,
    accepted_snapshot: { revision: { selling_price: '100', production_cost: '40', currency: 'EUR' } },
    created_at: now, updated_at: now, reservations: [],
  };
  const document = {
    id: 11, number: 'RE-100', document_type: 'invoice', payment_status: 'partially_paid',
    customer_id: 2, total_amount: '100', open_amount: '70', currency: 'EUR',
    due_date: dueDate, issue_date: now.slice(0, 10), created_at: now,
    payments: [{ id: 21, amount: '30', currency: 'EUR', paid_at: now, method: 'bank_transfer' }],
  };
  server.use(
    http.get('/api/v1/archives/stats', () => HttpResponse.json({
      total_prints: 1, successful_prints: 1, failed_prints: 0, cancelled_prints: 0,
      total_print_time_hours: 2, total_filament_grams: 250, total_cost: 10,
      prints_by_filament_type: { PLA: 1 }, prints_by_printer: { 'Workshop printer': 1 },
      total_energy_kwh: 1.5, total_energy_cost: 0.45, energy_source: 'print_logs',
    })),
    http.get('/api/v1/archives/slim', () => HttpResponse.json([
      { id: 1, created_at: now, completed_at: now, started_at: now, print_name: 'Bracket',
        printer_id: 1, actual_time_seconds: 7200, energy_kwh: 1.5, energy_cost: 0.45, cost: 10 },
    ])),
    http.get('/api/v1/archives/energy-history', () => HttpResponse.json([])),
    http.get('/api/v1/inventory/spools', () => HttpResponse.json([])),
    http.get('/api/v1/inventory/sku-settings', () => HttpResponse.json([])),
    http.get('/api/v1/small-parts', () => HttpResponse.json({ items: [], total: 0, limit: 200, offset: 0 })),
    http.get('/api/v1/suppliers', () => HttpResponse.json({ items: [], total: 0, limit: 200, offset: 0 })),
    http.get('/api/v1/offers', () => HttpResponse.json([])),
    http.get('/api/v1/orders', () => HttpResponse.json([order])),
    http.get('/api/v1/commercial-documents', () => HttpResponse.json([document])),
  );
}

beforeEach(() => {
  useDashboardData();
});

afterEach(async () => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState({}, '', '/');
  await i18n.changeLanguage('en');
});

describe('BusinessDashboardPage runtime translations', () => {
  it.each([
    ['overview', 'Financiële trend met kosten, energie en marge'],
    ['revenue', 'Orders, offertes en betalingsbron'],
    ['margin', 'Kostenstructuur in detail'],
    ['inventory', 'Voorraaddekking en verbruik'],
    ['energy', 'Energiekengetallen'],
  ])('renders the %s tab in Dutch using the real catalog', async (tab, title) => {
    await i18n.changeLanguage('nl');
    window.history.replaceState({}, '', `/business-dashboard?tab=${tab}`);
    render(<BusinessDashboardPage />);

    expect(await screen.findByRole('heading', { name: 'Bedrijfsdashboard' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Overzicht' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Inkomsten' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Kosten en marge' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Voorraad en verbruik' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Periode' })).toHaveTextContent('afgelopen 30 dagen');
    expect(document.body).not.toHaveTextContent(/Zahlungswirksam|Lager & Verbrauch|Nächster Schritt|keine Daten|Aufwärmphase/);
  });

  it('updates labels on a language change while preserving revenue and completed pipeline values', async () => {
    await i18n.changeLanguage('de');
    window.history.replaceState({}, '', '/business-dashboard');
    render(<BusinessDashboardPage />);
    await screen.findAllByRole('link', { name: 'AU-100' });

    const payments = screen.getAllByText('Zahlungswirksam')[0].closest('a')!;
    const orderValue = screen.getAllByText('Auftragswert')[0].closest('a')!;
    expect(within(payments).getByText(/30,00\s*€/, { selector: 'strong' })).toBeInTheDocument();
    expect(within(orderValue).getByText(/100,00\s*€/, { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByText('davon abgeschlossen').parentElement).toHaveTextContent(/100,00\s*€/);
    expect(screen.getByRole('button', { name: 'Einnahmen' })).toBeInTheDocument();

    await act(async () => { await i18n.changeLanguage('nl'); });

    expect(screen.getByRole('heading', { name: 'Bedrijfsdashboard' })).toBeInTheDocument();
    expect(within(payments).getByText('Ontvangen betalingen')).toBeInTheDocument();
    expect(within(payments).getByText(/30,00/, { selector: 'strong' })).toBeInTheDocument();
    expect(within(orderValue).getByText('Orderwaarde')).toBeInTheDocument();
    expect(within(orderValue).getByText(/100,00/, { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByText('waarvan afgerond').parentElement).toHaveTextContent('100,00');
    expect(screen.queryByRole('button', { name: 'Einnahmen' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Inkomsten' })).toBeInTheDocument();
  });

  it('exports Dutch CSV headings, statuses and payment labels without changing amounts or links', async () => {
    await i18n.changeLanguage('nl');
    window.history.replaceState({}, '', '/business-dashboard?tab=revenue');
    let exported: Blob | undefined;
    vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
      exported = blob as Blob;
      return 'blob:dashboard-csv';
    });
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const user = userEvent.setup();
    render(<BusinessDashboardPage />);

    expect(await screen.findByText('Bankoverschrijving')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Betaling registreren' })[0]).toHaveAttribute('href', '/orders/invoices?payment=11&filter=open');
    await user.click(screen.getByRole('button', { name: 'CSV-export' }));
    await waitFor(() => expect(exported).toBeInstanceOf(Blob));
    const csv = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = reject;
      reader.readAsText(exported!);
    });

    expect(csv).toContain('"Betalingsstatus"');
    expect(csv).toContain('"Klant"');
    expect(csv).toContain('"Bankoverschrijving"');
    expect(csv).toContain('30,00');
    expect(csv).not.toMatch(/Zahlungsstatus|Zahlungseingänge|Kunde #|bank_transfer/);
  });
});
