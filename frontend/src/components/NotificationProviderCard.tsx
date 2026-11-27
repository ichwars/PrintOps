import { useId, useState } from 'react';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Bell, Trash2, Settings2, Edit2, Send, Loader2, CheckCircle, XCircle, Moon, Clock, ChevronDown, ChevronUp, Calendar } from 'lucide-react';
import { api } from '../api/client';
import { formatDateOnly, parseUTCDate } from '../utils/date';
import type { NotificationProvider, NotificationProviderUpdate } from '../api/client';
import { dashboardStyles } from './dashboardStyles';
import { Button } from './Button';
import { ConfirmModal } from './ConfirmModal';
import { Toggle } from './Toggle';
import { TelegramQualitySettings } from './TelegramQualitySettings';

interface NotificationProviderCardProps {
  provider: NotificationProvider;
  onEdit: (provider: NotificationProvider) => void;
}

export function NotificationProviderCard({ provider, onEdit }: NotificationProviderCardProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const titleId = useId();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Fetch printers for linking
  const { data: printers } = useQuery({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  });

  const linkedPrinter = printers?.find(p => p.id === provider.printer_id);

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: NotificationProviderUpdate) => api.updateNotificationProvider(provider.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-providers'] });
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteNotificationProvider(provider.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-providers'] });
    },
  });

  // Test mutation
  const testMutation = useMutation({
    mutationFn: () => api.testNotificationProvider(provider.id),
    onSuccess: (result) => {
      setTestResult(result);
      queryClient.invalidateQueries({ queryKey: ['notification-providers'] });
    },
    onError: (err: Error) => {
      setTestResult({ success: false, message: err.message });
    },
  });

  // Format time for display
  const formatTime = (time: string | null) => {
    if (!time) return '';
    return time;
  };

  return (
    <>
      <article aria-labelledby={titleId} className="min-w-0 rounded-lg border border-bambu-dark-tertiary">
        <div className="flex flex-wrap items-start justify-between gap-2 rounded-t-lg border-b border-bambu-dark-tertiary bg-bambu-dark/30 px-3 py-2.5">
          <div className="flex min-w-0 flex-1 items-start gap-2">
            <Bell className={`h-4 w-4 shrink-0 ${provider.enabled ? 'text-accent-foreground' : 'text-table-secondary'}`} aria-hidden="true" />
            <div className="min-w-0">
              <h3 id={titleId} className={`${dashboardStyles.cardTitle} wrap-break-word`}>{provider.name}</h3>
              <p className="wrap-break-word text-xs text-table-secondary">{t(`notifications.providerTypes.${provider.provider_type}`, provider.provider_type)}</p>
            </div>
          </div>
          <div className="flex max-w-full flex-wrap items-center gap-2">
              {provider.last_success && (
                <span className="text-xs text-green-800 dark:text-green-300 hidden sm:inline">{t('notifications.lastSuccess', { date: formatDateOnly(provider.last_success) })}</span>
              )}
              {/* Only show error if it's more recent than last success */}
              {provider.last_error && provider.last_error_at && (
                !provider.last_success || (parseUTCDate(provider.last_error_at)?.getTime() || 0) > (parseUTCDate(provider.last_success)?.getTime() || 0)
              ) && (
                <span className="text-xs text-red-700 dark:text-red-300" title={provider.last_error}>{t('notifications.error')}</span>
              )}
              <Toggle
                ariaLabel={t('notifications.enabled')}
                checked={provider.enabled}
                onChange={(checked) => updateMutation.mutate({ enabled: checked })}
              />
            </div>
          </div>

        <div className="p-3">
          {provider.enabled && (<>
          {/* Linked Printer */}
          {linkedPrinter && (
            <div className="mb-3 px-2 py-1.5 bg-bambu-dark rounded-lg">
              <span className="text-xs text-table-secondary">{t('notifications.printer')} </span>
              <span className="text-sm text-white">{linkedPrinter.name}</span>
            </div>
          )}
          {!linkedPrinter && !provider.printer_id && (
            <div className="mb-3 px-2 py-1.5 bg-bambu-dark rounded-lg">
              <span className="text-xs text-table-secondary">{t('notifications.allPrinters')}</span>
            </div>
          )}

          {/* Event summary - show all event tags */}
          <div className="mb-3 flex flex-wrap gap-1">
            {provider.on_print_start && (
              <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-500/20 text-blue-800 dark:text-blue-300 text-xs rounded">{t('notifications.start')}</span>
            )}
            {provider.on_plate_not_empty && (
              <span className="px-2 py-0.5 bg-rose-100 dark:bg-rose-600/20 text-rose-700 dark:text-rose-300 text-xs rounded">{t('notifications.plateCheck')}</span>
            )}
            {provider.on_print_complete && (
              <span className="px-2 py-0.5 bg-bambu-green/20 text-accent-foreground text-xs rounded">{t('notifications.complete')}</span>
            )}
            {provider.on_print_failed && (
              <span className="px-2 py-0.5 bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300 text-xs rounded">{t('notifications.failed')}</span>
            )}
            {provider.on_print_stopped && (
              <span className="px-2 py-0.5 bg-orange-100 dark:bg-orange-500/20 text-orange-800 dark:text-orange-300 text-xs rounded">{t('notifications.stopped')}</span>
            )}
            {provider.on_print_progress && (
              <span className="px-2 py-0.5 bg-yellow-100 dark:bg-yellow-500/20 text-yellow-800 dark:text-yellow-300 text-xs rounded">{t('notifications.progress')}</span>
            )}
            {provider.on_print_pause_upcoming && (
              <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-500/20 text-blue-800 dark:text-blue-300 text-xs rounded">{t('notifications.pauseUpcoming')}</span>
            )}
            {provider.on_printer_offline && (
              <span className="px-2 py-0.5 bg-bambu-dark-tertiary text-table-secondary text-xs rounded">{t('notifications.offline')}</span>
            )}
            {provider.on_printer_error && (
              <span className="px-2 py-0.5 bg-rose-100 dark:bg-rose-500/20 text-rose-800 dark:text-rose-300 text-xs rounded">{t('notifications.error')}</span>
            )}
            {provider.on_ai_failure_detection && (
              <span className="px-2 py-0.5 bg-fuchsia-100 dark:bg-fuchsia-500/20 text-fuchsia-700 dark:text-fuchsia-300 text-xs rounded">{t('notifications.aiFailureDetection')}</span>
            )}
            {provider.on_storage_sensor_alert && (<span className="px-2 py-0.5 text-xs text-amber-800 dark:text-amber-300">{t('storageSensors.notifications')}</span>)}
            {provider.on_app_message && (<span className="px-2 py-0.5 text-xs text-accent-foreground">{t('appNotifications.label')}</span>)}
            {provider.on_ha_sensor_alert && (
              <span className="px-2 py-0.5 bg-indigo-100 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 text-xs rounded">{t('notifications.haSensorAlert')}</span>
            )}
            {provider.on_filament_low && (
              <span className="px-2 py-0.5 bg-cyan-100 dark:bg-cyan-500/20 text-cyan-800 dark:text-cyan-300 text-xs rounded">{t('notifications.lowFilament')}</span>
            )}
            {provider.on_maintenance_due && (
              <span className="px-2 py-0.5 bg-purple-100 dark:bg-purple-500/20 text-purple-800 dark:text-purple-300 text-xs rounded">{t('notifications.maintenance')}</span>
            )}
            {provider.on_ams_humidity_high && (
              <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-600/20 text-blue-700 dark:text-blue-300 text-xs rounded">{t('notifications.amsHumidity')}</span>
            )}
            {provider.on_ams_temperature_high && (
              <span className="px-2 py-0.5 bg-orange-100 dark:bg-orange-600/20 text-orange-700 dark:text-orange-300 text-xs rounded">{t('notifications.amsTemp')}</span>
            )}
            {provider.on_ams_ht_humidity_high && (
              <span className="px-2 py-0.5 bg-cyan-100 dark:bg-cyan-600/20 text-cyan-700 dark:text-cyan-300 text-xs rounded">{t('notifications.amsHtHumidity')}</span>
            )}
            {provider.on_ams_ht_temperature_high && (
              <span className="px-2 py-0.5 bg-amber-100 dark:bg-amber-600/20 text-amber-800 dark:text-amber-300 text-xs rounded">{t('notifications.amsHtTemp')}</span>
            )}
            {provider.on_bed_cooled && (
              <span className="px-2 py-0.5 bg-teal-100 dark:bg-teal-500/20 text-teal-800 dark:text-teal-300 text-xs rounded">{t('notifications.bedCooled')}</span>
            )}
            {provider.on_first_layer_complete && (
              <span className="px-2 py-0.5 bg-emerald-100 dark:bg-emerald-600/20 text-emerald-700 dark:text-emerald-300 text-xs rounded">{t('notifications.firstLayer')}</span>
            )}
            {provider.on_print_missing_spool_assignment && (
              <span className="px-2 py-0.5 bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300 text-xs rounded">{t('notifications.missingSpoolAssignmentLabel')}</span>
            )}
            {provider.on_stock_reorder_alert && (
              <span className="px-2 py-0.5 bg-lime-100 dark:bg-lime-500/20 text-lime-800 dark:text-lime-300 text-xs rounded">{t('notifications.stockReorderAlert')}</span>
            )}
            {provider.on_stock_break_alert && (
              <span className="px-2 py-0.5 bg-red-100 dark:bg-red-600/20 text-red-700 dark:text-red-300 text-xs rounded">{t('notifications.stockBreakAlert')}</span>
            )}
            {provider.quiet_hours_enabled && (
              <span className="px-2 py-0.5 bg-indigo-100 dark:bg-indigo-500/20 text-indigo-800 dark:text-indigo-300 text-xs rounded flex items-center gap-1">
                <Moon className="w-3 h-3" />
                {t('notifications.quiet')}
              </span>
            )}
            {provider.daily_digest_enabled && (
              <span className="px-2 py-0.5 bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 text-xs rounded flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {t('notifications.digest', { time: provider.daily_digest_time })}
              </span>
            )}
          </div>

          {/* Test Button */}
          <div className="mb-3">
            <Button
              size="sm"
              variant="secondary"
              disabled={testMutation.isPending}
              onClick={() => {
                setTestResult(null);
                testMutation.mutate();
              }}
              className="w-full"
            >
              {testMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              {t('notifications.sendTestNotification')}
            </Button>
          </div>

          {/* Test Result */}
          {testResult && (
            <div className={`mb-3 p-2 rounded-lg flex items-center gap-2 text-sm ${
              testResult.success
                ? 'bg-bambu-green/20 text-accent-foreground'
                : 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300'
            }`}>
              {testResult.success ? (
                <CheckCircle className="w-4 h-4" />
              ) : (
                <XCircle className="w-4 h-4" />
              )}
              <span className="min-w-0 wrap-anywhere">{testResult.message}</span>
            </div>
          )}

          </>)}
          {/* Toggle Settings Panel */}
          <Button variant="unstyled"
            onClick={() => setIsExpanded(expanded => !expanded)}
            aria-expanded={isExpanded}
            className="flex min-h-[34px] w-full items-center justify-between gap-2 rounded-lg border border-bambu-dark-tertiary px-2.5 py-1.5 text-left text-sm text-table-secondary transition-colors hover:bg-secondary-action-hover hover:text-white max-md:min-h-11"
          >
            <span className="flex items-center gap-2">
              <Settings2 className="w-4 h-4" />
              {t('notifications.eventSettings')}
            </span>
            {isExpanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </Button>

          {/* Expanded Settings */}
          {isExpanded && (
            <div className="mt-3 space-y-4 border-t border-bambu-dark-tertiary pt-3">
              {provider.provider_type === 'telegram' && <TelegramQualitySettings providerId={provider.id} />}
              {/* Enabled Toggle */}
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm text-white">{t('notifications.enabled')}</p>
                  <p className="text-xs text-table-secondary">{t('notifications.sendFromProvider')}</p>
                </div>
                <Toggle
                  checked={provider.enabled}
                  onChange={(checked) => updateMutation.mutate({ enabled: checked })}
                />
              </div>

              {provider.provider_type !== 'callmebot' && (
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.attachPhoto')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.attachPhotoHint')}</p>
                  </div>
                  <Toggle ariaLabel={t('notifications.attachPhoto')} checked={provider.attach_photo ?? true} onChange={(checked) => updateMutation.mutate({ attach_photo: checked })} />
                </div>
              )}

              {/* Print Lifecycle Events */}
              <div className="space-y-2">
                <p className="text-xs text-table-secondary uppercase tracking-wide">{t('notifications.printEvents')}</p>

                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-white">{t('notifications.printStarted')}</p>
                  <Toggle
                    checked={provider.on_print_start}
                    onChange={(checked) => updateMutation.mutate({ on_print_start: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.plateNotEmpty')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.plateNotEmptyDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_plate_not_empty ?? true}
                    onChange={(checked) => updateMutation.mutate({ on_plate_not_empty: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-white">{t('productionQuality.title')}</p>
                  <Toggle checked={provider.on_print_confirm_request ?? true} onChange={(checked) => updateMutation.mutate({ on_print_confirm_request: checked })} />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-white">{t('notifications.printCompleted')}</p>
                  <Toggle
                    checked={provider.on_print_complete}
                    onChange={(checked) => updateMutation.mutate({ on_print_complete: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.bedCooledLabel')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.bedCooledDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_bed_cooled ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_bed_cooled: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.firstLayerCompleteLabel')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.firstLayerCompleteDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_first_layer_complete ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_first_layer_complete: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.missingSpoolAssignmentLabel')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.missingSpoolAssignmentDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_print_missing_spool_assignment ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_print_missing_spool_assignment: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-white">{t('notifications.printFailed')}</p>
                  <Toggle
                    checked={provider.on_print_failed}
                    onChange={(checked) => updateMutation.mutate({ on_print_failed: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-white">{t('notifications.printStopped')}</p>
                  <Toggle
                    checked={provider.on_print_stopped}
                    onChange={(checked) => updateMutation.mutate({ on_print_stopped: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.progressMilestones')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.progressMilestonesDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_print_progress}
                    onChange={(checked) => updateMutation.mutate({ on_print_progress: checked })}
                  />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-white">{t('notifications.pauseUpcoming')}</p>
                  <Toggle
                    ariaLabel={t('notifications.pauseUpcoming')}
                    checked={provider.on_print_pause_upcoming ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_print_pause_upcoming: checked })}
                  />
                </div>
              </div>

              {/* Printer Status Events */}
              <div className="space-y-2">
                <p className="text-xs text-table-secondary uppercase tracking-wide">{t('notifications.printerStatus')}</p>

                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-white">{t('notifications.printerOffline')}</p>
                  <Toggle
                    checked={provider.on_printer_offline}
                    onChange={(checked) => updateMutation.mutate({ on_printer_offline: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-white">{t('notifications.printerError')}</p>
                  <Toggle
                    checked={provider.on_printer_error}
                    onChange={(checked) => updateMutation.mutate({ on_printer_error: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.aiFailureDetection')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.aiFailureDetectionDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_ai_failure_detection ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_ai_failure_detection: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.haSensorAlert')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.haSensorAlertDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_ha_sensor_alert ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_ha_sensor_alert: checked })}
                  />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <div><p className="text-sm text-white">{t('appNotifications.label')}</p><p className="text-xs text-table-secondary">{t('appNotifications.channelDescription')}</p></div>
                  <Toggle ariaLabel={t('appNotifications.label')} checked={provider.on_app_message ?? false} onChange={(checked) => updateMutation.mutate({ on_app_message: checked })} />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-white">{t('storageSensors.notifications')}</p>
                  <Toggle ariaLabel={t('storageSensors.notifications')} checked={provider.on_storage_sensor_alert ?? false} onChange={(checked) => updateMutation.mutate({ on_storage_sensor_alert: checked })} />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-white">{t('notifications.lowFilamentLabel')}</p>
<Toggle
                    checked={provider.on_filament_low}
                    onChange={(checked) => updateMutation.mutate({ on_filament_low: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.maintenanceDue')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.maintenanceDueDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_maintenance_due ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_maintenance_due: checked })}
                  />
                </div>
              </div>

              {/* AMS Environmental Alarms (regular AMS) */}
              <div className="space-y-2">
                <p className="text-xs text-table-secondary uppercase tracking-wide">{t('notifications.amsAlarms')}</p>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.amsHumidityHigh')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.amsHumidityHighDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_ams_humidity_high ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_ams_humidity_high: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.amsTemperatureHigh')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.amsTemperatureHighDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_ams_temperature_high ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_ams_temperature_high: checked })}
                  />
                </div>
              </div>

              {/* AMS-HT Environmental Alarms */}
              <div className="space-y-2">
                <p className="text-xs text-table-secondary uppercase tracking-wide">{t('notifications.amsHtAlarms')}</p>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.amsHtHumidityHigh')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.amsHtHumidityHighDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_ams_ht_humidity_high ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_ams_ht_humidity_high: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.amsHtTemperatureHigh')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.amsHtTemperatureHighDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_ams_ht_temperature_high ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_ams_ht_temperature_high: checked })}
                  />
                </div>
              </div>

              {/* Inventory Stock Alerts */}
              <div className="space-y-2">
                <p className="text-xs text-table-secondary uppercase tracking-wide">{t('notifications.inventoryAlerts')}</p>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.stockReorderAlert')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.stockReorderAlertDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_stock_reorder_alert ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_stock_reorder_alert: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.stockBreakAlert')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.stockBreakAlertDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_stock_break_alert ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_stock_break_alert: checked })}
                  />
                </div>
              </div>

              {/* Print Queue Events */}
              <div className="space-y-2">
                <p className="text-xs text-table-secondary uppercase tracking-wide">{t('notifications.printQueue')}</p>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.jobAdded')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.jobAddedDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_queue_job_added ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_queue_job_added: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.jobAssigned')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.jobAssignedDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_queue_job_assigned ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_queue_job_assigned: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.jobStarted')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.jobStartedDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_queue_job_started ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_queue_job_started: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.jobWaiting')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.jobWaitingDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_queue_job_waiting ?? true}
                    onChange={(checked) => updateMutation.mutate({ on_queue_job_waiting: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.jobSkipped')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.jobSkippedDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_queue_job_skipped ?? true}
                    onChange={(checked) => updateMutation.mutate({ on_queue_job_skipped: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.jobFailed')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.jobFailedDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_queue_job_failed ?? true}
                    onChange={(checked) => updateMutation.mutate({ on_queue_job_failed: checked })}
                  />
                </div>

                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">{t('notifications.queueComplete')}</p>
                    <p className="text-xs text-table-secondary">{t('notifications.queueCompleteDescription')}</p>
                  </div>
                  <Toggle
                    checked={provider.on_queue_completed ?? false}
                    onChange={(checked) => updateMutation.mutate({ on_queue_completed: checked })}
                  />
                </div>
              </div>

              {/* Quiet Hours */}
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Moon className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                    <p className="text-sm text-white">{t('notifications.quietHours')}</p>
                  </div>
                  <Toggle
                    checked={provider.quiet_hours_enabled}
                    onChange={(checked) => updateMutation.mutate({ quiet_hours_enabled: checked })}
                  />
                </div>

                {provider.quiet_hours_enabled && (
                  <div className="pl-4 border-l-2 border-bambu-dark-tertiary space-y-2">
                    <p className="text-xs text-table-secondary">{t('notifications.noNotificationsDuring')}</p>
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-table-secondary" />
                      <span className="text-sm text-white">
                        {formatTime(provider.quiet_hours_start) || '22:00'} - {formatTime(provider.quiet_hours_end) || '07:00'}
                      </span>
                    </div>
                    <p className="text-xs text-table-secondary">{t('notifications.editProviderToChangeQuietHours')}</p>
                  </div>
                )}
              </div>

              {/* Daily Digest */}
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                    <p className="text-sm text-white">{t('notifications.dailyDigest')}</p>
                  </div>
                  <Toggle
                    checked={provider.daily_digest_enabled}
                    onChange={(checked) => updateMutation.mutate({ daily_digest_enabled: checked })}
                  />
                </div>

                {provider.daily_digest_enabled && (
                  <div className="pl-4 border-l-2 border-bambu-dark-tertiary space-y-2">
                    <p className="text-xs text-table-secondary">{t('notifications.batchNotifications')}</p>
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-table-secondary" />
                      <span className="text-sm text-white">
                        {t('notifications.sendAt', { time: formatTime(provider.daily_digest_time) || '08:00' })}
                      </span>
                    </div>
                    <p className="text-xs text-table-secondary">{t('notifications.editProviderToChangeDigestTime')}</p>
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex gap-2 pt-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => onEdit(provider)}
                  className="flex-1"
                >
                  <Edit2 className="w-4 h-4" />
                  {t('notifications.edit')}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setShowDeleteConfirm(true)}
                  className="text-red-700 dark:text-red-300 hover:text-red-800 dark:hover:text-red-300"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </article>

      {/* Delete Confirmation */}
      {showDeleteConfirm && (
        <ConfirmModal
          title={t('notifications.deleteProvider')}
          message={t('notifications.deleteConfirm', { name: provider.name })}
          confirmText={t('notifications.delete')}
          variant="danger"
          onConfirm={() => {
            deleteMutation.mutate();
            setShowDeleteConfirm(false);
          }}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      )}
    </>
  );
}
