import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { WarehouseGoodsForecast } from '../../components/warehouse/WarehouseGoodsForecast';
import i18n from '../../i18n';
import { server } from '../mocks/server';

describe('WarehouseGoodsForecast', () => {
  it('shows stock in its own unit and distinguishes missing consumption from a reached minimum', async () => {
    await i18n.changeLanguage('en');
    server.use(http.get('*/api/v1/warehouse-articles/forecast', () => HttpResponse.json({
      window_days: 30, total: 2, limit: 50, offset: 0,
      items: [
        { id: 1, sku: 'M-01', name: 'Resin', unit_code: 'KGM', available: '3.1', minimum_stock: '0.2', daily_usage: '0.03', projected_available: '2.2', days_until_minimum: null },
        { id: 2, sku: 'A-01', name: 'Bracket', unit_code: 'C62', available: '0', minimum_stock: '1', daily_usage: null, projected_available: null, days_until_minimum: 0 },
      ],
    })));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><WarehouseGoodsForecast /></QueryClientProvider>);

    expect(await screen.findByRole('columnheader', { name: 'Stock in 30 days' })).toBeInTheDocument();
    const material = within(screen.getByRole('row', { name: /Resin/ }));
    expect(material.getByRole('cell', { name: '0.03 kg' })).toBeInTheDocument();
    expect(material.getByRole('cell', { name: '2.2 kg' })).toBeInTheDocument();
    expect(material.getByRole('cell', { name: '> 30' })).toBeInTheDocument();
    const article = within(screen.getByRole('row', { name: /Bracket/ }));
    expect(article.getByRole('cell', { name: 'No usage in this period' })).toBeInTheDocument();
    expect(article.getByRole('cell', { name: 'Minimum stock reached' })).toBeInTheDocument();
  });
});
