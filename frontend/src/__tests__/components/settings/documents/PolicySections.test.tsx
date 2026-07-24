import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

import { PaymentPolicySection } from '../../../../components/settings/documents/PaymentPolicySection';
import { TextBlocksSection } from '../../../../components/settings/documents/TextBlocksSection';
import i18n from '../../../../i18n';
import { render, screen, selectComboboxOption } from '../../../utils';

const sourced = <T,>(value: T, source = 'configuration', overridable = true) => ({
  value,
  source: source as 'system' | 'business_profile' | 'customer' | 'configuration' | 'document',
  overridable,
});

const payment = {
  payment_term_days: 30,
  currency: 'EUR',
  due_date_basis: 'issue_date',
  payment_methods: ['bank_transfer'],
  discount_days: 7,
  discount_percent: '2.00',
  installments: [],
  prepayment_percent: '0',
  installment_enabled: false,
  bank_account_id: null,
  bank_assignments: [],
  use_term_in_invoice_text: true,
};

describe('document policy sections', () => {
  it('shows the source and restores an inherited value', async () => {
    await i18n.changeLanguage('de');
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <PaymentPolicySection
        payment={payment}
        dunning={{ enabled: false, annual_interest_rate: '0', flat_fee: '0', stages: [] }}
        effectivePayment={{ payment_term_days: sourced(30, 'customer') }}
        findings={[]}
        disabled={false}
        onChange={onChange}
      />,
    );

    expect(screen.getByText('Vom Kunden übernommen')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Vorgabe wiederherstellen' }));
    expect(onChange).toHaveBeenCalledWith('payment.payment_term_days', undefined);
  });

  it('renders dunning stages in deterministic order and validates percentages', async () => {
    await i18n.changeLanguage('de');
    render(
      <PaymentPolicySection
        payment={{ ...payment, installment_enabled: true, installments: [{ percent: '60', due_days: 0 }, { percent: '30', due_days: 30 }] }}
        dunning={{
          enabled: true,
          annual_interest_rate: '5',
          flat_fee: '2.50',
          stages: [
            { level: 2, wait_days: 14, fee: '5', charge_interest: true, new_due_days: 7, body: 'Zweite Mahnung', escalation_hint: null },
            { level: 1, wait_days: 7, fee: '2.50', charge_interest: false, new_due_days: 7, body: 'Erste Mahnung', escalation_hint: null },
          ],
        }}
        effectivePayment={{}}
        findings={[]}
        disabled={false}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getAllByTestId('dunning-stage').map((node) => node.textContent)).toEqual([
      expect.stringContaining('Stufe 1'),
      expect.stringContaining('Stufe 2'),
    ]);
    expect(screen.getByText('Die Raten müssen zusammen 100 % ergeben.')).toBeInTheDocument();
  });

  it('offers only placeholders allowed for the selected type', async () => {
    await i18n.changeLanguage('de');
    render(
      <TextBlocksSection
        documentType="delivery_note"
        blocks={[]}
        catalog={{
          placeholders: ['document.service_date', 'payment.discount_deadline'],
          text_block_purposes: ['intro', 'delivery_terms', 'payment_terms'],
        }}
        findings={[]}
        disabled={false}
        onChange={vi.fn()}
      />,
    );

    selectComboboxOption(screen.getByLabelText('Platzhalter einfügen'), 'Lieferdatum');
    expect(screen.queryByRole('option', { name: 'Skontofrist' })).not.toBeInTheDocument();
  });
});
