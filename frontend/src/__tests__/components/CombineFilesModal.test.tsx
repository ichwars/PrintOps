import { expect, it, vi } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { CombineFilesModal } from '../../components/CombineFilesModal';
import type { LibraryFileListItem } from '../../api/client';

const files = [{ id: 1, filename: 'bracket.stl', file_type: 'stl' }] as LibraryFileListItem[];

it('submits an integer copy count and hands the returned source to slicing', async () => {
  let body: unknown;
  const onCombined = vi.fn();
  server.use(http.post('/api/v1/library/files/combine', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ id: 9, filename: 'bracket x4.3mf', file_type: '3mf' });
  }));
  render(<CombineFilesModal files={files} folderId={7} canSlice onClose={() => {}} onCombined={onCombined} />);
  fireEvent.change(screen.getByLabelText('Copies of bracket.stl'), { target: { value: '4' } });
  await userEvent.click(screen.getByRole('button', { name: 'Combine' }));
  await waitFor(() => expect(body).toEqual({ items: [{ file_id: 1, copies: 4 }], filename: 'bracket x4', folder_id: 7 }));
  await waitFor(() => expect(onCombined).toHaveBeenCalledWith({ id: 9, filename: 'bracket x4.3mf', file_type: '3mf' }, true));
});

it('rejects fractional and excessive copy counts before submission', () => {
  render(<CombineFilesModal files={files} folderId={null} canSlice={false} onClose={() => {}} onCombined={() => {}} />);
  fireEvent.change(screen.getByLabelText('Copies of bracket.stl'), { target: { value: '1.5' } });
  expect(screen.getByRole('button', { name: 'Combine' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Copies of bracket.stl'), { target: { value: '101' } });
  expect(screen.getByText('At most 100 objects per plate')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Combine' })).toBeDisabled();
});
