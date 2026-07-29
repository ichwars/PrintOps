import { useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Bug,
  CheckCircle,
  ExternalLink,
  Loader2,
  Stethoscope,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { api, bugReportApi, type PrinterDiagnosticResult } from '../api/client';
import { DiagnosticChecklist } from './ConnectionDiagnostic';
import { SystemHealthPanel } from './SystemHealthPanel';
import { Collapsible } from './Collapsible';

type DiagnosticEntry = { name: string; result: PrinterDiagnosticResult };

const FALLBACK_ISSUE_URL = 'https://github.com/ichwars/PrintOps/issues/new/choose';

export function BugReportBubble() {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);

  const diagnosticScan = useQuery({
    queryKey: ['bugReportDiagnostic'],
    enabled: isOpen,
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
    enabled: isOpen,
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
  const issueUrl = bugReportStatus.data?.issue_url || FALLBACK_ISSUE_URL;
  const repository = bugReportStatus.data?.repository || 'ichwars/PrintOps';

  const handleOpen = () => setIsOpen(true);
  const handleClose = () => setIsOpen(false);

  return (
    <>
      <button
        onClick={handleOpen}
        className="fixed bottom-4 right-4 z-40 w-12 h-12 rounded-full bg-red-500/55 hover:bg-red-500 focus-visible:bg-red-500 text-white/90 hover:text-white focus-visible:text-white shadow-lg hover:shadow-xl transition-all duration-200 hover:scale-110 flex items-center justify-center"
        title={t('bugReport.title')}
      >
        <Bug className="w-5 h-5" />
      </button>

      {isOpen && (
        <div id="bug-report-modal" className="fixed bottom-20 right-4 z-50 w-full max-w-md">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl border border-gray-200 dark:border-gray-700 max-h-[80vh] overflow-y-auto">
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

              <div className="flex items-start gap-2 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 p-3">
                <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0 text-blue-600 dark:text-blue-400" />
                <div>
                  <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
                    {t('bugReport.manualReportTitle')}
                  </p>
                  <p className="text-xs text-blue-700 dark:text-blue-300 mt-0.5">
                    {t('bugReport.manualReportDescription')}
                  </p>
                  <p className="text-xs text-blue-700/80 dark:text-blue-300/80 mt-2 truncate">
                    {repository}
                  </p>
                  {bugReportStatus.isLoading && (
                    <p className="text-xs text-blue-700/80 dark:text-blue-300/80 mt-1">
                      {t('support.bugReportStatusLoading', 'Checking bug report configuration...')}
                    </p>
                  )}
                  {bugReportStatus.isError && (
                    <p className="text-xs text-blue-700/80 dark:text-blue-300/80 mt-1">
                      {t('support.bugReportStatusUnavailable', 'Bug report configuration is currently unavailable')}
                    </p>
                  )}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={handleClose}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
                >
                  {t('common.cancel')}
                </button>
                <a
                  href={issueUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                  {t('bugReport.openIssueForm')}
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
