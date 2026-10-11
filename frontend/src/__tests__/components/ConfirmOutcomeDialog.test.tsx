import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { ConfirmOutcomeDialog } from '../../components/ConfirmOutcomeDialog';

const current = {
  id: 7, filename: 'Production.3mf', print_name: 'Production', status: 'completed',
  created_by_id: 1, quantity: 4, plate_id: 2, project_id: null,
  outcome_run_id: 41, outcome_expected_parts: 4, outcome_batch_id: null,
  good_quantity: null, reject_quantity: null, failure_reason: null,
};

async function enterPartial() {
  await screen.findByRole('spinbutton', { name: 'Good parts' });
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Good parts' }), { target: { value: '3' } });
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Rejected parts' }), { target: { value: '1' } });
}

describe('production outcome inspection', () => {
  beforeEach(() => {
    server.use(http.get('/api/v1/archives/7', () => HttpResponse.json(current)));
  });

  it('sends explicit run and part quantities through the normal authenticated API', async () => {
    let submitted: unknown;
    const close = vi.fn();
    server.use(http.post('/api/v1/archives/7/outcome', async ({ request }) => {
      submitted = await request.json();
      return HttpResponse.json({ run_id: 41, good_quantity: 3, reject_quantity: 1, user_verdict: 'mixed' });
    }));
    render(<ConfirmOutcomeDialog archiveId={7} onClose={close} />);
    await enterPartial();
    await userEvent.click(screen.getByRole('button', { name: 'Save inspection' }));
    await waitFor(() => expect(close).toHaveBeenCalledOnce());
    expect(submitted).toEqual({ run_id: 41, good_quantity: 3, reject_quantity: 1 });
  });

  it('requires nonnegative whole parts adding up to the intended quantity', async () => {
    render(<ConfirmOutcomeDialog archiveId={7} onClose={vi.fn()} />);
    await enterPartial();
    const save = screen.getByRole('button', { name: 'Save inspection' });
    expect(save).toBeEnabled();
    for (const invalid of ['2', '3.5', '-1', '']) {
      fireEvent.change(screen.getByRole('spinbutton', { name: 'Good parts' }), { target: { value: invalid } });
      expect(save).toBeDisabled();
    }
  });

  it('keeps the inspection open when a stale current run is rejected', async () => {
    const close = vi.fn();
    server.use(http.post('/api/v1/archives/7/outcome', () => HttpResponse.json({ detail: 'This print has changed' }, { status: 409 })));
    render(<ConfirmOutcomeDialog archiveId={7} onClose={close} />);
    await enterPartial();
    await userEvent.click(screen.getByRole('button', { name: 'Save inspection' }));
    expect(await screen.findByText('This print has changed')).toBeInTheDocument();
    expect(close).not.toHaveBeenCalled();
  });

  it('dispatches one replacement run from the existing batch without changing its target', async () => {
    const calls: string[] = [];
    let dispatched: unknown;
    const close = vi.fn();
    server.use(
      http.get('/api/v1/archives/7', () => HttpResponse.json({ ...current, outcome_batch_id: 9 })),
      http.post('/api/v1/archives/7/outcome', () => {
        calls.push('inspection');
        return HttpResponse.json({ run_id: 41, good_quantity: 3, reject_quantity: 1, user_verdict: 'mixed' });
      }),
      http.get('/api/v1/queue/batches/9', () => HttpResponse.json({ plates: [{ plate_id: null, quantity_target: 6 }] })),
      http.post('/api/v1/queue/batches/9/dispatch', async ({ request }) => {
        calls.push('dispatch'); dispatched = await request.json();
        return HttpResponse.json({ dispatched: 1, remaining: 0 });
      }),
    );
    render(<ConfirmOutcomeDialog archiveId={7} runId={41} onClose={close} />);
    await enterPartial();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Queue a replacement after saving' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save inspection' }));
    await waitFor(() => expect(close).toHaveBeenCalledOnce());
    expect(calls).toEqual(['inspection', 'dispatch']);
    expect(dispatched).toEqual({ limit: 1 });
  });

  it('reports a failed replacement separately after the inspection is already saved', async () => {
    let confirmations = 0;
    const close = vi.fn();
    server.use(
      http.get('/api/v1/archives/7', () => HttpResponse.json({ ...current, outcome_batch_id: 9 })),
      http.post('/api/v1/archives/7/outcome', () => { confirmations++; return HttpResponse.json({ run_id: 41 }); }),
      http.get('/api/v1/queue/batches/9', () => HttpResponse.json({ plates: [{ plate_id: 2 }] })),
      http.post('/api/v1/queue/batches/9/dispatch', () => HttpResponse.json({ detail: 'Printer unavailable' }, { status: 409 })),
    );
    render(<ConfirmOutcomeDialog archiveId={7} onClose={close} />);
    await enterPartial();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Queue a replacement after saving' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save inspection' }));
    expect(await screen.findByText(/Inspection saved\. The replacement could not be queued/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save inspection' })).toBeDisabled();
    expect(close).not.toHaveBeenCalled();
    expect(confirmations).toBe(1);
  });

  it('uses the selected historical run and its own quantity while a reprint is active', async () => {
    let submitted: unknown;
    const close = vi.fn();
    server.use(
      http.get('/api/v1/archives/7', () => HttpResponse.json({ ...current, status: 'printing', quantity: 12 })),
      http.get('/api/v1/archives/7/runs', () => HttpResponse.json({ total: 1, items: [{ id: 30, status: 'completed', quantity: 2 }] })),
      http.post('/api/v1/archives/7/runs/30/outcome', async ({ request }) => { submitted = await request.json(); return HttpResponse.json({ run_id: 30 }); }),
    );
    render(<ConfirmOutcomeDialog archiveId={7} runId={30} onClose={close} />);
    expect(await screen.findByText('Intended quantity: 2 parts')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'All rejected' }));
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Save inspection' }));
    await waitFor(() => expect(close).toHaveBeenCalledOnce());
    expect(submitted).toEqual({ run_id: 30, good_quantity: 0, reject_quantity: 2 });
  });
});
