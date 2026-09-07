import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { AiDetectionBadge } from '../../components/AiDetectionBadge';
import { server } from '../mocks/server';
import { render } from '../utils';

function respondWith(entry: Record<string, unknown>) {
  server.use(
    http.get('/api/v1/obico/printer-status', () =>
      HttpResponse.json({
        enabled: true,
        monitored_printers: [1],
        per_printer: { '1': entry },
        last_error: null,
      }),
    ),
  );
}

describe('AiDetectionBadge issue #141', () => {
  it('shows Not checking and omits a fabricated score after a failed poll', async () => {
    respondWith({
      class: 'error',
      frame_count: 0,
      score: 0,
      error: 'Obico ML API rejected the token (401).',
    });
    render(<AiDetectionBadge printerId={1} printerName="X1 Carbon" />);

    const badge = await screen.findByRole('button', { name: 'Not checking' });
    expect(badge).toHaveAttribute(
      'title',
      'AI Failure Detection is not checking this print: Obico ML API rejected the token (401). - click for details',
    );
    expect(screen.queryByText('Safe')).not.toBeInTheDocument();

    await userEvent.click(badge);
    expect(await screen.findByText('AI Failure Detection - X1 Carbon')).toBeInTheDocument();
    expect(screen.getByText('Obico ML API rejected the token (401).')).toBeInTheDocument();
    expect(screen.queryByText('0.000')).not.toBeInTheDocument();
    expect(screen.queryByText('Frames analyzed')).not.toBeInTheDocument();
  });

  it('shows Starting before the first inference and never falls back to Safe', async () => {
    respondWith({ class: 'unknown', frame_count: 0, score: 0, error: null });
    render(<AiDetectionBadge printerId={1} printerName="X1 Carbon" />);

    expect(await screen.findByRole('button', { name: 'Starting' })).toBeInTheDocument();
    expect(screen.queryByText('Safe')).not.toBeInTheDocument();
  });

  it('shows Safe only for an actual inference verdict', async () => {
    respondWith({ class: 'safe', frame_count: 12, score: 0, error: null });
    render(<AiDetectionBadge printerId={1} printerName="X1 Carbon" />);

    expect(await screen.findByRole('button', { name: 'Safe' })).toHaveAttribute(
      'title',
      'AI Failure Detection: Safe (score 0.000) - click for details',
    );
  });
});
