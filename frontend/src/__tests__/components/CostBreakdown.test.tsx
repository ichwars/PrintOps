import { beforeAll, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import i18n from '../../i18n';
import { CostBreakdown } from '../../components/orders/calculation/CostBreakdown';
import type { CalculationPreview } from '../../api/calculations';

beforeAll(() => i18n.loadLanguages('nl'));

describe('Dutch financial cost labels', () => {
  it('describes shipping as a cost and retains the amount and currency', () => {
    const preview = {
      breakdown: [{ code: 'shipping', label: 'Shipping', basis: 'flat amount', amount: '12.50' }],
    } as CalculationPreview;

    render(<CostBreakdown preview={preview} locale="nl-NL" currency="EUR" />);

    expect(screen.getByText('Verzendkosten')).toBeInTheDocument();
    expect(screen.getByText(/vast bedrag/i)).toBeInTheDocument();
    expect(screen.getByText(/€\s*12,50/)).toBeInTheDocument();
    expect(screen.queryByText('Verzendadres')).not.toBeInTheDocument();
  });
});
