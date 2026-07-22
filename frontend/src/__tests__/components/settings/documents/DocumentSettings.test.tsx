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
    payment: {
      payment_term_days: 14,
      currency: 'EUR',
      discount_days: 0,
      discount_percent: '0',
      installments: [],
      bank_assignments: [],
    },
    dunning: { enabled: false, annual_interest_rate: '0', flat_fee: '0', stages: [] },
    text_blocks: [],
  },
  validation_findings: [],
};

function useDocumentSettingsApi() {
  server.use(
    http.get('/api/v1/business-profiles/options', () => HttpResponse.json([profile])),
    http.get('/api/v1/document-configurations/catalog', () => HttpResponse.json({
      document_types: [
        { key: 'invoice', einvoice: true, issuer_role: 'seller', has_payment_terms: true, has_tax: true, allowed_successors: [] },
        { key: 'quotation', einvoice: false, issuer_role: 'seller', has_payment_terms: true, has_tax: true, allowed_successors: ['invoice'] },
      ],
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
