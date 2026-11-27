import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { History, CheckCircle, XCircle, Loader2, Trash2, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '../api/client';
import { parseUTCDate, formatTimeOnly, formatDateTime, type TimeFormat } from '../utils/date';
import type { NotificationLogEntry } from '../api/client';
import { Button } from './Button';
import { Checkbox, LegacySelect, Modal } from './ui';
import { useToast } from '../contexts/ToastContext';

const EVENT_COLORS: Record<string, string> = {
  print_start: 'text-blue-800 dark:text-blue-300',
  print_complete: 'text-green-800 dark:text-green-300',
  print_failed: 'text-red-700 dark:text-red-300',
  print_stopped: 'text-orange-800 dark:text-orange-300',
  print_progress: 'text-yellow-800 dark:text-yellow-300',
  printer_offline: 'text-table-secondary',
  printer_error: 'text-rose-800 dark:text-rose-300',
  filament_low: 'text-cyan-800 dark:text-cyan-300',
  maintenance_due: 'text-purple-800 dark:text-purple-300',
  test: 'text-table-secondary',
};

interface NotificationLogViewerProps {
  onClose: () => void;
}

export function NotificationLogViewer({ onClose }: NotificationLogViewerProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [days, setDays] = useState(7);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [showFailedOnly, setShowFailedOnly] = useState(false);

  const { data: settings } = useQuery({
    queryKey: ['settings', 'ui-flags'],
    queryFn: api.getUiFlags,
  });

  const timeFormat: TimeFormat = settings?.time_format || 'system';

  const { data: logs, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['notification-logs', days, showFailedOnly],
    queryFn: () => api.getNotificationLogs({
      days,
      limit: 100,
      success: showFailedOnly ? false : undefined,
    }),
  });

  const { data: stats } = useQuery({
    queryKey: ['notification-log-stats', days],
    queryFn: () => api.getNotificationLogStats(days),
  });

  const clearMutation = useMutation({
    mutationFn: () => api.clearNotificationLogs(30),
    onSuccess: (data) => {
      showToast(data.message, 'success');
      queryClient.invalidateQueries({ queryKey: ['notification-logs'] });
      queryClient.invalidateQueries({ queryKey: ['notification-log-stats'] });
    },
    onError: (error: Error) => {
      showToast(`Failed to clear logs: ${error.message}`, 'error');
    },
  });

  const formatDate = (dateStr: string) => {
    const date = parseUTCDate(dateStr);
    if (!date) return '';
    const now = new Date();
    const diff = now.getTime() - date.getTime();

    if (diff < 60000) return t('notifications.justNow');
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;

    return date.toLocaleDateString() + ' ' + formatTimeOnly(date, timeFormat);
  };

  return (
    <Modal
      open
      title={t('notifications.notificationLog')}
      onClose={onClose}
      closeLabel={t('common.close')}
      closeOnBackdrop={false}
      className="max-w-3xl!"
    >
      <div className="min-w-0 space-y-4 text-sm text-table-secondary">
        {/* Stats Bar */}
        {stats && (
          <div className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark/30 p-3">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="text-table-secondary">
                {t('notifications.statsSummary', { days })} <span className="text-white font-medium">{stats.total}</span> {t('notifications.statsNotifications')}
              </span>
              <span className="flex items-center gap-1 text-green-800 dark:text-green-300">
                <CheckCircle className="w-4 h-4" />
                {t('notifications.statsSent', { count: stats.success_count })}
              </span>
              {stats.failure_count > 0 && (
                <span className="flex items-center gap-1 text-red-700 dark:text-red-300">
                  <XCircle className="w-4 h-4" />
                  {t('notifications.statsFailed', { count: stats.failure_count })}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <LegacySelect
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="w-auto max-w-full text-sm"
          >
            <option value={1}>{t('notifications.last24Hours')}</option>
            <option value={7}>{t('notifications.last7Days')}</option>
            <option value={30}>{t('notifications.last30Days')}</option>
            <option value={90}>{t('notifications.last90Days')}</option>
          </LegacySelect>

          <label className="flex items-center gap-2 text-sm text-table-secondary cursor-pointer">
            <Checkbox
              checked={showFailedOnly}
              onChange={(e) => setShowFailedOnly(e.target.checked)}
              className="rounded border-bambu-dark-tertiary bg-bambu-dark text-green-800 dark:text-green-300 focus:ring-bambu-green"
            />
            {t('notifications.showFailedOnly')}
          </label>

          <Button
            size="sm"
            variant="secondary"
            onClick={() => refetch()}
            disabled={isRefetching}
          >
            {isRefetching ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            {t('notifications.refresh')}
          </Button>

          <Button
            size="sm"
            variant="secondary"
            onClick={() => clearMutation.mutate()}
            disabled={clearMutation.isPending}
            className="text-red-700 dark:text-red-300 hover:text-red-800 dark:hover:text-red-300"
          >
            {clearMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4" />
            )}
            {t('notifications.clearOld')}
          </Button>
        </div>

        {/* Log List */}
        <div>
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-6 h-6 text-green-800 dark:text-green-300 animate-spin" />
            </div>
          ) : logs && logs.length > 0 ? (
            <div className="space-y-2">
              {logs.map((log) => (
                <LogEntry
                  key={log.id}
                  log={log}
                  isExpanded={expandedId === log.id}
                  onToggle={() => setExpandedId(expandedId === log.id ? null : log.id)}
                  formatDate={formatDate}
                  formatFullDate={(dateStr) => formatDateTime(dateStr, timeFormat)}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-table-secondary">
              <History className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-sm">
                {showFailedOnly ? t('notifications.noFailedNotifications') : t('notifications.noNotificationsLogged')}
              </p>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}

function LogEntry({
  log,
  isExpanded,
  onToggle,
  formatDate,
  formatFullDate,
}: {
  log: NotificationLogEntry;
  isExpanded: boolean;
  onToggle: () => void;
  formatDate: (date: string) => string;
  formatFullDate: (date: string) => string;
}) {
  const { t } = useTranslation();
  return (
    <div
      className={`border rounded-lg overflow-hidden transition-colors ${
        log.success
          ? 'border-bambu-dark-tertiary bg-bambu-dark/30'
          : 'border-red-500/30 bg-red-500/5'
      }`}
    >
      <Button variant="unstyled"
        className="flex min-h-[34px] w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-left transition-colors hover:bg-secondary-action-hover max-md:min-h-11"
        onClick={onToggle}
        aria-expanded={isExpanded}
      >
        {log.success ? (
          <CheckCircle className="w-4 h-4 text-green-800 dark:text-green-300 shrink-0" />
        ) : (
          <XCircle className="w-4 h-4 text-red-600 dark:text-red-300 shrink-0" />
        )}

        <span className={`text-xs font-medium ${EVENT_COLORS[log.event_type] || 'text-table-secondary'}`}>
          {t(`notifications.eventTypes.${log.event_type}`, log.event_type)}
        </span>

        <span className="min-w-0 flex-1 wrap-anywhere text-sm text-white">
          {log.provider_name || t('notifications.unknownProvider')}
        </span>

        {log.printer_name && (
          <span className="text-xs text-table-secondary">
            {log.printer_name}
          </span>
        )}

        <span className="text-xs text-table-secondary shrink-0">
          {formatDate(log.created_at)}
        </span>

        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-table-secondary shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-table-secondary shrink-0" />
        )}
      </Button>

      {isExpanded && (
        <div className="px-3 py-2 border-t border-bambu-dark-tertiary bg-bambu-dark/20 space-y-2">
          <div>
            <p className="text-xs text-table-secondary mb-1">{t('notifications.logTitle')}</p>
            <p className="wrap-anywhere text-sm text-white">{log.title}</p>
          </div>
          <div>
            <p className="text-xs text-table-secondary mb-1">{t('notifications.logMessage')}</p>
            <p className="wrap-anywhere whitespace-pre-wrap text-sm text-white">{log.message}</p>
          </div>
          {!log.success && log.error_message && (
            <div>
              <p className="text-xs text-red-700 dark:text-red-300 mb-1">{t('notifications.logError')}</p>
              <p className="wrap-anywhere text-sm text-red-700 dark:text-red-300">{log.error_message}</p>
            </div>
          )}
          <div className="flex flex-wrap gap-3 text-xs text-table-secondary pt-1">
            <span>{t('notifications.logProvider', { type: log.provider_type })}</span>
            <span>{t('notifications.logTime', { time: formatFullDate(log.created_at) })}</span>
          </div>
        </div>
      )}
    </div>
  );
}
