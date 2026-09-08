/**
 * Server-side slicing is not offered for STEP/STP files (#92).
 *
 * The slicer sidecar cannot import CAD formats, so the library must not show
 * a Slice / Run-with-pipeline action for them — and must say why instead.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import { render } from '../utils';
import { FileManagerPage } from '../../pages/FileManagerPage';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import userEvent from '@testing-library/user-event';
import { setAuthToken } from '../../api/client';

const baseFile = {
  file_size: 524288,
  folder_id: null,
  thumbnail_path: null,
  print_name: null,
  print_time_seconds: null,
  print_count: 0,
  duplicate_count: 0,
  created_at: '2024-01-02T00:00:00Z',
};

const mockFiles = [
  { ...baseFile, id: 1, filename: 'bracket.stl', file_path: '/library/bracket.stl', file_type: 'stl' },
  { ...baseFile, id: 2, filename: 'flange.step', file_path: '/library/flange.step', file_type: 'step' },
  { ...baseFile, id: 3, filename: 'housing.stp', file_path: '/library/housing.stp', file_type: 'stp' },
];

describe('FileManagerPage - STEP files and server-side slicing', () => {
  beforeEach(() => {
    // localStorage is a vi.fn() mock (see __tests__/setup.ts); list view
    // exposes the per-row action icons without opening a menu.
    vi.mocked(localStorage.getItem).mockImplementation((key: string) =>
      key === 'library-view-mode' ? 'list' : null,
    );

    server.use(
      http.get('/api/v1/library/folders', () => HttpResponse.json([])),
      http.get('/api/v1/library/files', () => HttpResponse.json(mockFiles)),
      http.get('/api/v1/library/stats', () =>
        HttpResponse.json({
          total_files: 3,
          total_folders: 0,
          total_size_bytes: 1572864,
          disk_free_bytes: 10737418240,
          disk_total_bytes: 107374182400,
        }),
      ),
      http.get('/api/v1/settings/', () =>
        HttpResponse.json({
          check_updates: false,
          check_printer_firmware: false,
          library_disk_warning_gb: 5,
          use_slicer_api: true,
        }),
      ),
      http.get('/api/v1/projects/', () => HttpResponse.json([])),
      http.get('/api/v1/archives/', () => HttpResponse.json([])),
    );
  });

  const rowFor = (filename: string) => {
    const cell = screen.getByText(filename);
    const row = cell.closest('tr') ?? cell.closest('div[class*="grid"]');
    expect(row).not.toBeNull();
    return row as HTMLElement;
  };

  it('offers the slice action for STL', async () => {
    render(<FileManagerPage />);

    await waitFor(() => expect(screen.getByText('bracket.stl')).toBeInTheDocument());
    expect(within(rowFor('bracket.stl')).getByTitle('Slice')).toBeInTheDocument();
  });

  it('offers no slice or pipeline action for STEP/STP', async () => {
    render(<FileManagerPage />);

    await waitFor(() => expect(screen.getByText('flange.step')).toBeInTheDocument());

    for (const filename of ['flange.step', 'housing.stp']) {
      const row = within(rowFor(filename));
      expect(row.queryByTitle('Slice')).toBeNull();
      expect(row.queryByTitle('Run with pipeline')).toBeNull();
    }
  });

  it('explains why server-side slicing is unavailable', async () => {
    render(<FileManagerPage />);

    await waitFor(() => expect(screen.getByText('flange.step')).toBeInTheDocument());

    const hint = within(rowFor('flange.step')).getByLabelText(/STEP\/STP files cannot be sliced/i);
    expect(hint).toBeInTheDocument();
  });

  it('preserves the same file-type gates in portalled card menus', async () => {
    vi.mocked(localStorage.getItem).mockReturnValue(null);
    const user = userEvent.setup();
    render(<FileManagerPage />);
    await user.click(await screen.findByRole('button', { name: 'Actions: bracket.stl' }));
    expect(screen.getByRole('menuitem', { name: 'Slice', exact: true })).toBeEnabled();
    expect(screen.getByRole('menuitem', { name: 'Run with pipeline' })).toBeEnabled();
    expect(screen.queryByRole('menuitem', { name: 'Print', exact: true })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');
    for (const filename of ['flange.step', 'housing.stp']) {
      await user.click(screen.getByRole('button', { name: `Actions: ${filename}` }));
      expect(screen.queryByRole('menuitem', { name: 'Slice', exact: true })).not.toBeInTheDocument();
      expect(screen.queryByRole('menuitem', { name: 'Run with pipeline' })).not.toBeInTheDocument();
      expect(screen.getByTitle(/STEP\/STP files cannot be sliced/i)).toBeInTheDocument();
      await user.keyboard('{Escape}');
    }
  });

  it('retains permission and ownership restrictions in the card menu', async () => {
    vi.mocked(localStorage.getItem).mockReturnValue(null);
    setAuthToken('test-only-token');
    server.use(
      http.get('*/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
      http.get('/api/v1/auth/me', () => HttpResponse.json({
        id: 1, username: 'reader', is_admin: false, is_active: true, groups: [],
        permissions: ['library:read', 'library:update_own'],
      })),
      http.get('/api/v1/library/files', () => HttpResponse.json(mockFiles.map(file => ({ ...file, created_by_id: 2 })))),
    );
    try {
      const user = userEvent.setup();
      render(<FileManagerPage />);
      await user.click(await screen.findByRole('button', { name: 'Actions: bracket.stl' }));
      await waitFor(() => expect(screen.getByRole('menuitem', { name: 'Slice', exact: true })).toBeDisabled());
      for (const name of ['Run with pipeline', 'Rename', 'Generate Thumbnail', 'Delete']) {
        expect(screen.getByRole('menuitem', { name, exact: true })).toBeDisabled();
      }
      expect(screen.getByRole('menuitem', { name: 'Download' })).toBeEnabled();
      expect(screen.getByRole('menuitem', { name: '3D Preview' })).toBeEnabled();
    } finally {
      setAuthToken(null);
    }
  });
});
