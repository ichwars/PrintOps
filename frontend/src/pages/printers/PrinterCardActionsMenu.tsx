import { MoreVertical, Trash2, RefreshCw, RotateCw, Terminal, Wrench, Pencil, Info, Stethoscope } from 'lucide-react';
import { Button } from '../../components/Button';
import type { usePrinterCardModel } from './usePrinterCardModel';

export function PrinterCardActionsMenu({ model }: { model: NonNullable<ReturnType<typeof usePrinterCardModel>> }) {
  const {
    printer, t, hasPermission, showMenu, setShowMenu, setShowDeleteConfirm, setShowEditModal,
    setShowMQTTDebug, setShowPrinterInfo, setShowDiagnostic, printerActionsMenuRef,
    connectMutation, forceRefreshMutation, maintenanceMutation, handleEnterMaintenance,
    footerIconButtonClass,
  } = model;
  return (
    <div ref={printerActionsMenuRef} className="relative flex-shrink-0">
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setShowMenu(!showMenu)}
        title={t('common.more', 'More')}
        className={footerIconButtonClass}
      >
        <MoreVertical className="w-4 h-4" />
      </Button>
      {showMenu && (
        <div className="absolute left-0 bottom-full mb-2 w-48 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg shadow-lg z-20">
          <button
            className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 ${
              hasPermission('printers:update')
                ? 'hover:bg-bambu-dark-tertiary'
                : 'opacity-50 cursor-not-allowed'
            }`}
            onClick={() => {
              if (!hasPermission('printers:update')) return;
              setShowEditModal(true);
              setShowMenu(false);
            }}
            title={!hasPermission('printers:update') ? t('printers.permission.noEdit') : undefined}
          >
            <Pencil className="w-4 h-4" />
            {t('common.edit')}
          </button>
          <button
            className="w-full px-4 py-2 text-left text-sm hover:bg-bambu-dark-tertiary flex items-center gap-2"
            onClick={() => {
              setShowPrinterInfo(true);
              setShowMenu(false);
            }}
          >
            <Info className="w-4 h-4" />
            {t('printers.printerInformation')}
          </button>
          {/* Maintenance Mode toggle (#1476) — leverages backend is_active flag */}
          <button
            className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 ${
              hasPermission('printers:update')
                ? 'hover:bg-bambu-dark-tertiary'
                : 'opacity-50 cursor-not-allowed'
            }`}
            disabled={maintenanceMutation.isPending || !hasPermission('printers:update')}
            onClick={() => {
              if (!hasPermission('printers:update')) return;
              setShowMenu(false);
              if (printer.is_active !== false) {
                handleEnterMaintenance();
              } else {
                maintenanceMutation.mutate(true);
              }
            }}
            title={!hasPermission('printers:update') ? t('printers.permission.noEdit') : undefined}
          >
            <Wrench className="w-4 h-4" />
            {printer.is_active !== false
              ? t('printers.maintenance.menuEnter')
              : t('printers.maintenance.menuExit')}
          </button>
          <button
            className="w-full px-4 py-2 text-left text-sm hover:bg-bambu-dark-tertiary flex items-center gap-2"
            onClick={() => {
              connectMutation.mutate();
              setShowMenu(false);
            }}
          >
            <RefreshCw className="w-4 h-4" />
            {t('printers.reconnect')}
          </button>
          <button
            className="w-full px-4 py-2 text-left text-sm hover:bg-bambu-dark-tertiary flex items-center gap-2 disabled:opacity-50"
            disabled={forceRefreshMutation.isPending}
            onClick={() => {
              forceRefreshMutation.mutate();
              setShowMenu(false);
            }}
          >
            <RotateCw className={`w-4 h-4 ${forceRefreshMutation.isPending ? 'animate-spin' : ''}`} />
            {t('printers.forceRefresh')}
          </button>
          <button
            className="w-full px-4 py-2 text-left text-sm hover:bg-bambu-dark-tertiary flex items-center gap-2"
            onClick={() => {
              setShowMQTTDebug(true);
              setShowMenu(false);
            }}
          >
            <Terminal className="w-4 h-4" />
            {t('printers.mqttDebug')}
          </button>
          <button
            className="w-full px-4 py-2 text-left text-sm hover:bg-bambu-dark-tertiary flex items-center gap-2"
            onClick={() => {
              setShowDiagnostic(true);
              setShowMenu(false);
            }}
          >
            <Stethoscope className="w-4 h-4" />
            {t('diagnostic.runButton')}
          </button>
          <button
            className={`w-full px-4 py-2 text-left text-sm flex items-center gap-2 ${
              hasPermission('printers:delete')
                ? 'text-red-700 dark:text-red-400 hover:bg-bambu-dark-tertiary'
                : 'text-red-700/50 dark:text-red-400/50 cursor-not-allowed'
            }`}
            onClick={() => {
              if (!hasPermission('printers:delete')) return;
              setShowDeleteConfirm(true);
              setShowMenu(false);
            }}
            title={!hasPermission('printers:delete') ? t('printers.permission.noDelete') : undefined}
          >
            <Trash2 className="w-4 h-4" />
            {t('common.delete')}
          </button>
        </div>
      )}
    </div>
  );
}
