import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { render } from '../utils';
import { ApiError } from '../../api/client';
import { KProfileReadFailure } from '../../components/KProfileReadFailure';


describe('KProfileReadFailure', () => {
  it('offers a retry after no answer without claiming the printer has no profiles', () => {
    const retry = vi.fn();
    render(<KProfileReadFailure error={new ApiError('Timeout', 504)} onRefresh={retry} />);
    expect(screen.getByRole('heading', { name: "Couldn't read K-Profiles" })).toBeInTheDocument();
    expect(screen.getByText(/Its profiles may still be there/)).toBeInTheDocument();
    expect(screen.queryByText(/Create.*first.*profile/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Refresh/i }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it('shows other concrete read errors', () => {
    render(<KProfileReadFailure error={new Error('Transport unavailable')} onRefresh={vi.fn()} />);
    expect(screen.getByText('Transport unavailable')).toBeInTheDocument();
  });
});
