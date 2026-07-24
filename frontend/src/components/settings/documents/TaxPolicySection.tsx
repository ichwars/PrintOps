import { useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { PolicyFinding, TaxPolicyDraft } from '../../../api/documentManagement';
import { Button, Checkbox, NumberField, Select, Switch, TextArea, TextField } from '../../ui';

interface TaxPolicySectionProps {
  tax: TaxPolicyDraft;
  ruleVersion: string;
  canOverride: boolean;
  disabled: boolean;
  findings: PolicyFinding[];
  onChange: (path: string, value: unknown) => void;
}

const TAX_CASES = ['domestic_standard', 'small_business_exempt', 'intra_community_supply', 'eu_reverse_charge', 'eu_b2c_oss', 'third_country', 'explicit_exemption'];

export function TaxPolicySection({ tax, ruleVersion, canOverride, disabled, findings, onChange }: TaxPolicySectionProps) {
  const { t } = useTranslation();
  const recorded = tax.decision_rules.manual_override as Record<string, unknown> | undefined;
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [override, setOverride] = useState({
    treatment: String(recorded?.treatment ?? 'domestic_standard'),
    tax_country: String(recorded?.tax_country ?? 'DE'),
    place_of_supply: String(recorded?.place_of_supply ?? 'DE'),
    category_code: String(recorded?.category_code ?? 'S'),
    rate: String(recorded?.rate ?? '19.00'),
    legal_reason_code: String(recorded?.legal_reason_code ?? ''),
    legal_reason_text: String(recorded?.legal_reason_text ?? ''),
    seller_vat_id: String(recorded?.seller_vat_id ?? ''),
    buyer_vat_id: String(recorded?.buyer_vat_id ?? ''),
    evidence: String(recorded?.evidence ?? ''),
    reason: String(recorded?.reason ?? ''),
  });
  const updateOverride = (field: keyof typeof override, value: string) => setOverride((current) => ({ ...current, [field]: value }));

  return (
    <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4" aria-labelledby="document-tax-policy-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h3 id="document-tax-policy-heading" className="font-semibold text-white">{t('settings.documents.tax.title', 'Tax determination')}</h3><p className="mt-1 text-sm text-gray-400">{t('settings.documents.tax.description', 'Permitted tax outcomes and governed manual deviations.')}</p></div>
        <span className="inline-flex items-center gap-1 rounded-full border border-bambu-green/30 bg-bambu-green/10 px-2 py-1 text-xs text-bambu-green"><ShieldCheck className="h-3.5 w-3.5" />{t('settings.documents.tax.ruleVersion', { version: ruleVersion, defaultValue: `Tax rules ${ruleVersion}` })}</span>
      </div>
      <fieldset className="mt-4"><legend className="text-sm font-medium text-white">{t('settings.documents.tax.allowedCases', 'Permitted tax cases')}</legend><div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {TAX_CASES.map((taxCase) => <Checkbox key={taxCase} checked={tax.allowed_cases.includes(taxCase)} disabled={disabled} label={t(`settings.documents.tax.cases.${taxCase}`, taxCase)} onCheckedChange={(checked) => onChange('tax.allowed_cases', checked ? [...tax.allowed_cases, taxCase] : tax.allowed_cases.filter((item) => item !== taxCase))} />)}
      </div></fieldset>
      <div className="mt-4"><Switch checked={tax.allow_override} disabled={disabled} label={t('settings.documents.tax.allowOverride', 'Permit reasoned tax overrides on documents')} onCheckedChange={(checked) => onChange('tax.allow_override', checked)} /></div>

      {recorded ? <div className="mt-4 rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-100"><p className="font-medium">{t('settings.documents.tax.recordedOverride', 'Recorded manual override')}</p><dl className="mt-2 grid grid-cols-2 gap-2"><div><dt className="text-xs text-amber-200/70">{t('settings.documents.tax.treatment', 'Treatment')}</dt><dd>{String(recorded.treatment ?? '—')}</dd></div><div><dt className="text-xs text-amber-200/70">{t('settings.documents.tax.overrideReason', 'Reason')}</dt><dd>{String(recorded.reason ?? '—')}</dd></div></dl></div> : null}

      {canOverride ? <div className="mt-4 border-t border-bambu-dark-tertiary pt-4">
        <Checkbox checked={overrideOpen} disabled={disabled || !tax.allow_override} label={t('settings.documents.tax.manualOverride', 'Set a manual tax deviation')} onCheckedChange={setOverrideOpen} />
        {overrideOpen ? <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <Select label={t('settings.documents.tax.treatment', 'Treatment')} value={override.treatment} options={TAX_CASES.map((value) => ({ value, label: t(`settings.documents.tax.cases.${value}`, value) }))} onValueChange={(value) => updateOverride('treatment', value)} />
          <TextField label={t('settings.documents.tax.taxCountry', 'Tax country')} value={override.tax_country} maxLength={2} onValueChange={(value) => updateOverride('tax_country', value.toUpperCase())} />
          <TextField label={t('settings.documents.tax.placeOfSupply', 'Place of supply')} value={override.place_of_supply} maxLength={2} onValueChange={(value) => updateOverride('place_of_supply', value.toUpperCase())} />
          <Select label={t('settings.documents.tax.category', 'VAT category')} value={override.category_code} options={['S', 'E', 'AE', 'K', 'G', 'O', 'Z'].map((value) => ({ value, label: value }))} onValueChange={(value) => updateOverride('category_code', value)} />
          <NumberField label={t('settings.documents.tax.rate', 'Tax rate')} value={override.rate} min={0} max={100} step="0.01" suffix="%" onValueChange={(value) => updateOverride('rate', value)} />
          <TextField label={t('settings.documents.tax.legalReasonCode', 'Legal reason code')} value={override.legal_reason_code} onValueChange={(value) => updateOverride('legal_reason_code', value)} />
          <div className="md:col-span-2"><TextArea label={t('settings.documents.tax.legalReasonText', 'Legal reason')} value={override.legal_reason_text} onValueChange={(value) => updateOverride('legal_reason_text', value)} /></div>
          <TextField label={t('settings.documents.tax.sellerVatId', 'Seller VAT ID')} value={override.seller_vat_id} onValueChange={(value) => updateOverride('seller_vat_id', value)} />
          <TextField label={t('settings.documents.tax.buyerVatId', 'Buyer VAT ID')} value={override.buyer_vat_id} onValueChange={(value) => updateOverride('buyer_vat_id', value)} />
          <TextField label={t('settings.documents.tax.evidence', 'Validation evidence')} value={override.evidence} onValueChange={(value) => updateOverride('evidence', value)} />
          <TextField label={t('settings.documents.tax.overrideReason', 'Reason')} value={override.reason} onValueChange={(value) => updateOverride('reason', value)} />
          <div className="md:col-span-2 flex justify-end"><Button disabled={override.reason.trim().length < 10} onClick={() => onChange('tax.decision_rules.manual_override', { ...override, rate: override.rate, rule_version: ruleVersion })}>{t('settings.documents.tax.applyOverride', 'Apply deviation')}</Button></div>
        </div> : null}
      </div> : null}
      {findings.filter((item) => item.field_path.startsWith('tax.')).map((item) => <p key={`${item.field_path}-${item.code}`} className="mt-2 text-sm text-red-300">{t(item.message_key, item.message_key)}</p>)}
    </section>
  );
}
