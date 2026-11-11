import { AlertCircle, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '../api/client';
import { Card, CardContent } from './Card';
import { Button } from './Button';

export function KProfileReadFailure({ error, onRefresh }: { error: Error; onRefresh: () => void }) {
  const { t } = useTranslation();
  const noAnswer = error instanceof ApiError && error.status === 504;
  return (
    <Card>
      <CardContent className="py-12 text-center">
        <AlertCircle className="w-12 h-12 text-amber-700 dark:text-amber-400 mx-auto mb-4" />
        <h3 className="text-lg font-semibold text-white mb-2">{t('kProfiles.readFailed')}</h3>
        <p className="text-bambu-gray mb-4">{noAnswer ? t('kProfiles.noAnswerDesc') : error.message}</p>
        <Button variant="secondary" onClick={onRefresh}>
          <RefreshCw className="w-4 h-4" />{t('common.refresh')}
        </Button>
      </CardContent>
    </Card>
  );
}
