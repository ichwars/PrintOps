import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '../../api/client';
import { smallPartsApi } from '../../api/smallParts';
import { SmallPartEditor } from '../../components/warehouse/SmallPartEditor';

vi.mock('../../api/client', () => ({
  api: {
    getLocations: vi.fn(),
    getSettings: vi.fn(),
  },
}));

vi.mock('../../api/smallParts', () => ({
  smallPartsApi: {
    categories: { list: vi.fn() },
    units: { list: vi.fn() },
    create: vi.fn(),
    update: vi.fn(),
  },
}));

describe('SmallPartEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getLocations).mockResolvedValue([]);
    vi.mocked(api.getSettings).mockResolvedValue({ small_parts_default_minimum_stock: '12.5' } as never);
    vi.mocked(smallPartsApi.categories.list).mockResolvedValue([]);
    vi.mocked(smallPartsApi.units.list).mockResolvedValue([]);
  });

  it('uses the configured default minimum stock for new parts', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SmallPartEditor part={null} onClose={vi.fn()} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByLabelText('Meldebestand')).toHaveValue(12.5));
  });
});
