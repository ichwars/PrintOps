import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { ConfirmModal } from './ConfirmModal';

export function ShoppingListClearButton() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const clearList = useMutation({
    mutationFn: () => api.clearShoppingList(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shopping-list'] });
      setConfirm(false);
    },
    onError: () => showToast(t('forecast.failedSaveSettings'), 'error'),
  });

  return (
    <>
      <button type="button" onClick={() => setConfirm(true)} className="text-xs text-red-700 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 transition-colors px-2 py-1 rounded border border-red-200 dark:border-red-500/20 hover:bg-red-50 dark:hover:bg-red-500/10">
        {t('forecast.clearAll')}
      </button>
      {confirm && (
        <ConfirmModal
          title={t('forecast.clearAll')}
          message={t('forecast.clearAllConfirm')}
          confirmText={t('forecast.clearAll')}
          variant="danger"
          isLoading={clearList.isPending}
          onConfirm={() => clearList.mutate()}
          onCancel={() => setConfirm(false)}
        />
      )}
    </>
  );
}
