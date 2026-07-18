import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { SmallPartCombobox } from '../../components/warehouse/SmallPartCombobox';
import { server } from '../mocks/server';


describe('SmallPartCombobox', () => {
  it('searches by keyboard and selects the highlighted article', async () => {
    server.use(
      http.get('/api/v1/small-parts/search', ({ request }) => {
        expect(new URL(request.url).searchParams.get('q')).toBe('m3');
        return HttpResponse.json([
          {
            id: 7,
            sku: 'M3-INSERT',
            name: 'M3 Gewindeeinsatz',
            unit_code: 'C62',
            unit_cost: '0.080000',
            available: '42.000000',
          },
        ]);
      }),
    );
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SmallPartCombobox value={null} onChange={onChange} locale="de-DE" />);

    await user.type(screen.getByRole('combobox'), 'm3');
    await waitFor(() => expect(screen.getByRole('option', { name: /M3-INSERT/ })).toBeInTheDocument());
    await user.keyboard('{ArrowDown}{Enter}');

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }));
  });

  it('does not accept arbitrary free text', async () => {
    server.use(http.get('/api/v1/small-parts/search', () => HttpResponse.json([])));
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SmallPartCombobox value={null} onChange={onChange} locale="de-DE" />);

    await user.type(screen.getByRole('combobox'), 'unbekannt{Enter}');

    expect(onChange).not.toHaveBeenCalled();
  });
});
