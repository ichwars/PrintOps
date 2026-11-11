import { LogIn, LogOut, RefreshCw } from 'lucide-react';
import type { usePrinterCardModel } from './usePrinterCardModel';

/** Shared slot actions retain the printer's permissions and control availability. */
export function createAmsSlotActions(model: NonNullable<ReturnType<typeof usePrinterCardModel>>) {
  const {
    status, hasPermission, localPrinterControlUnavailable, refreshAmsSlotMutation,
    t, getLocalPrinterControlUnavailableTitle, canUsePrinterControl,
    loadAmsTrayMutation, unloadAmsMutation, getPrinterControlUnavailableTitle,
  } = model;
  return ({
    amsId,
    slotId,
    loadTrayId,
    isRefreshing,
    includeRfid = true,
  }: {
    amsId: number;
    slotId: number;
    loadTrayId: number;
    isRefreshing?: boolean;
    includeRfid?: boolean;
  }) => {
    const printerBusy = status?.state === 'RUNNING';

    return (
      <>
        {includeRfid && (
          <button
            className={`w-full px-2 py-1.5 text-left text-xs flex items-center gap-2 rounded transition-colors ${
              hasPermission('printers:ams_rfid') && !localPrinterControlUnavailable
                ? 'text-white hover:bg-bambu-dark-tertiary'
                : 'text-bambu-gray/50 cursor-not-allowed'
            }`}
            onClick={(e) => {
              e.stopPropagation();
              if (printerBusy || localPrinterControlUnavailable || !hasPermission('printers:ams_rfid')) return;
              refreshAmsSlotMutation.mutate({ amsId, slotId });
            }}
            disabled={printerBusy || isRefreshing || localPrinterControlUnavailable || !hasPermission('printers:ams_rfid')}
            title={printerBusy ? t('printers.bedJog.disabledWhilePrinting') : localPrinterControlUnavailable ? getLocalPrinterControlUnavailableTitle('amsSlot') : !hasPermission('printers:ams_rfid') ? t('printers.permission.noAmsRfid') : undefined}
          >
            <RefreshCw className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
            {t('printers.rfid.reread')}
          </button>
        )}
        <button
          className={`w-full px-2 py-1.5 text-left text-xs flex items-center gap-2 rounded transition-colors ${
            canUsePrinterControl
              ? 'text-white hover:bg-bambu-dark-tertiary'
              : 'text-bambu-gray/50 cursor-not-allowed'
          }`}
          onClick={(e) => {
            e.stopPropagation();
            if (printerBusy || !canUsePrinterControl) return;
            loadAmsTrayMutation.mutate({ trayId: loadTrayId });
          }}
          disabled={printerBusy || !canUsePrinterControl}
          title={printerBusy ? t('printers.bedJog.disabledWhilePrinting') : !canUsePrinterControl ? getPrinterControlUnavailableTitle('amsSlot') : undefined}
        >
          <LogIn className="w-3 h-3" />
          {t('printers.ams.load')}
        </button>
        <button
          className={`w-full px-2 py-1.5 text-left text-xs flex items-center gap-2 rounded transition-colors ${
            canUsePrinterControl
              ? 'text-white hover:bg-bambu-dark-tertiary'
              : 'text-bambu-gray/50 cursor-not-allowed'
          }`}
          onClick={(e) => {
            e.stopPropagation();
            if (printerBusy || !canUsePrinterControl) return;
            unloadAmsMutation.mutate();
          }}
          disabled={printerBusy || !canUsePrinterControl}
          title={printerBusy ? t('printers.bedJog.disabledWhilePrinting') : !canUsePrinterControl ? getPrinterControlUnavailableTitle('amsSlot') : undefined}
        >
          <LogOut className="w-3 h-3" />
          {t('printers.ams.unload')}
        </button>
      </>
    );
  };
}
