import { afterEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import userEvent from '@testing-library/user-event';

import { setAuthToken } from '../../../../api/client';
import { DocumentSettings } from '../../../../components/settings/documents/DocumentSettings';
import i18n from '../../../../i18n';
import { server } from '../../../mocks/server';
import { render, screen, selectComboboxOption } from '../../../utils';

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

const summary = {
  id: 17,
  business_profile_id: 4,
  document_type: 'invoice',
  language: 'de',
  version: 2,
  status: 'draft',
  effective_from: null,
  lock_version: 3,
  change_reason: 'Initial configuration',
  created_by_id: 1,
  published_by_id: null,
  created_at: '2026-07-01T10:00:00Z',
  updated_at: '2026-07-01T10:00:00Z',
  published_at: null,
  publication_validation_status: null,
  rule_versions: {},
};

const detail = {
  ...summary,
  policy: {
    document_type: 'invoice',
    language: 'de',
    basic: { subject: 'Rechnung', validity_days: null, date_rule: 'issue_date', rounding_mode: 'half_up', reference_requirements: {}, allowed_successors: [] },
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
      bank_account_id: null,
      bank_assignments: [],
      use_term_in_invoice_text: true,
    },
    dunning: { enabled: false, annual_interest_rate: '0', flat_fee: '0', stages: [] },
    content: { include_calculation_data: true, visible_content: {} },
    tax: { allowed_cases: ['domestic_standard'], decision_rules: {}, allow_override: false },
    einvoice: {
      requirement: 'rule_required', en16931_version: '1.3.16', cius_name: 'XRechnung', cius_version: '3.0.2',
      syntax: 'ubl_2_1', zugferd_profile: 'EN16931', process_identifier: null, seller_identifier: null,
      seller_identifier_scheme: null, default_payment_method: null, bank_account_id: null, recipient_requirements: {},
    },
    text_blocks: [],
  },
  validation_findings: [],
};

function useDocumentSettingsApi() {
  server.use(
    http.get('/api/v1/business-profiles/options', () => HttpResponse.json([profile])),
    http.get('/api/v1/document-configurations/catalog', () => HttpResponse.json({
      tax_rule_version: '2026.1',
      einvoice_rule_versions: { en16931: '1.3.16', xrechnung: '3.0.2-2026-01-31' },
      document_types: [
        { key: 'invoice', einvoice: true, issuer_role: 'seller', has_payment_terms: true, has_tax: true, allowed_successors: [] },
        { key: 'quotation', einvoice: false, issuer_role: 'seller', has_payment_terms: true, has_tax: true, allowed_successors: ['invoice'] },
      ],
    })),
    http.get('/api/v1/document-configurations/placeholders', () => HttpResponse.json({ placeholders: [], text_block_purposes: ['intro', 'closing', 'footer'] })),
    http.post('/api/v1/document-configurations/effective', () => HttpResponse.json({
      configuration_id: 17,
      configuration_version: 2,
      basic: {}, payment: {}, content: {}, tax: {}, einvoice: {}, text_blocks: [],
    })),
    http.get('/api/v1/document-configurations/', () => HttpResponse.json([summary])),
    http.get('/api/v1/document-configurations/17', () => HttpResponse.json(detail)),
    http.get('/api/v1/document-configurations/17/readiness', () => HttpResponse.json({
      context: 'configuration',
      status: 'blocked',
      findings: [{
        severity: 'blocker',
        code: 'number_sequence_missing',
        field_path: 'number_sequence',
        message_key: 'documents.errors.numberSequenceMissing',
        correction: 'Configure the invoice number sequence',
        rule_id: null,
      }],
    })),
    http.get('/api/v1/document-configurations/17/history', () => HttpResponse.json([summary])),
    http.get('/api/v1/document-configurations/17/audit', () => HttpResponse.json([])),
  );
}

describe('DocumentSettings', () => {
  afterEach(async () => {
    setAuthToken(null);
    await i18n.changeLanguage('en');
  });

  it('renders profile, type, language, version, and readiness in the context header', async () => {
    await i18n.changeLanguage('de');
    useDocumentSettingsApi();

    render(<DocumentSettings />);

    expect(await screen.findByLabelText('Unternehmensprofil')).toHaveTextContent('TT - ModelPrint');
    expect(screen.getByLabelText('Dokumenttyp')).toHaveTextContent('Rechnung');
    expect(screen.getByLabelText('Sprache')).toHaveTextContent('Deutsch');
    expect(await screen.findByText('Entwurf · Version 2')).toBeInTheDocument();
    expect(screen.getByText('Blockiert')).toBeInTheDocument();
  });

  it('blocks context changes until unsaved edits are discarded or saved', async () => {
    await i18n.changeLanguage('de');
    useDocumentSettingsApi();
    const user = userEvent.setup();

    render(<DocumentSettings />);

    await user.type(await screen.findByLabelText('Änderungsgrund'), 'Neue Zahlungsregeln');
    selectComboboxOption(screen.getByLabelText('Dokumenttyp'), 'Angebot');

    expect(screen.getByRole('dialog', { name: 'Ungespeicherte Änderungen' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Änderungen verwerfen' })).toBeInTheDocument();
  });
});
