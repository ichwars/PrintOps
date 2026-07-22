import { FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Card, CardContent, CardHeader } from '../../Card';

export function DocumentSettings() {
  const { t } = useTranslation();

  return (
    <section id="card-document-settings" className="w-full" aria-labelledby="document-settings-heading">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-bambu-green" aria-hidden="true" />
            <h2 id="document-settings-heading" className="text-base font-semibold text-white">
              {t('settings.documents.title', 'Document settings')}
            </h2>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-400">
            {t(
              'settings.documents.description',
              'Manage versioned rules for commercial documents and electronic invoices.',
            )}
          </p>
          <p className="mt-3 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-4 py-3 text-sm text-gray-300">
            {t(
              'settings.documents.contextHint',
              'Select a business profile, document type, and language to manage its approved configuration.',
            )}
          </p>
        </CardContent>
      </Card>
    </section>
  );
}
