import { afterEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import userEvent from '@testing-library/user-event';

import { DocumentSettings } from '../../components/settings/documents/DocumentSettings';
import i18n from '../../i18n';
import { server } from '../mocks/server';
import { render, screen, within } from '../utils';

const profile = {
  id: 4,
  name: 'TT - ModelPrint',
  country_code: 'DE',
  default_currency: 'EUR',
  timezone: 'Europe/Berlin',
  default_locale: 'de',
  billing_mode: 'internal',
  is_default: true,
  is_active: true,
};

const policy = {
  document_type: 'invoice' as const,
  language: 'de',
  basic: { subject: 'Rechnung {DOCUMENT_NUMBER}', validity_days: null, date_rule: 'issue_date', rounding_mode: 'half_up', reference_requirements: {}, allowed_successors: [] },
  payment: {
    payment_term_days: 14,
    currency: 'EUR',
    due_date_basis: 'issue_date',
    payment_methods: ['bank_transfer'],
    discount_days: 0,
    discount_percent: '0',
    installments: [],
    prepayment_percent: '0',
    installment_enabled: false,
    bank_account_id: 2,
    bank_assignments: [{ bank_account_id: 2, is_default: true }],
    use_term_in_invoice_text: true,
  },
  dunning: { enabled: false, annual_interest_rate: '0', flat_fee: '0', stages: [] },
  content: { include_calculation_data: true, visible_content: {} },
  tax: { allowed_cases: ['domestic_standard'], decision_rules: {}, allow_override: false },
  einvoice: {
    requirement: 'rule_required', en16931_version: '1.3.16', cius_name: 'XRechnung', cius_version: '3.0.2',
    syntax: 'ubl_2_1', zugferd_profile: 'EN16931', process_identifier: null, seller_identifier: 'rechnung@example.de',
    seller_identifier_scheme: 'EM', default_payment_method: 'bank_transfer', bank_account_id: 2, recipient_requirements: {},
  },
  text_blocks: [
    { purpose: 'intro', body: 'Rechnung {DOCUMENT_NUMBER}', condition: null, position: 0 },
    { purpose: 'closing', body: 'Vielen Dank.', condition: null, position: 1 },
    { purpose: 'payment_terms', body: 'Zahlbar bis {DUE_DATE}.', condition: null, position: 2 },
  ],
};

function installFlowApi() {
  let status: 'draft' | 'active' = 'draft';
  let lockVersion = 3;
  let currentPolicy = structuredClone(policy);
  const summary = () => ({
    id: 17, business_profile_id: 4, document_type: 'invoice', language: 'de', version: 2,
    status, effective_from: status === 'active' ? '2026-07-22' : null, lock_version: lockVersion,
    change_reason: status === 'active' ? 'Freigegebene Rechnungsbedingungen' : 'Initial',
    created_by_id: 1, published_by_id: status === 'active' ? 1 : null,
    created_at: '2026-07-01T10:00:00Z', updated_at: '2026-07-22T10:00:00Z',
    published_at: status === 'active' ? '2026-07-22T10:00:00Z' : null,
    publication_validation_status: status === 'active' ? 'passed' : null,
    rule_versions: { tax: '2026.1', en16931: '1.3.16', xrechnung: '3.0.2-2026-01-31' },
  });
  const detail = () => ({ ...summary(), policy: currentPolicy, validation_findings: [] });

  server.use(
    http.get('/api/v1/business-profiles/options', () => HttpResponse.json([profile])),
    http.get('/api/v1/document-configurations/catalog', () => HttpResponse.json({
      tax_rule_version: '2026.1',
      einvoice_rule_versions: { en16931: '1.3.16', xrechnung: '3.0.2-2026-01-31', zugferd: '2.5' },
      document_types: [{ key: 'invoice', einvoice: true, issuer_role: 'seller', has_payment_terms: true, has_tax: true, allowed_successors: [] }],
    })),
    http.get('/api/v1/document-configurations/placeholders', () => HttpResponse.json({ placeholders: ['DOCUMENT_NUMBER', 'DUE_DATE'], text_block_purposes: ['intro', 'closing', 'payment_terms'] })),
    http.get('/api/v1/document-configurations/', () => HttpResponse.json([summary()])),
    http.get('/api/v1/document-configurations/17', () => HttpResponse.json(detail())),
    http.post('/api/v1/document-configurations/effective', () => HttpResponse.json({ configuration_id: 17, configuration_version: 2, basic: {}, payment: {}, content: {}, tax: {}, einvoice: {}, text_blocks: [] })),
    http.get('/api/v1/document-configurations/17/readiness', () => HttpResponse.json({ context: 'configuration', status: 'ready', findings: [] })),
    http.get('/api/v1/document-configurations/17/history', () => HttpResponse.json([summary()])),
    http.get('/api/v1/document-configurations/17/audit', () => HttpResponse.json([])),
    http.patch('/api/v1/document-configurations/17', async ({ request }) => {
      const body = await request.json() as { patch: { payment: typeof policy.payment } };
      currentPolicy = { ...currentPolicy, ...body.patch };
      lockVersion += 1;
      return HttpResponse.json(detail());
    }),
    http.post('/api/v1/document-configurations/17/publish', async ({ request }) => {
      const body = await request.json() as { reason: string };
      expect(body.reason).toBe('Freigegebene Rechnungsbedingungen');
      status = 'active';
      lockVersion += 1;
      return HttpResponse.json(detail());
    }),
  );

  return { getPaymentTerm: () => currentPolicy.payment.payment_term_days };
}

describe('document settings complete flow', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('saves, checks, schedules and publishes a German invoice configuration', async () => {
    await i18n.changeLanguage('de');
    const state = installFlowApi();
    const user = userEvent.setup();
    render(<DocumentSettings />);

    const paymentTerm = await screen.findByLabelText('Zahlungsziel in Tagen');
    await user.clear(paymentTerm);
    await user.type(paymentTerm, '30');
    await user.type(screen.getByLabelText('Änderungsgrund'), 'Zahlungsziel auf 30 Tage');
    await user.click(screen.getByRole('button', { name: 'Entwurf speichern' }));

    expect(await screen.findByText('Entwurf gespeichert.')).toBeInTheDocument();
    expect(state.getPaymentTerm()).toBe(30);
    await user.click(screen.getByRole('button', { name: 'Bereitschaft prüfen' }));
    expect(await screen.findByText('Bereit')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Änderungsgrund'), 'Freigegebene Rechnungsbedingungen');
    await user.click(screen.getByRole('button', { name: 'Freigeben' }));
    const dialog = screen.getByRole('dialog', { name: 'Konfiguration freigeben' });
    await user.click(within(dialog).getByRole('button', { name: 'Freigeben' }));

    expect(await screen.findByText('Aktiv · Version 2')).toBeInTheDocument();
  });
});
