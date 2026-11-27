import type { MouseEvent, ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { dashboardStyles } from '../dashboardStyles';
import { ScrollArea } from '../ui';
import { tableBodyRowClass, tableFrameClass } from '../ui/tableStyles';

export const orderPageClass = `min-w-0 space-y-6 ${dashboardStyles.page}`;
export const orderPanelClass = 'min-w-0 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4';
export const orderControlClass = 'bg-bambu-dark-secondary! text-sm max-[768px]:min-h-[44px]!';
export const orderActionClass = 'inline-flex min-h-[34px] items-center gap-1.5 rounded-md px-2.5 text-sm font-medium text-table-secondary transition-colors hover:bg-bambu-dark-tertiary hover:text-white focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-foreground max-[768px]:min-h-[44px]';

const orderTones = {
  neutral: 'bg-bambu-dark-tertiary/50 text-table-secondary',
  positive: 'bg-green-500/10 text-green-800 dark:text-green-300',
  warning: 'bg-amber-500/10 text-amber-800 dark:text-amber-300',
  danger: 'bg-red-500/10 text-red-700 dark:text-red-300',
};

export function OrderHeader({ icon: Icon, title, description, children }: {
  icon: LucideIcon;
  title: ReactNode;
  description: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div className="min-w-0">
        <h1 className={dashboardStyles.title}>
          <Icon aria-hidden="true" className={dashboardStyles.titleIcon} />
          <span className="min-w-0 wrap-break-word">{title}</span>
        </h1>
        <p className={`${dashboardStyles.subtitle} text-table-secondary`}>{description}</p>
      </div>
      {children && <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">{children}</div>}
    </header>
  );
}

export function OrderTable({ label, children, footer }: { label: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className={tableFrameClass}>
      <ScrollArea
        direction="horizontal"
        scrollbar="thin"
        role="region"
        aria-label={label}
        tabIndex={0}
        className="focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-foreground"
      >
        {children}
      </ScrollArea>
      {footer}
    </div>
  );
}

export function OrderTableRow({ children, className = '', onOpen, busy }: {
  children: ReactNode;
  className?: string;
  onOpen?: () => void;
  busy?: boolean;
}) {
  function handleClick(event: MouseEvent<HTMLTableRowElement>) {
    const { currentTarget: row, target } = event;
    if (event.defaultPrevented || !(target instanceof Element) || !row.contains(target)) return;
    if (target.closest('a, button, input, label, select, textarea, summary, [contenteditable], [role="button"], [role="link"]')) return;
    const selection = row.ownerDocument.getSelection();
    if (selection && !selection.isCollapsed && selection.rangeCount && selection.getRangeAt(0).intersectsNode(row)) return;
    row.focus({ preventScroll: true });
    onOpen?.();
  }

  return (
    <tr
      className={`${tableBodyRowClass} ${onOpen ? 'cursor-pointer focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-foreground' : ''} ${className}`}
      tabIndex={onOpen ? 0 : undefined}
      aria-busy={busy || undefined}
      aria-keyshortcuts={onOpen ? 'Enter Space' : undefined}
      onClick={onOpen ? handleClick : undefined}
      onKeyDown={onOpen && (event => {
        if (event.target !== event.currentTarget || event.defaultPrevented) return;
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        if (!event.repeat) onOpen();
      })}
    >
      {children}
    </tr>
  );
}

export function OrderStatus({ tone = 'neutral', children }: {
  tone?: keyof typeof orderTones;
  children: ReactNode;
}) {
  return (
    <span className={`inline-flex max-w-full items-center gap-1 rounded-md px-2 py-1 text-xs font-medium ${orderTones[tone]}`}>
      {children}
    </span>
  );
}
