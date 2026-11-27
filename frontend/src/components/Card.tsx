import { createContext, useContext } from 'react';
import type { ReactNode, MouseEvent, HTMLAttributes } from 'react';
import { dashboardStyles } from './dashboardStyles';

type CardDensity = 'normal' | 'dense';

const CardDensityContext = createContext<CardDensity>('normal');
const DashboardCardContext = createContext(false);

export function CardDensityProvider({ density, dashboard = false, children }: { density: CardDensity; dashboard?: boolean; children: ReactNode }) {
  return <CardDensityContext.Provider value={density}>
    <DashboardCardContext.Provider value={dashboard}>{children}</DashboardCardContext.Provider>
  </CardDensityContext.Provider>;
}

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  className?: string;
  onClick?: (e: MouseEvent) => void;
  onContextMenu?: (e: MouseEvent) => void;
}

interface CardSectionProps {
  children: ReactNode;
  className?: string;
  dense?: boolean;
}

export function Card({ children, className = '', onClick, onContextMenu, ...rest }: CardProps) {
  const dashboard = useContext(DashboardCardContext);
  return (
    <div
      className={`${dashboard ? `${dashboardStyles.card} min-w-0` : 'bg-bambu-dark-secondary rounded-xl border border-bambu-dark-tertiary card-shadow'} ${className}`}
      onClick={onClick}
      onContextMenu={onContextMenu}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className = '', dense }: CardSectionProps) {
  const ctxDense = useContext(CardDensityContext) === 'dense';
  const dashboard = useContext(DashboardCardContext);
  const layout = dashboard ? `${dashboardStyles.cardHeader} rounded-t-xl [&_h2]:text-sm [&_h3]:text-sm [&_h2]:font-medium [&_h3]:font-medium` :
    `${(dense ?? ctxDense) ? 'px-4 py-2.5' : 'px-6 py-4'} border-b border-bambu-dark-tertiary`;
  return (
    <div className={`${layout} ${className}`}>
      {children}
    </div>
  );
}

export function CardContent({ children, className = '', dense }: CardSectionProps) {
  const ctxDense = useContext(CardDensityContext) === 'dense';
  const dashboard = useContext(DashboardCardContext);
  const layout = dashboard ? `${dashboardStyles.cardBody} text-sm text-table-secondary` : (dense ?? ctxDense) ? 'p-4' : 'p-6';
  return <div className={`${layout} ${className}`}>{children}</div>;
}
