import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { expect, it, vi } from 'vitest';
import { PurgeArchivesModal } from '../../components/PurgeArchivesModal';
import { server } from '../mocks/server';
import { render } from '../utils';

it('only submits purge settings after the matching preview is shown', async () => {
  const submitted = vi.fn();
  server.use(
    http.get('/api/v1/archives/purge/preview', ({ request }) => {
      const days = new URL(request.url).searchParams.get('older_than_days');
      return HttpResponse.json({ count: days === '365' ? 1 : 4, total_bytes: 128, sample_filenames: [] });
    }),
    http.post('/api/v1/archives/purge', async ({ request }) => {
      submitted(await request.json());
      return HttpResponse.json({ deleted: 4, purge_stats: false });
    }),
  );
  const user = userEvent.setup();
  const onClose = vi.fn();
  render(<PurgeArchivesModal onClose={onClose} />);

  const oldPreview = await screen.findByRole('button', { name: 'Remove 1 archive(s)' });
  expect(oldPreview).toBeEnabled();
  fireEvent.change(screen.getByLabelText('Delete archives not printed in the last'), { target: { value: '90' } });
  expect(oldPreview).toBeDisabled();
  await user.click(await screen.findByRole('button', { name: 'Remove 4 archive(s)' }));

  await waitFor(() => expect(submitted).toHaveBeenCalledExactlyOnceWith({ older_than_days: 90, purge_stats: false }));
  expect(onClose).toHaveBeenCalledOnce();
});
