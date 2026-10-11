import { expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { render } from '../utils';
import { SpreadsheetPreviewModal } from '../../components/SpreadsheetPreviewModal';

it('renders bounded server values as text and switches sheets without executing formulas or HTML', async () => {
  server.use(http.get('/api/v1/library/files/4/spreadsheet-preview', () => HttpResponse.json({
    sheets: [
      { name:'Parts', rows:[['<script>window.BAD=true</script>', '=SUM(1,2)']], totalRows:501, totalCols:1 },
      { name:'Suppliers', rows:[['Local workshop']], totalRows:1, totalCols:1 },
    ], truncated:true,
  })));
  render(<SpreadsheetPreviewModal libraryFileId={4} filename="parts.xlsx" fileType="xlsx" fileSize={20} onClose={() => {}} />);
  expect(await screen.findByText('<script>window.BAD=true</script>')).toBeInTheDocument();
  expect(document.querySelector('script')).toBeNull();
  expect(screen.getByText('Showing the first 1 of 501 rows')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', {name:'Suppliers'}));
  expect(screen.getByText('Local workshop')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', {name:'Fullscreen'}));
  expect(screen.getByRole('button', {name:'Exit fullscreen'})).toBeInTheDocument();
});
