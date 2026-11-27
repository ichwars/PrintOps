import { useId, useState } from 'react';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { Plug, Power, PowerOff, Loader2, Trash2, Settings2, Thermometer, Clock, Wifi, WifiOff, Edit2, Bell, Calendar, LayoutGrid, ExternalLink, Home, Radio, Eye, Globe, Wind } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import type { SmartPlug, SmartPlugUpdate } from '../api/client';
import { dashboardStyles } from './dashboardStyles';
import { Button } from './Button';
import { ConfirmModal } from './ConfirmModal';
import { useToast } from '../contexts/ToastContext';
import { NumberField, Switch } from './ui';

interface SmartPlugCardProps {
  plug: SmartPlug;
  onEdit: (plug: SmartPlug) => void;
}

export function SmartPlugCard({ plug, onEdit }: SmartPlugCardProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const titleId = useId();
  const { showToast } = useToast();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showPowerOnConfirm, setShowPowerOnConfirm] = useState(false);
  const [showPowerOffConfirm, setShowPowerOffConfirm] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  // Fetch current status
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['smart-plug-status', plug.id],
    queryFn: () => api.getSmartPlugStatus(plug.id),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Fetch printers for linking
  const { data: printers } = useQuery({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  });

  const { data: dryers } = useQuery({
    queryKey: ['equipment'],
    queryFn: () => api.getEquipment(false),
  });

  const linkedPrinter = printers?.find(p => p.id === plug.printer_id);
  const linkedDryer = dryers?.find(d => d.id === plug.equipment_id);

  // Control mutation with optimistic updates
  const controlMutation = useMutation({
    mutationFn: (action: 'on' | 'off' | 'toggle') => api.controlSmartPlug(plug.id, action),
    onMutate: async (action) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['smart-plug-status', plug.id] });

      // Snapshot the previous value
      const previousStatus = queryClient.getQueryData(['smart-plug-status', plug.id]);

      // Optimistically update to the new value
      const newState = action === 'on' ? 'ON' : action === 'off' ? 'OFF' : (status?.state === 'ON' ? 'OFF' : 'ON');
      queryClient.setQueryData(['smart-plug-status', plug.id], (old: typeof status) => ({
        ...old,
        state: newState,
      }));

      return { previousStatus };
    },
    onError: (_err, action, context) => {
      // Rollback on error
      if (context?.previousStatus) {
        queryClient.setQueryData(['smart-plug-status', plug.id], context.previousStatus);
      }
      showToast(t('smartPlugs.failedToTurn', { action, name: plug.name }), 'error');
    },
    onSettled: () => {
      // Refetch after a short delay to get actual state
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['smart-plug-status', plug.id] });
        queryClient.invalidateQueries({ queryKey: ['smart-plugs'] });
      }, 1000);
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: SmartPlugUpdate) => api.updateSmartPlug(plug.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart-plugs'] });
      // Also invalidate printer-specific smart plug queries to keep PrintersPage in sync
      if (plug.printer_id) {
        queryClient.invalidateQueries({ queryKey: ['smartPlugByPrinter', plug.printer_id] });
        queryClient.invalidateQueries({ queryKey: ['scriptPlugsByPrinter', plug.printer_id] });
      }
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteSmartPlug(plug.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart-plugs'] });
      // Also invalidate printer card HA entity queries
      if (plug.printer_id) {
        queryClient.invalidateQueries({ queryKey: ['scriptPlugsByPrinter', plug.printer_id] });
      }
    },
  });

  const isOn = status?.state === 'ON';
  // For MQTT plugs, consider reachable if we have power data (even if backend says not reachable)
  const hasMqttData = plug.plug_type === 'mqtt' && (status?.energy?.power !== null && status?.energy?.power !== undefined);
  const isReachable = (status?.reachable ?? false) || hasMqttData;
  const isPending = controlMutation.isPending;
  const PlugIcon = { mqtt: Radio, homeassistant: Home, rest: Globe, tasmota: Plug }[plug.plug_type];
  const onlineColor = 'text-green-800 dark:text-green-300';
  const offlineColor = 'text-red-700 dark:text-red-300';
  const stateColor = !isReachable ? offlineColor : isOn ? onlineColor : 'text-table-secondary';

  // Generate admin URL with auto-login credentials (Tasmota only)
  const getAdminUrl = () => {
    if (plug.plug_type !== 'tasmota' || !plug.ip_address) return null;
    const ip = plug.ip_address;
    if (plug.username && plug.password) {
      // Use HTTP Basic Auth in URL for auto-login
      return `http://${encodeURIComponent(plug.username)}:${encodeURIComponent(plug.password)}@${ip}/`;
    }
    return `http://${ip}/`;
  };

  const adminUrl = getAdminUrl();

  const connectionLabel = {
    mqtt: plug.mqtt_topic,
    homeassistant: plug.ha_entity_id,
    rest: 'REST',
    tasmota: plug.ip_address,
  }[plug.plug_type];

  return (
    <>
      <article aria-labelledby={titleId} className={`${dashboardStyles.card} min-w-0`}>
        <div className={`${dashboardStyles.cardHeader} flex flex-wrap items-start justify-between gap-2 rounded-t-xl`}>
          <div className="flex min-w-0 flex-1 items-start gap-2">
            <PlugIcon className={`h-4 w-4 shrink-0 ${stateColor}`} aria-hidden="true" />
            <div className="min-w-0">
              <h3 id={titleId} className={`${dashboardStyles.cardTitle} wrap-break-word`}>{plug.name}</h3>
              {connectionLabel && (
                <p className="mt-1 wrap-anywhere font-mono text-xs text-table-secondary" title={connectionLabel}>
                  {connectionLabel}
                </p>
              )}
            </div>
          </div>
          <div className="flex max-w-full shrink-0 flex-wrap items-center gap-1.5">
              {statusLoading ? (
                <Loader2 className="h-4 w-4 animate-spin text-table-secondary" />
              ) : plug.plug_type === 'mqtt' ? (
                /* MQTT plugs - show badge and checkmark when receiving data */
                <div className="flex items-center gap-1.5 text-sm whitespace-nowrap">
                  <span className="px-1.5 py-0.5 bg-teal-100 dark:bg-teal-500/20 text-teal-800 dark:text-teal-300 text-xs font-medium rounded flex-shrink-0">MQTT</span>
                  {isReachable && <span className={onlineColor}>✓</span>}
                </div>
              ) : plug.plug_type === 'homeassistant' ? (
                <div className="flex items-center gap-1 text-sm">
                  <span className="px-1 py-0.5 bg-blue-100 dark:bg-blue-500/20 text-blue-800 dark:text-blue-300 text-xs font-medium rounded">HA</span>
                  <span className={stateColor}>
                    {isReachable ? (status?.state || '?') : t('smartPlugs.offline')}
                  </span>
                </div>
              ) : plug.plug_type === 'rest' ? (
                <div className="flex items-center gap-1 text-sm">
                  <span className="px-1 py-0.5 bg-purple-100 dark:bg-purple-500/20 text-purple-800 dark:text-purple-300 text-xs font-medium rounded">REST</span>
                  <span className={stateColor}>
                    {isReachable ? (status?.state || '?') : t('smartPlugs.offline')}
                  </span>
                </div>
              ) : isReachable ? (
                <div className="flex items-center gap-1 text-sm">
                  <Wifi className={`h-4 w-4 ${onlineColor}`} aria-hidden="true" />
                  <span className={stateColor}>{status?.state || t('smartPlugs.unknown')}</span>
                </div>
              ) : (
                <div className={`flex items-center gap-1 text-sm ${offlineColor}`}>
                  <WifiOff className="w-4 h-4" />
                  <span>{t('smartPlugs.offline')}</span>
                </div>
              )}
              {/* Admin page link - only for Tasmota */}
              {adminUrl && (
                <a
                  href={adminUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 rounded-md bg-bambu-dark px-2 py-1 text-xs text-table-secondary transition-colors hover:bg-secondary-action-hover hover:text-white"
                  title={t('smartPlugs.openPlugAdminPage')}
                >
                  <ExternalLink className="w-3 h-3" />
                  {t('smartPlugs.admin')}
                </a>
              )}
            </div>
        </div>
        <div className={`${dashboardStyles.cardBody} space-y-3 text-sm text-table-secondary`}>
          {/* Linked target */}
          {(linkedPrinter || linkedDryer) && (
            <div className="flex items-center gap-2 rounded-lg bg-bambu-dark px-2 py-1.5">
              {linkedDryer ? (
                <Wind className="w-3.5 h-3.5 text-bambu-green" />
              ) : (
                <Plug className="w-3.5 h-3.5 text-bambu-green" />
              )}
              <div className="min-w-0">
                <span className="text-xs text-table-secondary">{t('smartPlugs.linkedTo')} </span>
                <span className="wrap-break-word text-sm text-white">{linkedDryer?.name || linkedPrinter?.name}</span>
              </div>
            </div>
          )}


          {/* Feature Badges */}
          {(plug.power_alert_enabled || plug.schedule_enabled || plug.plug_type === 'mqtt') && (
            <div className="flex flex-wrap gap-1.5">
              {plug.plug_type === 'mqtt' && (
                <span className="flex items-center gap-1 px-2 py-0.5 bg-teal-100 dark:bg-teal-500/20 text-teal-800 dark:text-teal-300 text-xs rounded-full">
                  <Eye className="w-3 h-3" />
                  {t('smartPlugs.monitorOnly')}
                </span>
              )}
              {plug.power_alert_enabled && (
                <span className="flex items-center gap-1 px-2 py-0.5 bg-yellow-100 dark:bg-yellow-500/20 text-yellow-800 dark:text-yellow-300 text-xs rounded-full">
                  <Bell className="w-3 h-3" />
                  {t('smartPlugs.alerts')}
                </span>
              )}
              {plug.schedule_enabled && (
                <span className="flex items-center gap-1 px-2 py-0.5 bg-blue-100 dark:bg-blue-500/20 text-blue-800 dark:text-blue-300 text-xs rounded-full">
                  <Calendar className="w-3 h-3" />
                  {plug.schedule_on_time && plug.schedule_off_time
                    ? `${plug.schedule_on_time} - ${plug.schedule_off_time}`
                    : plug.schedule_on_time
                      ? t('smartPlugs.scheduleOn', { time: plug.schedule_on_time })
                      : t('smartPlugs.scheduleOff', { time: plug.schedule_off_time })}
                </span>
              )}
            </div>
          )}

          {/* Quick Controls - hidden for MQTT plugs (monitor-only) */}
          {plug.plug_type !== 'mqtt' && (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant={isOn ? 'primary' : 'secondary'}
                disabled={!isReachable || isPending}
                onClick={() => setShowPowerOnConfirm(true)}
                className={`flex-1 ${isOn ? 'text-black!' : ''}`}
              >
                {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Power className="w-4 h-4" />}
                {t('smartPlugs.on')}
              </Button>
              <Button
                size="sm"
                variant={!isOn ? 'primary' : 'secondary'}
                disabled={!isReachable || isPending}
                onClick={() => setShowPowerOffConfirm(true)}
                className={`flex-1 ${!isOn ? 'text-black!' : ''}`}
              >
                {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <PowerOff className="w-4 h-4" />}
                {t('smartPlugs.off')}
              </Button>
            </div>
          )}

          {/* Energy display for MQTT plugs */}
          {plug.plug_type === 'mqtt' && status?.energy && (
            <div className="flex flex-wrap gap-2 px-3 py-2 bg-bambu-dark rounded-lg">
              {status.energy.power !== null && status.energy.power !== undefined && (
                <div className="flex-1 text-center">
                  <p className="text-lg font-semibold tabular-nums text-white">{Math.round(status.energy.power)} W</p>
                  <p className="text-xs text-table-secondary">{t('smartPlugs.power')}</p>
                </div>
              )}
              {status.energy.today !== null && status.energy.today !== undefined && (
                <div className="flex-1 text-center border-l border-bambu-dark-tertiary">
                  <p className="text-lg font-semibold tabular-nums text-white">{status.energy.today.toFixed(3)}</p>
                  <p className="text-xs text-table-secondary">{t('smartPlugs.kwhToday')}</p>
                </div>
              )}
            </div>
          )}

          {/* Toggle Settings Panel */}
          <Button variant="unstyled"
            onClick={() => setIsExpanded(expanded => !expanded)}
            aria-expanded={isExpanded}
            className="flex min-h-[34px] w-full items-center justify-between gap-2 rounded-lg border border-bambu-dark-tertiary px-2.5 py-1.5 text-left text-sm text-table-secondary transition-colors hover:bg-secondary-action-hover hover:text-white max-md:min-h-11"
          >
            <span className="flex items-center gap-2">
              <Settings2 className="w-4 h-4" />
              {plug.plug_type === 'mqtt' ? t('smartPlugs.settings') : t('smartPlugs.automationSettings')}
            </span>
            <span aria-hidden="true">{isExpanded ? '−' : '+'}</span>
          </Button>

          {/* Expanded Settings */}
          {isExpanded && (
            <div className="pt-3 border-t border-bambu-dark-tertiary space-y-4">
              {/* Show in Switchbar Toggle */}
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <LayoutGrid className="w-4 h-4 text-bambu-green" />
                  <div>
                    <p className="text-sm text-white">{t('smartPlugs.showInSwitchbar')}</p>
                    <p className="text-xs text-table-secondary">{t('smartPlugs.quickAccessSidebar')}</p>
                  </div>
                </div>
                <Switch
                    ariaLabel={t('smartPlugs.showInSwitchbar')}
                    checked={plug.show_in_switchbar}
                    onChange={(e) => updateMutation.mutate({ show_in_switchbar: e.target.checked })}
                  />
              </div>

              {plug.printer_id != null && (
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Power className="w-4 h-4 text-bambu-green" />
                    <div>
                      <p className="text-sm text-white">{t('smartPlugs.controlsPrinterPower')}</p>
                      <p className="text-xs text-table-secondary">{t('smartPlugs.controlsPrinterPowerDescription')}</p>
                    </div>
                  </div>
                  <Switch
                    ariaLabel={t('smartPlugs.controlsPrinterPower')}
                    checked={plug.controls_printer_power}
                    onChange={(e) => updateMutation.mutate({ controls_printer_power: e.target.checked })}
                  />
                </div>
              )}

              {/* Automation controls - only for controllable plugs (not MQTT) */}
              {plug.plug_type !== 'mqtt' && (
                <>
                  {/* Enabled Toggle */}
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm text-white">{t('smartPlugs.enabled')}</p>
                      <p className="text-xs text-table-secondary">{t('smartPlugs.enableAutomation')}</p>
                    </div>
                    <Switch
                    ariaLabel={t('smartPlugs.enabled')}
                    checked={plug.enabled}
                        onChange={(e) => updateMutation.mutate({ enabled: e.target.checked })}
                  />
                  </div>

                  {/* Auto On */}
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm text-white">{t('smartPlugs.autoOn')}</p>
                      <p className="text-xs text-table-secondary">{t('smartPlugs.autoOnDescription')}</p>
                    </div>
                    <Switch
                    ariaLabel={t('smartPlugs.autoOn')}
                    checked={plug.auto_on}
                        onChange={(e) => updateMutation.mutate({ auto_on: e.target.checked })}
                  />
                  </div>

                  {/* Auto Off */}
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm text-white">{t('smartPlugs.autoOff')}</p>
                      <p className="text-xs text-table-secondary">{t('smartPlugs.autoOffDescription')}</p>
                </div>
                <Switch
                    ariaLabel={t('smartPlugs.autoOff')}
                    checked={plug.auto_off}
                    onChange={(e) => updateMutation.mutate({ auto_off: e.target.checked })}
                  />
              </div>

              {/* Auto Off Persistent */}
              {plug.auto_off && (
                <div className="flex items-center justify-between gap-3 pl-4 border-l-2 border-bambu-dark-tertiary">
                  <div>
                    <p className="text-sm text-white">{t('smartPlugs.autoOffPersistent')}</p>
                    <p className="text-xs text-table-secondary">{t('smartPlugs.autoOffPersistentDescription')}</p>
                  </div>
                  <Switch
                    ariaLabel={t('smartPlugs.autoOffPersistent')}
                    checked={plug.auto_off_persistent}
                      onChange={(e) => updateMutation.mutate({ auto_off_persistent: e.target.checked })}
                  />
                </div>
              )}

              {/* Delay Mode */}
              {plug.auto_off && (
                <div className="space-y-3 pl-4 border-l-2 border-bambu-dark-tertiary">
                  <div>
                    <p className="text-sm text-white mb-2">{t('smartPlugs.turnOffDelayMode')}</p>
                    <div className="flex gap-2">
                      <Button variant="unstyled"
                        onClick={() => updateMutation.mutate({ off_delay_mode: 'time' })}
                        className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                          plug.off_delay_mode === 'time'
                            ? 'bg-bambu-green text-black'
                            : 'bg-bambu-dark text-table-secondary hover:bg-secondary-action-hover hover:text-white'
                        }`}
                      >
                        <Clock className="w-4 h-4" />
                        {t('smartPlugs.time')}
                      </Button>
                      <Button variant="unstyled"
                        onClick={() => updateMutation.mutate({ off_delay_mode: 'temperature' })}
                        className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                          plug.off_delay_mode === 'temperature'
                            ? 'bg-bambu-green text-black'
                            : 'bg-bambu-dark text-table-secondary hover:bg-secondary-action-hover hover:text-white'
                        }`}
                      >
                        <Thermometer className="w-4 h-4" />
                        {t('smartPlugs.temp')}
                      </Button>
                    </div>
                  </div>

                  {plug.off_delay_mode === 'time' ? (
                    <div>
                      <label className="block text-xs text-table-secondary mb-1">{t('smartPlugs.delayMinutes')}</label>
                    <NumberField
                        min="1"
                        max="60"
                        value={plug.off_delay_minutes}
                        onChange={(e) => updateMutation.mutate({ off_delay_minutes: parseInt(e.target.value) || 5 })}
                        className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:border-bambu-green focus:outline-none"
                      />
                    </div>
                  ) : (
                    <div>
                      <label className="block text-xs text-table-secondary mb-1">{t('smartPlugs.tempThreshold')}</label>
                    <NumberField
                        min="30"
                        max="100"
                        value={plug.off_temp_threshold}
                        onChange={(e) => updateMutation.mutate({ off_temp_threshold: parseInt(e.target.value) || 70 })}
                        className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:border-bambu-green focus:outline-none"
                      />
                      <p className="text-xs text-table-secondary mt-1">{t('smartPlugs.tempThresholdDescription')}</p>
                    </div>
                  )}
                </div>
              )}

              {/* Auto Off After Drying (#1349) — independent of the
                  print-finish auto-off above. Uses its own delay because
                  the AMS chamber is hot post-cycle and users often want
                  more cooldown than the print-finish default. Fires when
                  any AMS attached to the linked printer finishes a dry
                  cycle. */}
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm text-white">{t('smartPlugs.autoOffAfterDrying')}</p>
                  <p className="text-xs text-table-secondary">{t('smartPlugs.autoOffAfterDryingDescription')}</p>
                </div>
                <Switch
                    ariaLabel={t('smartPlugs.autoOffAfterDrying')}
                    checked={plug.auto_off_after_drying}
                    onChange={(e) => updateMutation.mutate({ auto_off_after_drying: e.target.checked })}
                  />
              </div>

              {plug.auto_off_after_drying && (
                <div className="pl-4 border-l-2 border-bambu-dark-tertiary">
                  <label className="block text-xs text-table-secondary mb-1">{t('smartPlugs.delayAfterDryingMinutes')}</label>
                <NumberField
                    min="0"
                    max="120"
                    value={plug.off_delay_after_drying_minutes}
                    onChange={(e) => updateMutation.mutate({ off_delay_after_drying_minutes: parseInt(e.target.value) || 10 })}
                    className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:border-bambu-green focus:outline-none"
                  />
                </div>
              )}
                </>
              )}

              {/* Action Buttons */}
              <div className="flex gap-2 pt-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => onEdit(plug)}
                  className="flex-1"
                >
                  <Edit2 className="w-4 h-4" />
                  {t('smartPlugs.edit')}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setShowDeleteConfirm(true)}
                  className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
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
          title={t('smartPlugs.deleteSmartPlug')}
          message={t('smartPlugs.deleteConfirm', { name: plug.name })}
          confirmText={t('smartPlugs.delete')}
          variant="danger"
          onConfirm={() => {
            deleteMutation.mutate();
            setShowDeleteConfirm(false);
          }}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      )}

      {/* Power On Confirmation */}
      {showPowerOnConfirm && (
        <ConfirmModal
          title={t('smartPlugs.turnOnSmartPlug')}
          message={t('smartPlugs.turnOnConfirm', { name: plug.name })}
          confirmText={t('smartPlugs.turnOn')}
          variant="default"
          onConfirm={() => {
            controlMutation.mutate('on');
            setShowPowerOnConfirm(false);
          }}
          onCancel={() => setShowPowerOnConfirm(false)}
        />
      )}

      {/* Power Off Confirmation */}
      {showPowerOffConfirm && (
        <ConfirmModal
          title={t('smartPlugs.turnOffSmartPlug')}
          message={t('smartPlugs.turnOffConfirm', { name: plug.name })}
          confirmText={t('smartPlugs.turnOff')}
          variant="danger"
          onConfirm={() => {
            controlMutation.mutate('off');
            setShowPowerOffConfirm(false);
          }}
          onCancel={() => setShowPowerOffConfirm(false)}
        />
      )}
    </>
  );
}