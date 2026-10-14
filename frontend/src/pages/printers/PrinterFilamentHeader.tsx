import { Eye, EyeOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { AmsBackupBadge } from './printer-card-visuals';
import type { useExternalSpoolDisplay } from '../../hooks/useExternalSpoolDisplay';
import type { ComponentProps } from 'react';

/** The recovery control stays outside the optional external-spool panel. */
export function PrinterFilamentHeader({ backupState, onBackupClick, canToggleExternal, externalDisplay }: {
  backupState: ComponentProps<typeof AmsBackupBadge>['state'];
  onBackupClick: () => void;
  canToggleExternal: boolean;
  externalDisplay: ReturnType<typeof useExternalSpoolDisplay>;
}) {
  const { t } = useTranslation();
  const label = t(externalDisplay.hidden ? 'printers.externalSpoolDisplay.show' : 'printers.externalSpoolDisplay.hide');
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="text-[10px] uppercase tracking-wider text-bambu-gray font-medium">{t('printers.filaments')}</span>
      <AmsBackupBadge state={backupState} onClick={onBackupClick} />
      <div className="flex-1 h-[2px] bg-bambu-dark-tertiary" />
      {canToggleExternal && (
        <button
          type="button"
          aria-label={label}
          title={label}
          disabled={!externalDisplay.ready}
          onClick={event => { event.stopPropagation(); externalDisplay.setHidden(!externalDisplay.hidden); }}
          className="p-1 rounded text-bambu-gray hover:text-white hover:bg-bambu-dark-tertiary focus-visible:outline-2 focus-visible:outline-bambu-green disabled:opacity-50"
        >
          {externalDisplay.hidden ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      )}
    </div>
  );
}
