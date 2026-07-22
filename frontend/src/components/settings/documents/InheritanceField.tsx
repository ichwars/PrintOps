import type { ReactNode } from 'react';
import { RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { SourcedValue } from '../../../api/documentManagement';
import { Button } from '../../ui';

interface InheritanceFieldProps<T> {
  path: string;
  sourced?: SourcedValue<T>;
  children: ReactNode;
  onReset: (path: string) => void;
}

const sourceKeys: Record<SourcedValue<unknown>['source'], string> = {
  system: 'system',
  business_profile: 'businessProfile',
  customer: 'customer',
  configuration: 'configuration',
  document: 'document',
};

export function InheritanceField<T>({ path, sourced, children, onReset }: InheritanceFieldProps<T>) {
  const { t } = useTranslation();
  const source = sourced?.source ?? 'configuration';
  const canReset = Boolean(sourced?.overridable && source !== 'configuration');

  return (
    <div data-field-path={path} className="space-y-1.5">
      <div className="flex min-h-6 flex-wrap items-center justify-between gap-2">
        <span className="rounded-full border border-bambu-dark-tertiary bg-bambu-dark px-2 py-0.5 text-[11px] font-medium text-gray-400">
          {t(`settings.documents.inheritance.${sourceKeys[source]}`, source)}
        </span>
        {canReset ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => onReset(path)}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            {t('settings.documents.inheritance.reset', 'Restore default')}
          </Button>
        ) : null}
      </div>
      {children}
    </div>
  );
}
