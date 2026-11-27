import { useState, useCallback, useRef, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useOutletContext } from 'react-router';
import { useTranslation } from 'react-i18next';
import type { SpoolBuddyOutletContext } from '../../components/spoolbuddy/SpoolBuddyLayout';
import { spoolbuddyApi, type SpoolBuddyDevice } from '../../api/client';
import { DiagnosticModal } from '../../components/spoolbuddy/DiagnosticModal';
import { FileText, Wand2, Zap } from 'lucide-react';
import { parseUTCDate } from '../../utils/date';
import { Slider, TextField } from '../../components/ui';
import { useKioskDevice } from '../../hooks/useKioskDevice';


function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '-';
  const d = parseUTCDate(iso);
  if (!d) return '-';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

const BLANK_OPTIONS = [
  { label: 'Off', value: 0 },
  { label: '1m', value: 60 },
  { label: '2m', value: 120 },
  { label: '5m', value: 300 },
  { label: '10m', value: 600 },
  { label: '30m', value: 1800 },
];

// --- Device Tab ---

function DeviceTab({ device }: { device: SpoolBuddyDevice }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [diagnosticOpen, setDiagnosticOpen] = useState<'nfc' | 'scale' | 'read_tag' | null>(null);
  const [backendUrl, setBackendUrl] = useState('');
  const [apiToken, setApiToken] = useState('');
  const [systemBusy, setSystemBusy] = useState(false);
  const [systemMsg, setSystemMsg] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);
  const [restartOffered, setRestartOffered] = useState(false);
  const configPending = device.pending_command === 'apply_system_config';

  useEffect(() => {
    if (!backendUrl && device.backend_url) {
      setBackendUrl(device.backend_url);
    }
  }, [device.backend_url, backendUrl]);

  const saveConfig = async () => {
    if (!backendUrl.trim()) {
      setSystemMsg({ type: 'error', text: t('spoolbuddy.settings.systemFieldsRequired', 'Backend URL is required.') });
      return;
    }

    setSystemBusy(true);
    setSystemMsg(null);
    try {
      await spoolbuddyApi.updateSystemConfig(
        device.device_id,
        backendUrl.trim(),
        apiToken.trim() || undefined
      );
      const devicesKey = ['spoolbuddy-devices'];
      await queryClient.cancelQueries({ queryKey: devicesKey });
      queryClient.setQueryData<SpoolBuddyDevice[]>(devicesKey, (devices) => devices?.map((row) =>
        row.device_id === device.device_id ? { ...row, pending_command: 'apply_system_config' } : row
      ));
      setRestartOffered(true);
      setSystemMsg({ type: 'ok', text: t('spoolbuddy.settings.systemQueued', 'Config queued.') });
      await queryClient.invalidateQueries({ queryKey: devicesKey });
    } catch (e) {
      setSystemMsg({ type: 'error', text: e instanceof Error ? e.message : t('common.error', 'Error') });
    } finally {
      setSystemBusy(false);
    }
  };

  const restartDaemon = async () => {
    if (systemBusy || configPending) return;
    setSystemBusy(true);
    try {
      await spoolbuddyApi.systemCommand(device.device_id, 'restart_daemon');
      setRestartOffered(false);
      setSystemMsg({ type: 'ok', text: t('spoolbuddy.settings.systemRestartQueued', 'Daemon restart queued.') });
    } catch (e) {
      setSystemMsg({ type: 'error', text: e instanceof Error ? e.message : t('common.error', 'Error') });
    } finally {
      setSystemBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      {/* NFC Reader + Device Info side by side */}
      <div className="grid grid-cols-2 gap-2">
        {/* NFC Reader */}
        <div className="bg-bambu-dark-secondary rounded-lg p-3">
          <h3 className="text-sm font-semibold text-bambu-gray-light mb-2">
            {t('spoolbuddy.settings.nfcReader', 'NFC Reader')}
          </h3>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-bambu-gray">{t('spoolbuddy.settings.type', 'Type')}</span>
              <span className="text-bambu-gray-light font-mono">
                {device.nfc_reader_type || 'N/A'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-bambu-gray">{t('spoolbuddy.settings.connection', 'Connection')}</span>
              <span className="text-bambu-gray-light font-mono">
                {device.nfc_connection || 'N/A'}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-bambu-gray">{t('spoolbuddy.status.status', 'Status')}</span>
              <div className="flex items-center gap-1.5">
                <div className={`w-2 h-2 rounded-full ${
                  device.nfc_ok ? 'bg-green-500' : device.nfc_reader_type ? 'bg-red-500' : 'bg-bambu-dark-tertiary'
                }`} />
                <span className={
                  device.nfc_ok ? 'text-green-400' : device.nfc_reader_type ? 'text-red-400' : 'text-bambu-gray'
                }>
                  {device.nfc_ok
                    ? t('spoolbuddy.status.nfcReady', 'Ready')
                    : device.nfc_reader_type
                      ? t('common.error', 'Error')
                      : t('spoolbuddy.settings.notConnected', 'N/A')}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Device Info */}
        <div className="bg-bambu-dark-secondary rounded-lg p-3">
          <h3 className="text-sm font-semibold text-bambu-gray-light mb-2">
            {t('spoolbuddy.settings.deviceInfo', 'Device Info')}
          </h3>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-bambu-gray">{t('spoolbuddy.settings.hostname', 'Host')}</span>
              <span className="text-bambu-gray-light truncate ml-2">{device.hostname}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-bambu-gray">IP</span>
              <span className="text-bambu-gray-light">{device.ip_address}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-bambu-gray">{t('spoolbuddy.settings.uptime', 'Uptime')}</span>
              <span className="text-bambu-gray-light">{formatUptime(device.uptime_s)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-bambu-gray">ID</span>
              <span className="text-bambu-gray font-mono truncate ml-2">{device.device_id}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Backend/Auth + Diagnostics side by side */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {/* Backend/Auth Config */}
        <div className="bg-bambu-dark-secondary rounded-lg p-3 space-y-2">
          <h3 className="text-sm font-semibold text-bambu-gray-light">
            {t('spoolbuddy.settings.systemConfig', 'Backend & Auth')}
          </h3>
          <TextField
            value={backendUrl}
            onChange={(e) => setBackendUrl(e.target.value)}
            placeholder="http://192.168.1.100:5000"
            className="w-full px-2 py-1.5 rounded bg-bambu-dark border border-bambu-dark-tertiary text-white text-xs"
          />
          <div className="flex flex-col gap-2 sm:flex-row">
            <TextField
              type="password"
              value={apiToken}
              onChange={(e) => setApiToken(e.target.value)}
              placeholder={t('spoolbuddy.settings.apiTokenPlaceholder', 'API token')}
              className="min-w-0 flex-1 px-2 py-1.5 rounded bg-bambu-dark border border-bambu-dark-tertiary text-white text-xs"
            />
            <button
              onClick={saveConfig}
              disabled={systemBusy}
              className="px-3 py-1.5 rounded bg-green-700 hover:bg-green-600 disabled:bg-bambu-dark-tertiary text-xs font-medium text-white"
            >
              {t('spoolbuddy.settings.saveConfig', 'Save')}
            </button>
          </div>
          {systemMsg && (
            <div className={`text-xs ${systemMsg.type === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
              {systemMsg.text}
            </div>
          )}
          {restartOffered && (
            <button
              onClick={restartDaemon}
              disabled={systemBusy || configPending}
              className="px-3 py-1.5 rounded bg-bambu-dark-tertiary hover:bg-bambu-dark-tertiary disabled:opacity-50 text-xs font-medium text-white"
            >
              {t('spoolbuddy.quickMenu.restartDaemon', 'Restart Daemon')}
            </button>
          )}
        </div>

        {/* Diagnostic Buttons */}
        <div className="bg-bambu-dark-secondary rounded-lg p-3 flex flex-col gap-2">
          <button
            onClick={() => setDiagnosticOpen('nfc')}
            className="flex-1 bg-blue-700 hover:bg-blue-600 transition-colors rounded-lg p-2 flex items-center gap-2"
          >
            <Wand2 className="w-4 h-4 text-blue-300 shrink-0" />
            <span className="text-xs font-medium text-blue-100">
              {t('spoolbuddy.settings.nfcDiagnostic', 'NFC Diagnostic')}
            </span>
          </button>
          <button
            onClick={() => setDiagnosticOpen('scale')}
            className="flex-1 bg-yellow-700 hover:bg-yellow-600 transition-colors rounded-lg p-2 flex items-center gap-2"
          >
            <Zap className="w-4 h-4 text-yellow-300 shrink-0" />
            <span className="text-xs font-medium text-yellow-100">
              {t('spoolbuddy.settings.scaleDiagnostic', 'Scale Diagnostic')}
            </span>
          </button>
          <button
            onClick={() => setDiagnosticOpen('read_tag')}
            className="flex-1 bg-emerald-700 hover:bg-emerald-600 transition-colors rounded-lg p-2 flex items-center gap-2"
          >
            <FileText className="w-4 h-4 text-emerald-300 shrink-0" />
            <span className="text-xs font-medium text-emerald-100">
              {t('spoolbuddy.settings.readTagDiagnostic', 'Read Tag')}
            </span>
          </button>
        </div>
      </div>

      {/* Diagnostic Modal */}
      {diagnosticOpen && device && (
        <DiagnosticModal
          type={diagnosticOpen}
          deviceId={device.device_id}
          onClose={() => setDiagnosticOpen(null)}
        />
      )}
    </div>
  );
}

// --- Display Tab ---

function DisplayTab({ device, onBrightnessChange }: {
  device: SpoolBuddyDevice;
  onBrightnessChange: (value: number) => void;
}) {
  const { t } = useTranslation();
  const [brightness, setBrightness] = useState(device.display_brightness);
  const [blankTimeout, setBlankTimeout] = useState(device.display_blank_timeout);
  const [saved, setSaved] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const savedTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Sync local state when device data updates from server
  useEffect(() => {
    setBrightness(device.display_brightness);
    setBlankTimeout(device.display_blank_timeout);
  }, [device.display_brightness, device.display_blank_timeout]);

  const showSaved = useCallback(() => {
    setSaved(true);
    if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
    savedTimerRef.current = setTimeout(() => setSaved(false), 1500);
  }, []);

  const sendDisplayUpdate = useCallback((b: number, bt: number) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      spoolbuddyApi.updateDisplay(device.device_id, b, bt)
        .then(() => showSaved())
        .catch((e) => console.error('Failed to update display:', e));
    }, 300);
  }, [device.device_id, showSaved]);

  const handleBrightnessChange = (value: number) => {
    setBrightness(value);
    onBrightnessChange(value);  // Instant layout update
    sendDisplayUpdate(value, blankTimeout);
  };

  const handleBlankTimeoutChange = (value: number) => {
    setBlankTimeout(value);
    sendDisplayUpdate(brightness, value);
  };

  return (
    <div className="space-y-4">
      {/* Brightness */}
      <div className="bg-bambu-dark-secondary rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-bambu-gray-light">
            {t('spoolbuddy.settings.brightness', 'Brightness')}
          </h3>
          {saved && (
            <span className="text-xs text-green-400 flex items-center gap-1 animate-pulse">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              {t('spoolbuddy.settings.saved', 'Saved')}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <svg className="w-4 h-4 text-bambu-gray flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
          <Slider
            min={0}
            max={100}
            value={brightness}
            onChange={(e) => handleBrightnessChange(parseInt(e.target.value))}
            className="flex-1 h-2 bg-bambu-dark-tertiary rounded-lg appearance-none cursor-pointer accent-green-500"
          />
          <span className="text-sm font-mono text-bambu-gray w-10 text-right">{brightness}%</span>
        </div>
        {!device.has_backlight && (
          <p className="text-xs text-bambu-gray-dark mt-2">
            {t('spoolbuddy.settings.noBacklight', 'No DSI backlight detected. Brightness control requires a DSI display.')}
          </p>
        )}
      </div>

      {/* Screen blank timeout */}
      <div className="bg-bambu-dark-secondary rounded-lg p-4">
        <h3 className="text-sm font-semibold text-bambu-gray-light mb-1">
          {t('spoolbuddy.settings.screenBlank', 'Screen Blank Timeout')}
        </h3>
        <p className="text-xs text-bambu-gray mb-3">
          {t('spoolbuddy.settings.screenBlankDesc', 'Screen turns off after inactivity. Touch to wake.')}
        </p>
        <div className="grid grid-cols-3 gap-2">
          {BLANK_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => handleBlankTimeoutChange(opt.value)}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors min-h-[40px] ${
                blankTimeout === opt.value
                  ? 'bg-green-600 text-white'
                  : 'bg-bambu-dark-tertiary text-bambu-gray-light hover:bg-bambu-dark-tertiary'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <p className="text-xs text-bambu-gray-dark text-center">
        {t('spoolbuddy.settings.displayNote', 'Brightness is applied as a software filter.')}
      </p>
    </div>
  );
}

// --- Scale Tab ---

function StepIndicator({ step, labels }: { step: 'tare' | 'weight'; labels: { tare: string; weight: string } }) {
  return (
    <div className="flex flex-col items-center w-16 shrink-0 pt-1">
      {/* Step 1 circle */}
      <div className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold ${
        step === 'tare'
          ? 'bg-green-600 text-white'
          : 'bg-green-600/20 text-green-400'
      }`}>
        {step === 'weight' ? (
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        ) : '1'}
      </div>
      <span className={`text-[10px] mt-0.5 ${step === 'tare' ? 'text-green-400 font-medium' : 'text-green-400/60'}`}>
        {labels.tare}
      </span>

      {/* Connector line */}
      <div className={`w-px h-5 my-1 ${step === 'weight' ? 'bg-green-600/40' : 'bg-bambu-dark-tertiary'}`} />

      {/* Step 2 circle */}
      <div className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold ${
        step === 'weight'
          ? 'bg-green-600 text-white'
          : 'bg-bambu-dark-tertiary text-bambu-gray'
      }`}>
        2
      </div>
      <span className={`text-[10px] mt-0.5 ${step === 'weight' ? 'text-green-400 font-medium' : 'text-bambu-gray-dark'}`}>
        {labels.weight}
      </span>
    </div>
  );
}

function ScaleTab({ device, weight, weightStable, rawAdc }: {
  device: SpoolBuddyDevice;
  weight: number | null;
  weightStable: boolean;
  rawAdc: number | null;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [calStep, setCalStep] = useState<'idle' | 'tare' | 'weight'>('idle');
  const [knownWeight, setKnownWeight] = useState('500');
  const [tareRawAdc, setTareRawAdc] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ type: 'ok' | 'error'; msg: string } | null>(null);
  // Snapshot of device.last_calibrated_at taken when a tare is dispatched.
  // The completion watcher below polls the device list and flips the banner
  // to "Tare complete!" (or "Tare timed out") once the daemon writes back
  // a new last_calibrated_at. Without this watcher the banner just sat at
  // "Waiting for device..." forever (#1536).
  const [awaitingTareSince, setAwaitingTareSince] = useState<{ snapshot: string | null; startedAtMs: number } | null>(null);
  const dismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear any pending auto-dismiss when status changes manually or on unmount.
  useEffect(() => {
    return () => {
      if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    };
  }, []);

  const scheduleStatusDismiss = useCallback((ms: number) => {
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    dismissTimerRef.current = setTimeout(() => setStatus(null), ms);
  }, []);

  // Tare-completion watcher: aggressively re-fetch device data while waiting,
  // detect when last_calibrated_at advances past the snapshot, then settle
  // the banner. Fails open on a 15s timeout so a dead daemon doesn't leave
  // the user staring at "Waiting for device..." indefinitely.
  useEffect(() => {
    if (!awaitingTareSince) return;
    const TARE_TIMEOUT_MS = 15000;
    const POLL_INTERVAL_MS = 1000;
    const elapsed = () => Date.now() - awaitingTareSince.startedAtMs;

    const pollHandle = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ['spoolbuddy-devices'] });
    }, POLL_INTERVAL_MS);
    const timeoutHandle = setTimeout(() => {
      setAwaitingTareSince(null);
      setStatus({
        type: 'error',
        msg: t('spoolbuddy.settings.tareTimedOut', 'Tare timed out — is the SpoolBuddy daemon running?'),
      });
      scheduleStatusDismiss(5000);
    }, Math.max(0, TARE_TIMEOUT_MS - elapsed()));

    return () => {
      clearInterval(pollHandle);
      clearTimeout(timeoutHandle);
    };
  }, [awaitingTareSince, queryClient, t, scheduleStatusDismiss]);

  // When fresh device data arrives, check whether last_calibrated_at moved.
  useEffect(() => {
    if (!awaitingTareSince) return;
    const current = device?.last_calibrated_at ?? null;
    if (current !== awaitingTareSince.snapshot) {
      setAwaitingTareSince(null);
      setStatus({ type: 'ok', msg: t('spoolbuddy.settings.tareComplete', 'Tare complete!') });
      scheduleStatusDismiss(3000);
    }
  }, [device?.last_calibrated_at, awaitingTareSince, t, scheduleStatusDismiss]);

  const numpadPress = (key: string) => {
    if (key === 'backspace') {
      setKnownWeight((v) => v.slice(0, -1) || '');
    } else if (key === '.' && !knownWeight.includes('.')) {
      setKnownWeight((v) => v + '.');
    } else if (key >= '0' && key <= '9') {
      setKnownWeight((v) => (v === '0' ? key : v + key));
    }
  };

  const handleTare = async () => {
    setBusy(true);
    setStatus(null);
    if (dismissTimerRef.current) {
      clearTimeout(dismissTimerRef.current);
      dismissTimerRef.current = null;
    }
    const snapshot = device?.last_calibrated_at ?? null;
    try {
      await spoolbuddyApi.tare(device.device_id);
      setStatus({ type: 'ok', msg: t('spoolbuddy.settings.tareSet', 'Tare command sent. Waiting for device...') });
      setAwaitingTareSince({ snapshot, startedAtMs: Date.now() });
    } catch {
      setStatus({ type: 'error', msg: t('spoolbuddy.settings.tareFailed', 'Failed to send tare command') });
      scheduleStatusDismiss(5000);
    } finally {
      setBusy(false);
    }
  };

  const handleCalStep = async () => {
    if (calStep === 'tare') {
      setBusy(true);
      setStatus(null);
      try {
        setTareRawAdc(rawAdc);
        await spoolbuddyApi.tare(device.device_id);
        setStatus({ type: 'ok', msg: t('spoolbuddy.settings.zeroSet', 'Zero point set. Place known weight on scale.') });
        setCalStep('weight');
      } catch {
        setStatus({ type: 'error', msg: t('spoolbuddy.settings.tareFailed', 'Failed to send tare command') });
      } finally {
        setBusy(false);
      }
    } else if (calStep === 'weight') {
      const weightNum = parseFloat(knownWeight);
      if (rawAdc === null || !weightNum || weightNum <= 0) return;
      setBusy(true);
      setStatus(null);
      try {
        await spoolbuddyApi.setCalibrationFactor(device.device_id, weightNum, rawAdc, tareRawAdc ?? undefined);
        setStatus({ type: 'ok', msg: t('spoolbuddy.settings.calibrationDone', 'Calibration complete!') });
        scheduleStatusDismiss(3000);
        setCalStep('idle');
      } catch {
        setStatus({ type: 'error', msg: t('spoolbuddy.settings.calibrationFailed', 'Calibration failed') });
        scheduleStatusDismiss(5000);
      } finally {
        setBusy(false);
      }
    }
  };

  // --- Idle state: weight card + buttons ---
  if (calStep === 'idle') {
    return (
      <div className="flex flex-col h-full">
        {/* Weight + info card */}
        <div className="bg-bambu-dark-secondary rounded-lg p-3 mb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${weightStable ? 'bg-green-500' : 'bg-amber-500 animate-pulse'}`} />
              <span className="text-lg font-mono text-bambu-gray-light">
                {weight !== null ? `${weight.toFixed(1)} g` : '-- g'}
              </span>
            </div>
            <div className="text-xs text-bambu-gray text-right">
              <span>{t('spoolbuddy.settings.tareOffset', 'Tare')}: {device.tare_offset}</span>
              <span className="mx-1.5">&middot;</span>
              <span>{t('spoolbuddy.settings.calFactor', 'Factor')}: {device.calibration_factor.toFixed(2)}</span>
            </div>
          </div>
          {device.last_calibrated_at && (
            <div className="text-xs text-bambu-gray-dark mt-1">
              {t('spoolbuddy.settings.lastCalibrated', 'Last calibrated')}: {formatDateTime(device.last_calibrated_at)}
            </div>
          )}
        </div>

        {/* Status message */}
        {status && (
          <div className={`rounded-lg px-3 py-2 mb-3 text-sm ${
            status.type === 'ok' ? 'bg-green-900/30 text-green-300 border border-green-800' : 'bg-red-900/30 text-red-300 border border-red-800'
          }`}>
            {status.msg}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-2">
          <button
            onClick={handleTare}
            disabled={busy}
            className="flex-1 px-4 py-2.5 rounded-lg text-sm font-medium bg-bambu-dark-tertiary text-bambu-gray-light hover:bg-bambu-dark-tertiary disabled:opacity-40 transition-colors min-h-[44px] flex items-center justify-center gap-2"
          >
            {busy && (
              <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            )}
            {t('spoolbuddy.weight.tare', 'Tare')}
          </button>
          <button
            onClick={() => { setCalStep('tare'); setStatus(null); }}
            className="flex-1 px-4 py-2.5 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700 transition-colors min-h-[44px]"
          >
            {t('spoolbuddy.weight.calibrate', 'Calibrate')}
          </button>
        </div>
      </div>
    );
  }

  // --- Calibration wizard: step indicator left + content right ---
  return (
    <div className="flex gap-3">
      {/* Left: step indicator */}
      <StepIndicator step={calStep} labels={{ tare: t('spoolbuddy.weight.tare', 'Tare'), weight: t('spoolbuddy.settings.knownWeight', 'Known weight') }} />

      {/* Right: content */}
      <div className="flex-1 min-w-0">
        {/* Live weight bar */}
        <div className="flex items-center gap-2 bg-bambu-dark-secondary rounded-lg px-3 py-1.5 mb-1.5">
          <div className={`w-2 h-2 rounded-full shrink-0 ${weightStable ? 'bg-green-500' : 'bg-amber-500 animate-pulse'}`} />
          <span className="text-sm font-mono text-bambu-gray-light">
            {weight !== null ? `${weight.toFixed(1)} g` : '-- g'}
          </span>
          <span className={`text-xs ml-auto ${weightStable ? 'text-green-400' : 'text-amber-400'}`}>
            {weightStable ? t('spoolbuddy.settings.stable', 'Stable') : t('spoolbuddy.settings.settling', 'Settling...')}
          </span>
        </div>

        {/* Status message */}
        {status && (
          <div className={`rounded-lg px-3 py-1.5 mb-1.5 text-xs ${
            status.type === 'ok' ? 'bg-green-900/30 text-green-300 border border-green-800' : 'bg-red-900/30 text-red-300 border border-red-800'
          }`}>
            {status.msg}
          </div>
        )}

        {/* Step content */}
        {calStep === 'tare' ? (
          <p className="text-sm text-bambu-gray-light mb-3">
            {t('spoolbuddy.settings.calStep1', 'Remove all items from the scale and press Set Zero.')}
          </p>
        ) : (
          <>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-xs text-bambu-gray shrink-0">{t('spoolbuddy.settings.knownWeight', 'Known weight')}</span>
              <div className="flex-1 bg-bambu-dark border border-bambu-dark-tertiary rounded px-3 py-1 text-right text-lg font-mono text-white">
                {knownWeight || '0'}<span className="text-bambu-gray ml-1">g</span>
              </div>
            </div>
            <div className="grid grid-cols-4 gap-1 mb-1.5">
              {['7','8','9','backspace','4','5','6','.','1','2','3','0'].map((key) => (
                <button
                  key={key}
                  onClick={() => numpadPress(key)}
                  className={`rounded text-lg font-medium transition-colors h-[48px] active:scale-95 ${
                    key === 'backspace'
                      ? 'bg-bambu-dark-tertiary text-bambu-gray-light hover:bg-bambu-dark-tertiary'
                      : 'bg-bambu-dark-secondary text-white hover:bg-bambu-dark-tertiary border border-bambu-dark-tertiary'
                  }`}
                >
                  {key === 'backspace' ? '\u232B' : key}
                </button>
              ))}
            </div>
          </>
        )}

        {/* Action buttons */}
        <div className="flex gap-2">
          <button
            onClick={() => { setCalStep('idle'); setStatus(null); }}
            className="flex-1 px-4 py-2 rounded-lg text-sm bg-bambu-dark-tertiary text-bambu-gray-light hover:bg-bambu-dark-tertiary transition-colors h-[40px]"
          >
            {t('common.cancel', 'Cancel')}
          </button>
          <button
            onClick={handleCalStep}
            disabled={busy}
            className="flex-1 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 transition-colors h-[40px] flex items-center justify-center gap-2"
          >
            {busy && (
              <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            )}
            {calStep === 'tare' ? t('spoolbuddy.settings.setZero', 'Set Zero') : t('spoolbuddy.settings.calibrateNow', 'Calibrate')}
          </button>
        </div>
      </div>
    </div>
  );
}

// --- Updates Tab ---

function UpdatesTab({ device }: { device: SpoolBuddyDevice }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState<'checking' | 'applying' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sshExpanded, setSSHExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const isUpdating = device.update_status === 'pending' || device.update_status === 'updating';

  // When applying succeeds and device picks up the update, keep showing busy
  useEffect(() => {
    if (isUpdating && busy === 'applying') {
      setBusy(null); // device has picked it up, isUpdating takes over the UI
    }
  }, [isUpdating, busy]);

  // Reload the page when daemon comes back online after an update
  useEffect(() => {
    const handleOnline = () => {
      if (isUpdating) {
        // Daemon re-registered — reload to get fresh version + state
        setTimeout(() => window.location.reload(), 1000);
      }
    };
    window.addEventListener('spoolbuddy-online', handleOnline);
    return () => window.removeEventListener('spoolbuddy-online', handleOnline);
  }, [isUpdating]);

  const { data: updateResult, refetch } = useQuery({
    queryKey: ['spoolbuddy-update-check', device.device_id],
    queryFn: () => spoolbuddyApi.checkDaemonUpdate(device.device_id),
    staleTime: 0,
  });

  const { data: sshKeyData } = useQuery({
    queryKey: ['spoolbuddy-ssh-key'],
    queryFn: () => spoolbuddyApi.getSSHPublicKey(),
    enabled: sshExpanded,
    staleTime: Infinity,
  });

  const checkForUpdates = async () => {
    setBusy('checking');
    setError(null);
    try {
      await refetch();
    } finally {
      setBusy(null);
    }
  };

  const applyUpdate = async () => {
    setBusy('applying');
    setError(null);
    try {
      await spoolbuddyApi.triggerUpdate(device.device_id);
      // Don't clear busy — keep showing spinner until isUpdating takes over or timeout
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to trigger update');
      setBusy(null);
    }
  };

  const showSpinner = busy != null || isUpdating;

  const copyKey = () => {
    if (sshKeyData?.public_key) {
      navigator.clipboard.writeText(sshKeyData.public_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const displayVersion = device.firmware_version
    || (updateResult?.current_version && updateResult.current_version !== '0.0.0' ? updateResult.current_version : null);

  return (
    <div className="space-y-3">
      {/* Version + Update status + Check — single card */}
      <div className="bg-bambu-dark-secondary rounded-lg p-3 space-y-3">
        {/* Version row */}
        <div className="flex justify-between items-center text-sm">
          <span className="text-bambu-gray">{t('spoolbuddy.settings.currentVersion', 'Current Version')}</span>
          <span className="text-bambu-gray-light font-mono">
            {displayVersion || (
              <span className="text-bambu-gray italic text-xs">{t('spoolbuddy.settings.versionPending', 'Waiting for daemon...')}</span>
            )}
          </span>
        </div>

        {/* Status / progress row */}
        {showSpinner ? (
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 animate-spin text-green-400 flex-shrink-0" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-green-300 text-xs">
              {busy === 'checking' ? t('spoolbuddy.settings.checking', 'Checking for updates...')
                : device.update_message || t('spoolbuddy.settings.updateWaiting', 'Updating...')}
            </span>
          </div>
        ) : device.update_status === 'error' ? (
          <p className="text-xs text-red-300">{device.update_message || t('spoolbuddy.settings.updateFailed', 'Update failed')}</p>
        ) : error ? (
          <p className="text-xs text-red-300">{error}</p>
        ) : updateResult?.update_available ? (
          <p className="text-xs text-green-300">
            {t('spoolbuddy.settings.updateAvailable', 'Update available')}: {displayVersion} → {updateResult.latest_version}
          </p>
        ) : null}

        {/* Action buttons */}
        {!showSpinner && (
          updateResult?.update_available ? (
            <button
              onClick={applyUpdate}
              disabled={!device.online}
              className="w-full px-3 py-2 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 transition-colors"
            >
              {!device.online
                ? t('spoolbuddy.settings.deviceOffline', 'Device Offline')
                : t('spoolbuddy.settings.applyUpdate', 'Apply Update')}
            </button>
          ) : (
            <div className="flex gap-2">
              <button
                onClick={checkForUpdates}
                className="flex-1 px-3 py-2 rounded-lg text-xs font-medium bg-bambu-dark-tertiary text-bambu-gray-light hover:bg-bambu-dark-tertiary transition-colors"
              >
                {t('spoolbuddy.settings.checkUpdates', 'Check for Updates')}
              </button>
              <button
                onClick={applyUpdate}
                disabled={!device.online}
                className="px-3 py-2 rounded-lg text-xs font-medium bg-bambu-dark-tertiary text-bambu-gray hover:bg-bambu-dark-tertiary hover:text-bambu-gray-light disabled:opacity-40 transition-colors"
              >
                {t('spoolbuddy.settings.forceUpdate', 'Force Update')}
              </button>
            </div>
          )
        )}
      </div>

      {/* SSH Setup — collapsible */}
      <div className="bg-bambu-dark-secondary rounded-lg p-3">
        <button
          onClick={() => setSSHExpanded(!sshExpanded)}
          className="w-full flex justify-between items-center text-xs"
        >
          <span className="font-medium text-bambu-gray">
            {t('spoolbuddy.settings.sshSetup', 'SSH Setup')}
          </span>
          <svg
            className={`w-3 h-3 text-bambu-gray transition-transform ${sshExpanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {sshExpanded && (
          <div className="mt-2 space-y-2">
            <p className="text-xs text-bambu-gray">
              {t('spoolbuddy.settings.sshDescription', 'SSH key is deployed automatically. For manual setup, add this key to ~/.ssh/authorized_keys on the device.')}
            </p>
            {sshKeyData?.public_key ? (
              <div className="relative">
                <pre className="bg-bambu-dark rounded p-2 text-[10px] text-bambu-gray font-mono break-all whitespace-pre-wrap">
                  {sshKeyData.public_key}
                </pre>
                <button
                  onClick={copyKey}
                  className="absolute top-1 right-1 px-1.5 py-0.5 rounded text-[10px] bg-bambu-dark-tertiary text-bambu-gray-light hover:bg-bambu-dark-tertiary transition-colors"
                >
                  {copied ? t('common.copied', 'Copied!') : t('common.copy', 'Copy')}
                </button>
              </div>
            ) : (
              <span className="text-[10px] text-bambu-gray italic">
                {t('spoolbuddy.settings.sshKeyLoading', 'Loading...')}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// --- System Tab ---

function UsageBar({ percent, color }: { percent: number; color: string }) {
  return (
    <div className="w-full h-2 bg-bambu-dark-tertiary rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all ${color}`}
        style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
      />
    </div>
  );
}

function formatSystemUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function SystemTab({ device }: { device: SpoolBuddyDevice }) {
  const { t } = useTranslation();
  const stats = device.system_stats;

  if (!stats) {
    return (
      <div className="flex items-center justify-center h-32">
        <p className="text-sm text-bambu-gray">
          {t('spoolbuddy.settings.systemStatsWaiting', 'Waiting for system stats...')}
        </p>
      </div>
    );
  }

  const mem = stats.memory;
  const disk = stats.disk;
  const tempColor = (stats.cpu_temp_c ?? 0) >= 80 ? 'text-red-400' : (stats.cpu_temp_c ?? 0) >= 65 ? 'text-amber-400' : 'text-green-400';
  const memColor = (mem?.percent ?? 0) >= 90 ? 'bg-red-500' : (mem?.percent ?? 0) >= 70 ? 'bg-amber-500' : 'bg-green-500';
  const diskColor = (disk?.percent ?? 0) >= 90 ? 'bg-red-500' : (disk?.percent ?? 0) >= 70 ? 'bg-amber-500' : 'bg-green-500';

  return (
    <div className="space-y-2">
      {/* CPU + Memory side by side */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-bambu-dark-secondary rounded-lg p-3">
          <h3 className="text-sm font-semibold text-bambu-gray-light mb-2">CPU</h3>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-bambu-gray">{t('spoolbuddy.settings.cores', 'Cores')}</span>
              <span className="text-bambu-gray-light font-mono">{stats.cpu_count ?? '-'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-bambu-gray">{t('spoolbuddy.settings.loadAvg', 'Load Avg')}</span>
              <span className="text-bambu-gray-light font-mono">
                {stats.load_avg ? stats.load_avg.join(' / ') : '-'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-bambu-gray">{t('spoolbuddy.settings.temp', 'Temp')}</span>
              <span className={`font-mono font-medium ${tempColor}`}>
                {stats.cpu_temp_c != null ? `${stats.cpu_temp_c}\u00B0C` : '-'}
              </span>
            </div>
          </div>
        </div>

        {/* Memory */}
        <div className="bg-bambu-dark-secondary rounded-lg p-3">
          <h3 className="text-sm font-semibold text-bambu-gray-light mb-2">
            {t('spoolbuddy.settings.memory', 'Memory')}
          </h3>
          {mem ? (
            <div className="space-y-1.5">
              <UsageBar percent={mem.percent ?? 0} color={memColor} />
              <div className="space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-bambu-gray">{t('spoolbuddy.settings.used', 'Used')}</span>
                  <span className="text-bambu-gray-light font-mono">{mem.used_mb} / {mem.total_mb} MB</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-bambu-gray">{t('spoolbuddy.settings.available', 'Free')}</span>
                  <span className="text-bambu-gray-light font-mono">{mem.available_mb} MB</span>
                </div>
              </div>
            </div>
          ) : (
            <span className="text-xs text-bambu-gray">-</span>
          )}
        </div>
      </div>

      {/* Disk — compact single row */}
      <div className="bg-bambu-dark-secondary rounded-lg px-3 py-2">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-bambu-gray-light shrink-0">
            {t('spoolbuddy.settings.disk', 'Disk')}
          </h3>
          {disk ? (
            <>
              <div className="flex-1"><UsageBar percent={disk.percent ?? 0} color={diskColor} /></div>
              <span className="text-xs text-bambu-gray-light font-mono shrink-0">{disk.used_gb} / {disk.total_gb} GB</span>
            </>
          ) : (
            <span className="text-xs text-bambu-gray">-</span>
          )}
        </div>
      </div>

      {/* OS + Runtime side by side */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-bambu-dark-secondary rounded-lg p-3">
          <h3 className="text-sm font-semibold text-bambu-gray-light mb-1.5">
            {t('spoolbuddy.settings.osInfo', 'OS')}
          </h3>
          <div className="space-y-1 text-xs">
            {stats.os?.os && (
              <div className="flex justify-between">
                <span className="text-bambu-gray">{t('spoolbuddy.settings.distro', 'Distro')}</span>
                <span className="text-bambu-gray-light truncate ml-2">{stats.os.os}</span>
              </div>
            )}
            {stats.os?.kernel && (
              <div className="flex justify-between">
                <span className="text-bambu-gray">{t('spoolbuddy.settings.kernel', 'Kernel')}</span>
                <span className="text-bambu-gray-light font-mono truncate ml-2">{stats.os.kernel}</span>
              </div>
            )}
            {stats.os?.arch && (
              <div className="flex justify-between">
                <span className="text-bambu-gray">{t('spoolbuddy.settings.arch', 'Arch')}</span>
                <span className="text-bambu-gray-light font-mono">{stats.os.arch}</span>
              </div>
            )}
          </div>
        </div>
        <div className="bg-bambu-dark-secondary rounded-lg p-3">
          <h3 className="text-sm font-semibold text-bambu-gray-light mb-1.5">
            {t('spoolbuddy.settings.runtime', 'Runtime')}
          </h3>
          <div className="space-y-1 text-xs">
            {stats.os?.python && (
              <div className="flex justify-between">
                <span className="text-bambu-gray">Python</span>
                <span className="text-bambu-gray-light font-mono">{stats.os.python}</span>
              </div>
            )}
            {stats.system_uptime_s != null && (
              <div className="flex justify-between">
                <span className="text-bambu-gray">{t('spoolbuddy.settings.systemUptime', 'Uptime')}</span>
                <span className="text-bambu-gray-light">{formatSystemUptime(stats.system_uptime_s)}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Main Settings Page ---

type SettingsTab = 'device' | 'display' | 'scale' | 'updates' | 'system';

export function SpoolBuddySettingsPage() {
  const { sbState, setDisplayBrightness } = useOutletContext<SpoolBuddyOutletContext>();
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<SettingsTab>('device');

  // This kiosk's device, not the one the last WebSocket event came from:
  // every device's weight updates reach every kiosk (#3504).
  const { device } = useKioskDevice(10000);


  const tabs: { id: SettingsTab; label: string }[] = [
    { id: 'device', label: t('spoolbuddy.settings.tabDevice', 'Device') },
    { id: 'display', label: t('spoolbuddy.settings.tabDisplay', 'Display') },
    { id: 'scale', label: t('spoolbuddy.settings.tabScale', 'Scale') },
    { id: 'updates', label: t('spoolbuddy.settings.tabUpdates', 'Updates') },
    { id: 'system', label: t('spoolbuddy.settings.tabSystem', 'System') },
  ];

  return (
    <div className="h-full flex flex-col p-4">
      <h1 className="text-xl font-semibold text-white mb-3">
        {t('spoolbuddy.nav.settings', 'Settings')}
      </h1>

      {/* Tab bar */}
      <div className="flex flex-wrap gap-1 bg-bambu-dark-secondary rounded-lg p-1 mb-4">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 px-2 py-2 rounded-md text-sm font-medium transition-colors min-h-[36px] ${
              activeTab === tab.id
                ? 'bg-bambu-dark-tertiary text-white'
                : 'text-bambu-gray hover:text-bambu-gray-light'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {!device ? (
          <div className="flex items-center justify-center h-32">
            <div className="text-center text-bambu-gray">
              <p className="text-sm">{t('spoolbuddy.settings.noDevice', 'No SpoolBuddy device found')}</p>
            </div>
          </div>
        ) : (
          <>
            {activeTab === 'device' && <DeviceTab key={device.device_id} device={device} />}
            {activeTab === 'display' && (
              <DisplayTab
                device={device}
                onBrightnessChange={setDisplayBrightness}
              />
            )}
            {activeTab === 'scale' && (
              <ScaleTab
                device={device}
                weight={sbState.weight}
                weightStable={sbState.weightStable}
                rawAdc={sbState.rawAdc}
              />
            )}
            {activeTab === 'updates' && <UpdatesTab device={device} />}
            {activeTab === 'system' && <SystemTab device={device} />}
          </>
        )}
      </div>
    </div>
  );
}
