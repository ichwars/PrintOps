import { Package, Search } from 'lucide-react';
import { Button } from '../../components/Button';

/* Empty state matching SpoolBuddy's design */
export function EmptyFilterState({
  hasFilters,
  onAddSpool,
  t,
}: {
  hasFilters: boolean;
  onAddSpool: () => void;
  t: (key: string) => string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <div className="relative mb-6">
        <div className="flex items-center justify-center w-24 h-24 rounded-2xl bg-bambu-dark-secondary border border-bambu-dark-tertiary shadow-lg">
          {hasFilters ? (
            <Search className="w-10 h-10 text-bambu-gray/40" strokeWidth={1.5} />
          ) : (
            <div className="relative">
              <div className="w-14 h-14 rounded-full border-4 border-bambu-gray/20 flex items-center justify-center">
                <div className="w-6 h-6 rounded-full bg-bambu-gray/10 border-2 border-bambu-gray/20" />
              </div>
              <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-bambu-green flex items-center justify-center">
                <span className="text-white text-lg font-bold leading-none">+</span>
              </div>
            </div>
          )}
        </div>
      </div>
      <h3 className="text-lg font-semibold text-white mb-2 text-center">
        {hasFilters ? t('inventory.noSpoolsMatch') : t('inventory.noSpools').split('.')[0]}
      </h3>
      <p className="text-sm text-bambu-gray text-center max-w-sm mb-6">
        {hasFilters
          ? t('inventory.noSpoolsMatchDesc')
          : t('inventory.noSpools')
        }
      </p>
      {!hasFilters && (
        <Button onClick={onAddSpool}>
          <Package className="w-4 h-4" />
          {t('inventory.addSpool')}
        </Button>
      )}
    </div>
  );
}
