import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { TablePagination } from '../../components/ui/TablePagination';
import { WarehousePage, WarehouseTableScroll } from '../../components/warehouse/WarehouseLayout';
import { setPageSelection, useTablePagination } from '../../hooks/useTablePagination';

function Example({ size, table = false, compact = false }: { size: number; table?: boolean; compact?: boolean }) {
  const pagination = useTablePagination(Array.from({ length: size }, (_, index) => index + 1), '', 15);
  return <>
    {table
      ? <div data-testid="table-rows"><table><tbody>{pagination.rows.map(row => <tr key={row}><td>{row}</td></tr>)}</tbody></table></div>
      : <output>{pagination.rows.join(', ')}</output>}
    <TablePagination {...pagination.footer} density={compact ? 'compact' : 'default'} />
  </>;
}

function PinnedExample() {
  const viewportRef = useRef<HTMLDivElement>(null);
  const pagination = useTablePagination(Array.from({ length: 32 }, (_, index) => index + 1));
  return (
    <WarehousePage footer={<TablePagination {...pagination.footer} viewportRef={viewportRef} />}>
      <WarehouseTableScroll label="Stock" viewportRef={viewportRef}>
        <table><tbody>{pagination.rows.map(row => <tr key={row}><td>{row}</td></tr>)}</tbody></table>
      </WarehouseTableScroll>
    </WarehousePage>
  );
}

describe('TablePagination', () => {
  it('moves to the last page, clamps after deletion and resets on page-size change', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Example size={40} />);
    expect(screen.getByText('Page 1 of 3')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Last page' }));
    expect(screen.getByText('Showing 31 to 40 of 40')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();

    rerender(<Example size={26} />);
    expect(screen.getByText('Page 2 of 2')).toBeVisible();
    await user.click(screen.getByRole('combobox', { name: 'Rows' }));
    await user.click(screen.getByRole('option', { name: '30' }));
    expect(screen.getByText('Page 1 of 1')).toBeVisible();
    expect(screen.getByText('Showing 1 to 26 of 26')).toBeVisible();
  });

  it('keeps the controls visible while fetching and reports a zero range for empty tables', () => {
    const change = vi.fn();
    render(<TablePagination total={0} offset={15} pageSize={15} busy onOffsetChange={change} onPageSizeChange={change} />);
    expect(screen.getByText('Showing 0 to 0 of 0')).toBeVisible();
    for (const button of screen.getAllByRole('button')) expect(button).toBeDisabled();
    expect(screen.getByRole('combobox')).toBeDisabled();
  });

  it('keeps the page size and navigation visible in a compact table with a single page', () => {
    const { rerender } = render(<Example size={1} table compact />);
    const viewport = screen.getByTestId('table-rows');
    expect(screen.getByText('Showing 1 to 1 of 1')).toBeVisible();
    expect(screen.getByText('Page 1 of 1')).toBeVisible();
    expect(screen.getByRole('combobox')).toBeEnabled();
    expect(screen.getAllByRole('button')).toHaveLength(4);
    for (const button of screen.getAllByRole('button')) expect(button).toBeDisabled();
    expect(viewport).toHaveAttribute('data-paginated-table-viewport');

    rerender(<Example size={16} table compact />);
    expect(screen.getByRole('combobox')).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeEnabled();
    expect(viewport).toHaveAttribute('data-paginated-table-viewport');
  });

  it('starts at the first row of the new page without changing the horizontal position', async () => {
    const user = userEvent.setup();
    render(<Example size={40} table />);
    const rows = screen.getByTestId('table-rows');
    expect(rows).toHaveAttribute('data-paginated-table-viewport');
    rows.scrollTop = 120;
    rows.scrollLeft = 60;

    await user.click(screen.getByRole('button', { name: 'Next page' }));

    expect(screen.getAllByRole('row')[0]).toHaveTextContent('16');
    expect(rows.scrollTop).toBe(0);
    expect(rows.scrollLeft).toBe(60);
  });

  it('resets the linked table when paging from outside the scroll area', async () => {
    const user = userEvent.setup();
    render(<PinnedExample />);
    const viewport = screen.getByRole('region', { name: 'Stock' });
    const next = screen.getByRole('button', { name: 'Next page' });
    expect(viewport).toHaveAttribute('data-paginated-table-viewport');
    expect(next.closest('[data-warehouse-pagination-dock]')).not.toBeNull();
    expect(viewport.closest('[data-warehouse-page-content]')).not.toContainElement(next);
    viewport.scrollTop = 120;
    viewport.scrollLeft = 60;

    await user.click(next);

    expect(screen.getAllByRole('row')[0]).toHaveTextContent('16');
    expect(viewport.scrollTop).toBe(0);
    expect(viewport.scrollLeft).toBe(60);
  });

  it('selects just the visible records and preserves previous selections', () => {
    expect(setPageSelection(new Set([1, 3]), [4, 5], true)).toEqual(new Set([1, 3, 4, 5]));
    expect(setPageSelection(new Set([1, 3, 4, 5]), [4, 5], false)).toEqual(new Set([1, 3]));
  });
});
