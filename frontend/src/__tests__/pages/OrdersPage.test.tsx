import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { documentManagementApi, type CommercialDocument } from '../../api/documentManagement';
import i18n from '../../i18n';
import { OrdersPage } from '../../pages/OrdersPage';
import * as clipboard from '../../utils/clipboard';

const permissions = vi.hoisted(() => ({ payments: false, readPayments: false, exportDocuments: false }));
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ hasPermission: (permission: string) => permission === 'commercial_documents:read' || (permission === 'payments:manage' && permissions.payments) || (permission === 'payments:read' && permissions.readPayments) || (permission === 'commercial_documents:export' && permissions.exportDocuments) }),
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
  permissions.readPayments = false;
  permissions.exportDocuments = false;
  await i18n.changeLanguage('en');
  vi.spyOn(documentManagementApi, 'listDocuments').mockResolvedValue([]);
});

afterEach(() => vi.restoreAllMocks());

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

it('sorts visible customer names in both directions and keeps unnamed invoices last', async () => {
  vi.mocked(documentManagementApi.listDocuments).mockResolvedValue([
    { ...invoice, id: 43, number: 'INV-43', customer_id: 7, customer_display_name: 'Zeta Works' },
    invoice,
    { ...invoice, id: 44, number: 'INV-44', customer_id: 19, customer_display_name: 'Alpha Studio' },
  ]);
  const user = userEvent.setup();
  mount('/orders/invoices?payment=42');
  expect(await screen.findByRole('cell', { name: 'Alpha Studio' })).toBeVisible();
  expect(screen.getByRole('cell', { name: 'Zeta Works' })).toBeVisible();
  const header = screen.getByRole('columnheader', { name: 'Customer' });
  const sort = within(header).getByRole('button');
  const rows = () => screen.getAllByRole('row').slice(1).map(row => within(row).getAllByRole('cell')[1].textContent);

  await user.click(sort);
  expect(header).toHaveAttribute('aria-sort', 'ascending');
  expect(rows()).toEqual(['Alpha Studio', 'Zeta Works', 'No customer']);
  await user.click(sort);
  expect(header).toHaveAttribute('aria-sort', 'descending');
  expect(rows()).toEqual(['Zeta Works', 'Alpha Studio', 'No customer']);
});

describe('Native invoice language and payment flow', () => {
  it('renders native financial labels in English for the English UI', async () => {
    vi.mocked(documentManagementApi.listDocuments).mockResolvedValue([invoice]);
    mount('/orders/invoices');
    expect(await screen.findByText('INV-42')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Actions: INV-42' }));
    expect(screen.queryByRole('menuitem', { name: 'Confirm payment' })).not.toBeInTheDocument();
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
    await user.click(screen.getByRole('button', { name: /INV-42/ }));
    await user.click(screen.getByRole('menuitem', { name: 'Betaling bevestigen' }));
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

it('shows invoice positions and totals alongside the payment journal and document download', async () => {
  permissions.readPayments = true;
  permissions.exportDocuments = true;
  const selected: CommercialDocument = {
    ...invoice,
    customer_id: 11,
    customer_display_name: 'Ada Example',
    lines: [{
      id: 1, position: 1, description: 'Mounting bracket', quantity: '2', unit_code: 'C62',
      unit_price: '24.125', net_amount: '48.25', tax_category_code: 'S', tax_rate: '19', product_identifier: 'BR-1',
    }, {
      id: 2, position: 2, description: 'Hardware', quantity: '0.5', unit_code: 'KGM',
      unit_price: '103.50', net_amount: '51.75', tax_category_code: 'S', tax_rate: '19', product_identifier: null,
    }],
    payments: [{
      id: 31, document_id: invoice.id, amount: '20.00', currency: 'EUR', paid_at: '2026-08-05',
      method: 'bank_transfer', reference: 'REF-31', note: null, recorded_by_id: null, created_at: '2026-08-05',
    }],
    artifacts: [{
      id: 8, kind: 'pdf', content_type: 'application/pdf', sha256: 'pdf-hash', validation_status: 'valid',
      original_role: 'original', rule_versions: {}, export_manifest: {}, layout_configuration_id: null,
      layout_version: null, layout_effective_sha256: null, renderer_version: null, validator_version: null,
      created_at: '2026-08-01',
    }],
  };
  vi.mocked(documentManagementApi.listDocuments).mockResolvedValue([selected]);
  const detail = vi.spyOn(documentManagementApi, 'getDocument').mockResolvedValue(selected);
  const blob = new Blob(['pdf'], { type: 'application/pdf' });
  const download = vi.spyOn(documentManagementApi, 'downloadDocumentArtifact').mockResolvedValue({ blob, filename: 'invoice.pdf' });
  const save = vi.spyOn(clipboard, 'downloadBlob').mockImplementation(() => {});
  const user = userEvent.setup();
  mount('/orders/invoices?customer=11&profile=7');
  await user.click(await screen.findByText('INV-42'));
  const dialog = within(await screen.findByRole('dialog', { name: 'Invoice INV-42' }));
  expect(dialog.getByText('Ada Example')).toBeVisible();
  const lines = within(dialog.getByRole('region', { name: 'Invoice lines' })).getAllByRole('listitem');
  expect(lines).toHaveLength(2);
  expect(lines[0]).toHaveTextContent('Mounting bracket');
  expect(lines[0]).toHaveTextContent('2 pc');
  expect(lines[0]).toHaveTextContent('€24.125');
  expect(lines[0]).toHaveTextContent('€48.25');
  expect(lines[1]).toHaveTextContent('0.5 kg');
  expect(lines[1]).toHaveTextContent('€51.75');
  for (const total of ['€100.00', '€19.00', '€119.00']) expect(dialog.getByText(total)).toBeVisible();
  expect(dialog.getByText('REF-31')).toBeVisible();
  await user.click(dialog.getByRole('button', { name: 'PDF' }));
  expect(download).toHaveBeenCalledWith(42, 8);
  expect(save).toHaveBeenCalledWith(blob, 'invoice.pdf');
  expect(detail).toHaveBeenCalledWith(42);
  expect(documentManagementApi.listDocuments).toHaveBeenCalledWith({ customerId: 11, businessProfileId: 7 });
});
