import { LegacySelect, Modal, TextField } from './ui';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, ArrowRightLeft } from 'lucide-react';
import { api, multiVirtualPrinterApi } from '../api/client';
import { Button } from './Button';
import { useToast } from '../contexts/ToastContext';

type Mode = 'archive' | 'review' | 'queue' | 'proxy';

const MODE_LABELS: Record<string, string> = {
  archive: 'archive',
  review: 'review',
  queue: 'queue',
  proxy: 'proxy',
};

interface VirtualPrinterAddDialogProps {
  onClose: () => void;
}

export function VirtualPrinterAddDialog({ onClose }: VirtualPrinterAddDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [name, setName] = useState('');
  const [mode, setMode] = useState<Mode>('archive');
  const [targetPrinterId, setTargetPrinterId] = useState<number | null>(null);

  const { data: printers } = useQuery({
    queryKey: ['printers'],
    queryFn: api.getPrinters,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      multiVirtualPrinterApi.create({
        name: name.trim() || 'PrintOps',
        mode,
        target_printer_id: mode === 'proxy' ? (targetPrinterId ?? undefined) : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['virtual-printers'] });
      showToast(t('virtualPrinter.toast.created'));
      onClose();
    },
    onError: (error: Error) => {
      showToast(error.message || t('virtualPrinter.toast.failedToCreate'), 'error');
    },
  });

  return (
    <Modal
      open
      onClose={onClose}
      closeLabel={t('common.close')}
      title={t('virtualPrinter.addDialog.title')}
      className="max-w-md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={createMutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button className="text-black!" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
            {createMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              t('virtualPrinter.addDialog.create')
            )}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {/* Name */}
        <div>
          <TextField
            label={t('virtualPrinter.addDialog.name')}
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="PrintOps"
            className="w-full bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-md px-3 py-2 text-white text-sm placeholder-bambu-gray"
          />
        </div>

        {/* Mode */}
        <div>
          <label className="text-sm text-white font-medium block mb-1">{t('virtualPrinter.mode.title')}</label>
          <div role="group" aria-label={t('virtualPrinter.mode.title')} className="grid grid-cols-2 gap-2">
            {(['archive', 'review', 'queue', 'proxy'] as const).map((m) => (
              <Button variant="unstyled"
                key={m}
                aria-pressed={mode === m}
                onClick={() => setMode(m)}
                className={`p-2 rounded-lg border text-left transition-colors ${
                  mode === m
                    ? m === 'proxy'
                      ? 'border-blue-500 bg-blue-500/10'
                      : 'border-accent-foreground bg-bambu-green/10'
                    : 'border-bambu-dark-tertiary hover:border-bambu-gray'
                }`}
              >
                <div className="flex items-center gap-1.5 text-white text-xs font-medium">
                  {m === 'proxy' && <ArrowRightLeft className="w-3 h-3" />}
                  {t(`virtualPrinter.mode.${MODE_LABELS[m]}`)}
                </div>
                <div className="text-xs text-table-secondary">
                  {t(`virtualPrinter.mode.${MODE_LABELS[m]}Desc`)}
                </div>
              </Button>
            ))}
          </div>
        </div>

        {/* Target Printer - only for proxy mode */}
        {mode === 'proxy' && (
          <div>
            <label className="text-sm text-white font-medium block mb-1">{t('virtualPrinter.targetPrinter.title')}</label>
            <div className="relative">
              <LegacySelect
                aria-label={t('virtualPrinter.targetPrinter.title')}
                value={targetPrinterId ?? ''}
                onChange={(e) => {
                  const id = parseInt(e.target.value, 10);
                  setTargetPrinterId(isNaN(id) ? null : id);
                }}
                className="w-full bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-md px-3 py-2 text-white text-sm appearance-none cursor-pointer pr-10"
              >
                <option value="">{t('virtualPrinter.targetPrinter.placeholder')}</option>
                {printers?.map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.ip_address})</option>
                ))}
              </LegacySelect>
            </div>
          </div>
        )}

        <p className="text-xs text-table-secondary">
          {t('virtualPrinter.addDialog.hint')}
        </p>
      </div>
    </Modal>
  );
}
