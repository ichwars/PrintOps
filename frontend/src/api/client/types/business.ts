export type BillingMode = 'internal' | 'external' | 'hybrid';

export type CustomerKind = 'company' | 'person';

export type CustomerStatus = 'active' | 'inactive' | 'blocked';

export type CustomerAddressKind = 'billing' | 'delivery' | 'other';

export type TaxValidationStatus = 'unchecked' | 'valid' | 'invalid';

export interface BusinessProfileAddress {
  kind: 'registered' | 'billing' | 'shipping' | 'other';
  label?: string | null;
  additional?: string | null;
  street: string;
  street_2?: string | null;
  postal_code: string;
  city: string;
  region?: string | null;
  country_code: string;
  is_default?: boolean;
}

export interface BusinessProfileTaxIdentifier {
  kind: string;
  value: string;
  country_code?: string | null;
  is_primary?: boolean;
  valid_from?: string | null;
  valid_until?: string | null;
}

export interface BusinessProfileBankAccount {
  label: string;
  account_holder: string;
  bank_name?: string | null;
  country_code?: string | null;
  currency: string;
  iban?: string | null;
  bic?: string | null;
  account_number?: string | null;
  routing_number?: string | null;
  is_default?: boolean;
}

export interface BusinessProfileAddressResponse extends Required<BusinessProfileAddress> {
  id: number;
}

export interface BusinessProfileTaxIdentifierResponse extends Required<BusinessProfileTaxIdentifier> {
  id: number;
}

export interface BusinessProfileBankAccountResponse extends Required<BusinessProfileBankAccount> {
  id: number;
}

export interface BusinessProfileCreate {
  name: string;
  legal_name: string;
  trading_name?: string | null;
  country_code: string;
  default_currency: string;
  timezone?: string;
  default_locale?: string;
  billing_mode?: BillingMode;
  tax_mode?: 'standard' | 'exempt' | 'none';
  default_tax_rate?: string;
  cash_accounting?: boolean;
  input_tax_deductible?: boolean;
  show_offer_qr?: boolean;
  paypal_me_url?: string | null;
  is_active?: boolean;
  is_default?: boolean;
  addresses: BusinessProfileAddress[];
  tax_identifiers?: BusinessProfileTaxIdentifier[];
  bank_accounts?: BusinessProfileBankAccount[];
}

export interface BusinessProfileUpdate extends BusinessProfileCreate {
  version: number;
}

export interface BusinessProfile extends Omit<Required<BusinessProfileCreate>, 'addresses' | 'tax_identifiers' | 'bank_accounts'> {
  id: number;
  version: number;
  created_at: string;
  updated_at: string;
  logo_media_type: string | null;
  logo_version: number | null;
  addresses: BusinessProfileAddressResponse[];
  tax_identifiers: BusinessProfileTaxIdentifierResponse[];
  bank_accounts: BusinessProfileBankAccountResponse[];
}

export interface BusinessProfileOption {
  id: number;
  name: string;
  country_code: string;
  default_currency: string;
  timezone: string;
  default_locale: string;
  billing_mode: BillingMode;
  is_default: boolean;
  is_active: boolean;
}

export interface DisplayCurrencyResponse {
  currency: string | null;
}

export type NumberSequenceKey = 'customer' | 'offer' | 'order' | 'invoice';

export type NumberSequenceResetPolicy = 'none' | 'yearly' | 'monthly';

export interface NumberSequenceValues {
  prefix: string;
  pattern: string;
  next_value: number;
  reset_policy: NumberSequenceResetPolicy;
}

export interface NumberSequenceCreate extends NumberSequenceValues {
  key: NumberSequenceKey;
}

export interface NumberSequenceUpdate extends NumberSequenceValues {
  version: number;
}

export interface NumberSequence extends NumberSequenceCreate {
  id: number;
  business_profile_id: number;
  current_period: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export type WarehouseNumberSequenceKey = 'material' | 'spool' | 'purchase_order' | 'goods_receipt';

export interface WarehouseNumberSequenceCreate extends NumberSequenceValues {
  key: WarehouseNumberSequenceKey;
}

export interface WarehouseNumberSequenceUpdate extends NumberSequenceValues {
  version: number;
}

export interface WarehouseNumberSequence extends WarehouseNumberSequenceCreate {
  id: number;
  current_period: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface CustomerAccount {
  business_profile_id: number;
  number?: string | null;
  preferred_currency: string;
  payment_term_days?: number;
  delivery_terms?: string | null;
  discount_percent?: string;
  is_active?: boolean;
}

export interface CustomerContact {
  salutation?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  role?: string | null;
  email?: string | null;
  phone?: string | null;
  is_primary?: boolean;
  include_on_documents?: boolean;
}

export interface CustomerAddress {
  kind: CustomerAddressKind;
  label?: string | null;
  additional?: string | null;
  street: string;
  street_2?: string | null;
  postal_code: string;
  city: string;
  region?: string | null;
  country_code: string;
  is_default?: boolean;
}

export interface CustomerTaxIdentifier {
  kind: string;
  value: string;
  country_code?: string | null;
  validation_status?: TaxValidationStatus;
}

export interface CustomerAccountResponse extends Required<CustomerAccount> {
  id: number;
}

export interface CustomerContactResponse extends Required<CustomerContact> {
  id: number;
}

export interface CustomerAddressResponse extends Required<CustomerAddress> {
  id: number;
}

export interface CustomerTaxIdentifierResponse extends Required<CustomerTaxIdentifier> {
  id: number;
}

export interface CustomerCreate {
  kind: CustomerKind;
  display_name: string;
  company_name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  status?: CustomerStatus;
  preferred_locale?: string;
  notes?: string | null;
  accounts: CustomerAccount[];
  contacts?: CustomerContact[];
  addresses?: CustomerAddress[];
  tax_identifiers?: CustomerTaxIdentifier[];
  tags?: string[];
}

export interface CustomerUpdate extends CustomerCreate {
  version: number;
}

export interface CustomerDetail extends Omit<Required<CustomerCreate>, 'accounts' | 'contacts' | 'addresses' | 'tax_identifiers'> {
  id: number;
  version: number;
  created_at: string;
  updated_at: string;
  accounts: CustomerAccountResponse[];
  contacts: CustomerContactResponse[];
  addresses: CustomerAddressResponse[];
  tax_identifiers: CustomerTaxIdentifierResponse[];
}

export interface CustomerListItem {
  id: number;
  business_profile_id: number;
  account_number: string;
  preferred_currency: string;
  payment_term_days: number;
  delivery_terms: string | null;
  discount_percent: string;
  account_is_active: boolean;
  display_name: string;
  company_name: string | null;
  first_name: string | null;
  last_name: string | null;
  kind: CustomerKind;
  status: CustomerStatus;
  preferred_locale: string;
  primary_contact_name: string | null;
  primary_contact_email: string | null;
  billing_city: string | null;
  billing_country_code: string | null;
  tags: string[];
  version: number;
}

export interface CustomerListParams {
  businessProfileId: number;
  search?: string;
  status?: CustomerStatus;
  kind?: CustomerKind;
  limit?: number;
  offset?: number;
}

export interface CustomerListResponse {
  items: CustomerListItem[];
  total: number;
  limit: number;
  offset: number;
}
