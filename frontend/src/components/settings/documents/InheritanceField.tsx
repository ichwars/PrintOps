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
  const showSource = source !== 'configuration';

  return (
    <div data-field-path={path} className="space-y-1.5">
      {showSource || canReset ? (
      <div className="flex min-h-5 flex-wrap items-center justify-end gap-2">
        {showSource ? (
          <span className="text-[11px] font-medium uppercase tracking-wide text-bambu-gray">
            {t(`settings.documents.inheritance.${sourceKeys[source]}`, source)}
          </span>
        ) : null}
        {canReset ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => onReset(path)}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            {t('settings.documents.inheritance.reset', 'Restore default')}
          </Button>
        ) : null}
      </div>
      ) : null}
      {children}
    </div>
  );
}
