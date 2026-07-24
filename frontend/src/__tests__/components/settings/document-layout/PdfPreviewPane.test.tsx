import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  createPreview: vi.fn(),
  pollPreviewJob: vi.fn(),
  getPreviewReport: vi.fn(),
  downloadPreviewPdf: vi.fn(),
  getDocument: vi.fn(),
  renderCancel: vi.fn(),
  documentDestroy: vi.fn(),
}));

vi.mock('../../../../api/documentLayouts', () => ({
  documentLayoutsApi: {
    createPreview: mocks.createPreview,
    pollPreviewJob: mocks.pollPreviewJob,
    getPreviewReport: mocks.getPreviewReport,
    downloadPreviewPdf: mocks.downloadPreviewPdf,
  },
}));

vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: mocks.getDocument,
}));

vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({
  default: '/assets/pdf.worker.test.mjs',
}));

import { PdfPreviewPane } from '../../../../components/settings/document-layout/PdfPreviewPane';

function job(lockVersion = 8, status: 'queued' | 'running' | 'ready' | 'failed' = 'ready') {
  return {
    public_id: 'job-1',
    status,
    layout_id: 17,
    lock_version: lockVersion,
    expires_at: '2026-07-23T11:00:00Z',
    result_sha256: status === 'ready' ? 'b'.repeat(64) : null,
  };
}

function renderPane(props: Partial<React.ComponentProps<typeof PdfPreviewPane>> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const result = render(
    <QueryClientProvider client={client}>
      <PdfPreviewPane
        layoutId={17}
        confirmedLockVersion={8}
        source={{ kind: 'sample', id: 'invoice-standard' }}
        pageFormat="A4"
        {...props}
      />
    </QueryClientProvider>,
  );
  return { ...result, client };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('devicePixelRatio', 2);
  vi.stubGlobal('IntersectionObserver', undefined);
  vi.stubGlobal('ResizeObserver', undefined);
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:preview-1'),
    revokeObjectURL: vi.fn(),
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as CanvasRenderingContext2D);

  mocks.createPreview.mockResolvedValue(job());
  mocks.pollPreviewJob.mockResolvedValue({ job: job(), etag: '"job-v1"', notModified: false });
  mocks.getPreviewReport.mockResolvedValue({
    status: 'ready',
    findings: { validation_status: 'valid', warnings: [] },
  });
  mocks.downloadPreviewPdf.mockResolvedValue({
    blob: new Blob(['pdf'], { type: 'application/pdf' }),
    etag: '"pdf-v1"',
  });
  mocks.getDocument.mockImplementation(() => ({
    promise: Promise.resolve({
      numPages: 2,
      getPage: vi.fn(async (pageNumber: number) => ({
        getViewport: ({ scale }: { scale: number }) => ({
          width: 595 * scale,
          height: 842 * scale,
        }),
        render: vi.fn(() => ({ promise: Promise.resolve(), cancel: mocks.renderCancel })),
        pageNumber,
      })),
      cleanup: mocks.documentDestroy,
    }),
    destroy: vi.fn(),
  }));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('PdfPreviewPane', () => {
  it('does not request a preview before a confirmed lock version exists', async () => {
    renderPane({ confirmedLockVersion: null });

    expect(screen.getByText('Save and check the current draft before generating a preview.')).toBeInTheDocument();
    expect(mocks.createPreview).not.toHaveBeenCalled();
  });

  it('creates a preview from the confirmed version and renders each PDF page to a canvas', async () => {
    renderPane();

    await waitFor(() =>
      expect(screen.getByRole('status', { name: 'PDF/A status' })).toHaveTextContent('Valid'),
    );
    await waitFor(() => expect(screen.getAllByRole('img', { name: /PDF page/ })).toHaveLength(2));
    expect(mocks.createPreview).toHaveBeenCalledWith(
      {
        layout_id: 17,
        layout_lock_version: 8,
        source_kind: 'sample',
        source_id: 'invoice-standard',
      },
      expect.any(AbortSignal),
    );
    expect(mocks.getDocument).toHaveBeenCalledWith({ data: expect.any(Uint8Array) });
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Download preview PDF' })).toHaveAttribute('href', 'blob:preview-1');
  });

  it('polls queued jobs and forwards ETags while retaining the previous preview during updates', async () => {
    mocks.createPreview.mockResolvedValueOnce(job(8, 'queued'));
    mocks.pollPreviewJob
      .mockResolvedValueOnce({ job: job(8, 'running'), etag: '"job-v1"', notModified: false })
      .mockResolvedValueOnce({ job: job(8, 'ready'), etag: '"job-v2"', notModified: false });

    renderPane();

    await waitFor(() => expect(mocks.pollPreviewJob).toHaveBeenCalledTimes(2));
    expect(mocks.pollPreviewJob.mock.calls[1][1]).toMatchObject({ etag: '"job-v1"' });
    expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument();
  });

  it('ignores an older blob completion after the confirmed version changes', async () => {
    let releaseOld: ((value: { blob: Blob; etag: string }) => void) | undefined;
    mocks.downloadPreviewPdf.mockImplementationOnce(
      () => new Promise((resolve) => {
        releaseOld = resolve;
      }),
    );
    const view = renderPane();

    await waitFor(() => expect(mocks.downloadPreviewPdf).toHaveBeenCalledTimes(1));
    mocks.createPreview.mockResolvedValueOnce({ ...job(9), public_id: 'job-2' });
    mocks.downloadPreviewPdf.mockResolvedValueOnce({
      blob: new Blob(['new-pdf'], { type: 'application/pdf' }),
      etag: '"pdf-v2"',
    });

    view.rerender(
      <QueryClientProvider client={view.client}>
        <PdfPreviewPane
          layoutId={17}
          confirmedLockVersion={9}
          source={{ kind: 'sample', id: 'invoice-standard' }}
          pageFormat="A4"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(mocks.getDocument).toHaveBeenCalledTimes(1));
    await act(async () => {
      releaseOld?.({ blob: new Blob(['old-pdf'], { type: 'application/pdf' }), etag: '"pdf-old"' });
      await Promise.resolve();
    });
    expect(mocks.getDocument).toHaveBeenCalledTimes(1);
  });

  it('revokes blob URLs and cancels PDF resources on replacement and unmount', async () => {
    const view = renderPane();
    await screen.findByText('Page 1 of 2');

    view.unmount();

    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview-1');
    expect(mocks.renderCancel).toHaveBeenCalled();
    expect(mocks.documentDestroy).toHaveBeenCalled();
  });

  it('supports page navigation, fixed zoom options, fit mode, and Letter proportions', async () => {
    renderPane({ pageFormat: 'Letter' });
    await screen.findByText('Page 1 of 2');

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Zoom'), { target: { value: '1.25' } });
    expect(screen.getByLabelText('Zoom')).toHaveValue('1.25');
    fireEvent.change(screen.getByLabelText('Zoom'), { target: { value: 'fit' } });
    expect(screen.getByTestId('pdf-paper-stack')).toHaveStyle({ '--paper-ratio': '8.5 / 11' });
  });

  it('keeps retry and authorized download available when PDF.js rendering fails', async () => {
    mocks.getDocument.mockImplementationOnce(() => ({
      promise: Promise.reject(new Error('broken pdf')),
      destroy: vi.fn(),
    }));

    renderPane();

    expect(await screen.findByText('The PDF preview could not be generated.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Download preview PDF' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(mocks.createPreview).toHaveBeenCalledTimes(2));
  });
});
