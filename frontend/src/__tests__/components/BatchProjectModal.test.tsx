import { expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BatchProjectModal } from '../../components/BatchProjectModal';
import { api } from '../../api/client';

const mockShowToast = vi.fn();

vi.mock('../../api/client', () => ({
  api: { getProjects: vi.fn(), addArchivesToProject: vi.fn() },
}));

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}));

it('reports the number of assignments returned by the server', async () => {
  vi.mocked(api.getProjects).mockResolvedValue([
    { id: 7, name: 'Voron', status: 'active', parent_id: null } as Awaited<ReturnType<typeof api.getProjects>>[number],
  ]);
  vi.mocked(api.addArchivesToProject).mockResolvedValue({ message: 'Added 1 archives to project', count: 1 });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <BatchProjectModal selectedIds={[1, 2, 3]} onClose={vi.fn()} />
    </QueryClientProvider>,
  );

  await user.click(await screen.findByText('Voron'));

  expect(api.addArchivesToProject).toHaveBeenCalledWith(7, [1, 2, 3]);
  await waitFor(() => expect(mockShowToast).toHaveBeenCalledWith('Added 1 archive to "Voron"'));
});
