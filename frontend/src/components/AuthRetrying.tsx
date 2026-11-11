import { useTranslation } from 'react-i18next';

export function AuthRetrying() {
  const { t } = useTranslation();
  return (
    <div role="status" className="flex min-h-screen items-center justify-center bg-bambu-dark p-6 text-center text-bambu-gray">
      {t('login.retryingConnection')}
    </div>
  );
}
