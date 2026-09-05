import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { documentManagementApi } from '../../api/documentManagement';
import i18n from '../../i18n';
import { OrdersPage } from '../../pages/OrdersPage';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ hasPermission: () => false }),
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
  await i18n.changeLanguage('en');
  vi.spyOn(documentManagementApi, 'listDocuments').mockResolvedValue([]);
});

describe('Orders page heading', () => {
  it.each([
    ['/orders', 'Order overview', 'Pipeline, deadlines, reservations, and open commercial work.'],
    ['/orders/calculation', 'Calculation', 'Material, machine time, margin, and project-based pricing.'],
    ['/orders/offers', 'Offers', 'Draft, sent, accepted, and rejected offers.'],
    ['/orders/invoices', 'Invoices', 'Invoices, due dates, payment status, and invoice history.'],
  ])('shows the active section in the page heading for %s', (path, title, subtitle) => {
    mount(path);
    const heading = screen.getByRole('heading', { level: 1, name: title });
    expect(heading.nextElementSibling).toHaveTextContent(subtitle);
  });
});
