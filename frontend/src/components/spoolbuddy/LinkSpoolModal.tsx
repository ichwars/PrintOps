import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import type { InventorySpool } from '../../api/client';
import { SpoolIcon } from './SpoolIcon';
import { spoolColorString } from '../../utils/colors';

interface LinkSpoolModalProps {
  isOpen: boolean;
  onClose: () => void;
  tagId: string;
  untaggedSpools: InventorySpool[];
  onLink: (spool: InventorySpool) => void;
}

export function LinkSpoolModal({
  isOpen,
  onClose,
  tagId,
  untaggedSpools,
  onLink,
}: LinkSpoolModalProps) {
  const { t: translateInterface } = useTranslation();
  const { t } = useTranslation();
  const [selectedSpool, setSelectedSpool] = useState<InventorySpool | null>(null);

  const handleClose = useCallback(() => {
    setSelectedSpool(null);
    onClose();
  }, [onClose]);

  // Handle escape key
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleClose();
    }
  }, [handleClose]);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, handleKeyDown]);

  if (!isOpen) return null;

  const handleConfirm = () => {
    if (selectedSpool) {
      onLink(selectedSpool);
      setSelectedSpool(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 animate-fade-in" onClick={handleClose}>
      <div
        className="bg-bambu-dark-secondary rounded-xl shadow-lg w-full max-w-lg mx-4 animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-bambu-dark-tertiary">
          <div>
            <h2 className="text-base font-semibold text-white">
              {t('spoolbuddy.dashboard.linkTagTitle', 'Link Tag to Spool')}
            </h2>
            <p className="text-sm text-bambu-gray font-mono">{tagId}</p>
          </div>
          <button
            onClick={handleClose}
            className="p-2 rounded-lg text-bambu-gray hover:text-bambu-gray-light hover:bg-bambu-dark-tertiary transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="px-5 py-4 space-y-3 max-h-[400px] overflow-y-auto">
          <p className="text-sm text-bambu-gray">
            {t('spoolbuddy.dashboard.selectSpool', 'Select a spool to link this tag to:')}
          </p>

          {untaggedSpools.length === 0 ? (
            <div className="text-center py-8 text-bambu-gray">
              {t('spoolbuddy.dashboard.noUntagged', 'No spools without tags found')}
            </div>
          ) : (
            <div className="space-y-2">
              {untaggedSpools.map((spool) => (
                <button
                  key={spool.id}
                  type="button"
                  onClick={() => setSelectedSpool(spool)}
                  className={`w-full flex items-center gap-3 p-3 rounded-lg border-2 transition-all text-left ${
                    selectedSpool?.id === spool.id
                      ? 'border-green-500 bg-green-500/10'
                      : 'border-bambu-dark-tertiary hover:border-green-500/50 hover:bg-bambu-dark-tertiary'
                  }`}
                >
                  <SpoolIcon
                    color={spoolColorString(spool.rgba)}
                    isEmpty={false}
                    size={40}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <div className="font-medium text-white truncate">
                        {spool.color_name || translateInterface("orders.runtimeInterface.unknownColor")}
                      </div>
                      <span className="text-[10px] font-mono text-bambu-gray shrink-0">#{spool.id}</span>
                    </div>
                    <div className="text-sm text-bambu-gray truncate">
                      {spool.brand} &bull; {spool.material}
                      {spool.subtype && ` ${spool.subtype}`}
                    </div>
                  </div>
                  <div className="text-sm font-mono text-bambu-gray">
                    {Math.max(0, spool.label_weight - spool.weight_used)}g
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-5 py-4 border-t border-bambu-dark-tertiary">
          <button
            onClick={handleClose}
            className="px-4 py-2.5 rounded-lg text-sm font-medium bg-bambu-dark-tertiary text-bambu-gray-light hover:bg-bambu-dark-tertiary transition-colors min-h-[44px]"
          >
            {t('common.cancel', 'Cancel')}
          </button>
          <button
            onClick={handleConfirm}
            disabled={!selectedSpool}
            className="px-4 py-2.5 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors min-h-[44px]"
          >
            {t('spoolbuddy.dashboard.linkTag', 'Link Tag')}
          </button>
        </div>
      </div>
    </div>
  );
}
