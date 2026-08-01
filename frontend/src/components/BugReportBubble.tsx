import { useState, useRef, useCallback, useEffect } from 'react';
import { Bug, X, Loader2, CheckCircle, AlertCircle, AlertTriangle, Trash2, Upload, Circle, CheckCircle2, Stethoscope } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { api, ApiError, bugReportApi, type PrinterDiagnosticResult } from '../api/client';
import { DiagnosticChecklist } from './ConnectionDiagnostic';
import { SystemHealthPanel } from './SystemHealthPanel';
import { Collapsible } from './Collapsible';
import { FileInput, TextArea, TextField } from './ui';

type ViewState = 'form' | 'logging' | 'stopping' | 'submitting' | 'success' | 'error';

type DiagnosticEntry = { name: string; result: PrinterDiagnosticResult };

const MAX_DIMENSION = 1920;
const JPEG_QUALITY = 0.7;
const MAX_LOG_SECONDS = 300;
const MANUAL_ISSUE_LOG_LIMIT = 8000;
const FALLBACK_REPOSITORY = 'ichwars/PrintOps';

function compressImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      let { width, height } = img;
      if (width > MAX_DIMENSION || height > MAX_DIMENSION) {
        const scale = MAX_DIMENSION / Math.max(width, height);
        width = Math.round(width * scale);
        height = Math.round(height * scale);
      }
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) { reject(new Error('No canvas context')); return; }
      ctx.drawImage(img, 0, 0, width, height);
      const dataUrl = canvas.toDataURL('image/jpeg', JPEG_QUALITY);
      resolve(dataUrl.replace(/^data:[^;]+;base64,/, ''));
    };
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function truncateForManualIssue(value: string): string {
  if (value.length <= MANUAL_ISSUE_LOG_LIMIT) return value;
  return `${value.slice(0, MANUAL_ISSUE_LOG_LIMIT)}\n\n[Logs gekürzt: ${value.length - MANUAL_ISSUE_LOG_LIMIT} weitere Zeichen nicht im Link enthalten]`;
}

function buildManualIssueUrl(
  repository: string,
  description: string,
  errorMessage?: string,
  debugLogs?: string,
  hasScreenshot?: boolean,
): string {
  const url = new URL(`https://github.com/${repository}/issues/new`);
  url.searchParams.set('title', '[Bug]: ');
  url.searchParams.set('body', [
    '### Beschreibung',
    description.trim() || '_Bitte Fehlerbeschreibung ergänzen._',
    '',
    '### Hinweis',
    'Die automatische Übermittlung aus PrintOps konnte nicht abgeschlossen werden.',
    errorMessage ? `Fehler: ${errorMessage}` : '',
    hasScreenshot ? '' : '',
    hasScreenshot
      ? '### Screenshot'
      : '',
    hasScreenshot
      ? 'Im PrintOps-Formular wurde ein Screenshot ausgewählt. Bitte im GitHub-Issue manuell anhängen, falls relevant.'
      : '',
    debugLogs ? '' : '',
    debugLogs ? '### Gesammelte Logs' : '',
    debugLogs ? '```text' : '',
    debugLogs ? truncateForManualIssue(debugLogs) : '',
    debugLogs ? '```' : '',
  ].filter(Boolean).join('\n'));
  return url.toString();
}

export function BugReportBubble() {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [viewState, setViewState] = useState<ViewState>('form');
  const [description, setDescription] = useState('');
  const [email, setEmail] = useState('');
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [issueUrl, setIssueUrl] = useState<string | null>(null);
  const [issueNumber, setIssueNumber] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [wasDebug, setWasDebug] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const handleStopLoggingRef = useRef<() => void>(() => {});
  const loggingActiveRef = useRef(false);
  const wasDebugRef = useRef(false);

  const diagnosticScan = useQuery({
    queryKey: ['bugReportDiagnostic'],
    enabled: isOpen && viewState === 'form',
    staleTime: 30_000,
    queryFn: async (): Promise<DiagnosticEntry[]> => {
      const printers = await api.getPrinters();
      const entries = await Promise.all(
        printers.map(async (p) => {
          const result = await api.diagnosePrinter(p.id).catch(() => null);
          return result ? { name: p.name, result } : null;
        }),
      );
      return entries.filter((e): e is DiagnosticEntry => e !== null);
    },
  });
  const diagnosticEntries = diagnosticScan.data ?? [];
  const diagnosticProblems = diagnosticEntries.filter((e) => e.result.overall === 'problems');

  const logHealthScan = useQuery({
    queryKey: ['bugReportLogHealth'],
    enabled: isOpen && viewState === 'form',
    staleTime: 30_000,
    queryFn: api.getSystemHealth,
  });
  const logFindings = logHealthScan.data?.findings ?? [];
  const bugReportStatus = useQuery({
    queryKey: ['bugReportStatus'],
    enabled: isOpen,
    staleTime: 60_000,
    queryFn: bugReportApi.getStatus,
  });
  const reportRepository = bugReportStatus.data?.repository || FALLBACK_REPOSITORY;

  const showSubmissionError = useCallback((
    message: string,
    options?: { manualIssueUrl?: string | null; debugLogs?: string },
  ) => {
    const shouldBuildManualIssue = Boolean(options?.debugLogs || screenshot || !options?.manualIssueUrl);
    setIssueUrl(
      shouldBuildManualIssue
        ? buildManualIssueUrl(reportRepository, description, message, options?.debugLogs, Boolean(screenshot))
        : options?.manualIssueUrl || null,
    );
    setErrorMessage(message);
    setViewState('error');
  }, [description, reportRepository, screenshot]);

  useEffect(() => {
    if (viewState !== 'logging') return;
    if (elapsedSeconds >= MAX_LOG_SECONDS) {
      handleStopLoggingRef.current();
      return;
    }
    const timer = setTimeout(() => setElapsedSeconds((s) => s + 1), 1000);
    return () => clearTimeout(timer);
  }, [viewState, elapsedSeconds]);

  const handleOpen = () => {
    setIsOpen(true);
    setViewState('form');
    setDescription('');
    setEmail('');
    setScreenshot(null);
    setIssueUrl(null);
    setIssueNumber(null);
    setErrorMessage('');
    setElapsedSeconds(0);
    setWasDebug(false);
  };

  const cancelActiveLogging = useCallback(async () => {
    if (!loggingActiveRef.current) return;
    loggingActiveRef.current = false;
    try {
      await bugReportApi.stopLogging(wasDebugRef.current);
    } catch {
      // Best effort: closing the dialog must not trap the user.
    }
  }, []);

  useEffect(() => () => {
    if (loggingActiveRef.current) {
      loggingActiveRef.current = false;
      void bugReportApi.stopLogging(wasDebugRef.current);
    }
  }, []);

  const handleClose = async () => {
    if (viewState === 'logging') {
      setViewState('stopping');
      await cancelActiveLogging();
    }
    setIsOpen(false);
  };

  const handleFile = useCallback(async (file: File) => {
    if (!file.type.startsWith('image/')) return;
    try {
      const b64 = await compressImage(file);
      setScreenshot(b64);
    } catch {
      // Ignore read errors
    }
  }, []);

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) handleFile(file);
        break;
      }
    }
  }, [handleFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleStartLogging = async () => {
    if (!description.trim()) return;
    try {
      const result = await bugReportApi.startLogging();
      setWasDebug(result.was_debug);
      wasDebugRef.current = result.was_debug;
      loggingActiveRef.current = true;
      setElapsedSeconds(0);
      setViewState('logging');
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        await handleSubmitReport('');
        return;
      }
      const message = err instanceof Error ? err.message : t('bugReport.unexpectedError');
      showSubmissionError(message);
    }
  };

  const handleStopLogging = async () => {
    setViewState('stopping');
    try {
      const stopResult = await bugReportApi.stopLogging(wasDebug);
      loggingActiveRef.current = false;
      await handleSubmitReport(stopResult.logs);
    } catch (err) {
      const message = err instanceof Error ? err.message : t('bugReport.unexpectedError');
      showSubmissionError(message);
    }
  };
  handleStopLoggingRef.current = handleStopLogging;

  const handleSubmitReport = async (debugLogs: string) => {
    setViewState('submitting');
    try {
      const result = await bugReportApi.submit({
        description: description.trim(),
        email: email.trim() || undefined,
        screenshot_base64: screenshot || undefined,
        include_support_info: true,
        debug_logs: debugLogs || undefined,
      });
      if (result.success) {
        setIssueUrl(result.issue_url || null);
        setIssueNumber(result.issue_number || null);
        setViewState('success');
      } else {
        showSubmissionError(result.message, { manualIssueUrl: result.issue_url, debugLogs });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t('bugReport.unexpectedError');
      showSubmissionError(message, { debugLogs });
    }
  };

  return (
    <>
      <button
        onClick={handleOpen}
        className="fixed bottom-4 right-4 z-40 w-12 h-12 rounded-full bg-red-500 hover:bg-red-600 text-white shadow-lg hover:shadow-xl transition-all duration-200 hover:scale-110 flex items-center justify-center"
        title={t('bugReport.title')}
      >
        <Bug className="w-5 h-5" />
      </button>

      {isOpen && (
        <div
          id="bug-report-modal"
          className="fixed bottom-20 right-4 z-50 w-full max-w-md"
          onPaste={handlePaste}
        >
          <div
            ref={modalRef}
            className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl border border-gray-200 dark:border-gray-700 max-h-[80vh] overflow-y-auto"
          >
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700 sticky top-0 bg-white dark:bg-gray-800 z-10">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <Bug className="w-5 h-5 text-red-500" />
                {t('bugReport.title')}
              </h2>
              <button
                onClick={handleClose}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 space-y-4">
              {viewState === 'form' && (
                <>
                  {diagnosticScan.isLoading && (
                    <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      {t('bugReport.diagnosticChecking')}
                    </div>
                  )}
                  {!diagnosticScan.isLoading && diagnosticProblems.length > 0 && (
                    <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 p-3 space-y-3">
                      <div className="flex items-start gap-2">
                        <Stethoscope className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
                        <div>
                          <p className="text-sm font-medium text-amber-700 dark:text-amber-300">
                            {t('bugReport.diagnosticSummary', {
                              problems: diagnosticProblems.length,
                              total: diagnosticEntries.length,
                            })}
                          </p>
                          <p className="text-xs text-amber-800 dark:text-amber-200 mt-0.5">
                            {t('bugReport.diagnosticIntro')}
                          </p>
                        </div>
                      </div>
                      <div className="space-y-2">
                        {diagnosticProblems.map((entry) => (
                          <Collapsible
                            key={entry.result.printer_id ?? entry.result.ip_address}
                            defaultOpen={diagnosticProblems.length === 1}
                            className="rounded-lg bg-amber-100/60 dark:bg-amber-900/30 px-3 py-2"
                            summary={
                              <div className="flex items-center gap-2 min-w-0">
                                <AlertTriangle className="w-4 h-4 flex-shrink-0 text-amber-600 dark:text-amber-400" />
                                <span className="text-sm font-medium text-amber-800 dark:text-amber-200 truncate">
                                  {entry.name}
                                </span>
                              </div>
                            }
                          >
                            <DiagnosticChecklist result={entry.result} />
                          </Collapsible>
                        ))}
                      </div>
                    </div>
                  )}
                  {!diagnosticScan.isLoading &&
                    diagnosticEntries.length > 0 &&
                    diagnosticProblems.length === 0 && (
                      <div className="flex items-start gap-2 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 p-3">
                        <CheckCircle className="w-4 h-4 mt-0.5 flex-shrink-0 text-green-600 dark:text-green-400" />
                        <p className="text-xs text-green-800 dark:text-green-200">
                          {t('bugReport.diagnosticHealthy')}
                        </p>
                      </div>
                    )}

                  {!logHealthScan.isLoading && logFindings.length > 0 && logHealthScan.data && (
                    <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 p-3 space-y-3">
                      <div className="flex items-start gap-2">
                        <Stethoscope className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
                        <div>
                          <p className="text-sm font-medium text-amber-700 dark:text-amber-300">
                            {t('bugReport.logHealthSummary')}
                          </p>
                          <p className="text-xs text-amber-800 dark:text-amber-200 mt-0.5">
                            {t('bugReport.logHealthIntro')}
                          </p>
                        </div>
                      </div>
                      <SystemHealthPanel result={logHealthScan.data} />
                    </div>
                  )}

                  <TextArea
                    label={t('bugReport.description')}
                    required
                    value={description}
                    onValueChange={setDescription}
                    placeholder={t('bugReport.descriptionPlaceholder')}
                    rows={3}
                    className="resize-vertical bg-white text-gray-900 placeholder-gray-400 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                  />

                  <TextField
                    type="email"
                    label={t('bugReport.email')}
                    value={email}
                    onValueChange={setEmail}
                    placeholder={t('bugReport.emailPlaceholder')}
                    helperText={t('bugReport.emailPrivacy')}
                    className="bg-white text-gray-900 placeholder-gray-400 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                  />

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('bugReport.screenshot')}
                    </label>
                    {screenshot ? (
                      <div className="relative">
                        <img
                          src={`data:image/jpeg;base64,${screenshot}`}
                          alt={t('bugReport.screenshot')}
                          className="w-full max-h-40 object-contain rounded-lg border border-gray-200 dark:border-gray-600"
                        />
                        <button
                          onClick={() => setScreenshot(null)}
                          className="absolute top-2 right-2 p-1 bg-red-500 hover:bg-red-600 text-white rounded-full shadow"
                          title={t('common.delete')}
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        className={`w-full flex flex-col items-center gap-2 px-4 py-4 border-2 border-dashed rounded-lg transition-colors cursor-pointer ${
                          isDragging
                            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-500'
                            : 'border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500 hover:text-gray-600 dark:hover:text-gray-300'
                        }`}
                      >
                        <Upload className="w-5 h-5" />
                        <span className="text-sm">{t('bugReport.uploadOrPaste')}</span>
                      </button>
                    )}
                    <FileInput
                      ref={fileInputRef}
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleFile(file);
                        e.target.value = '';
                      }}
                    />
                  </div>

                  <details className="text-xs bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3">
                    <summary className="cursor-pointer font-medium text-amber-700 dark:text-amber-300 hover:text-amber-800 dark:hover:text-amber-200">
                      {t('bugReport.dataCollectedSummary')}
                    </summary>
                    <div className="mt-2 space-y-2 pl-2 border-l-2 border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-200">
                      <p className="font-medium">{t('bugReport.dataIncluded')}</p>
                      <p>{t('bugReport.dataIncludedList')}</p>
                      <p className="font-medium">{t('bugReport.dataNeverIncluded')}</p>
                      <p>{t('bugReport.dataNeverIncludedList')}</p>
                    </div>
                  </details>

                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      onClick={handleClose}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
                    >
                      {t('common.cancel')}
                    </button>
                    <button
                      onClick={handleStartLogging}
                      disabled={!description.trim()}
                      className="px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                    >
                      {t('bugReport.startLogging')}
                    </button>
                  </div>
                </>
              )}

              {viewState === 'logging' && (
                <div className="py-6 space-y-6">
                  <div className="space-y-3 px-2">
                    <div className="flex items-center gap-3">
                      <CheckCircle2 className="w-5 h-5 text-green-500 flex-shrink-0" />
                      <span className="text-sm text-green-700 dark:text-green-400">{t('bugReport.stepEnableLogging')}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="relative flex h-5 w-5 flex-shrink-0 items-center justify-center">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
                      </span>
                      <span className="text-sm font-medium text-blue-700 dark:text-blue-300">{t('bugReport.stepReproduce')}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <Circle className="w-5 h-5 text-gray-300 dark:text-gray-600 flex-shrink-0" />
                      <span className="text-sm text-gray-400 dark:text-gray-500">{t('bugReport.stepStopLogging')}</span>
                    </div>
                  </div>

                  <div className="text-center">
                    <p className="text-3xl font-mono text-blue-500">{formatElapsed(elapsedSeconds)}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{t('bugReport.maxDuration', { minutes: 5 })}</p>
                  </div>

                  <div className="flex justify-center">
                    <button
                      onClick={handleStopLogging}
                      className="px-6 py-2.5 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors"
                    >
                      {t('bugReport.stopAndSubmit')}
                    </button>
                  </div>
                </div>
              )}

              {(viewState === 'stopping' || viewState === 'submitting') && (
                <div className="flex flex-col items-center justify-center py-6 gap-3">
                  <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                  <p className="text-sm text-gray-600 dark:text-gray-400 text-center">
                    {viewState === 'stopping' ? t('bugReport.stoppingLogs') : t('bugReport.submitting')}
                  </p>
                  {viewState === 'submitting' && (
                    <ul className="text-xs text-gray-500 dark:text-gray-400 list-disc list-inside space-y-0.5">
                      <li>{t('bugReport.submittingStepConnection')}</li>
                      <li>{t('bugReport.submittingStepVirtualPrinters')}</li>
                      <li>{t('bugReport.submittingStepLogScan')}</li>
                      <li>{t('bugReport.submittingStepSubmit')}</li>
                    </ul>
                  )}
                </div>
              )}

              {viewState === 'success' && (
                <div className="flex flex-col items-center justify-center py-8 gap-3">
                  <CheckCircle className="w-12 h-12 text-green-500" />
                  <p className="text-lg font-semibold text-gray-900 dark:text-white">{t('bugReport.thankYou')}</p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{t('bugReport.submitted')}</p>
                  {issueUrl && (
                    <a
                      href={issueUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-500 hover:text-blue-600 underline"
                    >
                      {t('bugReport.viewIssue')} #{issueNumber}
                    </a>
                  )}
                  <button
                    onClick={handleClose}
                    className="mt-4 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
                  >
                    {t('common.close')}
                  </button>
                </div>
              )}

              {viewState === 'error' && (
                <div className="flex flex-col items-center justify-center py-8 gap-3">
                  <AlertCircle className="w-12 h-12 text-red-500" />
                  <p className="text-lg font-semibold text-gray-900 dark:text-white">{t('bugReport.submitFailed')}</p>
                  <p className="text-sm text-gray-600 dark:text-gray-400 text-center">{errorMessage}</p>
                  <div className="flex gap-2 mt-4">
                    <button
                      onClick={() => {
                        setIssueUrl(null);
                        setErrorMessage('');
                        setViewState('form');
                      }}
                      className="px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors"
                    >
                      {t('bugReport.submit')}
                    </button>
                    {issueUrl && (
                      <a
                        href={issueUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-4 py-2 text-sm font-medium text-white bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors"
                      >
                        {t('bugReport.openIssueForm')}
                      </a>
                    )}
                    <button
                      onClick={handleClose}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
                    >
                      {t('common.close')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
