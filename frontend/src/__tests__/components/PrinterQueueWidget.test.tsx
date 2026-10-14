/**
 * Tests for the PrinterQueueWidget component.
 *
 * The compact authorized candidate snapshot respects scheduling order and
 * known holds without promising dispatch. Returns null when empty.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen, waitFor, act } from '@testing-library/react';
import { render } from '../utils';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { PrinterQueueWidget } from '../../components/PrinterQueueWidget';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';

const mockQueueItems = [
  {
    id: 1,
    printer_id: 1,
    archive_id: 1,
    position: 1,
    status: 'pending',
    archive_name: 'First Print',
    printer_name: 'X1 Carbon',
    print_time_seconds: 3600,
    scheduled_time: null,
  },
  {
    id: 2,
    printer_id: 1,
    archive_id: 2,
    position: 2,
    status: 'pending',
    archive_name: 'Second Print',
    printer_name: 'X1 Carbon',
    print_time_seconds: 7200,
    scheduled_time: null,
  },
];

describe('PrinterQueueWidget', () => {
  beforeEach(() => {
    server.use(
      http.get('/api/v1/queue/', ({ request }) => {
        const url = new URL(request.url);
        const printerId = url.searchParams.get('printer_id');
        if (printerId === '1') {
          return HttpResponse.json(mockQueueItems);
        }
        return HttpResponse.json([]);
      })
    );
  });

  describe('rendering', () => {
    it('labels the result as a candidate awaiting checks', async () => {
      render(<PrinterQueueWidget printerId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Queued candidate')).toBeInTheDocument();
      });
    });

    it('shows first pending item name', async () => {
      render(<PrinterQueueWidget printerId={1} />);

      await waitFor(() => {
        expect(screen.getByText('First Print')).toBeInTheDocument();
      });
    });

    it('shows additional items badge when multiple pending', async () => {
      render(<PrinterQueueWidget printerId={1} />);

      await waitFor(() => {
        // Shows "+1" badge since there are 2 items
        expect(screen.getByText('+1')).toBeInTheDocument();
      });
    });

    it('does not promise an immediate start for unscheduled items', async () => {
      render(<PrinterQueueWidget printerId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Awaiting printer checks')).toBeInTheDocument();
      });
    });
  });

  describe('empty state', () => {
    it('renders nothing when no pending items', async () => {
      const { container } = render(<PrinterQueueWidget printerId={999} />);

      // Wait for query to resolve
      await waitFor(() => {
        // Widget returns null when empty, so container should have no visible widget
        expect(container.querySelector('a[href="/queue"]')).not.toBeInTheDocument();
      });
    });
  });

  describe('single item', () => {
    it('does not show badge when only one item', async () => {
      server.use(
        http.get('/api/v1/queue/', () => {
          return HttpResponse.json([mockQueueItems[0]]);
        })
      );

      render(<PrinterQueueWidget printerId={1} />);

      await waitFor(() => {
        expect(screen.getByText('First Print')).toBeInTheDocument();
      });

      // Should not have a "+N" badge
      expect(screen.queryByText(/^\+\d+$/)).not.toBeInTheDocument();
    });
  });

  describe('link behavior', () => {
    it('links to queue page', async () => {
      render(<PrinterQueueWidget printerId={1} />);

      await waitFor(() => {
        const link = screen.getByRole('link');
        expect(link).toHaveAttribute('href', '/queue');
      });
    });
  });
});

function RefreshPreview() {
  const client = useQueryClient();
  const [count, setCount] = useState(0);
  return <><button onClick={() => { void client.invalidateQueries({ queryKey: ['queue'] }); setCount(count + 1); }}>Refresh {count}</button><PrinterQueueWidget printerId={1} /></>;
}

describe('queue candidate semantics', () => {
  function queue(items: object[], shortestFirst = false) {
    server.use(
      http.get('/api/v1/queue/', () => HttpResponse.json(items.map(item => ({ ...item, scheduler_shortest_first: shortestFirst })))),
      http.get('/api/v1/settings/', () => new HttpResponse(null, { status: 403 })),
    );
  }

  it('uses id as a deterministic tie break without mutating query order', async () => {
    queue([{ ...mockQueueItems[1], position: 1 }, mockQueueItems[0]]);
    render(<PrinterQueueWidget printerId={1} />);
    expect(await screen.findByText('First Print')).toBeInTheDocument();
  });

  it('skips known manual and future holds when previewing an automatic candidate', async () => {
    queue([{ ...mockQueueItems[0], manual_start: true }, { ...mockQueueItems[1], scheduled_time: '2099-01-01T10:00:00Z' }, { ...mockQueueItems[0], id: 3, position: 3, archive_name: 'Automatic candidate' }]);
    render(<PrinterQueueWidget printerId={1} />);
    expect(await screen.findByText('Automatic candidate')).toBeInTheDocument();
    expect(screen.getByText('Awaiting printer checks')).toBeInTheDocument();
  });

  it.each([
    [{ manual_start: true }, 'Manual start required'],
    [{ waiting_reason: 'Waiting on Enclosure Door' }, 'Blocked at last check'],
    [{ dispatching: true }, 'Dispatch in progress'],
  ])('shows the known hold instead of claiming next execution: %j', async (extra, label) => {
    queue([{ ...mockQueueItems[0], ...extra }]);
    render(<PrinterQueueWidget printerId={1} />);
    expect(await screen.findByText(label)).toBeInTheDocument();
    expect(screen.queryByText('Next in queue')).not.toBeInTheDocument();
  });

  it('shows a scheduled job with its actual time, not an immediate start', async () => {
    queue([{ ...mockQueueItems[0], scheduled_time: '2099-01-01T10:00:00Z' }]);
    render(<PrinterQueueWidget printerId={1} />);
    expect(await screen.findByText('Scheduled')).toBeInTheDocument();
    expect(document.querySelector('time')).toHaveAttribute('datetime', '2099-01-01T10:00:00Z');
  });

  it('uses persisted SJF duration rather than enriched archive time', async () => {
    queue([{ ...mockQueueItems[0], print_time_seconds: 10, scheduler_print_time_seconds: 400 }, { ...mockQueueItems[1], print_time_seconds: 999, scheduler_print_time_seconds: 20 }], true);
    render(<PrinterQueueWidget printerId={1} />);
    expect(await screen.findByText('Second Print')).toBeInTheDocument();
  });

  it('preserves SJF starvation priority and null-last duration', async () => {
    queue([{ ...mockQueueItems[0], scheduler_print_time_seconds: null }, { ...mockQueueItems[1], been_jumped: true, scheduler_print_time_seconds: 500 }], true);
    render(<PrinterQueueWidget printerId={1} />);
    expect(await screen.findByText('Second Print')).toBeInTheDocument();
  });

  it.each([
    [null, 20, 'Second Print'],
    [20, 20, 'First Print'],
  ])('orders SJF null-last and ties deterministically (%s, %s)', async (first, second, expected) => {
    queue([{ ...mockQueueItems[1], position: 1, scheduler_print_time_seconds: second }, { ...mockQueueItems[0], scheduler_print_time_seconds: first }], true);
    render(<PrinterQueueWidget printerId={1} />);
    expect(await screen.findByText(expected)).toBeInTheDocument();
  });

  it('keeps a last-reported blocked row from being called ready', async () => {
    queue([{ ...mockQueueItems[0], waiting_reason: 'Busy' }, mockQueueItems[1]]);
    render(<PrinterQueueWidget printerId={1} />);
    expect(await screen.findByText('Second Print')).toBeInTheDocument();
    expect(screen.getByText('Awaiting printer checks')).toBeInTheDocument();
  });

  it('refreshes the job and dispatch state on queue invalidation', async () => {
    queue([mockQueueItems[0]]);
    render(<RefreshPreview />);
    await screen.findByText('First Print');
    queue([{ ...mockQueueItems[1], dispatching: true }]);
    await act(async () => { screen.getByRole('button', { name: 'Refresh 0' }).click(); });
    expect(await screen.findByText('Second Print')).toBeInTheDocument();
    expect(screen.getByText('Dispatch in progress')).toBeInTheDocument();
    expect(screen.queryByText('First Print')).not.toBeInTheDocument();
  });
});


describe('preview scheduling refresh', () => {
  it('expires a future hold even when the unchanged queue response is cached', async () => {
    const start = Date.now();
    const clock = vi.spyOn(Date, 'now').mockReturnValue(start);
    server.use(http.get('/api/v1/queue/', () => HttpResponse.json([
      { ...mockQueueItems[0], scheduled_time: new Date(start + 10000).toISOString() },
    ])));
    const view = render(<PrinterQueueWidget printerId={1} />);
    try {
      await screen.findByText('Scheduled');
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
      // Remount so the component timer belongs to this controlled clock.
      view.unmount();
      render(<PrinterQueueWidget printerId={1} />);
      await screen.findByText('Scheduled');
      clock.mockReturnValue(start + 31000);
      await act(async () => { vi.advanceTimersByTime(30000); });
      expect(screen.getByText('Awaiting printer checks')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
      clock.mockRestore();
    }
  });
});
