/**
 * Tests for the BugReportBubble component.
 */

import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '../utils';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { BugReportBubble } from '../../components/BugReportBubble';

function setupBugReportStatus(issueUrl = 'https://github.com/ichwars/PrintOps/issues/new/choose') {
  server.use(
    http.get('*/bug-report/status', () =>
      HttpResponse.json({
        repository: 'ichwars/PrintOps',
        relay_configured: false,
        issue_url: issueUrl,
      })
    )
  );
}

/** Mocks the printer list and per-printer diagnostic the form scans on open. */
function setupDiagnosticEndpoints(
  printers: { id: number; name: string }[],
  results: Record<number, 'ok' | 'problems'>
) {
  server.use(
    http.get('*/printers/', () =>
      HttpResponse.json(
        printers.map((p) => ({
          id: p.id,
          name: p.name,
          serial_number: '00M09A000000000',
          ip_address: `192.168.1.${20 + p.id}`,
          is_active: true,
          model: 'X1C',
          nozzle_count: 1,
        }))
      )
    ),
    http.get('*/printers/:id/diagnostic', ({ params }) => {
      const overall = results[Number(params.id)] ?? 'ok';
      return HttpResponse.json({
        printer_id: Number(params.id),
        ip_address: `192.168.1.${20 + Number(params.id)}`,
        overall,
        checks: [{ id: 'port_mqtt', status: overall === 'problems' ? 'fail' : 'pass', params: {} }],
      });
    })
  );
}

describe('BugReportBubble', () => {
  it('renders the floating bug button', () => {
    render(<BugReportBubble />);

    const button = screen.getByRole('button');
    expect(button).toBeInTheDocument();
  });

  it('keeps the floating bug button subdued until hover or focus', () => {
    render(<BugReportBubble />);

    const button = screen.getByRole('button');
    expect(button.className).toContain('bg-red-500/55');
    expect(button.className).toContain('hover:bg-red-500');
    expect(button.className).toContain('focus-visible:bg-red-500');
  });

  it('opens a manual GitHub issue panel when bubble is clicked', async () => {
    const user = userEvent.setup();
    setupBugReportStatus();

    render(<BugReportBubble />);
    await user.click(screen.getByRole('button'));

    expect(await screen.findByText('Report through GitHub')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start Debug Logging' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open github issue/i })).toHaveAttribute(
      'href',
      'https://github.com/ichwars/PrintOps/issues/new/choose'
    );
  });

  it('uses the configured issue form URL from the backend status endpoint', async () => {
    const user = userEvent.setup();
    setupBugReportStatus('https://github.com/ichwars/PrintOps/issues/new?template=bug_report.yml');

    render(<BugReportBubble />);
    await user.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /open github issue/i })).toHaveAttribute(
        'href',
        'https://github.com/ichwars/PrintOps/issues/new?template=bug_report.yml'
      );
    });
  });

  it('closes panel when X button is clicked', async () => {
    const user = userEvent.setup();

    render(<BugReportBubble />);

    await user.click(screen.getByRole('button'));
    expect(await screen.findByText('Report through GitHub')).toBeInTheDocument();

    const buttons = screen.getAllByRole('button');
    const closeButton = buttons.find((b) => b.querySelector('.lucide-x'));
    if (closeButton) await user.click(closeButton);

    await waitFor(() => {
      expect(screen.queryByText('Report through GitHub')).not.toBeInTheDocument();
    });
  });

  it('lists affected printers as collapsed rows, not stacked checklists', async () => {
    const user = userEvent.setup();
    setupDiagnosticEndpoints(
      [
        { id: 1, name: 'Printer Alpha' },
        { id: 2, name: 'Printer Beta' },
        { id: 3, name: 'Printer Gamma' },
      ],
      { 1: 'problems', 2: 'problems', 3: 'ok' }
    );

    render(<BugReportBubble />);
    await user.click(screen.getByRole('button'));

    expect(
      await screen.findByText('2 of 3 printers have connection issues')
    ).toBeInTheDocument();
    expect(screen.getByText('Printer Alpha')).toBeInTheDocument();
    expect(screen.getByText('Printer Beta')).toBeInTheDocument();
    expect(screen.queryByText('Printer Gamma')).not.toBeInTheDocument();
    expect(screen.queryByText(/Found problems that explain/)).not.toBeInTheDocument();

    await user.click(screen.getByText('Printer Alpha'));
    expect(await screen.findByText(/Found problems that explain/)).toBeInTheDocument();
  });

  it('auto-expands the checklist when only one printer has problems', async () => {
    const user = userEvent.setup();
    setupDiagnosticEndpoints([{ id: 1, name: 'Solo Printer' }], { 1: 'problems' });

    render(<BugReportBubble />);
    await user.click(screen.getByRole('button'));

    expect(
      await screen.findByText('1 of 1 printers have connection issues')
    ).toBeInTheDocument();
    expect(await screen.findByText(/Found problems that explain/)).toBeInTheDocument();
  });

  it('shows the log-health panel when the scan finds known issues', async () => {
    const user = userEvent.setup();
    setupDiagnosticEndpoints([{ id: 1, name: 'Solo Printer' }], { 1: 'ok' });
    server.use(
      http.get('*/system/health', () =>
        HttpResponse.json({
          findings: [
            {
              signature_id: 'ftp-auth-rejected',
              severity: 'error',
              category: 'layer8',
              wiki_anchor: 'wrong-access-code',
              count: 3,
              first_seen: '2026-05-22 09:00:00,000',
              last_seen: '2026-05-22 10:00:00,000',
              sample: 'FTP connection permission error to [IP]',
            },
          ],
          scanned_entries: 500,
          log_available: true,
          summary: { total: 1, layer8: 1, environment: 0, bug: 0 },
        })
      )
    );

    render(<BugReportBubble />);
    await user.click(screen.getByRole('button'));

    expect(await screen.findByText('Known issues found in your logs')).toBeInTheDocument();
    expect(screen.getByText('Printer rejected the access code')).toBeInTheDocument();
  });
});
