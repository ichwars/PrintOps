import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { documentManagementApi, type CommercialDocument } from '../../api/documentManagement';
import i18n from '../../i18n';
import { OrdersPage } from '../../pages/OrdersPage';

const permissions = vi.hoisted(() => ({ payments: false }));
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ hasPermission: (permission: string) => permission === 'payments:manage' && permissions.payments }),
}));

function mount(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={client}>
        <OrdersPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(async () => {
  permissions.payments = false;
  await i18n.changeLanguage('en');
  vi.spyOn(documentManagementApi, 'listDocuments').mockResolvedValue([]);
});

describe('Orders page heading', () => {
  it('shows the invoices heading at the route that mounts OrdersPage', () => {
    mount('/orders/invoices');
    const heading = screen.getByRole('heading', { level: 1, name: 'Invoices' });
    expect(heading.nextElementSibling).toHaveTextContent(
      'Invoices, due dates, payment status, and invoice history.',
    );
  });
});

const invoice: CommercialDocument = {
  id: 42, document_type: 'invoice', business_profile_id: 1, customer_id: null,
  source_offer_id: null, source_order_id: null, number: 'INV-42', external_issuer_number: null,
  technical_status: 'issued', business_status: 'open', payment_status: 'partially_paid',
  issue_date: '2026-08-01', service_date: null, due_date: '2020-08-30', language: 'de', currency: 'EUR',
  subtotal_amount: '100.00', tax_amount: '19.00', total_amount: '119.00', open_amount: '99.00',
  content_options: {}, tax_decision: {}, lock_version: 3, created_at: '2026-08-01', updated_at: '2026-08-01',
  lines: [], artifacts: [], payments: [], snapshot_sha256: null,
};

describe('Native invoice language and payment flow', () => {
  it('renders native financial labels in English for the English UI', async () => {
    vi.mocked(documentManagementApi.listDocuments).mockResolvedValue([invoice]);
    mount('/orders/invoices');
    expect(await screen.findByText('INV-42')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm payment' })).toBeDisabled();
    expect(screen.getByText('No customer')).toBeInTheDocument();
    expect(screen.getByText(/Partially paid/)).toHaveTextContent('open');
    expect(screen.queryByText('Zahlung bestätigen')).not.toBeInTheDocument();
  });

  it('renders Dutch invoice status and payment dialog while preserving the payment command', async () => {
    permissions.payments = true;
    await i18n.changeLanguage('nl');
    vi.mocked(documentManagementApi.listDocuments).mockResolvedValue([invoice]);
    const record = vi.spyOn(documentManagementApi, 'recordPayment').mockResolvedValue(invoice);
    const user = userEvent.setup();
    mount('/orders/invoices');
    expect(await screen.findByText('INV-42')).toBeInTheDocument();
    expect(screen.getByText('Geen klant')).toBeInTheDocument();
    expect(screen.getByText(/Gedeeltelijk betaald/)).toHaveTextContent('openstaand');
    expect(screen.getByRole('button', { name: 'Achterstallig 1' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Betaling bevestigen' }));
    expect(screen.getByRole('heading', { name: 'Ontvangen betaling bevestigen' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Betaalmethode' })).toHaveTextContent('Bankoverschrijving');
    await user.clear(screen.getByLabelText('Bedrag'));
    await user.type(screen.getByLabelText('Bedrag'), '12,50');
    await user.type(screen.getByLabelText('Referentie'), ' NL-bank-42 ');
    await user.click(screen.getByRole('button', { name: 'Opslaan' }));
    await waitFor(() => expect(record).toHaveBeenCalledWith(42, expect.objectContaining({
      amount: '12.50', method: 'bank_transfer', reference: 'NL-bank-42', note: null,
    })));
  });
});
