import { Copy, Star } from 'lucide-react';

import type { CalculationVariant } from '../../../api/calculations';

interface VariantStripProps {
  variants: CalculationVariant[];
  activeIndex: number;
  locale: string;
  onActiveChange: (index: number) => void;
  onPreferredChange: (index: number) => void;
  onClone: () => void;
}

export function VariantStrip({ variants, activeIndex, locale, onActiveChange, onPreferredChange, onClone }: VariantStripProps) {
  const de = locale.startsWith('de');
  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-white">2. {de ? 'Varianten' : 'Variants'}</h3>
          <p className="text-xs text-bambu-gray">{de ? 'Anklicken zum Bearbeiten; Stern bestimmt die Angebotsvariante.' : 'Click to edit; the star selects the offer variant.'}</p>
        </div>
        <button type="button" onClick={onClone} className="inline-flex items-center gap-2 rounded bg-bambu-dark px-3 py-2 text-sm text-white">
          <Copy className="h-4 w-4" />{de ? 'Variante kopieren' : 'Clone variant'}
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {variants.map((variant, index) => (
          <div key={`${variant.name}-${index}`} className={`flex items-center rounded-lg border ${index === activeIndex ? 'border-bambu-green bg-bambu-green/5' : 'border-bambu-dark-tertiary'}`}>
            <button type="button" aria-label={de ? `Variante ${variant.name} bearbeiten` : `Edit variant ${variant.name}`} onClick={() => onActiveChange(index)} className="px-3 py-2 text-sm text-white">
              {variant.name}
            </button>
            <button type="button" aria-label={de ? `${variant.name} als bevorzugt markieren` : `Mark ${variant.name} as preferred`} aria-pressed={variant.is_preferred} onClick={() => onPreferredChange(index)} className={`border-l border-bambu-dark-tertiary p-2 ${variant.is_preferred ? 'text-bambu-green' : 'text-bambu-gray hover:text-white'}`}>
              <Star className="h-4 w-4" fill={variant.is_preferred ? 'currentColor' : 'none'} />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
