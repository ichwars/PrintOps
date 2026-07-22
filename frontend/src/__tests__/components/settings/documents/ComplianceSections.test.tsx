import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

import { ApiError } from '../../../../api/client';
import { EInvoicePolicySection } from '../../../../components/settings/documents/EInvoicePolicySection';
import { ReadinessPanel } from '../../../../components/settings/documents/ReadinessPanel';
import { TaxPolicySection } from '../../../../components/settings/documents/TaxPolicySection';
import i18n from '../../../../i18n';
import { render, screen } from '../../../utils';

const einvoice = {
  requirement: 'rule_required',
  en16931_version: '1.3.16',
  cius_name: 'XRechnung',
  cius_version: '3.0.2',
  syntax: 'ubl_2_1',
  zugferd_profile: 'EN16931',
  process_identifier: null,
  seller_identifier: null,
  seller_identifier_scheme: null,
  default_payment_method: null,
  bank_account_id: null,
  recipient_requirements: {},
};

describe('document compliance sections', () => {
  it('requires a reason before a permitted tax override can be saved', async () => {
    await i18n.changeLanguage('de');
    const user = userEvent.setup();
    render(
      <TaxPolicySection
        tax={{ allowed_cases: ['domestic_standard'], decision_rules: {}, allow_override: true }}
        ruleVersion="2026.1"
        canOverride
        disabled={false}
        findings={[]}
        onChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('checkbox', { name: 'Steuerfall manuell abweichend festlegen' }));
    expect(screen.getByRole('button', { name: 'Abweichung übernehmen' })).toBeDisabled();
    await user.type(screen.getByLabelText('Begründung'), 'Steuerberaterprüfung vom 20.07.2026');
    expect(screen.getByRole('button', { name: 'Abweichung übernehmen' })).toBeEnabled();
  });

  it('focuses the field selected from a blocking readiness finding', async () => {
    await i18n.changeLanguage('de');
    const user = userEvent.setup();
    render(
      <>
        <EInvoicePolicySection policy={einvoice} disabled={false} findings={[]} onChange={vi.fn()} />
        <ReadinessPanel report={{
          context: 'configuration',
          status: 'blocked',
          findings: [{
            severity: 'blocker',
            code: 'buyer_endpoint_missing',
            field_path: 'einvoice.buyer_endpoint',
            message_key: 'documents.errors.buyerEndpointMissing',
            correction: 'Empfängerkennung ergänzen',
            rule_id: 'BR-DE-15',
          }],
        }} />
      </>,
    );

    await user.click(screen.getByRole('button', { name: /Empfängerkennung fehlt/ }));
    expect(screen.getByLabelText('Empfängerkennung')).toHaveFocus();
  });

  it('shows rule id and correlation id instead of a generic error', () => {
    render(<ReadinessPanel error={new ApiError('Not found', 422, 'validation_failed', { rule_id: 'BR-DE-15', correlation_id: 'corr-123' })} />);
    expect(screen.getByText('BR-DE-15')).toBeInTheDocument();
    expect(screen.getByText('corr-123')).toBeInTheDocument();
    expect(screen.queryByText('Not found')).not.toBeInTheDocument();
  });
});
