import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ThumbnailHoverPreview } from '../../components/ThumbnailHoverPreview';

afterEach(() => vi.restoreAllMocks());

describe('ThumbnailHoverPreview', () => {
  it('shows the enlarged thumbnail outside the clipping parent and hides it on scroll', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList);
    const { container } = render(<div style={{ overflow: 'hidden' }}>
      <ThumbnailHoverPreview src="/thumb.png"><span>Thumbnail</span></ThumbnailHoverPreview>
    </div>);
    fireEvent.mouseEnter(screen.getByText('Thumbnail'));
    const enlarged = screen.getByTestId('thumbnail-hover-preview');
    expect(enlarged).toHaveAttribute('src', '/thumb.png');
    expect(container.contains(enlarged)).toBe(false);
    fireEvent.scroll(window);
    expect(screen.queryByTestId('thumbnail-hover-preview')).not.toBeInTheDocument();
  });

  it('does not show a hover preview on a touch-only device', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: false } as MediaQueryList);
    render(<ThumbnailHoverPreview src="/thumb.png"><span>Thumbnail</span></ThumbnailHoverPreview>);
    fireEvent.mouseEnter(screen.getByText('Thumbnail'));
    expect(screen.queryByTestId('thumbnail-hover-preview')).not.toBeInTheDocument();
  });
});
