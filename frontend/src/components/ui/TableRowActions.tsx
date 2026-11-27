import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ActionMenu } from './ActionMenu';
import { tableStickyActionCellClass, tableStickyActionHeaderClass } from './tableStyles';

export interface TableAction {
  label: string;
  icon: LucideIcon;
  onSelect: (trigger: HTMLButtonElement | null) => void;
  disabled?: boolean;
  destructive?: boolean;
}

export function TableActionHeader() {
  const { t } = useTranslation();
  return <th scope="col" className={tableStickyActionHeaderClass}>{t('common.actions')}</th>;
}

export function TableRowActions({ subject, actions }: { subject: string; actions: TableAction[] }) {
  return (
    <td className={tableStickyActionCellClass} onClick={event => event.stopPropagation()}>
      {actions.length > 0 && <TableRowMenu subject={subject} actions={actions} />}
    </td>
  );
}

export function TableRowMenu({ subject, actions }: { subject: string; actions: TableAction[] }) {
  const { t } = useTranslation();
  return (
    <ActionMenu
        label={`${t('common.actions')}: ${subject}`}
        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-table-secondary transition-colors hover:bg-bambu-dark-tertiary hover:text-white focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-foreground aria-expanded:bg-bambu-dark-tertiary max-[768px]:h-[44px] max-[768px]:w-[44px] [&>svg]:text-current"
      >
        {(close) => actions.map(({ label, icon: Icon, onSelect, disabled, destructive }) => (
          <button
            key={label}
            type="button"
            role="menuitem"
            tabIndex={-1}
            disabled={disabled}
            onClick={() => onSelect(close())}
            className={`flex min-h-8 w-full items-center gap-2 px-3 py-2 text-start text-sm leading-normal hover:bg-bambu-dark-tertiary focus-visible:bg-bambu-dark-tertiary focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-foreground disabled:cursor-not-allowed disabled:opacity-50 max-[768px]:min-h-[44px] ${destructive ? 'text-red-700 dark:text-red-300' : 'text-white'}`}
          >
            <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
            {label}
          </button>
        ))}
    </ActionMenu>
  );
}
