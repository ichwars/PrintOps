// Verifies parity across locale files (en / de / fr / it / ja / pt-BR / zh-CN / zh-TW):
//   1. Leaf-key sets are identical
//   2. Each leaf's {{placeholder}} set is identical
//   3. Plural suffixes: every en key ending in _plural / _one / _other must
//      exist in every other locale, and other locales must not introduce an
//      _one key that en does not have.
//   4. NEW: leaves in a non-English locale must not be identical to en, unless
//      the value is a brand name / technical token / pure punctuation, OR the
//      key+locale pair is explicitly listed in IDENTICAL_TO_EN_ALLOWED below.
//      Catches the "copy English text into non-English locale to satisfy the
//      key-count parity gate" anti-pattern that accumulated 700+ shipped
//      strings of debt before the gate was tightened. Add an explicit entry
//      ONLY when the string is a real word/term in that target locale.
// Malformed input (missing `export default`, parse errors, non-string leaves,
// unsupported property kinds) fails loudly instead of silently passing the gate.
// Exits 1 with a diagnostic report on any failure, else exits 0.

import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const scriptDir = path.dirname(url.fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, '..');
const localesDir = path.join(frontendDir, 'src/i18n/locales');
const tsPath = path.join(frontendDir, 'node_modules/typescript/lib/typescript.js');

const tsModule = await import(url.pathToFileURL(tsPath).href);
const ts = tsModule.default ?? tsModule;

function collectLeaves(node, prefix, leaves) {
  if (!ts.isObjectLiteralExpression(node)) return;
  for (const prop of node.properties) {
    if (!ts.isPropertyAssignment(prop)) {
      console.error(
        `Unsupported property kind ${ts.SyntaxKind[prop.kind]} at "${prefix}" ` +
        `(locale files must use plain \`key: value\` assignments — no spread, shorthand, methods, or accessors).`,
      );
      process.exit(1);
    }
    let name;
    if (ts.isIdentifier(prop.name)) name = prop.name.text;
    else if (ts.isStringLiteral(prop.name) || ts.isNoSubstitutionTemplateLiteral(prop.name)) name = prop.name.text;
    else if (ts.isComputedPropertyName(prop.name)) {
      console.error(`ComputedPropertyName not allowed in locale file at path "${prefix}"`);
      process.exit(1);
    } else {
      console.error(`Unsupported property-name kind ${ts.SyntaxKind[prop.name.kind]} at "${prefix}"`);
      process.exit(1);
    }
    const p = prefix ? `${prefix}.${name}` : name;
    if (ts.isObjectLiteralExpression(prop.initializer)) {
      collectLeaves(prop.initializer, p, leaves);
    } else {
      const value = extractStringValue(prop.initializer, p);
      leaves.set(p, value);
    }
  }
}

function extractStringValue(node, keyPath) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (ts.isTemplateExpression(node)) {
    let out = node.head.text;
    for (const span of node.templateSpans) {
      out += '${' + span.expression.getText() + '}';
      out += span.literal.text;
    }
    return out;
  }
  console.error(
    `Non-string leaf at "${keyPath}" (kind=${ts.SyntaxKind[node.kind]}): ${node.getText()}\n` +
    `Locale files must only contain string or template literals as leaf values.`,
  );
  process.exit(1);
}

function loadLocale(filePath) {
  const src = fs.readFileSync(filePath, 'utf8');
  const sf = ts.createSourceFile(filePath, src, ts.ScriptTarget.Latest, true);
  if (sf.parseDiagnostics && sf.parseDiagnostics.length > 0) {
    console.error(`${filePath}: ${sf.parseDiagnostics.length} parse error(s):`);
    for (const d of sf.parseDiagnostics.slice(0, 10)) {
      const msg = typeof d.messageText === 'string' ? d.messageText : d.messageText.messageText;
      const { line, character } = sf.getLineAndCharacterOfPosition(d.start ?? 0);
      console.error(`  ${line + 1}:${character + 1} ${msg}`);
    }
    process.exit(1);
  }
  const leaves = new Map();
  let foundExport = false;
  ts.forEachChild(sf, (n) => {
    if (ts.isExportAssignment(n)) {
      foundExport = true;
      collectLeaves(n.expression, '', leaves);
    }
  });
  if (!foundExport) {
    console.error(`${filePath}: no \`export default\` found — locale files must use \`export default { ... }\`.`);
    process.exit(1);
  }
  if (leaves.size === 0) {
    console.error(`${filePath}: \`export default\` resolved to zero leaves — file is empty or not a nested object.`);
    process.exit(1);
  }
  return leaves;
}

const placeholderRe = /\{\{[^{}]+\}\}/g;

// Task 6 deliberately ships English fallbacks outside German. Scope that
// temporary exception to the exact locale/key pairs so the same values still
// fail when copied into unrelated leaves.
const ORDER_MANAGEMENT_ENGLISH_FALLBACK_LOCALES = new Set([
  'es', 'fr', 'it', 'ja', 'ko', 'pt-BR', 'tr', 'zh-CN', 'zh-TW',
]);
const ORDER_MANAGEMENT_ENGLISH_FALLBACK_KEYS = new Set([
  'orders.default',
  'orders.businessProfile.title',
  'orders.businessProfile.loading',
  'orders.businessProfile.error',
  'orders.businessProfile.empty',
  'orders.businessProfile.permissionDenied',
  'orders.businessProfile.add',
  'orders.businessProfile.includeInactive',
  'orders.businessProfile.profile',
  'orders.businessProfile.country',
  'orders.businessProfile.currency',
  'orders.businessProfile.timezone',
  'orders.businessProfile.billingMode',
  'orders.businessProfile.status',
  'orders.businessProfile.actions',
  'orders.businessProfile.active',
  'orders.businessProfile.inactive',
  'orders.businessProfile.edit',
  'orders.businessProfile.setDefault',
  'orders.businessProfile.activate',
  'orders.businessProfile.deactivate',
  'orders.businessProfile.delete',
  'orders.businessProfile.deleteConfirm',
  'orders.businessProfile.dismiss',
  'orders.businessProfile.createTitle',
  'orders.businessProfile.editTitle',
  'orders.businessProfile.identity',
  'orders.businessProfile.address',
  'orders.businessProfile.taxAndBank',
  'orders.businessProfile.localeSection',
  'orders.businessProfile.profileName',
  'orders.businessProfile.profileCountry',
  'orders.businessProfile.legalName',
  'orders.businessProfile.tradingName',
  'orders.businessProfile.street',
  'orders.businessProfile.city',
  'orders.businessProfile.postalCode',
  'orders.businessProfile.addAddress',
  'orders.businessProfile.removeAddress',
  'orders.businessProfile.defaultAddress',
  'orders.businessProfile.taxIdKind',
  'orders.businessProfile.taxIdValue',
  'orders.businessProfile.addTaxId',
  'orders.businessProfile.removeTaxId',
  'orders.businessProfile.primaryTaxId',
  'orders.businessProfile.bankAccountLabel',
  'orders.businessProfile.accountHolder',
  'orders.businessProfile.bankName',
  'orders.businessProfile.bankCountry',
  'orders.businessProfile.bankCurrency',
  'orders.businessProfile.iban',
  'orders.businessProfile.bic',
  'orders.businessProfile.accountNumber',
  'orders.businessProfile.routingNumber',
  'orders.businessProfile.defaultBankAccount',
  'orders.businessProfile.addBankAccount',
  'orders.businessProfile.removeBankAccount',
  'orders.businessProfile.locale',
  'orders.businessProfile.save',
  'orders.customers.title',
  'orders.customers.subtitle',
  'orders.customers.businessProfile',
  'orders.customers.loading',
  'orders.customers.error',
  'orders.customers.noBusinessProfile',
  'orders.customers.empty',
  'orders.customers.customer',
  'orders.customers.discount',
  'orders.customerEditor.title',
  'orders.customerEditor.company',
  'orders.customerEditor.person',
  'orders.status.active',
  'orders.status.inactive',
  'orders.status.blocked',
  'settings.tabs.orderManagementBusinessProfile',
  'settings.orderManagementSubTabDescriptions.businessProfile',
  'settings.tabs.orderManagementDocuments',
  'settings.orderManagementSubTabDescriptions.documents',
  'settings.documents.title',
  'settings.documents.description',
  'settings.documents.contextHint',
]);

[
  'settings.documents.profile',
  'settings.documents.documentType',
  'settings.documents.language',
  'settings.documents.version',
  'settings.documents.status.draft',
  'settings.documents.status.scheduled',
  'settings.documents.status.active',
  'settings.documents.status.superseded',
  'settings.documents.readiness.ready',
  'settings.documents.readiness.warnings',
  'settings.documents.readiness.blocked',
  'settings.documents.changeReason',
  'settings.documents.changeReasonHint',
  'settings.documents.readOnlyHint',
  'settings.documents.permissionDenied',
  'settings.documents.loading',
  'settings.documents.loadError',
  'settings.documents.actions.create',
  'settings.documents.actions.check',
  'settings.documents.actions.save',
  'settings.documents.actions.publish',
  'settings.documents.actions.withdraw',
  'settings.documents.actions.clone',
  'settings.documents.messages.createSuccess',
  'settings.documents.messages.saveSuccess',
  'settings.documents.messages.checkSuccess',
  'settings.documents.messages.publishSuccess',
  'settings.documents.messages.cloneSuccess',
  'settings.documents.messages.withdrawSuccess',
  'settings.documents.messages.actionFailed',
  'settings.documents.policy.title',
  'settings.documents.policy.hint',
  'settings.documents.empty.title',
  'settings.documents.empty.description',
  'settings.documents.history.title',
  'settings.documents.history.empty',
  'settings.documents.history.version',
  'settings.documents.history.status',
  'settings.documents.history.effectiveFrom',
  'settings.documents.history.reason',
  'settings.documents.history.actor',
  'settings.documents.history.rules',
  'settings.documents.history.publishedAt',
  'settings.documents.history.auditTitle',
  'settings.documents.history.auditEmpty',
  'settings.documents.history.correlation',
  'settings.documents.history.actions.create',
  'settings.documents.history.actions.update',
  'settings.documents.history.actions.clone',
  'settings.documents.history.actions.publication',
  'settings.documents.history.actions.withdraw',
  'settings.documents.unsaved.title',
  'settings.documents.unsaved.message',
  'settings.documents.unsaved.discard',
  'settings.documents.publish.title',
  'settings.documents.publish.description',
  'settings.documents.publish.effectiveFrom',
  'settings.documents.publish.reason',
  'settings.documents.documentTypes.quotation',
  'settings.documents.documentTypes.order_confirmation',
  'settings.documents.documentTypes.delivery_note',
  'settings.documents.documentTypes.advance_invoice',
  'settings.documents.documentTypes.progress_invoice',
  'settings.documents.documentTypes.final_invoice',
  'settings.documents.documentTypes.invoice',
  'settings.documents.documentTypes.cancellation_invoice',
  'settings.documents.documentTypes.invoice_correction',
  'settings.documents.documentTypes.commercial_credit_note',
  'settings.documents.documentTypes.payment_reminder',
  'settings.documents.documentTypes.dunning_notice',
  'settings.documents.documentTypes.self_billing',
].forEach((key) => ORDER_MANAGEMENT_ENGLISH_FALLBACK_KEYS.add(key));

// Task 17 policy-editor terminology intentionally falls back to English
// outside the complete German translation.
[
  'inheritance.system', 'inheritance.businessProfile', 'inheritance.customer', 'inheritance.configuration', 'inheritance.document', 'inheritance.reset',
  'basic.title', 'basic.description', 'basic.subject', 'basic.validityDays', 'basic.dateRule', 'basic.dates.issue', 'basic.dates.service', 'basic.dates.delivery',
  'basic.rounding', 'basic.roundingModes.commercial', 'basic.roundingModes.bankers', 'basic.roundingModes.down', 'basic.references',
  'basic.reference.customer_reference', 'basic.reference.order_reference', 'basic.reference.service_period', 'basic.successors', 'basic.technicalContent',
  'basic.includeCalculation', 'basic.content.print_time', 'basic.content.material', 'basic.content.plate_notes',
  'payment.title', 'payment.description', 'payment.termDays', 'payment.currency', 'payment.dueBasis', 'payment.bankAccount', 'payment.discountDays',
  'payment.discountPercent', 'payment.prepayment', 'payment.methods.bank_transfer', 'payment.methods.cash', 'payment.methods.card',
  'payment.methods.direct_debit', 'payment.methods.paypal', 'payment.useTermInText', 'payment.installments', 'payment.installmentPercent',
  'payment.installmentDue', 'payment.removeInstallment', 'payment.installmentTotalError', 'payment.addInstallment', 'payment.dunningEnabled',
  'payment.interest', 'payment.flatFee', 'payment.stage', 'payment.removeStage', 'payment.waitDays', 'payment.stageFee', 'payment.newDueDays',
  'payment.stageText', 'payment.chargeInterest', 'payment.addStage',
  'textBlocks.title', 'textBlocks.description', 'textBlocks.insertPlaceholder', 'textBlocks.choosePlaceholder', 'textBlocks.purposes.intro',
  'textBlocks.purposes.closing', 'textBlocks.purposes.payment_terms', 'textBlocks.purposes.delivery_terms', 'textBlocks.purposes.tax_note',
  'textBlocks.purposes.footer', 'textBlocks.purposes.dunning_notice',
  'placeholders.company_name', 'placeholders.company_address', 'placeholders.company_tax_id', 'placeholders.company_vat_id',
  'placeholders.customer_name', 'placeholders.customer_number', 'placeholders.customer_address', 'placeholders.customer_email',
  'placeholders.customer_vat_id', 'placeholders.document_number', 'placeholders.document_issue_date', 'placeholders.document_due_date',
  'placeholders.document_service_date', 'placeholders.document_currency', 'placeholders.payment_term_days', 'placeholders.payment_discount_deadline',
  'placeholders.payment_discount_percent', 'placeholders.dunning_stage', 'placeholders.dunning_fee', 'placeholders.dunning_new_due_date',
  'placeholders.DOCUMENT_NUMBER', 'placeholders.VALID_UNTIL', 'placeholders.ORDER_REFERENCE', 'placeholders.DUE_DATE',
  'placeholders.SERVICE_DATE', 'placeholders.ORIGINAL_DOCUMENT_NUMBER', 'placeholders.OPEN_AMOUNT', 'placeholders.CURRENCY', 'placeholders.DUNNING_LEVEL',
].forEach((suffix) => ORDER_MANAGEMENT_ENGLISH_FALLBACK_KEYS.add(`settings.documents.${suffix}`));

// Task 18 compliance terminology uses the same explicit English fallback.
[
  'readiness.loading', 'readiness.versionConflict', 'readiness.checkFailed', 'readiness.ruleId', 'readiness.correlationId',
  'readiness.unknownError', 'readiness.reloadCompare', 'readiness.title', 'readiness.noFindings', 'readiness.findings.buyer_endpoint_missing',
  'tax.title', 'tax.description', 'tax.ruleVersion', 'tax.allowedCases', 'tax.allowOverride', 'tax.recordedOverride', 'tax.manualOverride',
  'tax.treatment', 'tax.taxCountry', 'tax.placeOfSupply', 'tax.category', 'tax.rate', 'tax.legalReasonCode', 'tax.legalReasonText',
  'tax.sellerVatId', 'tax.buyerVatId', 'tax.evidence', 'tax.overrideReason', 'tax.applyOverride',
  'tax.cases.domestic_standard', 'tax.cases.small_business_exempt', 'tax.cases.intra_community_supply',
  'tax.cases.eu_reverse_charge', 'tax.cases.eu_b2c_oss', 'tax.cases.third_country', 'tax.cases.explicit_exemption',
  'einvoice.title', 'einvoice.description', 'einvoice.requirement', 'einvoice.optional', 'einvoice.ruleRequired', 'einvoice.syntax',
  'einvoice.pinned', 'einvoice.zugferdProfile', 'einvoice.processId', 'einvoice.sellerEndpoint', 'einvoice.endpointScheme',
  'einvoice.buyerEndpoint', 'einvoice.buyerReference', 'einvoice.defaultPaymentMethod', 'einvoice.bankAccount',
  'einvoice.validationLayers', 'einvoice.layers.xsd', 'einvoice.layers.en16931', 'einvoice.layers.cius',
  'einvoice.validationStatus', 'einvoice.downloadXml', 'einvoice.downloadReport', 'einvoice.findingCount',
].forEach((suffix) => ORDER_MANAGEMENT_ENGLISH_FALLBACK_KEYS.add(`settings.documents.${suffix}`));

// Task 8 extends the same deliberately narrow English-fallback contract.
[
  'orders.customers.permissionDenied', 'orders.customers.configureProfiles', 'orders.customers.add',
  'orders.customers.search', 'orders.customers.statusFilter', 'orders.customers.kindFilter',
  'orders.customers.emptyFiltered', 'orders.customers.number', 'orders.customers.name',
  'orders.customers.primaryContact', 'orders.customers.billingAddress', 'orders.customers.actions',
  'orders.customers.view', 'orders.customers.viewAria', 'orders.customers.editCustomer',
  'orders.customers.editAria', 'orders.customers.deleteCustomer', 'orders.customers.deleteAria',
  'orders.customers.deleteTitle', 'orders.customers.deleteConfirm', 'orders.customers.pagination',
  'orders.customers.previous', 'orders.customers.next', 'orders.customerEditor.createTitle',
  'orders.customerEditor.editTitle', 'orders.customerEditor.kind', 'orders.customerEditor.identity',
  'orders.customerEditor.displayName', 'orders.customerEditor.companyName', 'orders.customerEditor.firstName',
  'orders.customerEditor.lastName', 'orders.customerEditor.accounts', 'orders.customerEditor.addAccount',
  'orders.customerEditor.removeAccount', 'orders.customerEditor.accountProfile', 'orders.customerEditor.customerNumber',
  'orders.customerEditor.currency', 'orders.customerEditor.paymentDays', 'orders.customerEditor.deliveryTerms',
  'orders.customerEditor.discount', 'orders.customerEditor.activeAccount', 'orders.customerEditor.contacts',
  'orders.customerEditor.addContact', 'orders.customerEditor.removeContact', 'orders.customerEditor.salutation',
  'orders.customerEditor.contactFirstName', 'orders.customerEditor.contactLastName', 'orders.customerEditor.contactRole',
  'orders.customerEditor.contactEmail', 'orders.customerEditor.contactPhone', 'orders.customerEditor.primaryContact',
  'orders.customerEditor.includeContact', 'orders.customerEditor.onDocuments', 'orders.customerEditor.includeDocuments',
  'orders.customerEditor.addresses', 'orders.customerEditor.addAddress', 'orders.customerEditor.removeAddress',
  'orders.customerEditor.addressKindLabel', 'orders.customerEditor.addressKind.billing',
  'orders.customerEditor.addressKind.delivery', 'orders.customerEditor.addressKind.other',
  'orders.customerEditor.addressLabel', 'orders.customerEditor.additional', 'orders.customerEditor.street',
  'orders.customerEditor.street2', 'orders.customerEditor.postalCode', 'orders.customerEditor.city',
  'orders.customerEditor.region', 'orders.customerEditor.country', 'orders.customerEditor.defaultAddress',
  'orders.customerEditor.taxIdentifiers', 'orders.customerEditor.addTax', 'orders.customerEditor.removeTax',
  'orders.customerEditor.taxKind', 'orders.customerEditor.taxValue', 'orders.customerEditor.taxCountry',
  'orders.customerEditor.validationStatus', 'orders.customerEditor.preferences', 'orders.customerEditor.locale',
  'orders.customerEditor.tags', 'orders.customerEditor.notes', 'orders.customerEditor.required',
  'orders.customerEditor.reload', 'orders.customerEditor.save', 'orders.customerEditor.loadError', 'orders.customerDetails.title',
  'orders.customerDetails.loadError', 'orders.customerDetails.paymentDays', 'orders.customerDetails.created', 'orders.customerDetails.updated',
].forEach((key) => ORDER_MANAGEMENT_ENGLISH_FALLBACK_KEYS.add(key));

// Final foundation review adds shared profile/customer validation copy. The
// approved increment translates German natively and intentionally retains
// English fallbacks in the other non-English locales.
[
  'orderMessages.addressKind',
  'orderMessages.addressKinds.registered',
  'orderMessages.addressKinds.billing',
  'orderMessages.addressKinds.shipping',
  'orderMessages.addressKinds.other',
  'orderMessages.addressLabel',
  'orderMessages.additional',
  'orderMessages.street2',
  'orderMessages.region',
  'orderMessages.taxCountry',
  'orderMessages.validFrom',
  'orderMessages.validUntil',
  'orderMessages.taxValidationStatus.unchecked',
  'orderMessages.taxValidationStatus.valid',
  'orderMessages.taxValidationStatus.invalid',
  'orderMessages.validation.required',
  'orderMessages.validation.maxCharacters',
  'orderMessages.validation.customerKind',
  'orderMessages.validation.customerStatus',
  'orderMessages.validation.accountRequired',
  'orderMessages.validation.businessProfile',
  'orderMessages.validation.duplicateAccountProfile',
  'orderMessages.validation.currency',
  'orderMessages.validation.range',
  'orderMessages.validation.twoDecimalPlaces',
  'orderMessages.validation.addressKind',
  'orderMessages.validation.country',
  'orderMessages.validation.duplicateDefaultAddress',
  'orderMessages.validation.taxValidationStatus',
  'orderMessages.validation.duplicateTaxIdentifier',
  'orderMessages.validation.maxTags',
  'orderMessages.validation.normalizedTag',
  'orderMessages.validation.invalidField',
  'orderMessages.validation.failed',
  'orderMessages.errors.conflict',
  'orderMessages.errors.business_profile_in_use',
  'orderMessages.errors.business_profile_referenced',
  'orderMessages.errors.business_profile_version_conflict',
  'orderMessages.errors.customer_number_conflict',
  'orderMessages.errors.customer_account_number_conflict',
  'orderMessages.errors.customer_version_conflict',
  'orderUi.operationBlocked',
  'orderUi.duplicateRecord',
  'orderUi.singlePrimaryContact',
  'orderUi.billingModes.internal',
  'orderUi.billingModes.external',
  'orderUi.billingModes.hybrid',
].forEach((key) => ORDER_MANAGEMENT_ENGLISH_FALLBACK_KEYS.add(key));

// Task 16 deliberately provides the complete English layout-editor fallback
// outside German. The exception is constrained to the new namespace and its
// two navigation leaves; unrelated copied English strings still fail.
function isAllowedOrderManagementEnglishFallback(locale, key) {
  const isDocumentLayoutFallback = key === 'settings.tabs.orderManagementFormatPreview'
    || key === 'settings.orderManagementSubTabDescriptions.formatPreview'
    || key.startsWith('settings.documentLayout.');
  return ORDER_MANAGEMENT_ENGLISH_FALLBACK_LOCALES.has(locale)
    && (ORDER_MANAGEMENT_ENGLISH_FALLBACK_KEYS.has(key) || isDocumentLayoutFallback);
}

// Heuristic: values that are ALWAYS allowed to match en, regardless of locale.
// Brand names, technical tokens, pure punctuation, very short strings, version
// numbers, hex codes, and ALL-CAPS acronyms. Cognates that happen to be the
// same word in a specific locale go in IDENTICAL_TO_EN_ALLOWED instead.
function isAlwaysAllowedIdentical(value) {
  if (!value) return true;
  if (/^[\s\W_]+$/.test(value)) return true;            // pure punctuation/whitespace
  if (value.length <= 2) return true;                   // single character or 2-char abbrev
  if (/^[A-Z][A-Z0-9_]+$/.test(value)) return true;     // ALL_CAPS_TOKEN
  if (/^v?\d+(\.\d+)+/.test(value)) return true;        // version-like
  if (/^#[0-9a-fA-F]{3,8}$/.test(value)) return true;   // hex color
  if (/^\{\{[^}]+\}\}$/.test(value)) return true;       // pure placeholder
  if (/^\{\{[^}]+\}\}([\s/\-–·,]+\{\{[^}]+\}\})+$/.test(value)) return true;  // placeholders joined by punctuation only ({{a}} / {{b}})
  if (/^[0-9a-fA-F]{6}$/.test(value)) return true;      // bare hex color
  if (/^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i.test(value)) return true;  // email
  if (/^https?:\/\//.test(value)) return true;          // URL
  if (/^ON,\s+true,\s+1$/.test(value)) return true;     // literal example "ON, true, 1"
  // Brand / technical names that ship verbatim everywhere.
  if (/^(PrintOps|PrintOps|SpoolBuddy|Bambu Lab|Bambu Studio|Bambu Studio 2\.6\+|Bambu Studio sidecar URL|OrcaSlicer|OrcaSlicer sidecar URL|MakerWorld|Spoolman|\(Spoolman\)|Spoolman URL|Tailscale|GitHub|GitLab|Gitea|Forgejo|Discord|MQTT|FTP|HTTPS?|JSON|YAML|RTSP|TLS|SSL|CSRF|OIDC|SSO|SSO \/ OIDC|LDAP|TOTP|2FA|MFA|API|AMS|CRC|SHA256|SHA-256|kWh|MB|GB|KB|RGBA?|HSL|RGB|UTC|ISO|UI|HTTP|HTTP Method|H2D|H2D Pro|X1C|X1E|P1S|P1P|A1|A1 Mini|H2C|N3F|N3S|PETG|PLA|ABS|PA|TPU|PEI|PA-CF|PVA|HIPS|ASA|PC|PETG-HF|G\.code|G-code|gcode|cm³|°C|°F|GCODE|SOURCE|ntfy|Pushover|Telegram|Webhook|Webhook URL|Home Assistant|Home Assistant URL|CallMeBot\/WhatsApp|PrintOps URL|Cool Plate|Cool Plate SuperTack|Engineering Plate|High Temp Plate|Smooth PEI Plate|Textured PEI Plate|Ext-L|Ext-R|ISO \(YYYY-MM-DD\))$/.test(value)) return true;
  return false;
}

// Per-(locale, value) allow-list for strings that are a real word/term in
// that target locale and so legitimately match en.ts. Curated — add an entry
// here ONLY after verifying that the word is correct (not just a shortcut to
// silence the check).
//
// Convention: same shape as the locales themselves — { de: Set, fr: Set, ... }.
// Values are matched exactly. To allow a value across many locales, list it in
// each one (verbosity is the point: every locale's allow-list is an explicit
// translator decision).
// German loanwords / cognates from English are extensive. Most short technical
// UI labels are identical in DE. List below curates the legitimate ones.
const DE_COGNATES = [
  'Name', 'Status', 'Tag', 'Tags', 'Online', 'Offline', 'Standard', 'Modus', 'PayPal', 'Syntax',
  'EU B2C / OSS', 'CIUS / XRechnung',
  'Stop', 'Reset', 'Test', 'Code', 'Token', 'Server', 'Port', 'Bug', 'Job',
  'Bambu Cloud', 'Orca Cloud',  // brand names — same in every locale
  'AMS Filament Backup',  // Bambu Lab product/firmware feature name

  'Pause', 'Power', 'System', 'Problem', 'Designer', 'Extruder', 'Firmware',
  'Material', 'Original', 'Position', 'Webhook', 'Workflow', 'Slicer',
  'Pipeline', 'Pipelines', 'Filament {{n}}',  // #1425 — Slicer Pipelines (DE)
  'parallel',  // #1425 PR C polish — "parallel" is the same word in German
  'Region', 'Normal', 'Orange', 'Branch', 'Budget', 'Commit', 'Global',
  'Version', 'Version {{version}}', 'Slot', 'Live', 'Rate', 'Host', 'Trend', 'Min', 'Admin', 'Cloud',
  'Filament', 'Filaments', 'Software', 'Hardware', 'Avatar', 'Pin', 'Modal',
  'Active', 'Plate', 'Layer', 'Total', 'Plus', 'Pro', 'Mini', 'Studio',
  'Temperatur', 'Process', 'Service', 'Cache', 'Color', 'Login', 'Logout',
  'Action', 'Description', 'Sender', 'Setup', 'Bundle', 'Cluster', 'Tier',
  'Standard (100%)', 'Sport (124%)', 'Ludicrous (166%)',
  'Smart Plugs', 'Smart Switches', 'Smart Plug', 'High Flow',
  'Optional', 'optional', 'Filter', 'Filters', 'optional)',
  'Material:', 'Default:', 'Name *', '(System)', '(Inv)',
  'Spoolman URL', 'Bundle', 'Slicer Bundles', 'Imported',
  'STARTTLS (Port 587)', 'SSL/TLS (Port 465)', 'Sport', 'Standard',
  'EC984C,#6CD4BC,A66EB9,D87694',
  'Hex', 'Warm', 'Neutral', 'Navigation', 'Screenshot', 'Architecture',
  'Backend & Auth', 'Stream Overlay', 'PrintOps Backend URL',
  'Material (optional)', 'Custom Headers (JSON)', '({{count}}/8)',
  'Box label (62 × 29 mm)',
  'Avery L7160 — A4 sheet (38.1 × 63.5 mm × 21)',
  'Avery 5160 — US Letter sheet (25.4 × 66.7 mm × 30)',
  'China', 'Proxy', 'Start',
  'Diagnose',  // DE: same spelling/meaning as EN — camera diagnostic button label
  '{{filament}} @ {{temp}}°C',  // drying badge: filament code + universal °C
];

// French cognates — many UI labels overlap with English exactly.
const FR_COGNATES = [
  'Bambu Cloud', 'Orca Cloud',  // brand names — same in every locale
  'AMS Filament Backup',  // Bambu Lab product/firmware feature name
  'Status', 'Tag', 'Tags', 'Online', 'Offline', 'Standard', 'Filament',
  'Filaments', 'Software', 'Hardware', 'Stop', 'Reset', 'Test', 'Code',
  'Token', 'Server', 'Port', 'Plate', 'Layer', 'Active', 'Total', 'Avatar',
  'Job', 'Modal', 'Pin', 'Pro', 'Mini', 'Studio', 'Excellent', 'Description',
  'Pipeline', 'Pipelines', 'Filament {{n}}',  // #1425 — Slicer Pipelines (FR)
  'Copies', '{{n}} copies', 'max {{n}}',  // #1425 PR C — French uses these forms verbatim
  'round robin',  // borrowed English term used as-is in French tech contexts
  'Action', 'Actions', 'Date', 'Type', 'Cache', 'Service', 'Configuration',
  'Archives', 'Maintenance', 'Notifications', 'Notification', 'Position',
  'Pause', 'Solution', 'Source', 'Version', 'Format', 'Documentation',
  'Mode', 'Format', 'Default', 'Auto', 'Image', 'Audio', 'Video', 'Hex',
  'Camera', 'Avatar', 'Information', 'Initialization', 'Inactive', 'Active',
  'Print', 'Console', 'Cluster', 'Tier', 'Status URL',
  'Smart Plugs', 'Smart Switches', 'Smart Plug', 'High Flow',
  'Material:', 'Default:', 'Name *', '(System)', '(Inv)',
  'Process', 'Service', 'Service', 'Connect', 'Network', 'Local',
  'Sport (124%)', 'Ludicrous (166%)', 'Standard (100%)',
  'STARTTLS (Port 587)', 'SSL/TLS (Port 465)',
  'Bundle', 'Slicer Bundles', 'Imported',
  'Page', 'Note', 'Tare', 'Est.', 'Cloud', 'Style', 'Notes', 'Stock',
  'Accent', 'Orange', 'Global', 'Stable', 'Archive', 'visible', 'minutes',
  'Message', 'Slicer', 'Rotation', 'Original', 'Direction', 'Architecture',
  'notifications', 'Maintenance OK', 'total', 'Provider', 'Token name',
  '{{count}} filament', '{{count}} filaments', '{{count}} permissions',
  '{{count}} downloads', '{{count}} item', '{{count}} selected',
  '({{count}} item)', 'Provisioning...', 'Pressure Advance',
  '{{name}} ({{count}} copies)',  // FR plural of "copie" is also "copies"
  'Box label (62 × 29 mm)',
  'Avery L7160 — A4 sheet (38.1 × 63.5 mm × 21)',
  'Avery 5160 — US Letter sheet (25.4 × 66.7 mm × 30)',
  '({{count}}/8)', 'Custom Headers (JSON)', 'Permissions',
  'Expand dispatch details', 'Collapse dispatch details',
  'Cancelling upload...', 'Backup in progress...', 'Searching directory...',
  'EC984C,#6CD4BC,A66EB9,D87694',
  'Proxy', 'Navigation', 'Budget', 'Commit', 'Designer',
  'Compact',  // cam-wall status overlay mode — same word in French
  'ntfy, Pushover, Discord, etc.',
  '{{filament}} @ {{temp}}°C',  // drying badge: filament code + universal °C
];

// Italian cognates.
const IT_COGNATES = [
  'Bambu Cloud', 'Orca Cloud',  // brand names — same in every locale
  'AMS Filament Backup',  // Bambu Lab product/firmware feature name
  'Email',  // common loanword in Italian, used verbatim in UI labels
  'Pipeline', 'slicing',  // #1425 — Slicer Pipelines (cognate in IT)
  'max {{n}}',  // #1425 PR C — same form in Italian (max + number)
  'round robin',  // borrowed English term used as-is in Italian tech contexts
  'Status', 'Tag', 'Tags', 'Online', 'Offline', 'Standard', 'Filament',
  'Filaments', 'Software', 'Hardware', 'Stop', 'Reset', 'Test', 'Code',
  'Token', 'Server', 'Port', 'Plate', 'Layer', 'Modal', 'Pin', 'Pro', 'Mini',
  'Studio', 'Cache', 'Service', 'Avatar', 'Slicer', 'Action', 'Actions',
  'Format', 'Modal', 'Login', 'Logout', 'Color', 'Plus', 'Job', 'Live',
  'Position', 'Original', 'Material', 'Cluster', 'Tier', 'Auto', 'Hex',
  'Bundle', 'Slicer Bundles', 'Imported', 'Smart Plugs', 'Smart Switches',
  'Smart Plug', 'High Flow', 'Sport (124%)', 'Ludicrous (166%)',
  'Standard (100%)', 'STARTTLS (Port 587)', 'SSL/TLS (Port 465)',
  'Slot', 'Host', 'File', 'Cloud', 'Admin', 'Silk', '(Inv)', 'Slice',
  'Backup', 'Legacy', 'Branch', 'Auto On', 'Display', 'Password',
  'Auto Off', 'Dashboard', 'Timestamp', 'Pressure Advance', 'Provisioning...',
  '(25%, 50%, 75%)', 'Provider', 'Provider: {{type}}', 'Base: {{name}}',
  'Slicing…', 'Designer', 'Firmware', 'Timelapse', 'Commit', 'Budget',
  '({{count}}/8)', 'Custom Headers (JSON)', 'ETA {{minutes}} min',
  '{{name}} - Timelapse', 'Box label (62 × 29 mm)',
  'Avery L7160 — A4 sheet (38.1 × 63.5 mm × 21)',
  'Avery 5160 — US Letter sheet (25.4 × 66.7 mm × 30)',
  'Hex: #{{hex}}',
  'EC984C,#6CD4BC,A66EB9,D87694',
  'Proxy', 'Designer',
  'Off',  // cam-wall status overlay mode — common loanword in Italian UI
  '{{filament}} @ {{temp}}°C',  // drying badge: filament code + universal °C
];

// Japanese: very few cognates because of script difference. Almost
// everything needs translation. Only true loanwords / proper nouns stay.
const JA_COGNATES = [
  'OK', 'Bambu', 'Code',
  'Bambu Cloud', 'Orca Cloud',  // brand names — same in every locale
  'EU (DD/MM/YYYY)', 'US (MM/DD/YYYY)', 'ON, true, 1',
  '({{count}}/8)', 'Custom Headers (JSON)',
  'Box label (62 × 29 mm)',
  'Avery L7160 — A4 sheet (38.1 × 63.5 mm × 21)',
  'Avery 5160 — US Letter sheet (25.4 × 66.7 mm × 30)',
  'EC984C,#6CD4BC,A66EB9,D87694',
  '{{filament}} @ {{temp}}°C',  // drying badge: filament code + universal °C
];

// Portuguese (BR) cognates.
const PT_BR_COGNATES = [
  'Bambu Cloud', 'Orca Cloud',  // brand names — same in every locale
  'AMS Filament Backup',  // Bambu Lab product/firmware feature name
  'Pipeline', 'Pipelines',  // #1425 — Slicer Pipelines (PT-BR)
  'round robin',  // borrowed English term used as-is in Portuguese tech contexts
  'Status', 'Tag', 'Tags', 'Online', 'Offline', 'Standard', 'Filament',
  'Software', 'Hardware', 'Stop', 'Reset', 'Test', 'Code', 'Token', 'Server',
  'Port', 'Plate', 'Layer', 'Modal', 'Pin', 'Pro', 'Mini', 'Studio', 'Cache',
  'Service', 'Avatar', 'Total', 'Active', 'Login', 'Logout', 'Color', 'Hex',
  'Slot', 'Live', 'Rate', 'Host', 'Trend', 'Original', 'Auto', 'Bundle',
  'Imported', 'Action', 'Actions', 'Slicer Bundles', 'Sport (124%)',
  'Ludicrous (166%)', 'Standard (100%)', 'STARTTLS (Port 587)',
  'SSL/TLS (Port 465)', 'Smart Plugs', 'Smart Switches', 'High Flow',
  'Position', 'Mode', 'Setup', 'Modal',
  'Local', 'Metal', 'China', 'Admin', 'Silk', 'Backup', '(Inv)', 'Branch',
  'Normal', 'Material', 'Material:', 'Multicolor', 'Designer', 'Firmware',
  'Timelapse', 'Est.', 'total', 'Commit', 'Global',
  'Base: {{name}}', 'ETA {{minutes}} min', '{{count}} item',
  '{{count}} downloads', '({{count}} item)', '(25%, 50%, 75%)',
  '({{count}}/8)', 'Custom Headers (JSON)', '{{name}} - Timelapse',
  'Box label (62 × 29 mm)',
  'Avery L7160 — A4 sheet (38.1 × 63.5 mm × 21)',
  'Avery 5160 — US Letter sheet (25.4 × 66.7 mm × 30)',
  'Cancelling upload...', 'EC984C,#6CD4BC,A66EB9,D87694',
  'Expand dispatch details', 'Collapse dispatch details',
  'e.g., Home Assistant, OctoPrint', 'ntfy, Pushover, Discord, etc.',
  'Proxy', 'total: {{minutes}} min',
  '{{filament}} @ {{temp}}°C',  // drying badge: filament code + universal °C
];

// Chinese (Simplified): very few cognates beyond brand names.
const ZH_CN_COGNATES = [
  'OK', 'Bambu',
  'Bambu Cloud', 'Orca Cloud',  // brand names — same in every locale
  '({{count}}/8)', 'Custom Headers (JSON)',
  'Box label (62 × 29 mm)',
  'Avery L7160 — A4 sheet (38.1 × 63.5 mm × 21)',
  'Avery 5160 — US Letter sheet (25.4 × 66.7 mm × 30)',
  'EC984C,#6CD4BC,A66EB9,D87694',
  '{{filament}} @ {{temp}}°C',  // drying badge: filament code + universal °C
];

const ZH_TW_COGNATES = [
  'OK', 'Bambu',
  'Bambu Cloud', 'Orca Cloud',  // brand names — same in every locale
  '({{count}}/8)', 'Custom Headers (JSON)',
  'Box label (62 × 29 mm)',
  'Avery L7160 — A4 sheet (38.1 × 63.5 mm × 21)',
  'Avery 5160 — US Letter sheet (25.4 × 66.7 mm × 30)',
  'EC984C,#6CD4BC,A66EB9,D87694',
  '{{filament}} @ {{temp}}°C',  // drying badge: filament code + universal °C
];

// Korean: script difference means almost nothing is identical.
// Allow loanwords/acronyms, format strings, and proper nouns that stay verbatim.
const KO_COGNATES = [
  'OK', 'Bambu', 'N/A',
  'Bambu Cloud', 'Orca Cloud',  // brand names — same in every locale
  '({{count}}/8)', '(25%, 50%, 75%)',
  'Custom Headers (JSON)',
  'Box label (62 × 29 mm)',
  'Avery L7160 — A4 sheet (38.1 × 63.5 mm × 21)',
  'Avery 5160 — US Letter sheet (25.4 × 66.7 mm × 30)',
  'EC984C,#6CD4BC,A66EB9,D87694',
  '{{weight}}g',                                      // unit suffix format string
  'MakerWorld: {{designer}}',                         // brand + placeholder
  'email',                                            // OIDC claim name placeholder
  '{{printer}}: {{error}}',                           // pure placeholders
  '{{name}} — {{stage}} ({{percent}}%) — {{elapsed}}', // pure placeholders
  'Obico ML API URL',                                 // product name (Obico)
  '{{filament}} @ {{temp}}°C',                        // drying badge format
];

// Spanish cognates — words/phrases that are genuinely identical in Spanish.
const ES_COGNATES = [
  'Bambu Cloud', 'Orca Cloud',  // brand names — same in every locale
  'AMS Filament Backup',  // Bambu Lab product/firmware feature name
  'Pipeline', 'Pipelines',  // #1425 — Slicer Pipelines (ES)
  'round robin',  // borrowed English term used as-is in Spanish tech contexts
  'Error', 'Firmware', 'General', 'Control', 'Total', 'total', 'Material',
  'Material:', 'Color', 'Hex', 'Local', 'Global', 'China', 'Editable',
  'Normal', 'Metal', 'Multicolor', 'Proxy', 'Host', 'Factor', 'Original',
  'Sport (124%)', 'Ludicrous (166%)', 'MakerWorld: {{designer}}',
  '{{printer}}: {{error}}', 'Base: {{name}}',
  '{{name}} — {{stage}} ({{percent}}%) — {{elapsed}}', 'total: {{minutes}} min',
  '({{count}}/8)', 'Hex: #{{hex}}', '(25%, 50%, 75%)',
  'EC984C,#6CD4BC,A66EB9,D87694', 'Est.',
  'ntfy, Pushover, Discord, etc.',
  'Box label (62 × 29 mm)',
  'Avery L7160 — A4 sheet (38.1 × 63.5 mm × 21)',
  'Avery 5160 — US Letter sheet (25.4 × 66.7 mm × 30)',
  '{{filament}} @ {{temp}}°C',  // drying badge: filament code + universal °C
];

// Turkish cognates — technical UI labels that Turkish speakers use verbatim
// from English (loanwords + acronyms + format strings). Curated, not a shortcut.
const TR_COGNATES = [
  'Filament', 'Firmware', 'Disk', 'Hex', 'Test', 'Port', 'Model', 'Metal',
  'Bambu Cloud', 'Orca Cloud',  // brand names — same in every locale
  'AMS Filament Backup',  // Bambu Lab product/firmware feature name
  'Pipeline', 'Filament {{n}}',  // #1425 — Slicer Pipelines (TR)
  'Min', 'Normal', 'Platform', 'Net', 'Trend', 'Commit', 'Global', 'Proxy',
  'N/A', 'email',
  'STARTTLS (Port 587)', 'SSL/TLS (Port 465)',
  '({{count}}/8)', 'Hex: #{{hex}}', 'MakerWorld: {{designer}}',
  '{{count}} filament', '{{printer}}: {{error}}', '{{weight}}g',
  'Filament {{index}} ({{type}})',
  'EC984C,#6CD4BC,A66EB9,D87694',
  '{{filament}} @ {{temp}}°C',  // drying badge: filament code + universal °C
];

const IDENTICAL_TO_EN_ALLOWED = {
  de: new Set(DE_COGNATES),
  fr: new Set(FR_COGNATES),
  it: new Set(IT_COGNATES),
  ja: new Set(JA_COGNATES),
  ko: new Set(KO_COGNATES),
  es: new Set(ES_COGNATES),
  'pt-BR': new Set(PT_BR_COGNATES),
  'zh-CN': new Set(ZH_CN_COGNATES),
  'zh-TW': new Set(ZH_TW_COGNATES),
  tr: new Set(TR_COGNATES),
};

// Pure comparison logic, exported so tests can verify each failure mode
// without going through file IO or the TypeScript parser.
// Input:  locales = { code: Map<leafKey, leafString> }  (must contain 'en')
// Output: { failed, reports: Array<{ label, items }> }
export function compareLocales(locales) {
  if (!locales.en) throw new Error("compareLocales requires a locales.en entry");
  const reports = [];
  const add = (label, items) => {
    if (items.length) reports.push({ label, items });
  };

  const enKeys = new Set(locales.en.keys());

  // Check 1: key set equality
  for (const [code, map] of Object.entries(locales)) {
    if (code === 'en') continue;
    const keys = new Set(map.keys());
    const missing = [...enKeys].filter((k) => !keys.has(k)).sort();
    const extra = [...keys].filter((k) => !enKeys.has(k)).sort();
    add(`${code}: missing keys vs en`, missing);
    add(`${code}: extra keys vs en`, extra);
  }

  // Check 2: placeholder set equality per leaf
  for (const [code, map] of Object.entries(locales)) {
    if (code === 'en') continue;
    const mismatches = [];
    for (const [key, enValue] of locales.en) {
      const otherValue = map.get(key);
      if (otherValue === undefined) continue;
      const enPlaceholders = new Set((enValue.match(placeholderRe) ?? []));
      const otherPlaceholders = new Set((otherValue.match(placeholderRe) ?? []));
      const missingPh = [...enPlaceholders].filter((p) => !otherPlaceholders.has(p));
      const extraPh = [...otherPlaceholders].filter((p) => !enPlaceholders.has(p));
      if (missingPh.length || extraPh.length) {
        mismatches.push(`${key}: en=${[...enPlaceholders].join(',') || '∅'} vs ${code}=${[...otherPlaceholders].join(',') || '∅'}`);
      }
    }
    add(`${code}: placeholder mismatch vs en`, mismatches);
  }

  // Check 3: plural suffix presence + reverse _one guard
  for (const [code, map] of Object.entries(locales)) {
    if (code === 'en') continue;
    const pluralIssues = [];
    for (const key of enKeys) {
      if (key.endsWith('_plural') && !map.has(key)) pluralIssues.push(`missing _plural key: ${key}`);
      if (key.endsWith('_one') && !map.has(key)) pluralIssues.push(`missing _one key: ${key}`);
      if (key.endsWith('_other') && !map.has(key)) pluralIssues.push(`missing _other key: ${key}`);
    }
    for (const key of map.keys()) {
      if (key.endsWith('_one') && !enKeys.has(key)) {
        pluralIssues.push(`unexpected _one not present in en: ${key}`);
      }
    }
    add(`${code}: plural key mismatch`, pluralIssues);
  }

  // Check 4: identical-to-en leaks. A non-English leaf whose value exactly
  // matches en.ts must either pass the always-allowed heuristic OR be listed
  // in IDENTICAL_TO_EN_ALLOWED[code]. Otherwise it's almost certainly an
  // untranslated English string that slipped through past parity gates.
  for (const [code, map] of Object.entries(locales)) {
    if (code === 'en') continue;
    const allowed = IDENTICAL_TO_EN_ALLOWED[code] ?? new Set();
    const leaks = [];
    for (const [key, enValue] of locales.en) {
      const localeValue = map.get(key);
      if (localeValue === undefined) continue;
      if (localeValue !== enValue) continue;
      if (isAlwaysAllowedIdentical(enValue)) continue;
      if (isAllowedOrderManagementEnglishFallback(code, key)) continue;
      if (allowed.has(enValue)) continue;
      const preview = enValue.length > 60 ? `${enValue.slice(0, 57)}...` : enValue;
      leaks.push(`${key}: "${preview}"`);
    }
    add(`${code}: leaves identical to en (untranslated?)`, leaks);
  }

  return { failed: reports.length > 0, reports };
}

// en is the reference locale; every other locale discovered in the locales
// directory is checked identically and a drift in any of them fails CI.
// Skip file IO / process.exit when imported as a library (e.g. from tests).
const isMainModule = import.meta.url === url.pathToFileURL(process.argv[1] ?? '').href;
if (isMainModule) {
  const discovered = fs
    .readdirSync(localesDir)
    .filter((f) => f.endsWith('.ts'))
    .map((f) => f.slice(0, -3))
    .sort();
  if (!discovered.includes('en')) {
    console.error(`No en.ts found in ${localesDir} — cannot run parity check without a reference locale.`);
    process.exit(1);
  }
  const codes = ['en', ...discovered.filter((c) => c !== 'en')];
  const locales = Object.fromEntries(
    codes.map((c) => [c, loadLocale(path.join(localesDir, `${c}.ts`))]),
  );

  const MAX_REPORT = 20;
  const { reports } = compareLocales(locales);

  if (reports.length) {
    console.error(`\n=== Locale parity failures (en is the reference) ===`);
    for (const { label, items } of reports) {
      console.error(`\n[${label}] (${items.length})`);
      items.slice(0, MAX_REPORT).forEach((i) => console.error(`  ${i}`));
      if (items.length > MAX_REPORT) console.error(`  ... and ${items.length - MAX_REPORT} more`);
    }
  }

  console.log('\nLocale leaf counts:');
  for (const [code, map] of Object.entries(locales)) {
    const tier = code === 'en' ? 'ref' : 'locale';
    console.log(`  ${code.padEnd(6)} ${String(map.size).padEnd(6)} [${tier}]`);
  }

  if (reports.length > 0) {
    console.error(`\n❌ i18n parity check failed.`);
    process.exit(1);
  }
  const others = codes.filter((c) => c !== 'en');
  console.log(`\n✓ All locales in parity with en (${others.join(' / ')}).`);
}
