import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { HMSErrorModal, filterKnownHMSErrors, isSevereHMSError } from '../../components/HMSErrorModal';
import type { HMSError } from '../../api/client';
import { classifyPrinterStatus } from '../../pages/printers/printer-status';

const fault = (overrides: Partial<HMSError> = {}): HMSError => ({
  code: '0x10008', attr: 0x03000200, module: 3, severity: 1,
  full_code: '0300020000010008', description: 'Manufacturer says the nozzle cannot reach its set temperature.',
  actions: [], job_id: 'job-7', ...overrides,
});

describe('manufacturer HMS faults', () => {
  it('shows manufacturer words, real severity and full code while preserving action ownership', async () => {
    let captured: unknown;
    server.use(http.post('*/api/v1/printers/7/hms/execute-action', async ({ request }) => {
      captured = await request.json();
      return HttpResponse.json({ success: true });
    }));
    const user = userEvent.setup();
    render(<HMSErrorModal printerName="Fixture" printerId={7} errors={[fault({ actions: ['CHECK_ASSISTANT'] })]} onClose={vi.fn()} hasPermission={() => true} />);
    expect(await screen.findByText('Manufacturer says the nozzle cannot reach its set temperature.')).toBeInTheDocument();
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(screen.getByText('[0300-0200-0001-0008]')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /assistant/i }));
    await waitFor(() => expect(captured).toEqual({ action: 'CHECK_ASSISTANT', print_error: '0300020000010008', job_id: 'job-7' }));
  });

  it('counts errors and actionable notices but leaves idle notices, empty text and invalid levels out', () => {
    const error = fault();
    const notice = fault({ severity: 3, description: 'The top cover is open.' });
    const actionable = fault({ severity: 3, description: null, actions: ['OK_BUTTON'] });
    const unknown = fault({ description: null });
    const invalid = fault({ severity: 0, actions: ['OK_BUTTON'] });
    expect(filterKnownHMSErrors([error, notice, actionable, unknown, invalid])).toEqual([error, actionable]);
    const prompt = fault({ severity: 3, full_code: '1880C003' });
    expect(filterKnownHMSErrors([prompt])).toEqual([prompt]);
    expect(filterKnownHMSErrors([fault({ code: "0x4000", full_code: "0300020000014000", description: undefined })])).toEqual([]);
    expect(isSevereHMSError(error)).toBe(true);
    expect(isSevereHMSError(invalid)).toBe(false);
    expect(classifyPrinterStatus({ connected: true, state: "RUNNING", hms_errors: [notice] })).toBe("printing");
    expect(classifyPrinterStatus({ connected: true, state: "RUNNING", hms_errors: [error] })).toBe("error");
    expect(classifyPrinterStatus({ connected: true, state: "FAILED", hms_errors: [unknown] })).toBe("finished");
  });

  it('makes uncounted notices and unknown codes inspectable without inventing text', async () => {
    const user = userEvent.setup();
    render(<HMSErrorModal printerName="Fixture" printerId={7} errors={[fault({ severity: 3, description: 'The top cover is open.' }), fault({ full_code:'FFFFFFFF00010008', description:null })]} onClose={vi.fn()} hasPermission={() => true} />);
    await user.click(await screen.findByText('Also reported, not counted (2)'));
    expect(screen.getByText('The top cover is open.')).toBeVisible();
    expect(screen.getByText('[FFFF-FFFF-0001-0008]')).toBeVisible();
  });
});
