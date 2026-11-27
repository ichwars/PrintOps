import { useMutation } from '@tanstack/react-query';
import { useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { ConfirmModal } from '../ConfirmModal';

interface WarehouseStatusDialogProps {
  action: string;
  subject: string;
  deactivate: boolean;
  onChange: () => Promise<void>;
  onClose: () => void;
}

export function WarehouseStatusDialog({ action, subject, deactivate, onChange, onClose }: WarehouseStatusDialogProps) {
  const { t } = useTranslation();
  const pending = useRef(false);
  const mutation = useMutation({
    mutationFn: onChange,
    onSuccess: onClose,
    onSettled: () => { pending.current = false; },
  });
  return (
    <ConfirmModal
      title={action}
      message={subject}
      variant={deactivate ? 'warning' : 'default'}
      confirmText={action}
      isLoading={mutation.isPending}
      onConfirm={() => {
        if (pending.current) return;
        pending.current = true;
        mutation.mutate();
      }}
      onCancel={() => { if (!pending.current) onClose(); }}
    >
      {mutation.isError && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-300">
          {mutation.error instanceof Error ? mutation.error.message : t('common.unknownError')}
        </p>
      )}
    </ConfirmModal>
  );
}
