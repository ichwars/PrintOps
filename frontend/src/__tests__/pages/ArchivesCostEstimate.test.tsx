/**
 * A running print's cost is an estimate until completion re-prices it from
 * the spools that actually fed it (#3261). The card says so; a finished
 * print's cost is shown as final.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { render } from '../utils';
import { ArchivesPage } from '../../pages/ArchivesPage';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { setAuthToken } from '../../api/client';

const baseArchive = {
  printer_id: 1,
  printer_name: 'H2S',
  print_time_seconds: 3600,
  filament_used_grams: 4.17,
  thumbnail_path: null,
  notes: null,
  rating: null,
  project_id: null,
  project_name: null,
  project_color: null,
  print_count: 1,
  tags: '',
  has_f3d: false,
  started_at: '2026-10-07T10:00:00Z',
  created_at: '2026-10-07T10:00:00Z',
  updated_at: '2026-10-07T10:00:00Z',
};

const archives = [
  {
    ...baseArchive,
    id: 1,
    filename: 'running.gcode.3mf',
    print_name: 'Running',
    status: 'printing',
    completed_at: null,
    cost: 7.8,
  },
  {
    ...baseArchive,
    id: 2,
    filename: 'finished.gcode.3mf',
    print_name: 'Finished',
    status: 'completed',
    completed_at: '2026-10-07T11:00:00Z',
    cost: 10.94,
  },
];

describe('ArchivesPage cost estimate (#3261)', () => {
  beforeEach(() => {
    setAuthToken(null);
    server.use(
      http.get('/api/v1/archives/', () => HttpResponse.json(archives)),
      http.get('/api/v1/archives/stats', () =>
        HttpResponse.json({
          total_archives: 2,
          total_print_time_seconds: 7200,
          total_filament_grams: 8.34,
          prints_this_week: 2,
          prints_this_month: 2,
        })
      ),
      http.get('/api/v1/printers/', () => HttpResponse.json([{ id: 1, name: 'H2S' }])),
      http.get('/api/v1/projects/', () => HttpResponse.json([])),
      http.get('/api/v1/archives/tags', () => HttpResponse.json([]))
    );
  });

  it('marks a running print cost as an estimate and a finished one as final', async () => {
    render(<ArchivesPage />);

    await waitFor(() => {
      expect(screen.getAllByTestId('archive-cost')).toHaveLength(2);
    });
    const [running, finished] = screen.getAllByTestId('archive-cost');

    expect(running.textContent).toMatch(/^~.*7\.80$/);
    expect(running).toHaveAttribute('title', 'Estimate — the final cost is set when the print finishes');

    expect(finished.textContent).not.toContain('~');
    expect(finished.textContent).toMatch(/10\.94$/);
    expect(finished).not.toHaveAttribute('title');
  });
});
