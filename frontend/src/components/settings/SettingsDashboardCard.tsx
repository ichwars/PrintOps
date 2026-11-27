import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { dashboardStyles } from '../dashboardStyles';

export function SettingsDashboardCard({ id, title, icon: Icon, children }: {
  id: string;
  title: string;
  icon: LucideIcon;
  children: ReactNode;
}) {
  const titleId = `${id}-title`;
  return (
    <section id={id} aria-labelledby={titleId} className={`${dashboardStyles.card} min-w-0`}>
      <div className={`${dashboardStyles.cardHeader} rounded-t-xl`}>
        <h2 id={titleId} className={`${dashboardStyles.cardTitle} flex items-center gap-2`}>
          <Icon className="h-4 w-4 shrink-0 text-bambu-green" aria-hidden="true" />
          {title}
        </h2>
      </div>
      <div className={`${dashboardStyles.cardBody} space-y-4 text-sm text-table-secondary`}>{children}</div>
    </section>
  );
}
