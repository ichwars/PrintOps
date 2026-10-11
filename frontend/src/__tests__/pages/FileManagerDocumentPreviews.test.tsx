import { expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { FileManagerPage } from '../../pages/FileManagerPage';

vi.mock('../../components/ModelViewer', () => ({ ModelViewer: () => <div>STEP model canvas</div> }));

it.each(['png', 'pdf', 'csv', 'step'])('offers an in-app preview for a %s file', async (fileType) => {
  server.use(http.get('/api/v1/library/files', () => HttpResponse.json([{
    id: 55, filename: `instructions.${fileType}`, file_type: fileType, file_size: 40,
    folder_id: null, print_count: 0, created_at: '2026-01-01T00:00:00Z', tags: [],
  }])));
  render(<FileManagerPage />);
  await userEvent.click(await screen.findByTitle('List view'));
  await userEvent.click(await screen.findByTitle(fileType === 'step' ? '3D Preview' : 'Preview'));
  expect(await screen.findByRole('heading', { name: `instructions.${fileType}` })).toBeInTheDocument();
});

it('keeps combining limited to selected STL sources when STEP previews are available', async () => {
  server.use(http.get('/api/v1/library/files', () => HttpResponse.json([{
    id: 55, filename:'model.step', file_type:'step', file_size:40,
    folder_id:null, print_count:0, created_at:'2026-01-01T00:00:00Z', tags:[],
  }])));
  render(<FileManagerPage />);
  await userEvent.click(await screen.findByText('model.step'));
  expect(screen.queryByTitle('Combine the selected STLs into one 3MF so they can be sliced on a single plate')).not.toBeInTheDocument();
});
