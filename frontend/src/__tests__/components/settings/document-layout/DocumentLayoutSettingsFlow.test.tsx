import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { layoutDetail, layoutSummary } from './layoutFixtures';

const mocks = vi.hoisted(() => ({
  getBusinessProfileOptions: vi.fn(),
  getCatalog: vi.fn(),
  getSamples: vi.fn(),
  listLayouts: vi.fn(),
  getLayout: vi.fn(),
  getReadiness: vi.fn(),
  getPreviewDocuments: vi.fn(),
  getAudit: vi.fn(),
  patchLayout: vi.fn(),
  createLayout: vi.fn(),
  cloneLayout: vi.fn(),
  publishLayout: vi.fn(),
  withdrawLayout: vi.fn(),
  currentLock: 3,
}));

vi.mock('../../../../api/client', () => ({ api: { getBusinessProfileOptions: mocks.getBusinessProfileOptions } }));
vi.mock('../../../../api/documentLayouts', () => {
  class LayoutVersionConflictError extends Error {
    status = 409;
  }
  return {
    LayoutVersionConflictError,
    documentLayoutsApi: {
      getCatalog: mocks.getCatalog, getSamples: mocks.getSamples, listLayouts: mocks.listLayouts,
      getLayout: mocks.getLayout, getReadiness: mocks.getReadiness,
      getPreviewDocuments: mocks.getPreviewDocuments, getAudit: mocks.getAudit,
      patchLayout: mocks.patchLayout, createLayout: mocks.createLayout, cloneLayout: mocks.cloneLayout,
      publishLayout: mocks.publishLayout, withdrawLayout: mocks.withdrawLayout,
    },
  };
});
vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({ loading: false, hasPermission: () => true }),
}));
vi.mock('../../../../components/settings/document-layout/PdfPreviewPane', () => ({
  PdfPreviewPane: ({ confirmedLockVersion }: { confirmedLockVersion: number }) => <div data-testid="flow-preview">Confirmed {confirmedLockVersion}</div>,
}));

import { LayoutVersionConflictError } from '../../../../api/documentLayouts';
import { DocumentLayoutSettings } from '../../../../components/settings/document-layout/DocumentLayoutSettings';

function renderFlow() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}><DocumentLayoutSettings /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.currentLock = 3;
  mocks.getBusinessProfileOptions.mockResolvedValue([{ id: 2, name: 'Main GmbH', country_code: 'DE', default_currency: 'EUR', timezone: 'Europe/Berlin', default_locale: 'en', billing_mode: 'commercial', is_default: true, is_active: true }]);
  mocks.getCatalog.mockResolvedValue({ templates: [{ key: 'classic', version: '1', description: '' }], page_formats_mm: { A4: [210, 297], Letter: [216, 279] }, languages: ['en'], document_types: ['invoice'] });
  mocks.getSamples.mockResolvedValue([{ id: 'invoice-standard', label: 'Standard invoice', document_type: 'invoice', language: 'en' }]);
  mocks.listLayouts.mockImplementation(async () => [layoutSummary(mocks.currentLock)]);
  mocks.getLayout.mockImplementation(async () => layoutDetail(mocks.currentLock));
  mocks.getReadiness.mockResolvedValue({ ready: true, findings: [], renderer_version: '1', validator_version: '1' });
  mocks.getPreviewDocuments.mockResolvedValue([]);
  mocks.getAudit.mockResolvedValue([]);
  mocks.patchLayout.mockImplementation(async () => {
    mocks.currentLock += 1;
    return layoutSummary(mocks.currentLock);
  });
  mocks.cloneLayout.mockResolvedValue({ ...layoutSummary(1), id: 18, version: 2 });
  mocks.publishLayout.mockResolvedValue({ ...layoutSummary(3), status: 'active' });
  mocks.withdrawLayout.mockResolvedValue({ ...layoutSummary(3), status: 'withdrawn' });
});

describe('DocumentLayoutSettings flow', () => {
  it('autosaves and advances the preview only after confirmation', async () => {
    renderFlow();
    expect(await screen.findByTestId('flow-preview')).toHaveTextContent('Confirmed 3');

    fireEvent.change(screen.getByRole('spinbutton', { name: 'Top margin' }), { target: { value: '23' } });
    expect(screen.getByTestId('flow-preview')).toHaveTextContent('Confirmed 3');


    await waitFor(() => expect(mocks.patchLayout).toHaveBeenCalledTimes(1), { timeout: 1000 });
    expect(mocks.patchLayout).toHaveBeenCalledWith(17, expect.objectContaining({
      expected_lock_version: 3,
      edit_session_id: expect.any(String),
      page: expect.objectContaining({ margin_top_mm: 23 }),
    }), expect.any(AbortSignal));
    await waitFor(() => expect(screen.getByTestId('flow-preview')).toHaveTextContent('Confirmed 4'));
  });

  it('stops on a concurrent edit and reloads without overwriting it', async () => {
    mocks.patchLayout.mockRejectedValueOnce(new LayoutVersionConflictError('conflict'));
    renderFlow();
    await screen.findByTestId('flow-preview');

    fireEvent.change(screen.getByRole('spinbutton', { name: 'Top margin' }), { target: { value: '24' } });
    expect(await screen.findByText('This draft was changed in another session.', {}, { timeout: 1200 })).toBeInTheDocument();
    expect(mocks.patchLayout).toHaveBeenCalledTimes(1);

    const callsBeforeReload = mocks.getLayout.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: /latest version/i }));
    await waitFor(() => expect(mocks.getLayout.mock.calls.length).toBeGreaterThan(callsBeforeReload));
    expect(screen.queryByText('This draft was changed in another session.')).not.toBeInTheDocument();
  });

  it('requires an auditable reason before cloning or publishing', async () => {
    renderFlow();
    await screen.findByTestId('flow-preview');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Publish' })).toBeEnabled());

    fireEvent.click(screen.getByRole('button', { name: /Clone/ }));
    fireEvent.change(screen.getByLabelText('Reason for the new draft'), { target: { value: 'New corporate design' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(mocks.cloneLayout).toHaveBeenCalledWith({ source_layout_id: 17, reason: 'New corporate design' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(screen.getByText('Enter a reason with at least three characters.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Publication reason'), { target: { value: 'Approved by accounting' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(mocks.publishLayout).toHaveBeenCalledWith(17, {
      expected_lock_version: 3,
      reason: 'Approved by accounting',
      effective_from: null,
    }));
  });
});
