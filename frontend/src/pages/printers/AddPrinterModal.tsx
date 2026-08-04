import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Checkbox, LegacySelect, TextField } from '../../components/ui';
import { AlertTriangle, ChevronDown, Search, Loader2, Stethoscope } from 'lucide-react';
import { api, discoveryApi } from '../../api/client';
import type { PrinterCreate, DiscoveredPrinter, PrinterDiagnosticResult } from '../../api/client';
import { Card, CardContent } from '../../components/Card';
import { Button } from '../../components/Button';
import { ConnectionDiagnosticModal, DiagnosticChecklist } from '../../components/ConnectionDiagnostic';
import { mapModelCode } from './printer-status';

export function AddPrinterModal({
  onClose,
  onAdd,
  existingSerials,
}: {
  onClose: () => void;
  onAdd: (data: PrinterCreate) => void;
  existingSerials: string[];
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<PrinterCreate>({
    name: '',
    serial_number: '',
    ip_address: '',
    access_code: '',
    model: '',
    location: '',
    auto_archive: true,
  });

  // Discovery state
  const [discovering, setDiscovering] = useState(false);
  const [discovered, setDiscovered] = useState<DiscoveredPrinter[]>([]);
  const [discoveryError, setDiscoveryError] = useState('');
  const [hasScanned, setHasScanned] = useState(false);
  const [isDocker, setIsDocker] = useState(false);
  const [detectedSubnets, setDetectedSubnets] = useState<string[]>([]);
  const [subnet, setSubnet] = useState('');
  // Custom subnet — `__custom__` sentinel in the dropdown reveals a CIDR
  // text input so users can scan a subnet PrintOps isn't directly on
  // (printer behind a router on a different L3 segment — SSDP multicast
  // won't cross that boundary, only an active unicast scan will). #1564
  const [customSubnet, setCustomSubnet] = useState('');
  const [useCustomSubnet, setUseCustomSubnet] = useState(false);
  const [scanProgress, setScanProgress] = useState({ scanned: 0, total: 0 });
  const [showDiagnostic, setShowDiagnostic] = useState(false);

  // Setup-time pre-flight: run the connection diagnostic on save and warn
  // (not block) when checks fail, so the user doesn't add a printer that
  // immediately shows offline. checkingSave = probe in flight; saveWarning =
  // failed result awaiting an explicit "save anyway".
  const [checkingSave, setCheckingSave] = useState(false);
  const [saveWarning, setSaveWarning] = useState<PrinterDiagnosticResult | null>(null);

  // Fetch discovery info on mount + restore the last custom CIDR the user
  // typed (kept in localStorage so they don't retype `10.1.1.0/24` every
  // time they open this modal).
  useEffect(() => {
    discoveryApi.getInfo().then(info => {
      setIsDocker(info.is_docker);
      if (info.subnets.length > 0) {
        setDetectedSubnets(info.subnets);
        setSubnet(info.subnets[0]);
      }
    }).catch(() => {
      // Ignore errors, assume not Docker
    });
    try {
      const saved = localStorage.getItem('printops.discovery.customSubnet');
      if (saved) setCustomSubnet(saved);
    } catch {
      // localStorage unavailable (private mode, quota); recall is opportunistic
    }
  }, []);

  // Filter out already-added printers
  const newPrinters = discovered.filter(p => !existingSerials.includes(p.serial));

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCheckingSave(true);
    try {
      const result = await api.diagnoseConnection({
        ip_address: form.ip_address.trim(),
        serial_number: form.serial_number.trim() || undefined,
        access_code: form.access_code || undefined,
      });
      if (result.checks.some((c) => c.status === 'fail')) {
        setSaveWarning(result);
        return;
      }
    } catch {
      // Diagnostic infrastructure failed — never block the save on it.
    } finally {
      setCheckingSave(false);
    }
    onAdd(form);
  };

  const startDiscovery = async () => {
    setDiscoveryError('');
    setDiscovered([]);
    setDiscovering(true);
    setHasScanned(false);
    setScanProgress({ scanned: 0, total: 0 });

    // Native installs fall back to subnet scanning when the user picks
    // "Custom" — SSDP can't reach a printer on a different L3 segment
    // (#1564). Docker mode always uses subnet scan (multicast unavailable).
    const scanCidr = useCustomSubnet ? customSubnet.trim() : subnet;
    const wantsSubnetScan = isDocker || useCustomSubnet;

    if (wantsSubnetScan && useCustomSubnet) {
      try {
        localStorage.setItem('printops.discovery.customSubnet', scanCidr);
      } catch {
        // localStorage write best-effort; user just retypes next time
      }
    }

    try {
      if (wantsSubnetScan) {
        await discoveryApi.startSubnetScan(scanCidr);

        // Poll for scan status and results
        const pollInterval = setInterval(async () => {
          try {
            const status = await discoveryApi.getScanStatus();
            setScanProgress({ scanned: status.scanned, total: status.total });

            const printers = await discoveryApi.getDiscoveredPrinters();
            setDiscovered(printers);

            if (!status.running) {
              clearInterval(pollInterval);
              setDiscovering(false);
              setHasScanned(true);
            }
          } catch (e) {
            console.error('Failed to get scan status:', e);
          }
        }, 500);
      } else {
        // Use SSDP discovery for native installs
        await discoveryApi.startDiscovery(10);

        // Poll for discovered printers every second
        const pollInterval = setInterval(async () => {
          try {
            const printers = await discoveryApi.getDiscoveredPrinters();
            setDiscovered(printers);
          } catch (e) {
            console.error('Failed to get discovered printers:', e);
          }
        }, 1000);

        // Stop after 10 seconds
        setTimeout(async () => {
          clearInterval(pollInterval);
          try {
            await discoveryApi.stopDiscovery();
          } catch {
            // Ignore stop errors
          }
          setDiscovering(false);
          setHasScanned(true);
          // Final fetch
          try {
            const printers = await discoveryApi.getDiscoveredPrinters();
            setDiscovered(printers);
          } catch (e) {
            console.error('Failed to get final discovered printers:', e);
          }
        }, 10000);
      }
    } catch (e) {
      console.error('Failed to start discovery:', e);
      setDiscoveryError(e instanceof Error ? e.message : t('printers.discovery.failedToStart'));
      setDiscovering(false);
      setHasScanned(true);
    }
  };

  // Reuse module-level mapModelCode

  const selectPrinter = (printer: DiscoveredPrinter) => {
    // Don't pre-fill serial if it's a placeholder (unknown-*) - user needs to enter actual serial
    const serialNumber = printer.serial.startsWith('unknown-') ? '' : printer.serial;
    setForm({
      ...form,
      name: printer.name || '',
      serial_number: serialNumber,
      ip_address: printer.ip_address,
      model: mapModelCode(printer.model),
    });
    // Clear discovery results after selection
    setDiscovered([]);
  };

  // Cleanup discovery on unmount
  useEffect(() => {
    return () => {
      discoveryApi.stopDiscovery().catch(() => {});
      discoveryApi.stopSubnetScan().catch(() => {});
    };
  }, []);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <>
    <div
      className="fixed inset-0 bg-black/50 flex items-start sm:items-center justify-center z-50 p-4 overflow-y-auto"
      onClick={onClose}
    >
      <Card className="w-full max-w-md my-auto max-h-[calc(100vh-2rem)] overflow-y-auto" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
        <CardContent>
          <h2 className="text-xl font-semibold mb-4">{t('printers.addPrinter')}</h2>

          {/* Discovery Section */}
          <div className="mb-4 pb-4 border-b border-bambu-dark-tertiary">
            {/* Subnet picker — always visible. The dropdown lists detected
                interface subnets and a "Custom..." sentinel that reveals
                a CIDR text input for printers on a different L3 segment
                (router, VLAN, etc.). #1564 */}
            <div className="mb-3">
              <label className="block text-sm text-bambu-gray mb-1">
                {t('printers.discovery.subnetToScan')}
              </label>
              {detectedSubnets.length > 0 ? (
                <LegacySelect
                  aria-label={t('printers.discovery.subnetToScan')}
                  className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none text-sm"
                  value={useCustomSubnet ? '__custom__' : subnet}
                  onChange={(e) => {
                    if (e.target.value === '__custom__') {
                      setUseCustomSubnet(true);
                    } else {
                      setUseCustomSubnet(false);
                      setSubnet(e.target.value);
                    }
                  }}
                  disabled={discovering}
                >
                  {detectedSubnets.map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                  <option value="__custom__">{t('printers.discovery.customSubnetOption')}</option>
                </LegacySelect>
              ) : (
                <TextField
                  type="text"
                  className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none text-sm"
                  value={subnet}
                  onChange={(e) => setSubnet(e.target.value)}
                  placeholder="192.168.1.0/24"
                  disabled={discovering}
                />
              )}
              {useCustomSubnet && (
                <TextField
                  type="text"
                  aria-label={t('printers.discovery.customSubnetLabel')}
                  className="mt-2 w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none text-sm"
                  value={customSubnet}
                  onChange={(e) => setCustomSubnet(e.target.value)}
                  placeholder="10.1.1.0/24"
                  disabled={discovering}
                />
              )}
              <p className="mt-1 text-xs text-bambu-gray">
                {isDocker
                  ? t('printers.discovery.dockerNote')
                  : t('printers.discovery.customSubnetNote')}
              </p>
            </div>


            <Button
              type="button"
              variant="secondary"
              onClick={startDiscovery}
              disabled={discovering}
              className="w-full"
            >
              {discovering ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {(isDocker || useCustomSubnet) && scanProgress.total > 0
                    ? t('printers.discovery.scanProgress', { scanned: scanProgress.scanned, total: scanProgress.total })
                    : t('printers.discovery.scanning')}
                </>
              ) : (
                <>
                  <Search className="w-4 h-4" />
                  {(isDocker || useCustomSubnet) ? t('printers.discovery.scanSubnet') : t('printers.discovery.discoverNetwork')}
                </>
              )}
            </Button>

            {discoveryError && (
              <div className="mt-2 text-sm text-red-700 dark:text-red-400">{discoveryError}</div>
            )}

            {newPrinters.length > 0 && (
              <div className="mt-3 space-y-2 max-h-40 overflow-y-auto">
                {newPrinters.map((printer) => (
                  <div
                    key={printer.serial}
                    className="flex items-center justify-between p-2 bg-bambu-dark rounded-lg hover:bg-bambu-dark-secondary cursor-pointer transition-colors"
                    onClick={() => selectPrinter(printer)}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-white text-sm truncate">
                        {printer.name || printer.serial}
                      </p>
                      <p className="text-xs text-bambu-gray truncate">
                        {mapModelCode(printer.model) || t('printers.discovery.unknown')} • {printer.ip_address}
                        {printer.serial.startsWith('unknown-') && (
                          <span className="text-yellow-500"> • {t('printers.discovery.serialRequired')}</span>
                        )}
                      </p>
                    </div>
                    <ChevronDown className="w-4 h-4 text-bambu-gray -rotate-90 flex-shrink-0 ml-2" />
                  </div>
                ))}
              </div>
            )}

            {discovering && (
              <p className="mt-2 text-sm text-bambu-gray text-center">
                {(isDocker || useCustomSubnet) ? t('printers.discovery.scanningSubnet') : t('printers.discovery.scanningNetwork')}
              </p>
            )}

            {hasScanned && !discovering && discovered.length === 0 && (
              <p className="mt-2 text-sm text-bambu-gray text-center">
                {(isDocker || useCustomSubnet) ? t('printers.discovery.noPrintersFoundSubnet') : t('printers.discovery.noPrintersFoundNetwork')}
              </p>
            )}

            {hasScanned && !discovering && discovered.length > 0 && newPrinters.length === 0 && (
              <p className="mt-2 text-sm text-bambu-gray text-center">
                {t('printers.discovery.allConfigured')}
              </p>
            )}
          </div>
          <form onSubmit={handleAddSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.name')}</label>
              <TextField
                type="text"
                required
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder={t('printers.modal.myPrinter')}
              />
            </div>
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.ipAddress')}</label>
              <TextField
                type="text"
                required
                pattern="(\d{1,3}(\.\d{1,3}){3}|[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*)"
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.ip_address}
                onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
                placeholder="192.168.1.100 or printer.local"
              />
            </div>
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.serialNumber')}</label>
              <TextField
                type="text"
                required
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.serial_number}
                onChange={(e) => setForm({ ...form, serial_number: e.target.value })}
                placeholder="01P00A000000000"
              />
            </div>
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.accessCode')}</label>
              <TextField
                type="password"
                required
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.access_code}
                onChange={(e) => setForm({ ...form, access_code: e.target.value })}
                placeholder={t('printers.modal.fromPrinterSettings')}
              />
            </div>
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.modal.modelOptional')}</label>
              <LegacySelect
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.model || ''}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
              >
                <option value="">{t('printers.modal.selectModel')}</option>
                <optgroup label="A1 Series">
                  <option value="A1">A1</option>
                  <option value="A1 Mini">A1 Mini</option>
                </optgroup>
                <optgroup label="A2 Series">
                  <option value="A2L">A2L</option>
                </optgroup>
                <optgroup label="H2 Series">
                  <option value="H2C">H2C</option>
                  <option value="H2D">H2D</option>
                  <option value="H2D Pro">H2D Pro</option>
                  <option value="H2S">H2S</option>
                </optgroup>
                <optgroup label="P Series">
                  <option value="P1P">P1P</option>
                  <option value="P1S">P1S</option>
                  <option value="P2S">P2S</option>
                </optgroup>
                <optgroup label="X1 Series">
                  <option value="X1">X1</option>
                  <option value="X1C">X1 Carbon</option>
                  <option value="X1E">X1E</option>
                </optgroup>
                <optgroup label="X2 Series">
                  <option value="X2D">X2D</option>
                </optgroup>
              </LegacySelect>
            </div>
            <div>
              <label className="block text-sm text-bambu-gray mb-1">{t('printers.modal.locationGroup')}</label>
              <TextField
                type="text"
                className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
                value={form.location || ''}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                placeholder={t('printers.modal.locationPlaceholder')}
              />
              <p className="text-xs text-bambu-gray mt-1">{t('printers.locationHelp')}</p>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="auto_archive"
                checked={Boolean(form.auto_archive)}
                onChange={(e) => setForm({ ...form, auto_archive: e.target.checked })}
              />
              <label htmlFor="auto_archive" className="text-sm text-bambu-gray">
                {t('printers.modal.autoArchiveLabel')}
              </label>
            </div>
            <button
              type="button"
              onClick={() => setShowDiagnostic(true)}
              disabled={!form.ip_address.trim()}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-bambu-gray hover:text-white disabled:opacity-40 disabled:cursor-not-allowed border border-bambu-dark-tertiary rounded-lg transition-colors"
            >
              <Stethoscope className="w-4 h-4" />
              {t('diagnostic.runButton')}
            </button>
            {saveWarning ? (
              <div className="rounded-lg bg-amber-50 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-500/30 p-3 space-y-3">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
                  <p className="text-sm text-amber-700 dark:text-amber-300">{t('printers.addPreflight.warning')}</p>
                </div>
                <DiagnosticChecklist result={saveWarning} />
                <div className="flex gap-3">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setSaveWarning(null)}
                    className="flex-1"
                  >
                    {t('printers.addPreflight.back')}
                  </Button>
                  <Button type="button" onClick={() => onAdd(form)} className="flex-1">
                    {t('printers.addPreflight.saveAnyway')}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex gap-3 pt-2">
                <Button type="button" variant="secondary" onClick={onClose} className="flex-1">
                  {t('common.cancel')}
                </Button>
                <Button type="submit" disabled={checkingSave} className="flex-1">
                  {checkingSave ? t('printers.addPreflight.checking') : t('printers.addPrinter')}
                </Button>
              </div>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
    {showDiagnostic && (
      <ConnectionDiagnosticModal
        connection={{
          ip_address: form.ip_address.trim(),
          serial_number: form.serial_number.trim() || undefined,
          access_code: form.access_code || undefined,
        }}
        printerName={form.name || null}
        onClose={() => setShowDiagnostic(false)}
      />
    )}
    </>
  );
}
