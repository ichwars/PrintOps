import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Download, RefreshCw } from 'lucide-react';
import {
  GlobalWorkerOptions,
  getDocument,
  type PDFDocumentLoadingTask,
  type PDFDocumentProxy,
  type RenderTask,
} from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import { useTranslation } from 'react-i18next';

import {
  documentLayoutsApi,
  type LayoutPageFormat,
  type PreviewJob,
  type PreviewReport,
} from '../../../api/documentLayouts';
import { Button } from '../../ui/Button';

GlobalWorkerOptions.workerSrc = workerUrl;

export interface PdfPreviewSource {
  kind: 'sample' | 'document';
  id: string;
}

export interface PdfPreviewPaneProps {
  layoutId: number | null;
  confirmedLockVersion: number | null;
  source: PdfPreviewSource | null;
  pageFormat: LayoutPageFormat;
  className?: string;
}

interface PreviewResult {
  job: PreviewJob;
  report: PreviewReport;
  blob: Blob;
  etag: string | null;
}

type PreviewZoom = 'fit' | '0.75' | '1' | '1.25' | '1.5';

const POLL_INTERVAL_MS = 200;
const MAX_POLL_ATTEMPTS = 80;

function readBlob(blob: Blob): Promise<ArrayBuffer> {
  if (typeof blob.arrayBuffer === 'function') return blob.arrayBuffer();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error('BLOB_READ_FAILED'));
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) resolve(reader.result);
      else reject(new Error('BLOB_READ_FAILED'));
    };
    reader.readAsArrayBuffer(blob);
  });
}

function abortableDelay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const timer = window.setTimeout(resolve, milliseconds);
    signal.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timer);
        reject(new DOMException('Aborted', 'AbortError'));
      },
      { once: true },
    );
  });
}

async function loadPreview(
  layoutId: number,
  lockVersion: number,
  source: PdfPreviewSource,
  signal: AbortSignal,
): Promise<PreviewResult> {
  let job = await documentLayoutsApi.createPreview(
    {
      layout_id: layoutId,
      layout_lock_version: lockVersion,
      source_kind: source.kind,
      source_id: source.id,
    },
    signal,
  );
  let etag: string | null = null;
  let attempts = 0;

  while (job.status === 'queued' || job.status === 'running') {
    if (attempts >= MAX_POLL_ATTEMPTS) {
      throw new Error('PREVIEW_TIMEOUT');
    }
    attempts += 1;
    await abortableDelay(POLL_INTERVAL_MS, signal);
    const polled = await documentLayoutsApi.pollPreviewJob(job.public_id, { signal, etag });
    etag = polled.etag;
    if (polled.job) job = polled.job;
  }

  if (job.lock_version !== lockVersion) throw new Error('PREVIEW_STALE_VERSION');
  if (job.status !== 'ready') throw new Error(`PREVIEW_${job.status.toUpperCase()}`);

  const [download, report] = await Promise.all([
    documentLayoutsApi.downloadPreviewPdf(job.public_id, signal),
    documentLayoutsApi.getPreviewReport(job.public_id, signal),
  ]);
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError');

  return {
    job,
    report,
    blob: download.blob,
    etag: download.etag,
  };
}

interface PdfCanvasPageProps {
  document: PDFDocumentProxy;
  pageNumber: number;
  zoom: PreviewZoom;
  current: boolean;
  onVisible: (pageNumber: number) => void;
  onError: (error: Error) => void;
}

function PdfCanvasPage({
  document,
  pageNumber,
  zoom,
  current,
  onVisible,
  onError,
}: PdfCanvasPageProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === 'undefined');

  useEffect(() => {
    const element = wrapperRef.current;
    if (!element || typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting) {
          setVisible(true);
          onVisible(pageNumber);
        }
      },
      { rootMargin: '320px 0px' },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [onVisible, pageNumber]);

  useEffect(() => {
    if (!visible) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    let disposed = false;
    let renderTask: RenderTask | null = null;

    void document.getPage(pageNumber).then((page) => {
      if (disposed) return;
      const baseViewport = page.getViewport({ scale: 1 });
      const availableWidth = wrapperRef.current?.clientWidth ?? 0;
      const fitScale = availableWidth > 0
        ? Math.min(1.5, Math.max(0.25, (availableWidth - 24) / baseViewport.width))
        : 1;
      const scale = zoom === 'fit' ? fitScale : Number(zoom);
      const viewport = page.getViewport({ scale });
      const outputScale = Math.max(1, window.devicePixelRatio || 1);
      const renderViewport = page.getViewport({ scale: scale * outputScale });

      canvas.width = Math.floor(renderViewport.width);
      canvas.height = Math.floor(renderViewport.height);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;

      renderTask = page.render({ canvas, viewport: renderViewport });
      void renderTask.promise.catch((error: unknown) => {
        if (!disposed && !(error instanceof Error && error.name === 'RenderingCancelledException')) {
          onError(error instanceof Error ? error : new Error(String(error)));
        }
      });
    });

    return () => {
      disposed = true;
      renderTask?.cancel();
    };
  }, [document, onError, pageNumber, visible, zoom]);

  return (
    <div
      ref={wrapperRef}
      data-page-number={pageNumber}
      data-current={current || undefined}
      className="flex min-h-24 w-full justify-center scroll-mt-4"
    >
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={`PDF page ${pageNumber}`}
        tabIndex={0}
        className="max-w-full bg-white shadow-[0_14px_42px_rgba(0,0,0,0.35)] outline-none focus-visible:ring-2 focus-visible:ring-bambu-green"
      />
    </div>
  );
}

function pdfaLabel(report: PreviewReport | undefined): string {
  const status = report?.findings.validation_status;
  if (status === 'valid') return 'Valid';
  if (status === 'invalid') return 'Invalid';
  return 'Unchecked';
}

export function PdfPreviewPane({
  layoutId,
  confirmedLockVersion,
  source,
  pageFormat,
  className = '',
}: PdfPreviewPaneProps) {
  const { t } = useTranslation();
  const [zoom, setZoom] = useState<PreviewZoom>('fit');
  const [currentPage, setCurrentPage] = useState(1);
  const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | null>(null);
  const [pdfError, setPdfError] = useState<Error | null>(null);
  const paperRefs = useRef<Array<HTMLDivElement | null>>([]);
  const loadSequence = useRef(0);
  const enabled = Boolean(layoutId && confirmedLockVersion && source);

  const previewQuery = useQuery({
    queryKey: [
      'document-layout-preview',
      layoutId,
      confirmedLockVersion,
      source?.kind,
      source?.id,
    ],
    enabled,
    queryFn: ({ signal }) =>
      loadPreview(layoutId!, confirmedLockVersion!, source!, signal),
    placeholderData: keepPreviousData,
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const preview = previewQuery.data;
  const downloadUrl = useMemo(
    () => (preview?.blob ? URL.createObjectURL(preview.blob) : null),
    [preview?.blob],
  );

  useEffect(
    () => () => {
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    },
    [downloadUrl],
  );

  useEffect(() => {
    if (!preview?.blob) {
      setPdfDocument((current) => {
        void current?.cleanup();
        return null;
      });
      return;
    }

    const sequence = ++loadSequence.current;
    let disposed = false;
    let resolvedDocument: PDFDocumentProxy | null = null;
    let loadingTask: PDFDocumentLoadingTask | null = null;
    setPdfError(null);

    void readBlob(preview.blob)
      .then((buffer) => {
        if (disposed || sequence !== loadSequence.current) return null;
        loadingTask = getDocument({ data: new Uint8Array(buffer) });
        return loadingTask.promise;
      })
      .then((document) => {
        if (!document) return;
        resolvedDocument = document;
        if (disposed || sequence !== loadSequence.current) {
          void document.cleanup();
          return;
        }
        setPdfDocument((current) => {
          if (current && current !== document) void current.cleanup();
          return document;
        });
        setCurrentPage(1);
      })
      .catch((error: unknown) => {
        if (!disposed && sequence === loadSequence.current) {
          setPdfError(error instanceof Error ? error : new Error(String(error)));
        }
      });

    return () => {
      disposed = true;
      loadSequence.current += 1;
      void loadingTask?.destroy();
      void resolvedDocument?.cleanup();
    };
  }, [preview?.blob]);

  const numPages = pdfDocument?.numPages ?? 0;
  const ratio = pageFormat === 'Letter' ? '8.5 / 11' : '210 / 297';
  const queryError = previewQuery.error instanceof Error ? previewQuery.error : null;
  const visibleError = pdfError ?? queryError;

  const goToPage = (page: number) => {
    const next = Math.min(Math.max(page, 1), Math.max(numPages, 1));
    setCurrentPage(next);
    paperRefs.current[next - 1]?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  };

  const retry = () => {
    setPdfError(null);
    void previewQuery.refetch();
  };

  if (!enabled) {
    return (
      <section className={`rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary ${className}`}>
        <div className="p-5 text-sm text-bambu-gray">
          {confirmedLockVersion
            ? t('settings.documentLayout.preview.empty', 'Select or create a draft to generate a preview.')
            : t(
                'settings.documentLayout.preview.unchecked',
                'Save and check the current draft before generating a preview.',
              )}
        </div>
      </section>
    );
  }

  return (
    <section
      aria-label={t('settings.documentLayout.preview.title', 'PDF preview')}
      className={`flex min-h-[680px] min-w-0 flex-col overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-[#071b22] ${className}`}
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-bambu-dark-tertiary px-3 py-2">
        <div className="mr-auto min-w-0">
          <h2 className="truncate text-sm font-semibold text-white">
            {t('settings.documentLayout.preview.title', 'PDF preview')}
          </h2>
          <p className="text-xs text-bambu-gray">
            {t('settings.documentLayout.preview.paper', '{{format}} portrait', { format: pageFormat })}
          </p>
        </div>

        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={t('settings.documentLayout.actions.previousPage', 'Previous page')}
          disabled={currentPage <= 1 || numPages === 0}
          onClick={() => goToPage(currentPage - 1)}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="min-w-24 text-center text-xs text-bambu-gray">
          {t('settings.documentLayout.preview.page', 'Page {{page}} of {{pages}}', {
            page: numPages ? currentPage : 0,
            pages: numPages,
          })}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={t('settings.documentLayout.actions.nextPage', 'Next page')}
          disabled={currentPage >= numPages || numPages === 0}
          onClick={() => goToPage(currentPage + 1)}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>

        <label className="flex items-center gap-1 text-xs text-bambu-gray">
          {t('settings.documentLayout.preview.zoom', 'Zoom')}
          <select
            aria-label={t('settings.documentLayout.preview.zoom', 'Zoom')}
            value={zoom}
            onChange={(event) => setZoom(event.target.value as PreviewZoom)}
            className="min-h-9 rounded-md border border-bambu-dark-tertiary bg-bambu-dark px-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-bambu-green"
          >
            <option value="fit">{t('settings.documentLayout.preview.fit', 'Fit page')}</option>
            <option value="0.75">75%</option>
            <option value="1">100%</option>
            <option value="1.25">125%</option>
            <option value="1.5">150%</option>
          </select>
        </label>

        <span
          role="status"
          aria-label="PDF/A status"
          className={`rounded-full px-2 py-1 text-xs ${
            pdfaLabel(preview?.report) === 'Valid'
              ? 'bg-green-500/15 text-green-300'
              : pdfaLabel(preview?.report) === 'Invalid'
                ? 'bg-red-500/15 text-red-300'
                : 'bg-bambu-dark-tertiary text-bambu-gray'
          }`}
        >
          PDF/A: {pdfaLabel(preview?.report)}
        </span>

        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={t('settings.documentLayout.actions.refresh', 'Refresh')}
          onClick={retry}
        >
          <RefreshCw className={`h-4 w-4 ${previewQuery.isFetching ? 'animate-spin' : ''}`} />
        </Button>

        {downloadUrl && !visibleError ? (
          <a
            href={downloadUrl}
            download={`layout-preview-${layoutId}.pdf`}
            aria-label={t('settings.documentLayout.preview.download', 'Download preview PDF')}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2 text-xs text-bambu-green hover:bg-bambu-dark-tertiary focus:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green"
          >
            <Download className="h-4 w-4" />
            <span className="hidden xl:inline">
              {t('settings.documentLayout.actions.download', 'Download')}
            </span>
          </a>
        ) : null}
      </div>

      <div className="relative min-h-0 flex-1">
        {previewQuery.isFetching && preview ? (
          <div className="absolute inset-x-3 top-3 z-10 rounded-md bg-bambu-dark/90 px-3 py-2 text-xs text-bambu-gray shadow">
            {t(
              'settings.documentLayout.preview.updating',
              'Preview is being updated; the previous version remains visible.',
            )}
          </div>
        ) : null}

        {!preview && previewQuery.isPending ? (
          <div className="flex h-full min-h-[560px] items-center justify-center p-8 text-sm text-bambu-gray">
            {t('settings.documentLayout.preview.loading', 'Generating PDF preview...')}
          </div>
        ) : null}

        {visibleError ? (
          <div className="flex h-full min-h-[560px] flex-col items-center justify-center gap-3 p-8 text-center">
            <p className="text-sm text-red-300">
              {t('settings.documentLayout.preview.failed', 'The PDF preview could not be generated.')}
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              <Button type="button" variant="secondary" size="sm" onClick={retry}>
                {t('settings.documentLayout.actions.retry', 'Retry')}
              </Button>
              {downloadUrl ? (
                <a
                  href={downloadUrl}
                  download={`layout-preview-${layoutId}.pdf`}
                  aria-label={t('settings.documentLayout.preview.download', 'Download preview PDF')}
                  className="inline-flex min-h-9 items-center rounded-lg border border-bambu-dark-tertiary px-3 text-sm text-bambu-green"
                >
                  {t('settings.documentLayout.actions.download', 'Download')}
                </a>
              ) : null}
            </div>
          </div>
        ) : null}

        {!visibleError && preview && !pdfDocument ? (
          <div className="flex h-full min-h-[560px] items-center justify-center p-8 text-sm text-bambu-gray">
            {t('settings.documentLayout.preview.loading', 'Generating PDF preview...')}
          </div>
        ) : null}

        {!visibleError && pdfDocument ? (
          <div
            data-testid="pdf-paper-stack"
            style={{ '--paper-ratio': ratio } as CSSProperties}
            className="h-full max-h-[calc(100vh-13rem)] min-h-[580px] space-y-5 overflow-auto p-4 md:p-6"
            onKeyDown={(event) => {
              if (event.key === 'PageDown' || event.key === 'ArrowRight') {
                event.preventDefault();
                goToPage(currentPage + 1);
              }
              if (event.key === 'PageUp' || event.key === 'ArrowLeft') {
                event.preventDefault();
                goToPage(currentPage - 1);
              }
            }}
          >
            {Array.from({ length: pdfDocument.numPages }, (_, index) => {
              const pageNumber = index + 1;
              return (
                <div
                  key={pageNumber}
                  ref={(element) => {
                    paperRefs.current[index] = element;
                  }}
                  style={{ aspectRatio: ratio }}
                  className="mx-auto flex w-fit max-w-full items-start justify-center"
                >
                  <PdfCanvasPage
                    document={pdfDocument}
                    pageNumber={pageNumber}
                    zoom={zoom}
                    current={currentPage === pageNumber}
                    onVisible={setCurrentPage}
                    onError={setPdfError}
                  />
                </div>
              );
            })}
          </div>
        ) : null}
      </div>
    </section>
  );
}
