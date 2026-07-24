import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
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
  canManage: true,
  canReadCommercial: true,
}));

vi.mock('../../../../api/client', () => ({
  api: { getBusinessProfileOptions: mocks.getBusinessProfileOptions },
}));

vi.mock('../../../../api/documentLayouts', () => {
  class LayoutVersionConflictError extends Error {}
  return {
    LayoutVersionConflictError,
    documentLayoutsApi: {
      getCatalog: mocks.getCatalog,
      getSamples: mocks.getSamples,
      listLayouts: mocks.listLayouts,
      getLayout: mocks.getLayout,
      getReadiness: mocks.getReadiness,
      getPreviewDocuments: mocks.getPreviewDocuments,
      getAudit: mocks.getAudit,
      patchLayout: mocks.patchLayout,
      createLayout: mocks.createLayout,
      cloneLayout: mocks.cloneLayout,
      publishLayout: mocks.publishLayout,
      withdrawLayout: mocks.withdrawLayout,
    },
  };
});

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    loading: false,
    hasPermission: (permission: string) => {
      if (permission === 'document_layouts:manage') return mocks.canManage;
      if (permission === 'commercial_documents:read') return mocks.canReadCommercial;
      return true;
    },
  }),
}));

vi.mock('../../../../components/settings/document-layout/PdfPreviewPane', () => ({
  PdfPreviewPane: ({ layoutId, confirmedLockVersion, source }: { layoutId: number; confirmedLockVersion: number; source: { kind: string; id: string } | null }) => (
    <div data-testid="pdf-preview">Preview {layoutId}:{confirmedLockVersion}:{source?.kind}:{source?.id}</div>
  ),
}));

import { DocumentLayoutSettings } from '../../../../components/settings/document-layout/DocumentLayoutSettings';

function renderSettings() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}><DocumentLayoutSettings /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.canManage = true;
  mocks.canReadCommercial = true;
  mocks.getBusinessProfileOptions.mockResolvedValue([{
    id: 2, name: 'Main GmbH', country_code: 'DE', default_currency: 'EUR', timezone: 'Europe/Berlin',
    default_locale: 'en', billing_mode: 'commercial', is_default: true, is_active: true,
  }]);
  mocks.getCatalog.mockResolvedValue({
    templates: [{ key: 'classic', version: '1', description: 'Classic' }],
    page_formats_mm: { A4: [210, 297], Letter: [216, 279] },
    languages: ['de', 'en'],
    document_types: ['invoice'],
  });
  mocks.getSamples.mockResolvedValue([{ key: 'invoice-standard', title: 'Standard invoice', document_type: 'invoice', language: 'en' }]);
  mocks.listLayouts.mockResolvedValue([layoutSummary()]);
  mocks.getLayout.mockResolvedValue(layoutDetail());
  mocks.getReadiness.mockResolvedValue({ ready: true, findings: [], renderer_version: '1', validator_version: '1' });
  mocks.getPreviewDocuments.mockResolvedValue([]);
  mocks.getAudit.mockResolvedValue([]);
  mocks.patchLayout.mockResolvedValue(layoutSummary(4));
  mocks.cloneLayout.mockResolvedValue({ ...layoutSummary(1), id: 18, version: 2 });
  mocks.publishLayout.mockResolvedValue({ ...layoutSummary(3), status: 'active' });
  mocks.withdrawLayout.mockResolvedValue({ ...layoutSummary(3), status: 'withdrawn' });
});

describe('DocumentLayoutSettings', () => {
  it('loads the complete workspace with real preview first and compact controls second', async () => {
    const { container } = renderSettings();

    expect(await screen.findByTestId('pdf-preview')).toHaveTextContent('Preview 17:3:sample:invoice-standard');
    expect(screen.queryByRole('heading', { name: 'Format & Preview' })).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Business profile' })).toHaveTextContent('Main GmbH');
    expect(screen.getByRole('combobox', { name: 'Document type' })).toHaveTextContent('Invoice');
    expect(screen.getByRole('combobox', { name: 'Preview source' })).toHaveTextContent('Standard invoice');
    expect(screen.getByRole('button', { name: /Basic layout/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Assets and fonts/i })).toBeInTheDocument();

    const preview = screen.getByTestId('pdf-preview');
    const controls = container.querySelector('aside > div') as HTMLElement;
    expect(preview.compareDocumentPosition(controls) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector('main')).toHaveClass('min-[900px]:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]');
  });

  it('enforces read-only access without hiding previews or findings', async () => {
    mocks.canManage = false;
    renderSettings();

    expect(await screen.findByTestId('pdf-preview')).toBeInTheDocument();
    expect(screen.getByText('Read-only access')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Template' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();
  });

  it('never requests commercial documents when that read permission is missing', async () => {
    mocks.canReadCommercial = false;
    renderSettings();

    await screen.findByTestId('pdf-preview');
    expect(mocks.getPreviewDocuments).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Preview source' })).toHaveTextContent('Standard invoice'));
  });

  it('uses the backend key and title fields for sample preview sources', async () => {
    mocks.getSamples.mockResolvedValue([{
      key: 'invoice-en-standard',
      title: 'Invoice En',
      document_type: 'invoice',
      language: 'en',
    }]);

    renderSettings();

    expect(await screen.findByTestId('pdf-preview')).toHaveTextContent('Preview 17:3:sample:invoice-en-standard');
    expect(screen.getByRole('combobox', { name: 'Preview source' })).toHaveTextContent('Invoice En');
    expect(screen.getByRole('combobox', { name: 'Preview source' })).not.toHaveTextContent('undefined');
  });
});
