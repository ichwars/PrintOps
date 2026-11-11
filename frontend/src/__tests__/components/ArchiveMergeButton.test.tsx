import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ArchiveMergeButton } from '../../components/ArchiveMergeButton';
import { server } from '../mocks/server';

const permissions = vi.hoisted(() => ({ delete: true }));
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 5 },
    hasPermission: (permission: string) => permission !== 'archives:delete_all' || permissions.delete,
  }),
}));

const group = (id: number, skipped: 'busy' | null) => ({
  survivor: { id, print_name: 'Fixture', filename: 'fixture.3mf', run_count: 1 },
  merged: [{ id: id + 1, print_name: null, filename: 'fixture-copy.3mf', run_count: 2 }],
  skipped,
});

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ArchiveMergeButton /></QueryClientProvider>);
}

describe('ArchiveMergeButton', () => {
  beforeEach(() => { permissions.delete = true; });

  it('submits the exact selected members and reports a stale group', async () => {
    let submitted: unknown;
    server.use(
      http.get('/api/v1/archives/merge-count', () => HttpResponse.json({ groups: 2 })),
      http.get('/api/v1/archives/merge-preview', () => HttpResponse.json({ groups: [group(4, null), group(7, 'busy')] })),
      http.post('/api/v1/archives/merge', async ({ request }) => {
        submitted = await request.json();
        return HttpResponse.json({ merged: [], skipped: [{ survivor_id: 4, reason: 'invalid_group' }] });
      }),
    );
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole('button', { name: 'Merge duplicates' }));
    const dialog = within(screen.getByRole('dialog'));
    expect(await dialog.findByRole('checkbox', { name: 'Keep Fixture (#7)' })).toBeDisabled();
    expect(dialog.getByRole('button', { name: 'Merge groups (0)' })).toBeDisabled();
    await user.click(dialog.getByRole('checkbox', { name: 'Keep Fixture (#4)' }));
    await user.click(dialog.getByRole('button', { name: 'Merge groups (1)' }));
    expect(await dialog.findByText(/the group changed/i)).toBeInTheDocument();
    expect(submitted).toEqual({ groups: [{ survivor_id: 4, merged_ids: [5] }] });
  });

  it('hides the action without archive deletion permission', () => {
    permissions.delete = false;
    mount();
    expect(screen.queryByRole('button', { name: 'Merge duplicates' })).toBeNull();
  });
});
