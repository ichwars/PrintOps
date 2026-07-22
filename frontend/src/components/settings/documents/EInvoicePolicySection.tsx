import { Download, FileCheck2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { EInvoiceArtifact, EInvoicePolicyDraft, EInvoiceValidationReport, PolicyFinding } from '../../../api/documentManagement';
import { Button, Select, TextField } from '../../ui';
import { InheritanceField } from './InheritanceField';

interface EInvoicePolicySectionProps {
  policy: EInvoicePolicyDraft;
  disabled: boolean;
  findings: PolicyFinding[];
  ruleVersions?: Record<string, string>;
  artifact?: EInvoiceArtifact | null;
  validation?: EInvoiceValidationReport | null;
  canExport?: boolean;
  onDownload?: () => void;
  onChange: (path: string, value: unknown) => void;
}

export function EInvoicePolicySection({ policy, disabled, findings, ruleVersions = {}, artifact, validation, canExport = false, onDownload, onChange }: EInvoicePolicySectionProps) {
  const { t } = useTranslation();
  const reset = (path: string) => onChange(path, undefined);
  const error = (path: string) => { const key = findings.find((item) => item.field_path === path)?.message_key; return key ? t(key, key) : undefined; };
  const buyerEndpoint = String(policy.recipient_requirements.buyer_endpoint ?? '');
  const downloadReport = () => {
    if (!validation) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(validation, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `einvoice-validation-${artifact?.id ?? 'report'}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4" aria-labelledby="document-einvoice-policy-heading">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 id="document-einvoice-policy-heading" className="font-semibold text-white">{t('settings.documents.einvoice.title', 'E-invoice')}</h3><p className="mt-1 text-sm text-gray-400">{t('settings.documents.einvoice.description', 'EN 16931, XRechnung and ZUGFeRD delivery policy.')}</p></div><div className="flex flex-wrap gap-1">{Object.entries(ruleVersions).map(([name, version]) => <span key={name} className="rounded-full bg-bambu-dark px-2 py-1 text-xs text-gray-300">{name} {version}</span>)}</div></div>
      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <Select label={t('settings.documents.einvoice.requirement', 'Requirement')} value={policy.requirement} disabled={disabled} options={[{ value: 'optional', label: t('settings.documents.einvoice.optional', 'Optional') }, { value: 'rule_required', label: t('settings.documents.einvoice.ruleRequired', 'Required according to rules') }]} onValueChange={(value) => onChange('einvoice.requirement', value)} />
        <Select label={t('settings.documents.einvoice.syntax', 'Syntax')} value={policy.syntax} disabled={disabled} options={[{ value: 'ubl_2_1', label: 'UBL 2.1' }, { value: 'cii', label: 'UN/CEFACT CII' }]} onValueChange={(value) => onChange('einvoice.syntax', value)} />
        <TextField label="EN 16931" value={policy.en16931_version} readOnly helperText={t('settings.documents.einvoice.pinned', 'Pinned by the installed validator')} />
        <TextField label={`${policy.cius_name} CIUS`} value={policy.cius_version} readOnly helperText={t('settings.documents.einvoice.pinned', 'Pinned by the installed validator')} />
        <Select label={t('settings.documents.einvoice.zugferdProfile', 'ZUGFeRD profile')} value={policy.zugferd_profile} disabled={disabled} options={[{ value: 'EN16931', label: 'EN 16931' }, { value: 'XRECHNUNG', label: 'XRechnung' }]} onValueChange={(value) => onChange('einvoice.zugferd_profile', value)} />
        <TextField label={t('settings.documents.einvoice.processId', 'Business process ID')} value={policy.process_identifier ?? ''} disabled={disabled} onValueChange={(value) => onChange('einvoice.process_identifier', value || null)} />
        <InheritanceField path="einvoice.seller_identifier" onReset={reset}><TextField label={t('settings.documents.einvoice.sellerEndpoint', 'Seller electronic address')} value={policy.seller_identifier ?? ''} disabled={disabled} error={error('einvoice.seller_identifier')} onValueChange={(value) => onChange('einvoice.seller_identifier', value || null)} /></InheritanceField>
        <Select label={t('settings.documents.einvoice.endpointScheme', 'Electronic address scheme')} value={policy.seller_identifier_scheme ?? ''} disabled={disabled} options={[{ value: '', label: '—' }, { value: '0088', label: '0088 · GLN' }, { value: '0204', label: '0204 · Leitweg-ID' }, { value: '9930', label: '9930 · German VAT ID' }, { value: 'EM', label: 'EM · E-mail' }]} onValueChange={(value) => onChange('einvoice.seller_identifier_scheme', value || null)} />
        <InheritanceField path="einvoice.buyer_endpoint" onReset={reset}><TextField label={t('settings.documents.einvoice.buyerEndpoint', 'Buyer electronic address')} value={buyerEndpoint} disabled={disabled} error={error('einvoice.buyer_endpoint')} onValueChange={(value) => onChange('einvoice.recipient_requirements.buyer_endpoint', value)} /></InheritanceField>
        <TextField label={t('settings.documents.einvoice.buyerReference', 'Buyer reference / Leitweg-ID')} value={String(policy.recipient_requirements.buyer_reference ?? '')} disabled={disabled} onValueChange={(value) => onChange('einvoice.recipient_requirements.buyer_reference', value)} />
        <Select label={t('settings.documents.einvoice.defaultPaymentMethod', 'Default payment method')} value={policy.default_payment_method ?? ''} disabled={disabled} options={[{ value: '', label: '—' }, { value: '58', label: '58 · SEPA credit transfer' }, { value: '59', label: '59 · SEPA direct debit' }, { value: '30', label: '30 · Credit transfer' }]} onValueChange={(value) => onChange('einvoice.default_payment_method', value || null)} />
        <TextField type="number" label={t('settings.documents.einvoice.bankAccount', 'Bank account ID')} value={policy.bank_account_id ?? ''} disabled={disabled} onValueChange={(value) => onChange('einvoice.bank_account_id', value ? Number(value) : null)} />
      </div>
      <div className="mt-4 border-t border-bambu-dark-tertiary pt-4"><h4 className="text-sm font-medium text-white">{t('settings.documents.einvoice.validationLayers', 'Validation layers')}</h4><div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">{['xsd', 'en16931', 'cius'].map((layer) => <div key={layer} className="flex items-center gap-2 rounded-lg bg-bambu-dark p-3 text-sm text-gray-300"><FileCheck2 className="h-4 w-4 text-bambu-green" />{t(`settings.documents.einvoice.layers.${layer}`, layer)}</div>)}</div></div>
      {artifact ? <div className="mt-4 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-3 text-sm text-gray-300"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-medium text-white">{artifact.kind} · SHA-256</p><p className="mt-1 break-all font-mono text-xs">{artifact.sha256}</p><p className="mt-1">{t('settings.documents.einvoice.validationStatus', 'Validation')}: {artifact.validation_status}</p></div>{canExport ? <div className="flex flex-wrap gap-2">{onDownload ? <Button variant="secondary" onClick={onDownload}><Download className="h-4 w-4" />{t('settings.documents.einvoice.downloadXml', 'Download XML')}</Button> : null}{validation ? <Button variant="secondary" onClick={downloadReport}><Download className="h-4 w-4" />{t('settings.documents.einvoice.downloadReport', 'Download validation report')}</Button> : null}</div> : null}</div>{validation?.findings && Array.isArray(validation.findings) ? <div className="mt-3"><p className="text-xs text-gray-400">{t('settings.documents.einvoice.findingCount', { count: validation.findings.length, defaultValue: `${validation.findings.length} findings` })}</p><ul className="mt-2 space-y-1">{validation.findings.map((entry, index) => { const finding = entry as Record<string, unknown>; return <li key={index} className="rounded bg-bambu-dark-secondary px-2 py-1 text-xs"><code className="text-bambu-green">{String(finding.rule_id ?? '—')}</code> · {String(finding.message ?? finding.code ?? '—')}</li>; })}</ul></div> : null}</div> : null}
    </section>
  );
}
