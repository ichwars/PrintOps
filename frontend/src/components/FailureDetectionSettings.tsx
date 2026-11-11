import { useState, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, ScanEye, Check, X, AlertTriangle, Info } from 'lucide-react';
import { api, ApiError } from '../api/client';
import { Card, CardContent, CardHeader } from './Card';
import { Button } from './Button';
import { Checkbox, LegacySelect, NumberField, TextField } from './ui';
import { Toggle } from './Toggle';
import { useToast } from '../contexts/ToastContext';
import { aiDetectionClass, hasAiVerdict } from '../utils/aiDetection';
import { SECRET_PLACEHOLDER, selectPlaceholderOnFocus } from '../utils/secrets';

type TestResult = { ok: boolean; message: string } | null;

function readPrinterList(raw: string | null | undefined): number[] | null {
  if (!raw) return null;
  try {
    const ids: unknown = JSON.parse(raw);
    return Array.isArray(ids) ? ids.filter((id): id is number => Number.isInteger(id)) : [];
  } catch {
    return [];
  }
}

export function FailureDetectionSettings() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [enabled, setEnabled] = useState(false);
  const [mlUrl, setMlUrl] = useState('');
  const [mlToken, setMlToken] = useState('');
  const [sensitivity, setSensitivity] = useState<'low' | 'medium' | 'high'>('medium');
  const [action, setAction] = useState<'notify' | 'pause' | 'pause_and_off'>('notify');
  const [pollInterval, setPollInterval] = useState(10);
  const [enabledPrinters, setEnabledPrinters] = useState<number[] | null>(null); // null = all
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [initialized, setInitialized] = useState(false);
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
  });

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['obico-status'],
    queryFn: api.getObicoStatus,
    refetchInterval: 10000,
  });

  const { data: printers } = useQuery({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  });

  useEffect(() => {
    if (!settings) return;
    setEnabled(settings.obico_enabled ?? false);
    setMlUrl(settings.obico_ml_url ?? '');
    setMlToken(settings.obico_ml_token ?? '');
    setSensitivity(settings.obico_sensitivity ?? 'medium');
    setAction(settings.obico_action ?? 'notify');
    setPollInterval(settings.obico_poll_interval ?? 10);
    setEnabledPrinters(readPrinterList(settings.obico_enabled_printers));
    setInitialized(true);
  }, [settings]);

  const saveMutation = useMutation({
    mutationFn: (token: string) =>
      api.updateSettings({
        obico_enabled: enabled,
        obico_ml_url: mlUrl,
        obico_ml_token: token,
        obico_sensitivity: sensitivity,
        obico_action: action,
        obico_poll_interval: pollInterval,
        obico_enabled_printers: enabledPrinters === null ? '' : JSON.stringify(enabledPrinters),
      }),
    onError: async (error: Error) => {
      if (error instanceof ApiError && error.status === 400) {
        queryClient.invalidateQueries({ queryKey: ['printers'] });
        try {
          const stored = await api.getSettings();
          const updatedScope = readPrinterList(stored.obico_enabled_printers);
          if (JSON.stringify(updatedScope) !== JSON.stringify(enabledPrinters)) {
            setEnabledPrinters(current => current === enabledPrinters ? updatedScope : current);
            return;
          }
        } catch {
          // Keep the pending edit when the server cannot provide the current scope.
        }
      }
      showToast(t('settings.toast.saveFailed'), 'error');
    },
    onSuccess: (saved, submittedToken) => {
      if (saved?.obico_ml_token === SECRET_PLACEHOLDER) {
        setMlToken(current => current === submittedToken ? SECRET_PLACEHOLDER : current);
      }
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['obico-status'] });
      showToast(t('settings.toast.settingsSaved'));
    },
  });

  const hasUnsavedChanges = useMemo(() => {
    if (!initialized || !settings) return false;
    return (
      settings.obico_enabled !== enabled ||
      settings.obico_ml_url !== mlUrl ||
      (settings.obico_ml_token ?? '') !== mlToken ||
      settings.obico_sensitivity !== sensitivity ||
      settings.obico_action !== action ||
      settings.obico_poll_interval !== pollInterval ||
      JSON.stringify(readPrinterList(settings.obico_enabled_printers)) !== JSON.stringify(enabledPrinters)
    );
  }, [settings, initialized, enabled, mlUrl, mlToken, sensitivity, action, pollInterval, enabledPrinters]);

  const tokenNeedsReentry = mlToken === SECRET_PLACEHOLDER && mlUrl !== (settings?.obico_ml_url ?? '');

  // Auto-save on change (debounced)
  useEffect(() => {
    if (!hasUnsavedChanges || tokenNeedsReentry) return;
    autoSaveTimer.current = setTimeout(() => saveMutation.mutate(mlToken), 500);
    return () => {
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasUnsavedChanges, tokenNeedsReentry, enabled, mlUrl, mlToken, sensitivity, action, pollInterval, enabledPrinters]);

  const handleTest = async () => {
    setTestResult(null);
    try {
      const res = await api.testObicoConnection(mlUrl, mlToken);
      if (res.ok) {
        setTestResult({
          ok: true,
          message:
            res.auth_ok === null
              ? t('failureDetection.testSuccessTokenUnknown')
              : t('failureDetection.testSuccess'),
        });
      } else {
        setTestResult({
          ok: false,
          message: res.error || `HTTP ${res.status_code ?? '?'} — ${res.body ?? t('failureDetection.testFailed')}`,
        });
      }
    } catch (e: unknown) {
      setTestResult({ ok: false, message: e instanceof Error ? e.message : String(e) });
    }
  };

  const togglePrinter = (printerId: number, checked: boolean) => {
    if (enabledPrinters === null) {
      // switch from "all" to an explicit list
      const allIds = printers?.map((p) => p.id) ?? [];
      const next = checked ? allIds : allIds.filter((id) => id !== printerId);
      setEnabledPrinters(next);
      return;
    }
    if (checked) {
      setEnabledPrinters([...enabledPrinters, printerId]);
    } else {
      setEnabledPrinters(enabledPrinters.filter((id) => id !== printerId));
    }
  };

  return (
    <div className="flex flex-col lg:flex-row gap-4 lg:gap-6">
      <div className="space-y-3 flex-1 lg:max-w-xl">
        <Card id="card-fd-ml">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ScanEye className="w-5 h-5 text-bambu-green" />
                <h2 className="text-lg font-semibold text-white">{t('failureDetection.title')}</h2>
              </div>
              <Toggle checked={enabled} onChange={setEnabled} />
            </div>
            <p className="text-sm text-bambu-gray mt-2">{t('failureDetection.description')}</p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm text-bambu-gray mb-1">
                {t('failureDetection.mlUrl')}
              </label>
              <div className="flex gap-2">
                <TextField
                  type="text"
                  value={mlUrl}
                  onChange={(e) => setMlUrl(e.target.value)}
                  placeholder="http://192.168.1.10:3333"
                  className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm"
                  disabled={!enabled}
                />
                <Button
                  onClick={handleTest}
                  disabled={!mlUrl || tokenNeedsReentry || saveMutation.isPending}
                  variant="secondary"
                >
                  {t('failureDetection.test')}
                </Button>
              </div>
              <p className="text-xs text-bambu-gray mt-1">{t('failureDetection.mlUrlHint')}</p>
              {testResult && (
                <div
                  className={`flex items-start gap-2 mt-2 text-sm ${
                    testResult.ok ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'
                  }`}
                >
                  {testResult.ok ? <Check className="w-4 h-4 mt-0.5" /> : <X className="w-4 h-4 mt-0.5" />}
                  <span>{testResult.message}</span>
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm text-bambu-gray mb-1">
                {t('failureDetection.mlToken')}
              </label>
              <TextField
                type="password"
                value={mlToken}
                onFocus={selectPlaceholderOnFocus}
                onChange={(e) => setMlToken(e.target.value)}
                placeholder={t('failureDetection.mlTokenPlaceholder')}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm"
                disabled={!enabled}
              />
              <p className="text-xs text-bambu-gray mt-1">{t(tokenNeedsReentry ? 'common.secretReenter' : 'failureDetection.mlTokenHint')}</p>
            </div>

            <div>
              <label className="block text-sm text-bambu-gray mb-1">
                {t('failureDetection.sensitivity')}
              </label>
              <LegacySelect
                value={sensitivity}
                onChange={(e) => setSensitivity(e.target.value as 'low' | 'medium' | 'high')}
                disabled={!enabled}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm"
              >
                <option value="low">{t('failureDetection.sensitivityLow')}</option>
                <option value="medium">{t('failureDetection.sensitivityMedium')}</option>
                <option value="high">{t('failureDetection.sensitivityHigh')}</option>
              </LegacySelect>
              <p className="text-xs text-bambu-gray mt-1">{t('failureDetection.sensitivityHint')}</p>
            </div>

            <div>
              <label className="block text-sm text-bambu-gray mb-1">
                {t('failureDetection.action')}
              </label>
              <LegacySelect
                value={action}
                onChange={(e) => setAction(e.target.value as 'notify' | 'pause' | 'pause_and_off')}
                disabled={!enabled}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm"
              >
                <option value="notify">{t('failureDetection.actionNotify')}</option>
                <option value="pause">{t('failureDetection.actionPause')}</option>
                <option value="pause_and_off">{t('failureDetection.actionPauseOff')}</option>
              </LegacySelect>
            </div>

            <div>
              <label className="block text-sm text-bambu-gray mb-1">
                {t('failureDetection.pollInterval')}
              </label>
              <NumberField
                value={pollInterval}
                onChange={(e) => setPollInterval(Math.max(5, Math.min(120, Number(e.target.value) || 10)))}
                min={5}
                max={120}
                disabled={!enabled}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm"
              />
              <p className="text-xs text-bambu-gray mt-1">{t('failureDetection.pollIntervalHint')}</p>
            </div>

            {status && !status.external_url_configured && enabled && (
              <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700 rounded text-sm text-amber-800 dark:text-amber-200">
                <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <div>
                  <div className="font-medium">{t('failureDetection.externalUrlMissing')}</div>
                  <div className="text-xs mt-1">{t('failureDetection.externalUrlHint')}</div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card id="card-fd-perprinter">
          <CardHeader>
            <h2 className="text-lg font-semibold text-white">{t('failureDetection.perPrinterTitle')}</h2>
            <p className="text-sm text-bambu-gray mt-1">{t('failureDetection.perPrinterHint')}</p>
          </CardHeader>
          <CardContent className="space-y-2">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={enabledPrinters === null}
                onChange={(e) => setEnabledPrinters(e.target.checked ? null : printers?.map((p) => p.id) ?? [])}
                disabled={!enabled}
              />
              <span className="text-white">{t('failureDetection.monitorAll')}</span>
            </label>
            {enabledPrinters !== null && printers && (
              <div className="pl-5 space-y-1 border-l border-gray-700">
                {printers.map((p) => (
                  <label key={p.id} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={enabledPrinters.includes(p.id)}
                      onChange={(e) => togglePrinter(p.id, e.target.checked)}
                      disabled={!enabled}
                    />
                    <span className="text-white">{p.name}</span>
                  </label>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-3 flex-1 lg:max-w-xl">
        <Card id="card-fd-status">
          <CardHeader>
            <h2 className="text-lg font-semibold text-white">{t('failureDetection.statusTitle')}</h2>
          </CardHeader>
          <CardContent>
            {!status ? (
              <div className="flex items-center gap-2 text-bambu-gray">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{t('common.loading')}</span>
              </div>
            ) : (
              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-bambu-gray">{t('failureDetection.serviceRunning')}</span>
                  <span className={status.is_running ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}>
                    {status.is_running ? t('common.yes') : t('common.no')}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-bambu-gray">{t('failureDetection.thresholds')}</span>
                  <span className="text-white font-mono">
                    {status.thresholds.low.toFixed(2)} / {status.thresholds.high.toFixed(2)}
                  </span>
                </div>
                {status.thresholds.pause != null && (
                  <div className="flex justify-between">
                    <span className="text-bambu-gray">{t('failureDetection.pauseThreshold')}</span>
                    <span className="text-white font-mono">{status.thresholds.pause.toFixed(2)}</span>
                  </div>
                )}
                {status.last_error && (
                  <div className="flex items-start gap-2 text-red-700 dark:text-red-400">
                    <X className="w-4 h-4 mt-0.5 flex-shrink-0" />
                    <span className="break-words">{status.last_error}</span>
                  </div>
                )}
                <div>
                  <div className="text-bambu-gray mb-1">{t('failureDetection.activePrinters')}</div>
                  {Object.keys(status.per_printer).length === 0 ? (
                    <div className="text-bambu-gray italic text-xs">{t('failureDetection.noActivePrints')}</div>
                  ) : (
                    <div className="space-y-1">
                      {Object.entries(status.per_printer).map(([pid, info]) => {
                        const printer = printers?.find((p) => String(p.id) === pid);
                        const classification = aiDetectionClass(info);
                        const colorClass =
                          classification === 'failure'
                            ? 'text-red-700 dark:text-red-400'
                            : classification === 'warning'
                              ? 'text-amber-700 dark:text-amber-400'
                              : classification === 'safe'
                                ? 'text-green-700 dark:text-green-400'
                                : 'text-bambu-gray';
                        return (
                          <div key={pid} className="space-y-0.5">
                            <div className="flex justify-between">
                              <span className="text-white">{printer?.name ?? `Printer ${pid}`}</span>
                              <span className={`font-mono ${colorClass}`}>
                                {t(`printers.aiDetection.${classification}`)}
                                {hasAiVerdict(classification) && ` (${info.score.toFixed(3)}, ${info.frame_count}f)`}
                              </span>
                            </div>
                            {info.error && (
                              <div className="break-words text-xs text-red-700 dark:text-red-400">{info.error}</div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card id="card-fd-history">
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">{t('failureDetection.historyTitle')}</h2>
              <Button variant="unstyled" onClick={() => refetchStatus()} className="text-xs text-bambu-gray hover:text-white">
                {t('common.refresh')}
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {!status || status.history.length === 0 ? (
              <div className="flex items-center gap-2 text-bambu-gray text-sm">
                <Info className="w-4 h-4" />
                <span>{t('failureDetection.noHistory')}</span>
              </div>
            ) : (
              <div className="space-y-1 max-h-96 overflow-y-auto text-xs font-mono">
                {status.history.map((ev, idx) => {
                  const printer = printers?.find((p) => p.id === ev.printer_id);
                  const colorClass =
                    ev.class === 'failure'
                      ? 'text-red-700 dark:text-red-400'
                      : ev.class === 'warning'
                        ? 'text-amber-700 dark:text-amber-400'
                        : 'text-bambu-gray';
                  return (
                    <div key={idx} className="flex justify-between gap-2 py-1 border-b border-gray-800">
                      <span className="text-bambu-gray">{new Date(ev.timestamp).toLocaleTimeString()}</span>
                      <span className="text-white truncate">{printer?.name ?? `#${ev.printer_id}`}</span>
                      <span className={colorClass}>
                        {ev.class} {ev.score.toFixed(3)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
