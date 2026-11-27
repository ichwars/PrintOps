import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui';

export function OrderFilterChip({ label, onClear }: { label: string; onClear: () => void }) {
  const { t } = useTranslation();
  return (
    <Button variant="secondary" size="sm" type="button" title={t('common.reset')} onClick={onClear}
      className="max-[768px]:min-h-[44px]!">
      <span>{label}</span><X aria-hidden="true" className="h-4 w-4" />
    </Button>
  );
}
