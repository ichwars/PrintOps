export type PrinterControlAction =
  | 'status'
  | 'pause'
  | 'resume'
  | 'stop'
  | 'startPrint'
  | 'speed'
  | 'temperature'
  | 'fan'
  | 'light'
  | 'camera'
  | 'fileManagement'
  | 'movement'
  | 'airduct'
  | 'drying'
  | 'amsBackup'
  | 'amsSlot';

export type CloudControlSupport = 'documented' | 'likely' | 'uncertain' | 'localOnly';

export interface PrinterControlCapability {
  action: PrinterControlAction;
  cloudSupport: CloudControlSupport;
  printOpsCloudImplemented: boolean;
  localRequired: boolean;
  labelKey: string;
  labelFallback: string;
}

export const PRINTER_CONTROL_CAPABILITIES: Record<PrinterControlAction, PrinterControlCapability> = {
  status: {
    action: 'status',
    cloudSupport: 'documented',
    printOpsCloudImplemented: true,
    localRequired: false,
    labelKey: 'printers.controlCapabilities.status',
    labelFallback: 'Statusdaten',
  },
  pause: {
    action: 'pause',
    cloudSupport: 'documented',
    printOpsCloudImplemented: true,
    localRequired: true,
    labelKey: 'printers.pause',
    labelFallback: 'Pausieren',
  },
  resume: {
    action: 'resume',
    cloudSupport: 'documented',
    printOpsCloudImplemented: true,
    localRequired: true,
    labelKey: 'printers.resume',
    labelFallback: 'Fortsetzen',
  },
  stop: {
    action: 'stop',
    cloudSupport: 'documented',
    printOpsCloudImplemented: true,
    localRequired: true,
    labelKey: 'printers.stop',
    labelFallback: 'Stoppen',
  },
  startPrint: {
    action: 'startPrint',
    cloudSupport: 'documented',
    printOpsCloudImplemented: false,
    localRequired: true,
    labelKey: 'printers.controlCapabilities.startPrint',
    labelFallback: 'Druck starten',
  },
  speed: {
    action: 'speed',
    cloudSupport: 'documented',
    printOpsCloudImplemented: true,
    localRequired: true,
    labelKey: 'printers.speed.title',
    labelFallback: 'Druckgeschwindigkeit',
  },
  temperature: {
    action: 'temperature',
    cloudSupport: 'likely',
    printOpsCloudImplemented: true,
    localRequired: true,
    labelKey: 'printers.controlCapabilities.temperature',
    labelFallback: 'Temperatursteuerung',
  },
  fan: {
    action: 'fan',
    cloudSupport: 'likely',
    printOpsCloudImplemented: true,
    localRequired: true,
    labelKey: 'printers.controlCapabilities.fan',
    labelFallback: 'Lüftersteuerung',
  },
  light: {
    action: 'light',
    cloudSupport: 'likely',
    printOpsCloudImplemented: true,
    localRequired: true,
    labelKey: 'printers.controlCapabilities.light',
    labelFallback: 'Lichtsteuerung',
  },
  camera: {
    action: 'camera',
    cloudSupport: 'documented',
    printOpsCloudImplemented: false,
    localRequired: true,
    labelKey: 'printers.controlCapabilities.camera',
    labelFallback: 'Kamera',
  },
  fileManagement: {
    action: 'fileManagement',
    cloudSupport: 'uncertain',
    printOpsCloudImplemented: false,
    localRequired: true,
    labelKey: 'printers.controlCapabilities.fileManagement',
    labelFallback: 'Dateiverwaltung',
  },
  movement: {
    action: 'movement',
    cloudSupport: 'uncertain',
    printOpsCloudImplemented: false,
    localRequired: true,
    labelKey: 'printers.bedJog.title',
    labelFallback: 'Bewegung',
  },
  airduct: {
    action: 'airduct',
    cloudSupport: 'uncertain',
    printOpsCloudImplemented: false,
    localRequired: true,
    labelKey: 'printers.airduct.title',
    labelFallback: 'Luftkanal',
  },
  drying: {
    action: 'drying',
    cloudSupport: 'uncertain',
    printOpsCloudImplemented: false,
    localRequired: true,
    labelKey: 'printers.drying.start',
    labelFallback: 'Trocknung',
  },
  amsBackup: {
    action: 'amsBackup',
    cloudSupport: 'uncertain',
    printOpsCloudImplemented: false,
    localRequired: true,
    labelKey: 'printers.amsBackup.title',
    labelFallback: 'AMS Filament Backup',
  },
  amsSlot: {
    action: 'amsSlot',
    cloudSupport: 'uncertain',
    printOpsCloudImplemented: false,
    localRequired: true,
    labelKey: 'printers.controlCapabilities.amsSlot',
    labelFallback: 'AMS Slot-Steuerung',
  },
};

export function getPrinterControlCapability(action: PrinterControlAction): PrinterControlCapability {
  return PRINTER_CONTROL_CAPABILITIES[action];
}

export function isCloudControlCandidate(action: PrinterControlAction): boolean {
  const support = getPrinterControlCapability(action).cloudSupport;
  return support === 'documented' || support === 'likely';
}

export function isPrintOpsCloudControlImplemented(action: PrinterControlAction): boolean {
  return getPrinterControlCapability(action).printOpsCloudImplemented;
}

export function isCloudControlUncertain(action: PrinterControlAction): boolean {
  return getPrinterControlCapability(action).cloudSupport === 'uncertain';
}
