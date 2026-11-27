import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, AlertTriangle, RefreshCw, Unlink } from 'lucide-react';
import type { MatchedSpool } from '../../hooks/useSpoolBuddyState';
import { spoolbuddyApi } from '../../api/client';
import { SpoolIcon } from './SpoolIcon';
import { spoolColorString } from '../../utils/colors';

// Storage key for default core weight
const DEFAULT_CORE_WEIGHT_KEY = 'spoolbuddy-default-core-weight';

function getDefaultCoreWeight(): number {
  try {
    const stored = localStorage.getItem(DEFAULT_CORE_WEIGHT_KEY);
    if (stored) {
      const weight = parseInt(stored, 10);
      if (weight >= 0 && weight <= 500) return weight;
    }
  } catch {
    // Ignore errors
  }
  return 250; // Default 250g (typical Bambu spool core)
}

interface SpoolInfoCardProps {
  spool: MatchedSpool;
  scaleWeight: number | null;
  onClose?: () => void;
  onSyncWeight?: () => void;
  onAssignToAms?: () => void;
  isAssigned?: boolean;
  onUnassignFromAms?: () => void;
}

export function SpoolInfoCard({ spool, scaleWeight, onClose, onSyncWeight, onAssignToAms, isAssigned, onUnassignFromAms }: SpoolInfoCardProps) {
  const { t: translateInterface } = useTranslation();
  const { t } = useTranslation();
  const [syncing, setSyncing] = useState(false);
  const [synced, setSynced] = useState(false);

  const colorHex = spoolColorString(spool.rgba);

  // Use spool's core_weight if set, otherwise fall back to default
  const coreWeight = (spool.core_weight && spool.core_weight > 0)
    ? spool.core_weight
    : getDefaultCoreWeight();

  // Gross weight from scale (live) or fallback
  const grossWeight = scaleWeight !== null
    ? Math.round(Math.max(0, scaleWeight))
    : null;

  // Remaining filament = gross - core
  const remaining = grossWeight !== null
    ? Math.round(Math.max(0, grossWeight - coreWeight))
    : null;

  const labelWeight = Math.round(spool.label_weight || 1000);
  const fillPercent = remaining !== null ? Math.min(100, Math.round((remaining / labelWeight) * 100)) : null;
  const fillColor = fillPercent !== null
    ? fillPercent > 50 ? '#22c55e' : fillPercent > 20 ? '#eab308' : '#ef4444'
    : '#808080';

  // Weight comparison (scale vs calculated expected)
  const netWeight = Math.max(0,
    (spool.label_weight || 0) - (spool.weight_used || 0)
  );
  const calculatedWeight = netWeight + coreWeight;
  const difference = grossWeight !== null ? grossWeight - calculatedWeight : null;
  const isMatch = difference !== null ? Math.abs(difference) <= 50 : null;

  const handleSyncWeight = async () => {
    if (scaleWeight === null) return;
    setSyncing(true);
    try {
      await spoolbuddyApi.updateSpoolWeight(spool.id, Math.round(scaleWeight));
      setSynced(true);
      onSyncWeight?.();
      setTimeout(() => setSynced(false), 3000);
    } catch (e) {
      console.error('Failed to sync weight:', e);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="flex flex-col items-center space-y-4 max-w-md">
      {/* Top section: Spool icon + main info */}
      <div className="flex items-start gap-5">
        {/* Spool visualization */}
        <div className="relative shrink-0">
          <SpoolIcon color={colorHex} isEmpty={false} size={100} />
          {fillPercent !== null && (
            <div
              className="absolute -bottom-2 -right-2 px-2 py-0.5 rounded-full text-xs font-bold text-white shadow-lg"
              style={{ backgroundColor: fillColor }}
            >
              {fillPercent}%
            </div>
          )}
        </div>

        {/* Main info */}
        <div className="flex-1 min-w-0 pt-1">
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-white">
              {spool.color_name || translateInterface("orders.runtimeInterface.unknownColor")}
            </h3>
            <span className="text-xs font-mono text-bambu-gray shrink-0">#{spool.id}</span>
          </div>
          <p className="text-sm text-bambu-gray">
            {spool.brand} &bull; {spool.material}
            {spool.subtype && ` ${spool.subtype}`}
          </p>

          {/* Filament remaining - big number */}
          {remaining !== null && (
            <div className="mt-3">
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-bold font-mono text-white">{remaining}g</span>
                <span className="text-sm text-bambu-gray">/ {labelWeight}g</span>
              </div>
              <p className="text-xs text-bambu-gray mt-0.5">{t('spoolbuddy.spool.remaining', 'Remaining')}</p>

              {/* Fill bar */}
              <div className="mt-2 max-w-xs">
                <div className="h-2 bg-bambu-dark-tertiary rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${fillPercent}%`, backgroundColor: fillColor }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Details grid */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm bg-bambu-dark-secondary rounded-lg p-4 w-full">
        <div className="flex justify-between">
          <span className="text-bambu-gray">{t('spoolbuddy.dashboard.grossWeight', 'Gross weight')}</span>
          <span className="font-mono text-bambu-gray-light">{grossWeight !== null ? `${grossWeight}g` : '\u2014'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-bambu-gray">{t('spoolbuddy.spool.coreWeight', 'Core')}</span>
          <span className="font-mono text-bambu-gray-light">{coreWeight}g</span>
        </div>
        <div className="flex justify-between">
          <span className="text-bambu-gray">{t('spoolbuddy.dashboard.spoolSize', 'Spool size')}</span>
          <span className="font-mono text-bambu-gray-light">{labelWeight}g</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-bambu-gray">{t('spoolbuddy.spool.scaleWeight', 'Scale')}</span>
          {grossWeight !== null ? (
            <span className={`flex items-center gap-1 font-mono ${isMatch ? 'text-green-500' : 'text-yellow-500'}`}>
              {grossWeight}g
              {isMatch ? (
                <Check className="w-3.5 h-3.5" />
              ) : (
                <>
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <button
                    onClick={handleSyncWeight}
                    className="p-1 hover:bg-green-500/20 rounded transition-colors text-green-500"
                    title={t('spoolbuddy.dashboard.syncWeight', 'Sync Weight')}
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                </>
              )}
            </span>
          ) : (
            <span className="text-bambu-gray">{'\u2014'}</span>
          )}
        </div>
        <div className="flex justify-between items-center">
          <span className="text-bambu-gray">{t('spoolbuddy.dashboard.tagId', 'Tag')}</span>
          <span className="font-mono text-xs text-bambu-gray truncate max-w-[120px]" title={spool.tag_uid || ''}>
            {spool.tag_uid ? spool.tag_uid.slice(-8) : '\u2014'}
          </span>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2 justify-center">
        {onAssignToAms && (
          <button
            onClick={isAssigned ? undefined : onAssignToAms}
            disabled={!!isAssigned}
            className="px-5 py-2.5 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700 transition-colors min-h-[44px] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {t('spoolbuddy.modal.assignToAms', 'Assign to AMS')}
          </button>
        )}
        {onUnassignFromAms && (
          <button
            onClick={onUnassignFromAms}
            className="px-5 py-2.5 rounded-lg text-sm font-medium bg-red-600/20 text-red-400 hover:bg-red-600/30 transition-colors min-h-[44px]"
          >
            <Unlink className="w-4 h-4 inline mr-1" />
            {t('inventory.unassignSpool')}
          </button>
        )}
        <button
          onClick={handleSyncWeight}
          disabled={scaleWeight === null || syncing}
          className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-colors min-h-[44px] ${
            synced
              ? 'bg-green-600/20 text-green-400'
              : onAssignToAms
                ? 'bg-bambu-dark-tertiary text-bambu-gray-light hover:bg-bambu-dark-tertiary disabled:opacity-40 disabled:cursor-not-allowed'
                : 'bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed'
          }`}
        >
          {syncing ? '...' : synced ? t('spoolbuddy.dashboard.weightSynced', 'Synced') : t('spoolbuddy.dashboard.syncWeight', 'Sync Weight')}
        </button>
        {onClose && (
          <button
            onClick={onClose}
            className="px-5 py-2.5 rounded-lg text-sm font-medium bg-bambu-dark-tertiary text-bambu-gray-light hover:bg-bambu-dark-tertiary transition-colors min-h-[44px]"
          >
            {t('spoolbuddy.dashboard.close', 'Close')}
          </button>
        )}
      </div>
    </div>
  );
}

interface UnknownTagCardProps {
  tagUid: string;
  scaleWeight: number | null;
  coreWeight?: number;
  onLinkSpool?: () => void;
  onAddToInventory?: () => void;
  onClose?: () => void;
}

export function UnknownTagCard({ tagUid, scaleWeight, coreWeight, onLinkSpool, onAddToInventory, onClose }: UnknownTagCardProps) {
  const { t } = useTranslation();
  const defaultCoreWeight = coreWeight ?? getDefaultCoreWeight();
  const grossWeight = scaleWeight !== null
    ? Math.round(Math.max(0, scaleWeight))
    : null;
  const estimatedRemaining = grossWeight !== null
    ? Math.round(Math.max(0, grossWeight - defaultCoreWeight))
    : null;

  return (
    <div className="flex flex-col items-center text-center space-y-5">
      <div className="w-20 h-20 rounded-2xl bg-green-500/15 flex items-center justify-center">
        <svg className="w-10 h-10 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a4 4 0 014-4z" />
        </svg>
      </div>
      <div>
        <h3 className="text-lg font-semibold text-white">{t('spoolbuddy.dashboard.newTag', 'New Tag Detected')}</h3>
        <p className="text-sm text-bambu-gray font-mono mt-1">{tagUid}</p>
      </div>
      {grossWeight !== null && (
        <div className="text-sm text-bambu-gray">
          <span className="font-mono font-semibold">{grossWeight}g</span> {t('spoolbuddy.dashboard.onScale', 'on scale')}
          {estimatedRemaining !== null && estimatedRemaining > 0 && (
            <span className="text-bambu-gray"> &bull; ~{estimatedRemaining}g filament</span>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-2 justify-center">
        {onAddToInventory && (
          <button
            onClick={onAddToInventory}
            className="px-5 py-2.5 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700 transition-colors min-h-[44px]"
          >
            {t('spoolbuddy.modal.addToInventory', 'Add to Inventory')}
          </button>
        )}
        {onLinkSpool && (
          <button
            onClick={onLinkSpool}
            className="px-5 py-2.5 rounded-lg text-sm font-medium bg-bambu-dark-tertiary text-bambu-gray-light hover:bg-bambu-dark-tertiary transition-colors min-h-[44px]"
          >
            <svg className="w-4 h-4 inline-block mr-1.5 -mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
            {t('inventory.assignSpool', 'Assign Spool')}
          </button>
        )}
        {onClose && (
          <button
            onClick={onClose}
            className="px-5 py-2.5 rounded-lg text-sm font-medium bg-bambu-dark-tertiary text-bambu-gray-light hover:bg-bambu-dark-tertiary transition-colors min-h-[44px]"
          >
            {t('spoolbuddy.dashboard.close', 'Close')}
          </button>
        )}
      </div>
    </div>
  );
}
