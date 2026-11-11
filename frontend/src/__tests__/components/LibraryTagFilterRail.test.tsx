import { fireEvent, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { LibraryTag } from '../../api/client';
import { LibraryTagFilterRail } from '../../components/LibraryTagFilterRail';
import { render } from '../utils';

const tags = Array.from({ length: 160 }, (_, index) => ({
  id: index + 1,
  name: `Tag ${String(index + 1).padStart(3, '0')}`,
} as LibraryTag));

afterEach(() => vi.restoreAllMocks());

describe('LibraryTagFilterRail', () => {
  it('clamps a large catalog while leaving selected tags visible', () => {
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(1200);
    const toggle = vi.fn();
    const clear = vi.fn();
    render(<LibraryTagFilterRail tags={tags} selectedIds={[158, 1]} onToggle={toggle} onClear={clear} />);
    const selected = screen.getAllByRole('button', { pressed: true });
    expect(selected.map(node => node.textContent)).toEqual(['Tag 158', 'Tag 001']);
    const showAll = screen.getByRole('button', { name: 'Show all (158)' });
    const grid = document.getElementById(showAll.getAttribute('aria-controls')!);
    expect(grid?.contains(selected[0])).toBe(false);
    expect(grid).toHaveStyle({ maxHeight: '52px' });
    fireEvent.click(showAll);
    expect(screen.getByRole('button', { name: 'Show fewer' })).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(selected[0]);
    expect(toggle).toHaveBeenCalledWith(158);
    fireEvent.click(screen.getByRole('button', { name: 'Clear all' }));
    expect(clear).toHaveBeenCalledTimes(1);
  });

  it('searches the unselected catalog and preserves active filters', () => {
    render(<LibraryTagFilterRail tags={tags} selectedIds={[158]} onToggle={vi.fn()} onClear={vi.fn()} />);
    const search = screen.getByRole('searchbox', { name: 'Search tags' });
    fireEvent.change(search, { target: { value: 'tag 015' } });
    expect(screen.getAllByRole('button', { pressed: false }).map(node => node.textContent)).toEqual(['Tag 015']);
    expect(screen.getByRole('button', { name: 'Tag 158', pressed: true })).toBeInTheDocument();
    fireEvent.change(search, { target: { value: 'missing tag' } });
    expect(screen.getByRole('status')).toHaveTextContent('No tags match');
  });
});
