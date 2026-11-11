import { describe, expect, it } from 'vitest';
import { fireEvent, screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { PrintLogTable } from '../../components/PrintLogTable';
import { server } from '../mocks/server';
import { render } from '../utils';

describe('PrintLogTable', () => {
  it('shows each plate estimate beside its actual print duration and filament', async () => {
    server.use(http.get('/api/v1/archives/42/runs', () => HttpResponse.json({
      total: 1,
      items: [{
        id: 7,
        plate_id: 2,
        status: 'completed',
        duration_seconds: 480,
        estimate_seconds: 600,
        filament_used_grams: 5.4,
        estimate_grams: 6.7,
        cost: null,
      }],
    })));

    render(<PrintLogTable archiveId={42} />);
    expect(await screen.findByRole('columnheader', { name: 'Plate' })).toBeInTheDocument();
    const table = screen.getByRole('table');
    expect(within(table).getByRole('cell', { name: '2' })).toBeInTheDocument();
    expect(within(table).getByText('Estimated: 10m')).toBeInTheDocument();
    expect(within(table).getByText('Estimated: 6.7 g')).toBeInTheDocument();
  });

  it('opens the photo from the selected run', async () => {
    server.use(http.get('/api/v1/archives/42/runs', () => HttpResponse.json({
      total: 2,
      items: [
        { id: 9, status: 'completed', print_name: 'Newer', photos: ['newer.jpg'] },
        { id: 7, status: 'completed', print_name: 'Earlier', photos: ['earlier.jpg'] },
      ],
    })));

    render(<PrintLogTable archiveId={42} />);
    const buttons = await screen.findAllByRole('button', { name: 'View 1 photo' });
    fireEvent.click(buttons[1]);
    expect(await screen.findByAltText('Photo 1')).toHaveAttribute(
      'src', expect.stringContaining('/api/v1/archives/42/photos/earlier.jpg?run_id=7'),
    );
  });
});
