# Document Management and E-Invoice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete versioned document-settings domain, commercial-document lifecycle, tax decision support, and locally validated XRechnung/ZUGFeRD XML defined in the approved specification.

**Architecture:** Add relational document configuration and immutable commercial-document aggregates to the existing FastAPI/SQLAlchemy application. Isolate inheritance, readiness, tax, snapshot, numbering, XML rendering, and validation behind focused services; expose them through typed APIs and a dedicated React settings feature. Keep visual PDF layout, PDF/A-3 embedding, preview, transport, and automatic dunning execution outside this plan.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic 2, SQLAlchemy 2 async, SQLite/PostgreSQL, `Decimal`, lxml 5+, defusedxml, React 19, TypeScript 5.9, TanStack Query 5, Vitest, Testing Library, pytest, Ruff.

## Global Constraints

- Use SQL `NUMERIC` and Python `Decimal` for every monetary or percentage calculation; never use binary floats.
- Support SQLite and PostgreSQL with the existing idempotent startup-migration mechanism in `backend/app/core/database.py`.
- Keep drafts mutable; published configuration versions, issued snapshots, rule-version evidence, and artifacts are immutable.
- Resolve effective values in this order: system/legal rule, business profile, customer, document configuration, allowed document override.
- Require an audit reason for tax overrides and legally binding correction, cancellation, publication, issuance, and export actions.
- Use XRechnung 3.0.2 validator configuration dated 2026-01-31, EN-16931 validation artifacts 1.3.16, and ZUGFeRD 2.5 dated 2026-06-10.
- Validate E-invoices locally from vendored assets; runtime behavior must not require network access.
- Support XRechnung UBL 2.1 and UN/CEFACT CII plus ZUGFeRD 2.5 profiles `EN 16931` and `XRECHNUNG`.
- Maintain translation-key parity across all eleven files in `frontend/src/i18n/locales/`.
- Do not add PDF layout, preview, PDF/A-3 generation, ZUGFeRD embedding, email/Peppol/portal delivery, or automatic reminder/dunning execution.
- Every task uses TDD, leaves the relevant focused suite green, and commits only its own files.

## File and Module Map

### Backend domain

- `backend/app/models/document_configuration.py`: configuration versions, policy rows, text blocks, dunning stages, customer document preferences.
- `backend/app/models/commercial_document.py`: document headers, lines, relations, immutable snapshots, artifacts, number reservations.
- `backend/app/models/document_audit.py`: append-only audit events.
- `backend/app/schemas/document_configuration.py`: configuration commands, responses, inheritance, and readiness findings.
- `backend/app/schemas/commercial_document.py`: draft, line, relation, transition, issuance, and artifact contracts.
- `backend/app/schemas/einvoice.py`: profile, validation, XML artifact, and download metadata contracts.
- `backend/app/services/document_catalog.py`: enums, supported document-type capabilities, placeholders, and E-invoice applicability.
- `backend/app/services/document_configuration.py`: draft/version/publication lifecycle and effective-value resolution.
- `backend/app/services/document_policy_validation.py`: text, payment, installment, and dunning validation.
- `backend/app/services/document_readiness.py`: configuration and concrete-document preflight.
- `backend/app/services/tax_decision.py`: deterministic tax-case selection and audited override validation.
- `backend/app/services/document_snapshot.py`: canonical snapshot serialization and SHA-256.
- `backend/app/services/commercial_documents.py`: draft lifecycle, type rules, relations, correction/cancellation, and issuance orchestration.
- `backend/app/services/document_numbering.py`: reservation record and non-reuse evidence around the existing number service.
- `backend/app/services/document_audit.py`: append-only audit writer.
- `backend/app/services/einvoice/canonical.py`: typed EN-16931 semantic invoice.
- `backend/app/services/einvoice/xrechnung.py`: UBL 2.1 and CII XRechnung renderers.
- `backend/app/services/einvoice/zugferd.py`: ZUGFeRD 2.5 CII renderer.
- `backend/app/services/einvoice/validator.py`: safe local XSD/XSLT/Schematron validation.
- `backend/app/services/einvoice/artifacts.py`: protected storage and checksums.
- `backend/app/api/routes/document_configurations.py`: settings/version/readiness endpoints.
- `backend/app/api/routes/commercial_documents.py`: draft/lifecycle/issuance endpoints.
- `backend/app/api/routes/einvoices.py`: generation, validation report, and downloads.
- `backend/app/resources/einvoice/`: pinned official validation assets plus a machine-readable manifest.

### Frontend feature

- `frontend/src/api/documentManagement.ts`: all feature-specific request/response types and API calls.
- `frontend/src/components/settings/documents/DocumentSettings.tsx`: query ownership, context selection, dirty-state protection, actions.
- `frontend/src/components/settings/documents/DocumentContextHeader.tsx`: profile/type/language/version/status selectors.
- `frontend/src/components/settings/documents/DocumentActionBar.tsx`: save, check, publish, clone, and withdraw commands.
- `frontend/src/components/settings/documents/documentSettingsState.ts`: stable draft comparison and initial-context helpers.
- `frontend/src/components/settings/documents/InheritanceField.tsx`: source badge, override, reset, and locked-state behavior.
- `frontend/src/components/settings/documents/BasicPolicySection.tsx`: dates, currency, rounding, references, content policy.
- `frontend/src/components/settings/documents/PaymentPolicySection.tsx`: terms, discount, installments, bank assignment, dunning stages.
- `frontend/src/components/settings/documents/TextBlocksSection.tsx`: purpose-specific blocks and placeholder assistant.
- `frontend/src/components/settings/documents/TaxPolicySection.tsx`: automatic case preview and reasoned override controls.
- `frontend/src/components/settings/documents/EInvoicePolicySection.tsx`: standards, syntax, identifiers, validation report, download.
- `frontend/src/components/settings/documents/ReadinessPanel.tsx`: blockers/warnings and field navigation.
- `frontend/src/components/settings/documents/VersionHistoryPanel.tsx`: immutable history and audit events.

---

### Task 1: Domain Catalog and Permission Contract

**Files:**
- Create: `backend/app/services/document_catalog.py`
- Modify: `backend/app/core/permissions.py:77-96,264-287,449-470,535-550`
- Modify: `backend/app/core/auth.py:267-288`
- Modify: `frontend/src/api/client.ts:3470-3486`
- Modify: `backend/tests/unit/test_order_management_permissions.py`
- Create: `backend/tests/unit/services/test_document_catalog.py`

**Interfaces:**
- Produces: `DocumentType`, `DocumentCapability`, `EInvoiceRequirement`, `DOCUMENT_CAPABILITIES`, `TEXT_BLOCK_PURPOSES`, `PLACEHOLDERS`.
- Produces permissions `document_templates:read`, `document_templates:manage`, `commercial_documents:tax_override`, and reuses the existing commercial-document issue/correct/export permissions.
- Consumes: existing `Permission` enum and default-group seed behavior.

- [ ] **Step 1: Write failing catalog and permission tests**

```python
from backend.app.core.permissions import DEFAULT_GROUPS, Permission
from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES, DocumentType


def test_all_approved_document_types_have_capabilities():
    assert set(DOCUMENT_CAPABILITIES) == set(DocumentType)
    assert DOCUMENT_CAPABILITIES[DocumentType.DELIVERY_NOTE].einvoice is False
    assert DOCUMENT_CAPABILITIES[DocumentType.INVOICE].einvoice is True
    assert DOCUMENT_CAPABILITIES[DocumentType.SELF_BILLING].issuer_role == "buyer"


def test_document_template_and_tax_override_permissions_are_admin_only():
    admin = set(DEFAULT_GROUPS["Administrators"]["permissions"])
    operator = set(DEFAULT_GROUPS["Operators"]["permissions"])
    assert Permission.DOCUMENT_TEMPLATES_MANAGE.value in admin
    assert Permission.COMMERCIAL_DOCUMENTS_TAX_OVERRIDE.value in admin
    assert Permission.DOCUMENT_TEMPLATES_MANAGE.value not in operator
    assert Permission.COMMERCIAL_DOCUMENTS_TAX_OVERRIDE.value not in operator
```

- [ ] **Step 2: Run the focused tests and confirm the missing symbols**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_catalog.py backend/tests/unit/test_order_management_permissions.py -q`

Expected: FAIL during collection because `document_catalog` and the two permissions do not exist.

- [ ] **Step 3: Add the exact catalog and permission constants**

```python
class DocumentType(StrEnum):
    QUOTATION = "quotation"
    ORDER_CONFIRMATION = "order_confirmation"
    DELIVERY_NOTE = "delivery_note"
    ADVANCE_INVOICE = "advance_invoice"
    PROGRESS_INVOICE = "progress_invoice"
    FINAL_INVOICE = "final_invoice"
    INVOICE = "invoice"
    CANCELLATION_INVOICE = "cancellation_invoice"
    INVOICE_CORRECTION = "invoice_correction"
    COMMERCIAL_CREDIT_NOTE = "commercial_credit_note"
    PAYMENT_REMINDER = "payment_reminder"
    DUNNING_NOTICE = "dunning_notice"
    SELF_BILLING = "self_billing"


@dataclass(frozen=True, slots=True)
class DocumentCapability:
    einvoice: bool
    issuer_role: Literal["seller", "buyer"]
    has_payment_terms: bool
    has_tax: bool
    allowed_successors: frozenset[DocumentType]
```

Add `DOCUMENT_TEMPLATES_READ`, `DOCUMENT_TEMPLATES_MANAGE`, and `COMMERCIAL_DOCUMENTS_TAX_OVERRIDE` to the backend enum, permission category, admin defaults, authentication allow-list, and frontend union. Keep template management and tax override out of Operator and Viewer defaults.

- [ ] **Step 4: Run the tests and static checks**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_catalog.py backend/tests/unit/test_order_management_permissions.py -q`

Expected: PASS.

Run: `.venv\Scripts\python.exe -m ruff check backend/app/services/document_catalog.py backend/app/core/permissions.py backend/app/core/auth.py`

Expected: `All checks passed!`

- [ ] **Step 5: Commit the contract**

```bash
git add backend/app/services/document_catalog.py backend/app/core/permissions.py backend/app/core/auth.py backend/tests/unit/services/test_document_catalog.py backend/tests/unit/test_order_management_permissions.py frontend/src/api/client.ts
git commit -m "feat(documents): define catalog and permissions"
```

### Task 2: Relational Configuration Persistence and Migration

**Files:**
- Create: `backend/app/models/document_configuration.py`
- Create: `backend/app/services/document_defaults.py`
- Create: `backend/app/resources/document_defaults/de.json`
- Create: `backend/app/resources/document_defaults/en.json`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py:165-240,3352-3407,3650-3720`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/integration/test_document_configuration_schema.py`
- Create: `backend/tests/integration/test_document_configuration_migration.py`

**Interfaces:**
- Produces SQLAlchemy models `DocumentConfiguration`, `DocumentBasicPolicy`, `PaymentPolicy`, `DunningPolicy`, `DunningStage`, `DocumentTextBlock`, `DocumentContentPolicy`, `TaxPolicy`, `EInvoicePolicy`, `CustomerDocumentPreference`, `ConfigurationPublication`.
- Produces uniqueness `(business_profile_id, document_type, language, version)` and non-overlapping active-version service invariant.
- Consumes `BusinessProfile`, `Customer`, and `BusinessProfileBankAccount` foreign keys.

- [ ] **Step 1: Write failing metadata and migration tests**

```python
async def test_configuration_schema_has_versioned_children(db_session):
    config = DocumentConfiguration(
        business_profile_id=1,
        document_type="invoice",
        language="de",
        version=1,
        status="draft",
    )
    config.payment_policy = PaymentPolicy(payment_term_days=14, currency="EUR")
    config.text_blocks = [DocumentTextBlock(purpose="closing", body="Vielen Dank.")]
    db_session.add(config)
    await db_session.flush()
    assert config.payment_policy.configuration_id == config.id
    assert config.text_blocks[0].configuration_id == config.id


async def test_legacy_document_settings_migrate_to_unpublished_german_draft(initialized_database):
    row = await initialized_database.scalar(
        select(DocumentConfiguration).where(
            DocumentConfiguration.document_type == "invoice",
            DocumentConfiguration.language == "de",
        )
    )
    assert row is not None
    assert row.status == "draft"
    assert row.payment_policy.payment_term_days == 14


async def test_every_profile_receives_complete_german_and_english_drafts(initialized_database):
    rows = (await initialized_database.scalars(select(DocumentConfiguration))).all()
    keys = {(row.document_type, row.language) for row in rows}
    assert keys == {(document_type.value, language) for document_type in DocumentType for language in ("de", "en")}
```

- [ ] **Step 2: Run tests and confirm missing tables**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/integration/test_document_configuration_schema.py backend/tests/integration/test_document_configuration_migration.py -q`

Expected: FAIL because the models and tables are absent.

- [ ] **Step 3: Add focused SQLAlchemy models**

```python
class DocumentConfiguration(Base):
    __tablename__ = "document_configurations"
    __table_args__ = (
        UniqueConstraint(
            "business_profile_id", "document_type", "language", "version",
            name="uq_document_configuration_version",
        ),
        CheckConstraint("status IN ('draft','scheduled','active','superseded')"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(ForeignKey("business_profiles.id", ondelete="RESTRICT"))
    document_type: Mapped[str] = mapped_column(String(32), index=True)
    language: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    effective_from: Mapped[date | None] = mapped_column(Date)
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    change_reason: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Use one-to-one child rows for basic, payment, dunning, content, tax, and E-invoice policies; use one-to-many rows for dunning stages and text blocks. Store structured conditions as JSON only where they are versioned policy expressions, not as a replacement for the relational header fields.

- [ ] **Step 4: Register tables and add idempotent startup migration**

Add `document_configuration` to `init_db()` imports before `Base.metadata.create_all`. Add `_migrate_document_configurations(conn)` after table creation. Read these exact optional legacy setting keys: `orders.offer_validity_days`, `orders.payment_term_days`, `orders.default_order_status`, `orders.offer_default_text`, `orders.invoice_default_text`, `orders.pdf_footer_text`, `orders.include_calculation_data`, and `orders.use_payment_term_in_invoice_text`. Seed one German and one English draft for every catalog type and business profile when no matching configuration exists. Apply a present legacy value to the corresponding German quotation/invoice draft; use the Appendix A defaults when a key is absent. Preserve `orders.default_order_status` as an order-workflow setting instead of copying it into a document policy.

`document_defaults.py` loads and validates the two committed JSON resources. Startup fails with a precise administrative error if a catalog type, required text purpose, or placeholder referenced by the defaults is invalid.

- [ ] **Step 5: Run schema and migration tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/integration/test_document_configuration_schema.py backend/tests/integration/test_document_configuration_migration.py -q`

Expected: PASS on the test SQLite database.

- [ ] **Step 6: Commit persistence**

```bash
git add backend/app/models/document_configuration.py backend/app/services/document_defaults.py backend/app/resources/document_defaults backend/app/models/__init__.py backend/app/core/database.py backend/tests/conftest.py backend/tests/integration/test_document_configuration_schema.py backend/tests/integration/test_document_configuration_migration.py
git commit -m "feat(documents): persist versioned configuration"
```

### Task 3: Configuration Schemas, Lifecycle, and Effective Values

**Files:**
- Create: `backend/app/schemas/document_configuration.py`
- Create: `backend/app/services/document_configuration.py`
- Create: `backend/tests/unit/services/test_document_configuration.py`
- Create: `backend/tests/integration/test_document_configuration_service.py`

**Interfaces:**
- Produces `create_draft(session, command, actor_id) -> DocumentConfiguration`.
- Produces `update_draft(session, configuration_id, expected_version, patch, actor_id) -> DocumentConfiguration`.
- Produces `publish(session, configuration_id, expected_version, effective_from, reason, actor_id, rule_versions) -> DocumentConfiguration`.
- Produces `clone_version(session, configuration_id, actor_id) -> DocumentConfiguration`.
- Produces `resolve_effective(session, profile_id, customer_id, document_type, language, document_overrides) -> EffectiveDocumentPolicy`.

- [ ] **Step 1: Write failing lifecycle and inheritance tests**

```python
async def test_publishing_supersedes_previous_active_version(session, active_invoice_config):
    draft = await clone_version(session, active_invoice_config.id, actor_id=7)
    published = await publish(
        session,
        draft.id,
        expected_version=draft.lock_version,
        effective_from=date.today(),
        reason="Updated payment terms",
        actor_id=7,
        rule_versions={"tax": "2026.1", "en16931": "1.3.16"},
    )
    assert published.status == "active"
    assert active_invoice_config.status == "superseded"


async def test_effective_values_report_customer_source(session, profile_config, customer_preference):
    result = await resolve_effective(
        session, profile_config.business_profile_id, customer_preference.customer_id,
        "invoice", "de", {},
    )
    assert result.payment.payment_term_days.value == 30
    assert result.payment.payment_term_days.source == "customer"
```

- [ ] **Step 2: Run and verify service imports fail**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_configuration.py backend/tests/integration/test_document_configuration_service.py -q`

Expected: FAIL because the schemas and services are missing.

- [ ] **Step 3: Define strict Pydantic contracts**

```python
class SourcedValue(BaseModel, Generic[T]):
    value: T
    source: Literal["system", "business_profile", "customer", "configuration", "document"]
    overridable: bool


class PublishConfigurationCommand(BaseModel):
    expected_version: int = Field(gt=0)
    effective_from: date
    reason: str = Field(min_length=3, max_length=1000)


class EffectiveDocumentPolicy(BaseModel):
    configuration_id: int
    configuration_version: int
    basic: EffectiveBasicPolicy
    payment: EffectivePaymentPolicy
    content: EffectiveContentPolicy
    tax: EffectiveTaxPolicy
    einvoice: EffectiveEInvoicePolicy
    text_blocks: list[EffectiveTextBlock]
```

- [ ] **Step 4: Implement compare-and-swap lifecycle and field-level source resolution**

Use SQL `UPDATE ... WHERE id=:id AND lock_version=:expected RETURNING` for draft mutations. Lock all versions for the same profile/type/language when publishing, reject overlapping scheduled/active dates, and replace each old active row with `superseded` only when the new effective date arrives. Copy every child policy and text row in `clone_version`; never share mutable child rows.

- [ ] **Step 5: Run tests and Ruff**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_configuration.py backend/tests/integration/test_document_configuration_service.py -q`

Expected: PASS.

Run: `.venv\Scripts\python.exe -m ruff check backend/app/schemas/document_configuration.py backend/app/services/document_configuration.py`

Expected: `All checks passed!`

- [ ] **Step 6: Commit lifecycle**

```bash
git add backend/app/schemas/document_configuration.py backend/app/services/document_configuration.py backend/tests/unit/services/test_document_configuration.py backend/tests/integration/test_document_configuration_service.py
git commit -m "feat(documents): add configuration lifecycle"
```

### Task 4: Text, Payment, Installment, and Dunning Validation

**Files:**
- Create: `backend/app/services/document_policy_validation.py`
- Create: `backend/tests/unit/services/test_document_policy_validation.py`
- Modify: `backend/app/services/document_configuration.py`

**Interfaces:**
- Produces `validate_policy(policy: DocumentConfigurationDraft) -> tuple[PolicyFinding, ...]`.
- Produces `render_text_blocks(blocks, values, document_type) -> tuple[RenderedTextBlock, ...]`.
- Consumes `PLACEHOLDERS`, `TEXT_BLOCK_PURPOSES`, and the configuration schemas.

- [ ] **Step 1: Write failing rule tests**

```python
def test_policy_rejects_discount_after_due_date():
    findings = validate_policy(policy(payment_term_days=14, discount_days=30, discount_percent="2.00"))
    assert [(item.code, item.field_path) for item in findings] == [
        ("discount_after_due_date", "payment.discount_days")
    ]


def test_installment_percentages_must_total_one_hundred():
    findings = validate_policy(policy(installments=[("40.00", 7), ("40.00", 30)]))
    assert any(item.code == "installments_total_invalid" for item in findings)


def test_unknown_or_unavailable_placeholder_is_blocking():
    findings = validate_policy(policy(invoice_closing="Pay {QUOTATION_VALID_UNTIL} to {UNKNOWN}"))
    assert {item.code for item in findings} == {"placeholder_not_available", "placeholder_unknown"}
```

- [ ] **Step 2: Run and confirm missing validator**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_policy_validation.py -q`

Expected: FAIL because `document_policy_validation` is absent.

- [ ] **Step 3: Implement deterministic findings**

```python
@dataclass(frozen=True, slots=True)
class PolicyFinding:
    severity: Literal["warning", "blocker"]
    code: str
    field_path: str
    message_key: str
    rule_id: str | None = None


def validate_policy(policy: DocumentConfigurationDraft) -> tuple[PolicyFinding, ...]:
    findings: list[PolicyFinding] = []
    if policy.payment.discount_days > policy.payment.payment_term_days:
        findings.append(PolicyFinding("blocker", "discount_after_due_date", "payment.discount_days", "documents.errors.discountAfterDue"))
    if sum((item.percent for item in policy.payment.installments), Decimal("0")) != Decimal("100"):
        findings.append(PolicyFinding("blocker", "installments_total_invalid", "payment.installments", "documents.errors.installmentsTotal"))
    findings.extend(_validate_placeholders(policy.document_type, policy.text_blocks))
    return tuple(sorted(findings, key=lambda item: (item.field_path, item.code)))
```

Also validate non-negative fees and interest, unique ordered dunning stages, non-empty required text purposes, valid ISO currency/language/unit codes, and exactly one default bank assignment where payment data is required.

- [ ] **Step 4: Integrate validation into save and publication**

Draft save returns findings but permits blockers. Publication calls the same function and raises `ConfigurationNotReady` when any blocker exists. Preserve field paths and rule IDs in the error detail.

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_policy_validation.py backend/tests/integration/test_document_configuration_service.py -q`

Expected: PASS.

- [ ] **Step 6: Commit policy validation**

```bash
git add backend/app/services/document_policy_validation.py backend/app/services/document_configuration.py backend/tests/unit/services/test_document_policy_validation.py
git commit -m "feat(documents): validate payment and text policies"
```

### Task 5: Configuration Readiness and Settings API

**Files:**
- Create: `backend/app/services/document_readiness.py`
- Create: `backend/app/api/routes/document_configurations.py`
- Modify: `backend/app/main.py:6728-6733`
- Create: `backend/tests/integration/test_document_configuration_api.py`
- Create: `backend/tests/unit/services/test_document_readiness.py`

**Interfaces:**
- Produces `check_configuration(session, configuration_id) -> ReadinessReport`.
- Produces REST resources under `/api/v1/document-configurations`.
- Consumes configuration lifecycle, policy findings, business-profile master data, and number sequences.

- [ ] **Step 1: Write failing readiness and API tests**

```python
async def test_configuration_readiness_reports_clickable_blockers(session, invoice_config_without_iban):
    report = await check_configuration(session, invoice_config_without_iban.id)
    assert report.status == "blocked"
    assert any(item.code == "bank_account_missing" and item.field_path == "payment.bank_account_id" for item in report.findings)


async def test_publish_endpoint_requires_manage_permission(client, read_only_headers, draft_config):
    response = await client.post(
        f"/api/v1/document-configurations/{draft_config.id}/publish",
        json={"expected_version": 1, "effective_from": "2026-07-20", "reason": "Initial release"},
        headers=read_only_headers,
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run and confirm 404/import failures**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_readiness.py backend/tests/integration/test_document_configuration_api.py -q`

Expected: FAIL because readiness and routes do not exist.

- [ ] **Step 3: Implement readiness aggregation**

```python
class ReadinessReport(BaseModel):
    context: Literal["configuration", "document"]
    status: Literal["ready", "warnings", "blocked"]
    findings: list[ReadinessFinding]


async def check_configuration(session: AsyncSession, configuration_id: int) -> ReadinessReport:
    config = await load_configuration(session, configuration_id)
    findings = list(validate_policy(to_draft_schema(config)))
    findings.extend(await _profile_master_data_findings(session, config))
    findings.extend(await _number_sequence_findings(session, config))
    findings.extend(_einvoice_policy_findings(config))
    return report_from_findings("configuration", findings)
```

Configuration readiness checks seller address/tax IDs/bank, number sequence, required texts, language completeness, policy consistency, E-invoice profile, seller endpoint, and ruleset availability. It does not require a concrete buyer identifier.

- [ ] **Step 4: Add typed routes and structured errors**

Implement list, get, create draft, update draft, clone, readiness, publish, withdraw scheduled publication, effective policy, catalog, placeholders, and history endpoints. Return `{code, message, field_path, correction, rule_id, correlation_id}` for domain errors. Gate reads with `document_templates:read` and writes with `document_templates:manage`.

- [ ] **Step 5: Run API tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_readiness.py backend/tests/integration/test_document_configuration_api.py -q`

Expected: PASS.

- [ ] **Step 6: Commit readiness API**

```bash
git add backend/app/services/document_readiness.py backend/app/api/routes/document_configurations.py backend/app/main.py backend/tests/unit/services/test_document_readiness.py backend/tests/integration/test_document_configuration_api.py
git commit -m "feat(documents): expose configuration readiness API"
```

### Task 6: Customer E-Invoice Preferences and Tax Decision Engine

**Files:**
- Modify: `backend/app/models/document_configuration.py`
- Modify: `backend/app/schemas/customer.py`
- Modify: `backend/app/services/customer.py`
- Modify: `backend/app/api/routes/customers.py`
- Create: `backend/app/services/tax_decision.py`
- Create: `backend/tests/unit/services/test_tax_decision.py`
- Modify: `backend/tests/integration/test_customers_api.py`

**Interfaces:**
- Produces `TaxDecisionInput`, `TaxDecision`, `determine_tax(input, rules) -> TaxDecision`, `override_tax(decision, override, actor) -> TaxDecision`.
- Extends customer profile preferences with endpoint ID/scheme, Leitweg-ID, Buyer Reference, purchase/supplier references, E-invoice requirement, and verified VAT-ID evidence.
- Consumes existing customer accounts, addresses, tax identifiers, business-profile tax settings.

- [ ] **Step 1: Write failing tax matrix and customer round-trip tests**

```python
@pytest.mark.parametrize(
    ("seller", "buyer", "buyer_kind", "vat_valid", "place", "expected"),
    [
        ("DE", "DE", "business", True, "DE", "domestic_standard"),
        ("DE", "FR", "business", True, "FR", "eu_reverse_charge"),
        ("DE", "FR", "consumer", False, "FR", "eu_b2c_oss"),
        ("DE", "US", "business", False, "US", "third_country"),
    ],
)
def test_tax_matrix(seller, buyer, buyer_kind, vat_valid, place, expected):
    decision = determine_tax(tax_input(seller, buyer, buyer_kind, vat_valid, place), RULES_2026_1)
    assert decision.treatment == expected


async def test_customer_einvoice_preferences_round_trip(api_client, customer_payload):
    customer_payload["accounts"][0]["document_preferences"] = {
        "endpoint_id": "0204:9930123456789",
        "endpoint_scheme": "0204",
        "buyer_reference": "04011000-12345-34",
        "einvoice_requirement": "required",
    }
    created = (await api_client.post("/api/v1/customers/", json=customer_payload)).json()
    assert created["accounts"][0]["document_preferences"]["endpoint_scheme"] == "0204"
```

- [ ] **Step 2: Run and confirm the missing contracts**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_tax_decision.py backend/tests/integration/test_customers_api.py -q`

Expected: FAIL because tax decisions and document preferences are absent.

- [ ] **Step 3: Implement deterministic tax decisions**

```python
@dataclass(frozen=True, slots=True)
class TaxDecision:
    treatment: str
    tax_country: str
    place_of_supply: str
    category_code: str
    rate: Decimal
    legal_reason_code: str
    legal_reason_text: str
    seller_vat_id: str | None
    buyer_vat_id: str | None
    vat_validation_evidence: Mapping[str, str]
    rule_version: str
    manual_override: bool = False
    override_reason: str | None = None
```

Implement rules for domestic standard tax, §19 small business, intra-community supply, EU B2B reverse charge, EU B2C/OSS, third country, and explicit exemption. Return blocking findings for missing country, unknown place of supply, required invalid/missing VAT ID, or no matching rule. Override requires permission at the route and a non-empty reason in the service.

- [ ] **Step 4: Persist customer preferences and VAT evidence**

Use one `CustomerDocumentPreference` row per customer account. Store VAT validation provider, result, checked timestamp, and reference as evidence fields; do not make a network VIES call in this task.

- [ ] **Step 5: Run tests and Ruff**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_tax_decision.py backend/tests/integration/test_customers_api.py -q`

Expected: PASS.

- [ ] **Step 6: Commit tax and customer preferences**

```bash
git add backend/app/models/document_configuration.py backend/app/schemas/customer.py backend/app/services/customer.py backend/app/api/routes/customers.py backend/app/services/tax_decision.py backend/tests/unit/services/test_tax_decision.py backend/tests/integration/test_customers_api.py
git commit -m "feat(documents): add tax decisions and recipient preferences"
```

### Task 7: Commercial Document Aggregate and Immutable Snapshot

**Files:**
- Create: `backend/app/models/commercial_document.py`
- Create: `backend/app/models/document_audit.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py`
- Create: `backend/app/schemas/commercial_document.py`
- Create: `backend/app/services/document_snapshot.py`
- Create: `backend/app/services/document_audit.py`
- Create: `backend/tests/unit/services/test_document_snapshot.py`
- Create: `backend/tests/integration/test_commercial_document_schema.py`

**Interfaces:**
- Produces `CommercialDocument`, `CommercialDocumentLine`, `DocumentRelation`, `DocumentSnapshot`, `DocumentArtifact`, `DocumentNumberReservation`, `DocumentAuditEvent`.
- Produces `canonicalize_snapshot(snapshot: IssuedDocumentSnapshot) -> bytes` and `snapshot_sha256(snapshot) -> str`.
- Produces `append_audit(session, *, action, object_type, object_id, actor_id, reason, before, after, correlation_id)`.

- [ ] **Step 1: Write failing snapshot and immutability tests**

```python
def test_snapshot_hash_is_order_independent_and_decimal_exact():
    left = issued_snapshot(lines=[line(net=Decimal("10.00"))], metadata={"b": 2, "a": 1})
    right = issued_snapshot(lines=[line(net=Decimal("10.00"))], metadata={"a": 1, "b": 2})
    assert canonicalize_snapshot(left) == canonicalize_snapshot(right)
    assert snapshot_sha256(left) == snapshot_sha256(right)


async def test_issued_snapshot_cannot_be_updated(session, issued_document):
    with pytest.raises(ImmutableDocumentError):
        await replace_issued_snapshot(session, issued_document.id, issued_snapshot(total="11.00"))
```

- [ ] **Step 2: Run and confirm missing aggregate**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_snapshot.py backend/tests/integration/test_commercial_document_schema.py -q`

Expected: FAIL because the models and snapshot service do not exist.

- [ ] **Step 3: Add the relational aggregate**

```python
class CommercialDocument(Base):
    __tablename__ = "commercial_documents"
    __table_args__ = (
        UniqueConstraint("business_profile_id", "number", name="uq_commercial_document_profile_number"),
        CheckConstraint("technical_status IN ('draft','validation_failed','ready','issued','cancelled','corrected','replaced')"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_type: Mapped[str] = mapped_column(String(32), index=True)
    business_profile_id: Mapped[int] = mapped_column(ForeignKey("business_profiles.id", ondelete="RESTRICT"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"))
    number: Mapped[str | None] = mapped_column(String(100))
    technical_status: Mapped[str] = mapped_column(String(24), default="draft")
    business_status: Mapped[str] = mapped_column(String(32), default="open")
    payment_status: Mapped[str] = mapped_column(String(24), default="not_applicable")
    language: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
```

Store mutable lines relationally. `DocumentSnapshot` stores canonical JSON, SHA-256, configuration ID/version, tax rule version, E-invoice rule versions, issued actor/time, and never exposes an update command.

- [ ] **Step 4: Implement canonical JSON and append-only audit**

Encode Decimal as normalized strings, dates as ISO-8601, sort object keys, preserve line-array order, use UTF-8 without ASCII escaping, and hash exact canonical bytes. Reject audit writes without a reason for publication, tax override, issue, cancel, correct, and export actions.

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_snapshot.py backend/tests/integration/test_commercial_document_schema.py -q`

Expected: PASS.

- [ ] **Step 6: Commit aggregate foundation**

```bash
git add backend/app/models/commercial_document.py backend/app/models/document_audit.py backend/app/models/__init__.py backend/app/core/database.py backend/app/schemas/commercial_document.py backend/app/services/document_snapshot.py backend/app/services/document_audit.py backend/tests/unit/services/test_document_snapshot.py backend/tests/integration/test_commercial_document_schema.py
git commit -m "feat(documents): add immutable commercial document aggregate"
```

### Task 8: Document-Type Rules, Relations, and Lifecycle

**Files:**
- Create: `backend/app/services/commercial_documents.py`
- Create: `backend/tests/unit/services/test_commercial_document_rules.py`
- Create: `backend/tests/integration/test_commercial_document_lifecycle.py`
- Modify: `backend/app/services/offers.py`
- Modify: `backend/app/models/commerce.py`

**Interfaces:**
- Produces `create_draft`, `update_draft`, `validate_draft`, `mark_ready`, `create_successor`, `cancel_document`, `correct_document`.
- Consumes catalog capabilities, effective configuration, tax decision, policy validator, snapshot service, existing `Offer` and `CustomerOrder` sources.

- [ ] **Step 1: Write failing type and transition tests**

```python
def test_delivery_note_rejects_price_and_internal_calculation_by_default():
    findings = validate_document(delivery_note_draft(show_prices=True, include_internal_calculation=True))
    assert {item.code for item in findings} == {"delivery_prices_forbidden", "internal_calculation_forbidden"}


def test_final_invoice_requires_prior_payment_breakdown_by_tax_group():
    findings = validate_document(final_invoice_draft(prior_invoices=[prior_invoice("19", "119.00")], deductions=[]))
    assert any(item.code == "prior_payment_deduction_missing" for item in findings)


async def test_correction_creates_new_document_and_preserves_original(session, issued_invoice):
    correction = await correct_document(session, issued_invoice.id, reason="Quantity corrected", actor_id=1)
    assert correction.id != issued_invoice.id
    assert correction.document_type == "invoice_correction"
    assert issued_invoice.technical_status == "corrected"
```

- [ ] **Step 2: Run and confirm missing lifecycle service**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_commercial_document_rules.py backend/tests/integration/test_commercial_document_lifecycle.py -q`

Expected: FAIL because the lifecycle service is absent.

- [ ] **Step 3: Implement exact transition table and type validators**

```python
TECHNICAL_TRANSITIONS = {
    "draft": frozenset({"validation_failed", "ready"}),
    "validation_failed": frozenset({"draft", "ready"}),
    "ready": frozenset({"draft", "issued"}),
    "issued": frozenset({"cancelled", "corrected", "replaced"}),
    "cancelled": frozenset(),
    "corrected": frozenset(),
    "replaced": frozenset(),
}
```

Implement required fields and relations for all thirteen catalog types. Explicitly separate commercial credit note from self-billing. Self-billing swaps issuer roles and stores external issuer number separately. Reminder and dunning totals derive from invoice balance and add no VAT. Cancellation performs full reversal. Correction supports delta or full replacement. Final invoice deducts prior advance/progress invoices and payments per tax group.

- [ ] **Step 4: Connect existing offers and orders without destructive migration**

New offers create a linked `CommercialDocument` quotation draft while retaining the current `Offer` API as a compatibility facade. Accepted offers link the generated order confirmation to `CustomerOrder`. Existing Offer snapshots remain readable and are not rewritten.

- [ ] **Step 5: Run lifecycle tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_commercial_document_rules.py backend/tests/integration/test_commercial_document_lifecycle.py backend/tests/integration/test_offers_api.py -q`

Expected: PASS.

- [ ] **Step 6: Commit lifecycle rules**

```bash
git add backend/app/services/commercial_documents.py backend/app/services/offers.py backend/app/models/commerce.py backend/tests/unit/services/test_commercial_document_rules.py backend/tests/integration/test_commercial_document_lifecycle.py
git commit -m "feat(documents): enforce document lifecycle rules"
```

### Task 9: Transactional Number Reservation and Atomic Issuance

**Files:**
- Create: `backend/app/services/document_numbering.py`
- Modify: `backend/app/services/commercial_documents.py`
- Modify: `backend/app/services/number_sequence.py`
- Create: `backend/tests/unit/services/test_document_numbering.py`
- Create: `backend/tests/integration/test_document_issuance.py`

**Interfaces:**
- Produces `reserve_document_number(session, document, effective_date) -> DocumentNumberReservation`.
- Produces `issue_document(session, document_id, expected_version, actor_id, idempotency_key, correlation_id) -> CommercialDocument`.
- Consumes existing `reserve_number`, readiness, snapshot, audit, and E-invoice generation hook `generate_required_artifact` introduced as a protocol in this task and implemented in Task 12.

- [ ] **Step 1: Write failing concurrency and rollback-evidence tests**

```python
async def test_concurrent_issuance_returns_one_issued_document_and_one_idempotent_replay(two_sessions, ready_invoice):
    first, second = await asyncio.gather(
        issue_in_fresh_session(ready_invoice.id, "issue-key-123"),
        issue_in_fresh_session(ready_invoice.id, "issue-key-123"),
    )
    assert first.number == second.number
    assert first.snapshot.sha256 == second.snapshot.sha256


async def test_failed_artifact_validation_keeps_voided_number_evidence(session, ready_invoice, failing_generator):
    with pytest.raises(EInvoiceValidationFailed):
        await issue_document(session, ready_invoice.id, 1, 1, "issue-key-456", "corr-1")
    reservation = await reservation_for_document(session, ready_invoice.id)
    assert reservation.status == "voided"
    assert reservation.number is not None
    assert reservation.failure_code == "einvoice_invalid"
```

- [ ] **Step 2: Run and confirm issuance tests fail**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_numbering.py backend/tests/integration/test_document_issuance.py -q`

Expected: FAIL because reservation evidence and issuance orchestration are absent.

- [ ] **Step 3: Implement reservation evidence and issuance transaction**

```python
async def issue_document(session, document_id, expected_version, actor_id, idempotency_key, correlation_id):
    replay = await _load_issue_replay(session, idempotency_key, document_id)
    if replay:
        return replay
    document = await _lock_ready_document(session, document_id, expected_version)
    report = await check_document(session, document)
    report.raise_if_blocked()
    reservation = await reserve_document_number(session, document, document.issue_date)
    try:
        snapshot = await build_issued_snapshot(session, document, reservation.number, actor_id)
        artifact = await generate_required_artifact(session, document, snapshot)
        await _finalize_issue(session, document, reservation, snapshot, artifact, actor_id, correlation_id)
    except Exception as exc:
        await _mark_reservation_voided_in_independent_evidence(session, reservation, exc)
        raise
    return document
```

For PostgreSQL use row locking; for SQLite obtain the write lock through the existing compare-and-swap update. A failed number remains committed as `voided` evidence even when the document transaction rolls back. The retry key is unique and bound to one document and snapshot intent.

- [ ] **Step 4: Run concurrency tests repeatedly**

Run: `1..5 | ForEach-Object { & .venv\Scripts\python.exe -m pytest backend/tests/integration/test_document_issuance.py -q; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }`

Expected: all five runs PASS with no duplicate numbers.

- [ ] **Step 5: Commit numbering and issuance**

```bash
git add backend/app/services/document_numbering.py backend/app/services/commercial_documents.py backend/app/services/number_sequence.py backend/tests/unit/services/test_document_numbering.py backend/tests/integration/test_document_issuance.py
git commit -m "feat(documents): issue documents atomically"
```

### Task 10: Vendor Pinned E-Invoice Rule Assets

**Files:**
- Create: `backend/app/resources/einvoice/manifest.json`
- Create: `backend/app/resources/einvoice/en16931/1.3.16/`
- Create: `backend/app/resources/einvoice/xrechnung/3.0.2-2026-01-31/`
- Create: `backend/app/resources/einvoice/zugferd/2.5/`
- Create: `backend/tests/unit/services/test_einvoice_assets.py`
- Modify: `docs/superpowers/specs/2026-07-20-document-management-e-invoice-design.md`

**Interfaces:**
- Produces a normalized asset manifest consumed by `einvoice.validator` with paths, versions, syntax, profile, and SHA-256 per file.
- Sources: official EN-16931 1.3.16 release, KoSIT XRechnung 3.0.2 configuration dated 2026-01-31, FeRD ZUGFeRD 2.5 package dated 2026-06-10.

- [ ] **Step 1: Write a failing manifest-integrity test**

```python
def test_vendored_einvoice_assets_match_manifest():
    manifest = load_manifest()
    assert manifest["en16931"]["version"] == "1.3.16"
    assert manifest["xrechnung"]["version"] == "3.0.2"
    assert manifest["xrechnung"]["bundle_date"] == "2026-01-31"
    assert manifest["zugferd"]["version"] == "2.5"
    for item in manifest["files"]:
        path = RESOURCE_ROOT / item["path"]
        assert path.is_file()
        assert sha256(path.read_bytes()).hexdigest() == item["sha256"]
```

- [ ] **Step 2: Run and confirm the manifest is missing**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_einvoice_assets.py -q`

Expected: FAIL because no E-invoice resources exist.

- [ ] **Step 3: Download only the official pinned releases**

Use:

```powershell
Invoke-WebRequest https://github.com/ConnectingEurope/eInvoicing-EN16931/archive/refs/tags/validation-1.3.16.zip -OutFile $env:TEMP\en16931.zip
Invoke-WebRequest https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/download/v2026-01-31/xrechnung-3.0.2-validator-configuration-2026-01-31.zip -OutFile $env:TEMP\xrechnung.zip
```

Download ZUGFeRD 2.5 from the official FeRD direct-download link exposed by `https://www.ferd-net.de/download-zugferd`, accepting its published usage terms. Extract only XSD, Schematron/XSLT, codelists, and normative examples needed by the two supported profiles. Do not commit marketing documents, logos, or duplicate binaries.

- [ ] **Step 4: Normalize assets and create the exact manifest**

Generate `manifest.json` from the extracted files with `version`, `source_url`, `license`, `syntax`, `profile`, relative path, and SHA-256. Update the approved specification's rule-version paragraph to name these exact releases without changing product scope.

- [ ] **Step 5: Run integrity and repository checks**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_einvoice_assets.py -q`

Expected: PASS.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 6: Commit rule assets**

```bash
git add backend/app/resources/einvoice backend/tests/unit/services/test_einvoice_assets.py docs/superpowers/specs/2026-07-20-document-management-e-invoice-design.md
git commit -m "build(einvoice): vendor pinned validation rules"
```

### Task 11: Canonical EN-16931 Semantic Model and Math Validation

**Files:**
- Create: `backend/app/services/einvoice/__init__.py`
- Create: `backend/app/services/einvoice/canonical.py`
- Create: `backend/app/schemas/einvoice.py`
- Create: `backend/tests/unit/services/einvoice/test_canonical.py`

**Interfaces:**
- Produces `CanonicalInvoice`, `CanonicalParty`, `CanonicalLine`, `CanonicalTaxSubtotal`, `CanonicalPayment`, `CanonicalReference`.
- Produces `from_snapshot(snapshot) -> CanonicalInvoice` and `validate_math(invoice) -> tuple[EInvoiceFinding, ...]`.
- Consumes immutable issued-document snapshot only.

- [ ] **Step 1: Write failing semantic and rounding tests**

```python
def test_multi_rate_totals_are_grouped_and_exact():
    invoice = from_snapshot(snapshot_with_rates(("19.00", "100.00"), ("7.00", "50.00")))
    assert invoice.tax_subtotals[0].tax_amount == Decimal("19.00")
    assert invoice.tax_subtotals[1].tax_amount == Decimal("3.50")
    assert invoice.tax_total == Decimal("22.50")
    assert invoice.payable_amount == Decimal("172.50")


def test_empty_optional_values_are_omitted_not_serialized():
    invoice = from_snapshot(snapshot(contact_email=""))
    assert invoice.seller.contact.email is None
```

- [ ] **Step 2: Run and confirm the model is absent**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/einvoice/test_canonical.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement strict immutable dataclasses**

```python
@dataclass(frozen=True, slots=True)
class CanonicalInvoice:
    invoice_number: str
    type_code: str
    issue_date: date
    currency: str
    seller: CanonicalParty
    buyer: CanonicalParty
    lines: tuple[CanonicalLine, ...]
    tax_subtotals: tuple[CanonicalTaxSubtotal, ...]
    tax_total: Decimal
    line_net_total: Decimal
    allowance_total: Decimal
    charge_total: Decimal
    invoice_total: Decimal
    paid_amount: Decimal
    payable_amount: Decimal
    payment: CanonicalPayment
    references: tuple[CanonicalReference, ...]
```

Map document types to EN invoice type codes, including credit/correction/self-billing semantics. Normalize optional blank values to `None`, preserve Unicode, require ISO codes, and quantize only at explicitly defined currency/tax boundaries.

- [ ] **Step 4: Run semantic tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/einvoice/test_canonical.py -q`

Expected: PASS.

- [ ] **Step 5: Commit semantic model**

```bash
git add backend/app/services/einvoice/__init__.py backend/app/services/einvoice/canonical.py backend/app/schemas/einvoice.py backend/tests/unit/services/einvoice/test_canonical.py
git commit -m "feat(einvoice): add canonical EN 16931 model"
```

### Task 12: XRechnung and ZUGFeRD XML Renderers

**Files:**
- Create: `backend/app/services/einvoice/xrechnung.py`
- Create: `backend/app/services/einvoice/zugferd.py`
- Create: `backend/tests/unit/services/einvoice/test_xrechnung.py`
- Create: `backend/tests/unit/services/einvoice/test_zugferd.py`
- Create: `backend/tests/fixtures/einvoice/expected/`

**Interfaces:**
- Produces `render_xrechnung(invoice, syntax: Literal['ubl','cii']) -> bytes`.
- Produces `render_zugferd(invoice, profile: Literal['en16931','xrechnung']) -> bytes`.
- Consumes `CanonicalInvoice` and lxml element construction.

- [ ] **Step 1: Write failing namespace, value, and determinism tests**

```python
def test_ubl_xrechnung_contains_endpoint_buyer_reference_and_tax_totals(canonical_invoice):
    root = etree.fromstring(render_xrechnung(canonical_invoice, "ubl"))
    assert root.nsmap[None] == "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    assert xpath_text(root, "//cbc:BuyerReference") == "04011000-12345-34"
    assert xpath_text(root, "//cac:TaxTotal/cbc:TaxAmount") == "19.00"


def test_zugferd_25_uses_d22b_context_and_has_no_empty_elements(canonical_invoice):
    xml = render_zugferd(canonical_invoice, "en16931")
    root = etree.fromstring(xml)
    assert b"urn:factur-x.eu:1p0:en16931" in xml
    assert not root.xpath("//*[not(node())]")


def test_renderer_is_byte_deterministic(canonical_invoice):
    assert render_xrechnung(canonical_invoice, "cii") == render_xrechnung(canonical_invoice, "cii")
```

- [ ] **Step 2: Run and confirm renderer imports fail**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/einvoice/test_xrechnung.py backend/tests/unit/services/einvoice/test_zugferd.py -q`

Expected: FAIL because renderers do not exist.

- [ ] **Step 3: Implement explicit namespace-safe builders**

```python
def _element(parent: etree._Element, qname: str, value: str | None = None, **attributes) -> etree._Element:
    node = etree.SubElement(parent, qname, **attributes)
    if value is not None:
        if value == "":
            raise ValueError("Empty XML elements are forbidden")
        node.text = value
    return node
```

Build UBL Invoice/CreditNote and CII trees from the same canonical model. Format decimals locale-independently. Include all required seller/buyer endpoints, references, delivery, payment, allowances/charges, tax categories, exemption reasons, line totals, tax totals, and payable totals. Emit no optional element without a value.

- [ ] **Step 4: Run renderer tests and compare normalized fixtures**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/einvoice/test_xrechnung.py backend/tests/unit/services/einvoice/test_zugferd.py -q`

Expected: PASS.

- [ ] **Step 5: Commit renderers**

```bash
git add backend/app/services/einvoice/xrechnung.py backend/app/services/einvoice/zugferd.py backend/tests/unit/services/einvoice backend/tests/fixtures/einvoice/expected
git commit -m "feat(einvoice): render XRechnung and ZUGFeRD XML"
```

### Task 13: Local Validation and Protected Artifact Storage

**Files:**
- Create: `backend/app/services/einvoice/validator.py`
- Create: `backend/app/services/einvoice/artifacts.py`
- Create: `backend/tests/unit/services/einvoice/test_validator.py`
- Create: `backend/tests/integration/test_einvoice_artifacts.py`
- Modify: `backend/app/services/commercial_documents.py`

**Interfaces:**
- Produces `validate_xml(xml, standard, syntax, profile) -> EInvoiceValidationReport`.
- Produces `store_artifact(document, xml, report, rule_versions) -> DocumentArtifact`.
- Implements `generate_required_artifact(session, document, snapshot)` consumed by Task 9.

- [ ] **Step 1: Write failing validation and storage tests**

```python
def test_valid_official_xrechnung_fixture_has_no_blockers():
    report = validate_xml(load_fixture("01.01a-INVOICE_ubl.xml"), "xrechnung", "ubl", "3.0.2")
    assert report.valid is True
    assert report.rule_versions["xrechnung"] == "3.0.2-2026-01-31"


def test_invalid_buyer_reference_reports_rule_and_field_path():
    report = validate_xml(load_fixture("missing-buyer-reference.xml"), "xrechnung", "ubl", "3.0.2")
    finding = next(item for item in report.findings if item.severity == "error")
    assert finding.rule_id
    assert finding.field_path == "buyer.reference"


async def test_artifact_path_is_server_generated_and_hash_verified(session, issued_invoice, tmp_path):
    artifact = await store_artifact(session, issued_invoice, b"<Invoice/>", valid_report(), RULE_VERSIONS)
    assert ".." not in artifact.storage_path
    assert artifact.sha256 == sha256(b"<Invoice/>").hexdigest()
```

- [ ] **Step 2: Run and confirm validator/storage are missing**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/einvoice/test_validator.py backend/tests/integration/test_einvoice_artifacts.py -q`

Expected: FAIL during import.

- [ ] **Step 3: Implement safe local validation**

Parse with `resolve_entities=False`, `no_network=True`, `load_dtd=False`, and bounded input size. Select XSD/XSLT only through the manifest; never accept filesystem paths or stylesheet locations from request data. Run model/math validation, XSD, EN-16931 XSLT, CIUS/profile XSLT, and recipient requirements in order. Normalize SVRL assertions into stable findings with severity, code, rule ID, field path, message key, and source location.

- [ ] **Step 4: Implement protected storage and issuance hook**

Write to a server-generated path under the configured PrintOps data directory using an atomic temporary file and rename. Store media type, byte size, SHA-256, profile, syntax, standard versions, report JSON, and creation metadata. Invalid XML records the report but is not exposed as an issued/downloadable artifact and causes issuance to fail.

- [ ] **Step 5: Run validation, artifact, and issuance tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/einvoice/test_validator.py backend/tests/integration/test_einvoice_artifacts.py backend/tests/integration/test_document_issuance.py -q`

Expected: PASS.

- [ ] **Step 6: Commit validation and artifacts**

```bash
git add backend/app/services/einvoice/validator.py backend/app/services/einvoice/artifacts.py backend/app/services/commercial_documents.py backend/tests/unit/services/einvoice/test_validator.py backend/tests/integration/test_einvoice_artifacts.py
git commit -m "feat(einvoice): validate and store XML locally"
```

### Task 14: Commercial Document and E-Invoice APIs

**Files:**
- Create: `backend/app/api/routes/commercial_documents.py`
- Create: `backend/app/api/routes/einvoices.py`
- Modify: `backend/app/main.py:6731-6733`
- Create: `backend/tests/integration/test_commercial_documents_api.py`
- Create: `backend/tests/integration/test_einvoices_api.py`

**Interfaces:**
- Produces `/api/v1/commercial-documents` draft, validate, ready, issue, successor, correction, cancellation, history endpoints.
- Produces `/api/v1/einvoices/{artifact_id}`, `/validation`, and `/download` endpoints.
- Consumes lifecycle, issuance, artifact, audit, and existing permission dependencies.

- [ ] **Step 1: Write failing authorization and structured-error tests**

```python
async def test_issue_requires_issue_permission(client, draft_headers, ready_invoice):
    response = await client.post(
        f"/api/v1/commercial-documents/{ready_invoice.id}/issue",
        json={"expected_version": 1, "idempotency_key": "issue-12345678"},
        headers=draft_headers,
    )
    assert response.status_code == 403


async def test_invalid_document_returns_field_rule_and_correlation(client, issue_headers, incomplete_invoice):
    response = await client.post(
        f"/api/v1/commercial-documents/{incomplete_invoice.id}/validate",
        headers=issue_headers,
    )
    detail = response.json()["detail"]
    assert detail["code"] == "document_not_ready"
    assert detail["findings"][0]["field_path"]
    assert detail["correlation_id"]


async def test_xml_download_has_attachment_headers(client, export_headers, valid_artifact):
    response = await client.get(f"/api/v1/einvoices/{valid_artifact.id}/download", headers=export_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] in {"application/xml", "text/xml; charset=utf-8"}
    assert "attachment" in response.headers["content-disposition"]
```

- [ ] **Step 2: Run and confirm endpoints are 404**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/integration/test_commercial_documents_api.py backend/tests/integration/test_einvoices_api.py -q`

Expected: FAIL with 404 responses.

- [ ] **Step 3: Add routes with permission-per-command enforcement**

Use read/draft/issue/correct/export/tax-override permissions independently. Derive the actor from the authenticated user. Generate a correlation ID when middleware did not provide one. Stream artifacts only after verifying metadata and SHA-256; return 409 `artifact_integrity_failed` if verification fails.

- [ ] **Step 4: Run API and route-auth coverage tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/integration/test_commercial_documents_api.py backend/tests/integration/test_einvoices_api.py backend/tests/unit/test_route_auth_coverage.py -q`

Expected: PASS.

- [ ] **Step 5: Commit APIs**

```bash
git add backend/app/api/routes/commercial_documents.py backend/app/api/routes/einvoices.py backend/app/main.py backend/tests/integration/test_commercial_documents_api.py backend/tests/integration/test_einvoices_api.py
git commit -m "feat(documents): expose lifecycle and e-invoice APIs"
```

### Task 15: Frontend API Module and Settings Navigation

**Files:**
- Create: `frontend/src/api/documentManagement.ts`
- Create: `frontend/src/components/settings/documents/DocumentSettings.tsx`
- Modify: `frontend/src/lib/settingsNavigation.ts:35,170`
- Modify: `frontend/src/pages/SettingsPage.tsx:45-100,445-475,4011-4025`
- Modify: `frontend/src/__tests__/lib/settingsNavigation.test.ts`
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`
- Create: `frontend/src/__tests__/api/documentManagementApi.test.ts`
- Modify: `frontend/src/i18n/locales/de.ts`
- Modify: `frontend/src/i18n/locales/en.ts`
- Modify: `frontend/src/i18n/locales/es.ts`
- Modify: `frontend/src/i18n/locales/fr.ts`
- Modify: `frontend/src/i18n/locales/it.ts`
- Modify: `frontend/src/i18n/locales/ja.ts`
- Modify: `frontend/src/i18n/locales/ko.ts`
- Modify: `frontend/src/i18n/locales/pt-BR.ts`
- Modify: `frontend/src/i18n/locales/tr.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/zh-TW.ts`

**Interfaces:**
- Produces typed `documentManagementApi` using exported `request` from `client.ts`.
- Extends `OrderManagementSubTab` with `documents` between `business-profile` and `calculation`.
- Produces search anchor `card-document-settings`.

- [ ] **Step 1: Write failing navigation and request-serialization tests**

```typescript
it('resolves the documents subtab', () => {
  expect(resolveOrderManagementSubTab('documents')).toBe('documents');
});

it('publishes a configuration with optimistic version and reason', async () => {
  server.use(http.post('/api/v1/document-configurations/17/publish', async ({ request }) => {
    expect(await request.json()).toEqual({
      expected_version: 3,
      effective_from: '2026-08-01',
      reason: 'Updated invoice terms',
    });
    return HttpResponse.json(configurationFixture({ status: 'scheduled' }));
  }));
  await documentManagementApi.publishConfiguration(17, 3, '2026-08-01', 'Updated invoice terms');
});
```

- [ ] **Step 2: Run and confirm type/test failures**

Run: `npm.cmd run test -- --run src/__tests__/lib/settingsNavigation.test.ts src/__tests__/api/documentManagementApi.test.ts src/__tests__/pages/SettingsPage.test.tsx`

Workdir: `frontend`

Expected: FAIL because the subtab and API module are absent.

- [ ] **Step 3: Define complete frontend contracts and calls**

```typescript
export type ConfigurationStatus = 'draft' | 'scheduled' | 'active' | 'superseded';
export type ReadinessStatus = 'ready' | 'warnings' | 'blocked';
export interface ReadinessFinding {
  severity: 'warning' | 'blocker';
  code: string;
  field_path: string;
  message_key: string;
  correction: string;
  rule_id: string | null;
}
export interface SourcedValue<T> {
  value: T;
  source: 'system' | 'business_profile' | 'customer' | 'configuration' | 'document';
  overridable: boolean;
}
```

Add typed functions for catalog, placeholders, list/get/create/update/clone/readiness/publish/withdraw/history, effective policy, document readiness, E-invoice validation, and downloads. Use `ApiError.detail` for structured findings.

- [ ] **Step 4: Add navigation metadata and all locale keys**

Place `documents` after `business-profile`, add `FileText` icon and German/English descriptions, update URL parsing and settings search, and render a minimal `DocumentSettings` shell containing the localized heading and a loading-safe content region. Add semantically correct German and English strings; copy English values into the other nine locale files to preserve key parity until reviewed translations are available.

- [ ] **Step 5: Run tests and i18n parity**

Run: `npm.cmd run test -- --run src/__tests__/lib/settingsNavigation.test.ts src/__tests__/api/documentManagementApi.test.ts src/__tests__/pages/SettingsPage.test.tsx`

Expected: PASS.

Run: `npm.cmd run check:i18n`

Expected: PASS with no missing or extra keys.

- [ ] **Step 6: Commit API and navigation**

```bash
git add frontend/src/api/documentManagement.ts frontend/src/components/settings/documents/DocumentSettings.tsx frontend/src/lib/settingsNavigation.ts frontend/src/pages/SettingsPage.tsx frontend/src/__tests__/lib/settingsNavigation.test.ts frontend/src/__tests__/api/documentManagementApi.test.ts frontend/src/__tests__/pages/SettingsPage.test.tsx frontend/src/i18n/locales
git commit -m "feat(documents): add settings navigation and API client"
```

### Task 16: Document Settings Shell, Context, Versioning, and Dirty State

**Files:**
- Modify: `frontend/src/components/settings/documents/DocumentSettings.tsx`
- Create: `frontend/src/components/settings/documents/DocumentContextHeader.tsx`
- Create: `frontend/src/components/settings/documents/DocumentActionBar.tsx`
- Create: `frontend/src/components/settings/documents/documentSettingsState.ts`
- Create: `frontend/src/components/settings/documents/VersionHistoryPanel.tsx`
- Create: `frontend/src/__tests__/components/settings/documents/DocumentSettings.test.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`

**Interfaces:**
- Produces the feature query boundary and context `{profileId, documentType, language, configurationId}`.
- Produces `initialDocumentContext(profiles) -> DocumentContext` and `stableStringify(value) -> string`.
- Produces `DocumentActionBar` with explicit save/check/publish/clone/withdraw callbacks.
- Consumes `documentManagementApi`, business-profile options, permissions, `Button`, `Select`, existing modal/toast patterns.

- [ ] **Step 1: Write failing interaction tests**

```typescript
it('renders profile type language version and readiness in the sticky header', async () => {
  renderDocumentSettings();
  expect(await screen.findByLabelText('Unternehmensprofil')).toBeInTheDocument();
  expect(screen.getByLabelText('Dokumenttyp')).toBeInTheDocument();
  expect(screen.getByLabelText('Sprache')).toBeInTheDocument();
  expect(screen.getByText('Entwurf · Version 2')).toBeInTheDocument();
});

it('blocks context changes until unsaved edits are discarded or saved', async () => {
  const user = userEvent.setup();
  renderDocumentSettings();
  await user.type(await screen.findByLabelText('Änderungsgrund'), 'Neue Zahlungsregeln');
  await user.selectOptions(screen.getByLabelText('Dokumenttyp'), 'quotation');
  expect(screen.getByRole('dialog', { name: 'Ungespeicherte Änderungen' })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run and confirm component imports fail**

Run: `npm.cmd run test -- --run src/__tests__/components/settings/documents/DocumentSettings.test.tsx`

Workdir: `frontend`

Expected: FAIL because the components are missing.

- [ ] **Step 3: Implement query ownership and action state**

```tsx
export function DocumentSettings() {
  const { hasPermission } = useAuth();
  const canRead = hasPermission('document_templates:read');
  const canManage = hasPermission('document_templates:manage');
  const profilesQuery = useQuery({ queryKey: ['business-profile-options'], queryFn: api.getBusinessProfileOptions });
  const [context, setContext] = useState<DocumentContext>(() => initialDocumentContext([]));
  const [pendingContext, setPendingContext] = useState<DocumentContext | null>(null);
  useEffect(() => {
    if (context.profileId === 0 && profilesQuery.data?.length) {
      setContext(initialDocumentContext(profilesQuery.data));
    }
  }, [context.profileId, profilesQuery.data]);
  const configurationQuery = useQuery({
    queryKey: ['document-configuration', context],
    queryFn: () => documentManagementApi.getSelectedConfiguration(context),
    enabled: canRead && context.profileId > 0,
  });
  const readinessQuery = useQuery({
    queryKey: ['document-configuration-readiness', configurationQuery.data?.id],
    queryFn: () => documentManagementApi.getConfigurationReadiness(configurationQuery.data!.id),
    enabled: Boolean(configurationQuery.data?.id),
  });
  const historyQuery = useQuery({
    queryKey: ['document-configuration-history', context],
    queryFn: () => documentManagementApi.getConfigurationHistory(context),
    enabled: canRead && context.profileId > 0,
  });
  const [draft, setDraft] = useState<DocumentConfigurationDraft | null>(null);
  const dirty = draft !== null && stableStringify(draft) !== stableStringify(configurationQuery.data?.draft);
  const requestContextChange = useCallback((next: DocumentContext) => {
    if (dirty) setPendingContext(next);
    else setContext(next);
  }, [dirty]);
  useBeforeUnload(dirty);
  return (
    <section id="card-document-settings" className="space-y-4">
      <DocumentContextHeader context={context} onChange={requestContextChange} />
      <DocumentActionBar canManage={canManage} dirty={dirty} readiness={readinessQuery.data} />
      <VersionHistoryPanel items={historyQuery.data ?? []} />
    </section>
  );
}
```

Provide loading, empty, permission-denied, query-error, conflict, and retry states. Save permits incomplete drafts. Publish opens a reason/effective-date confirmation and is disabled on blockers. Scheduled versions can be withdrawn; active versions can only be cloned.

- [ ] **Step 4: Add version history and audit view**

Render immutable version rows with status, effective date, creator/publisher, change reason, tax/EN/XRechnung/ZUGFeRD rule versions, and audit events. Read-only users see actions disabled with explanatory text rather than hidden sections.

- [ ] **Step 5: Run component tests**

Run: `npm.cmd run test -- --run src/__tests__/components/settings/documents/DocumentSettings.test.tsx src/__tests__/pages/SettingsPage.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit settings shell**

```bash
git add frontend/src/components/settings/documents/DocumentSettings.tsx frontend/src/components/settings/documents/DocumentContextHeader.tsx frontend/src/components/settings/documents/DocumentActionBar.tsx frontend/src/components/settings/documents/documentSettingsState.ts frontend/src/components/settings/documents/VersionHistoryPanel.tsx frontend/src/__tests__/components/settings/documents/DocumentSettings.test.tsx frontend/src/pages/SettingsPage.tsx
git commit -m "feat(documents): add versioned settings shell"
```

### Task 17: Policy Editors and Inheritance UI

**Files:**
- Create: `frontend/src/components/settings/documents/InheritanceField.tsx`
- Create: `frontend/src/components/settings/documents/BasicPolicySection.tsx`
- Create: `frontend/src/components/settings/documents/PaymentPolicySection.tsx`
- Create: `frontend/src/components/settings/documents/TextBlocksSection.tsx`
- Modify: `frontend/src/components/settings/documents/DocumentSettings.tsx`
- Create: `frontend/src/__tests__/components/settings/documents/PolicySections.test.tsx`

**Interfaces:**
- Produces accessible two-column policy editors with source badges and reset controls.
- Consumes sourced effective values, catalog capabilities, placeholder metadata, UI `NumberField`, `Select`, `TextArea`, `Switch`.

- [ ] **Step 1: Write failing inheritance, payment, and placeholder tests**

```typescript
it('shows the source and restores an inherited value', async () => {
  const user = userEvent.setup();
  renderPolicy({ payment_term_days: sourced(30, 'customer', true) });
  expect(screen.getByText('Vom Kunden übernommen')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Vorgabe wiederherstellen' }));
  expect(onChange).toHaveBeenCalledWith('payment.payment_term_days', undefined);
});

it('renders dunning stages in deterministic order and validates percentages', async () => {
  renderPolicy({ dunning_stages: [stage(2), stage(1)] });
  expect(screen.getAllByTestId('dunning-stage').map(node => node.textContent)).toEqual([
    expect.stringContaining('Stufe 1'), expect.stringContaining('Stufe 2'),
  ]);
});

it('offers only placeholders allowed for the selected type', async () => {
  renderTextBlocks({ documentType: 'delivery_note' });
  expect(screen.getByRole('option', { name: 'Lieferdatum' })).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: 'Skontofrist' })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run and confirm missing editors**

Run: `npm.cmd run test -- --run src/__tests__/components/settings/documents/PolicySections.test.tsx`

Workdir: `frontend`

Expected: FAIL during import.

- [ ] **Step 3: Implement source-aware fields and complete sections**

```tsx
export function InheritanceField<T>({ path, sourced, children, onReset }: Props<T>) {
  return (
    <div data-field-path={path} className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <SourceBadge source={sourced.source} />
        {sourced.overridable && sourced.source !== 'configuration' && (
          <Button type="button" variant="ghost" onClick={() => onReset(path)}>
            Vorgabe wiederherstellen
          </Button>
        )}
      </div>
      {children}
    </div>
  );
}
```

Basic policy covers dates, currency, rounding, references, allowed successors, and technical-data content policy. Payment covers due basis, terms, methods, discount, advance, installments, bank, interest, fees, and ordered dunning stages. Text blocks cover every approved purpose and stage, with insertion at cursor and inline backend findings.

- [ ] **Step 4: Apply responsive two-column layout without empty cards**

Use `grid grid-cols-1 xl:grid-cols-2 gap-4`; render a section only when the catalog capability marks it applicable. Preserve DOM order for keyboard navigation. Do not render disabled placeholder cards for excluded document types.

- [ ] **Step 5: Run UI tests**

Run: `npm.cmd run test -- --run src/__tests__/components/settings/documents/PolicySections.test.tsx src/__tests__/components/settings/documents/DocumentSettings.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit policy editors**

```bash
git add frontend/src/components/settings/documents/InheritanceField.tsx frontend/src/components/settings/documents/BasicPolicySection.tsx frontend/src/components/settings/documents/PaymentPolicySection.tsx frontend/src/components/settings/documents/TextBlocksSection.tsx frontend/src/components/settings/documents/DocumentSettings.tsx frontend/src/__tests__/components/settings/documents/PolicySections.test.tsx
git commit -m "feat(documents): add policy and text editors"
```

### Task 18: Tax, E-Invoice, Readiness, and Error UX

**Files:**
- Create: `frontend/src/components/settings/documents/TaxPolicySection.tsx`
- Create: `frontend/src/components/settings/documents/EInvoicePolicySection.tsx`
- Create: `frontend/src/components/settings/documents/ReadinessPanel.tsx`
- Modify: `frontend/src/components/settings/documents/DocumentSettings.tsx`
- Create: `frontend/src/__tests__/components/settings/documents/ComplianceSections.test.tsx`

**Interfaces:**
- Produces tax outcome/rule-version display, reasoned override UI, E-invoice policy/report/download UI, and field-focused readiness navigation.
- Consumes structured API errors, readiness reports, permissions, E-invoice catalog and artifact metadata.

- [ ] **Step 1: Write failing compliance UX tests**

```typescript
it('requires a reason before a permitted tax override can be saved', async () => {
  const user = userEvent.setup();
  renderCompliance({ permissions: ['commercial_documents:tax_override'] });
  await user.click(screen.getByRole('checkbox', { name: 'Steuerfall manuell abweichend festlegen' }));
  expect(screen.getByRole('button', { name: 'Abweichung übernehmen' })).toBeDisabled();
  await user.type(screen.getByLabelText('Begründung'), 'Steuerberaterprüfung vom 20.07.2026');
  expect(screen.getByRole('button', { name: 'Abweichung übernehmen' })).toBeEnabled();
});

it('focuses the field selected from a blocking readiness finding', async () => {
  const user = userEvent.setup();
  renderCompliance({ findings: [blocker('buyer_endpoint_missing', 'einvoice.buyer_endpoint')] });
  await user.click(screen.getByRole('button', { name: /Empfängerkennung fehlt/ }));
  expect(screen.getByLabelText('Empfängerkennung')).toHaveFocus();
});

it('shows rule id and correlation id instead of a generic error', () => {
  renderCompliance({ apiError: structuredError('BR-DE-15', 'corr-123') });
  expect(screen.getByText('BR-DE-15')).toBeInTheDocument();
  expect(screen.getByText('corr-123')).toBeInTheDocument();
  expect(screen.queryByText('Not found')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run and confirm sections are absent**

Run: `npm.cmd run test -- --run src/__tests__/components/settings/documents/ComplianceSections.test.tsx`

Workdir: `frontend`

Expected: FAIL during import.

- [ ] **Step 3: Implement tax and E-invoice sections**

Tax displays treatment, country/place, rate/category, legal reason, IDs/evidence, and rule version. Manual controls render only with the override permission but read-only users still see recorded overrides. E-invoice displays requirement, XRechnung syntax, ZUGFeRD profile, process ID, seller endpoint, buyer rule, Leitweg/Buyer Reference requirements, and validation layers. XML/report downloads require export permission.

- [ ] **Step 4: Implement readiness navigation and precise errors**

```tsx
function focusFinding(finding: ReadinessFinding) {
  const target = document.querySelector<HTMLElement>(`[data-field-path="${CSS.escape(finding.field_path)}"]`);
  target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  target?.querySelector<HTMLElement>('input,select,textarea,button')?.focus();
}
```

Group blockers before warnings, preserve backend order within a field, show correction text, rule ID, and correlation ID. Map 409 version conflicts to a reload/compare action; never replace the current draft silently.

- [ ] **Step 5: Run compliance and full feature tests**

Run: `npm.cmd run test -- --run src/__tests__/components/settings/documents`

Expected: PASS.

- [ ] **Step 6: Commit compliance UI**

```bash
git add frontend/src/components/settings/documents/TaxPolicySection.tsx frontend/src/components/settings/documents/EInvoicePolicySection.tsx frontend/src/components/settings/documents/ReadinessPanel.tsx frontend/src/components/settings/documents/DocumentSettings.tsx frontend/src/__tests__/components/settings/documents/ComplianceSections.test.tsx
git commit -m "feat(documents): add compliance and readiness UI"
```

### Task 19: End-to-End Migration, Conformance, Backup, and Regression Gate

**Files:**
- Create: `backend/tests/integration/test_document_workflow_e2e.py`
- Create: `backend/tests/integration/test_document_backup_restore.py`
- Create: `backend/tests/integration/test_einvoice_conformance.py`
- Create: `frontend/src/__tests__/pages/DocumentSettingsFlow.test.tsx`
- Modify: `backend/app/services/local_backup.py`
- Modify: `backend/app/services/github_backup.py`
- Create: `docs/document-management.md`
- Modify: `docs/order-management.md`

**Interfaces:**
- Verifies every approved acceptance criterion across the completed feature.
- Consumes every previous task; produces no new product behavior except backup inclusion and user documentation.

- [ ] **Step 1: Write the complete failing workflow test**

```python
async def test_complete_document_and_einvoice_workflow(api):
    profile = await api.create_complete_german_profile()
    customer = await api.create_b2g_customer(endpoint="0204:9930123456789", leitweg="04011000-12345-34")
    config = await api.create_invoice_configuration(profile.id, language="de")
    assert (await api.configuration_readiness(config.id)).status == "ready"
    published = await api.publish_configuration(config.id, reason="Initial approved template")
    invoice = await api.create_invoice(customer.id, published.id, net="100.00", tax_rate="19.00")
    assert (await api.document_readiness(invoice.id)).status == "ready"
    issued = await api.issue(invoice.id, idempotency_key="e2e-issue-123456")
    assert issued.number
    assert issued.snapshot.sha256
    artifact = await api.get_einvoice_artifact(issued.id)
    assert artifact.validation.valid is True
    assert artifact.standard_versions == {
        "en16931": "1.3.16",
        "xrechnung": "3.0.2-2026-01-31",
    }
```

Add separate complete tests for quotation/order confirmation/delivery, advance/progress/final invoice, cancellation/correction/commercial credit note, self-billing, reminder/dunning, EU reverse charge, EU B2C OSS, third country, English templates, and manual tax override audit.

- [ ] **Step 2: Run the new end-to-end tests and record failures**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/integration/test_document_workflow_e2e.py backend/tests/integration/test_document_backup_restore.py backend/tests/integration/test_einvoice_conformance.py -q`

Expected: failures identify backup/resource or cross-feature integration gaps.

- [ ] **Step 3: Include all commercial evidence in backup and restore**

Backups include configuration tables, document tables, snapshots, audit events, number reservations, artifact files, validation reports, and the ruleset manifest. Restore verifies artifact hashes and reports missing/corrupt artifacts without silently marking them valid. Secrets and unnecessary personal content never enter support bundles.

- [ ] **Step 4: Write operator documentation**

Create `docs/document-management.md` with navigation, configuration inheritance, draft/check/publish/version flows, every document type, payment and dunning policy behavior, tax override audit requirements, XRechnung/ZUGFeRD XML validation/download, permissions, backup evidence, and the explicit PDF/transport exclusions. Link it from the document section of `docs/order-management.md` and name the bundled rule versions exactly.

- [ ] **Step 5: Add the complete frontend flow test**

```typescript
it('creates checks schedules and publishes a German invoice configuration', async () => {
  const user = userEvent.setup();
  renderSettingsAt('?tab=orders-calculation&sub=documents');
  await user.selectOptions(await screen.findByLabelText('Dokumenttyp'), 'invoice');
  await user.clear(screen.getByLabelText('Zahlungsziel in Tagen'));
  await user.type(screen.getByLabelText('Zahlungsziel in Tagen'), '30');
  await user.click(screen.getByRole('button', { name: 'Entwurf speichern' }));
  await user.click(screen.getByRole('button', { name: 'Vollständigkeit prüfen' }));
  expect(await screen.findByText('Bereit')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Veröffentlichen' }));
  await user.type(screen.getByLabelText('Änderungsgrund'), 'Freigegebene Rechnungsbedingungen');
  await user.click(screen.getByRole('button', { name: 'Veröffentlichung bestätigen' }));
  expect(await screen.findByText(/Aktiv · Version/)).toBeInTheDocument();
});
```

- [ ] **Step 6: Run focused full suites**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_document_catalog.py backend/tests/unit/services/test_document_configuration.py backend/tests/unit/services/test_document_policy_validation.py backend/tests/unit/services/test_document_readiness.py backend/tests/unit/services/test_tax_decision.py backend/tests/unit/services/test_document_snapshot.py backend/tests/unit/services/test_commercial_document_rules.py backend/tests/unit/services/test_document_numbering.py backend/tests/unit/services/einvoice backend/tests/integration/test_document_configuration_api.py backend/tests/integration/test_commercial_document_lifecycle.py backend/tests/integration/test_document_issuance.py backend/tests/integration/test_commercial_documents_api.py backend/tests/integration/test_einvoices_api.py backend/tests/integration/test_document_workflow_e2e.py backend/tests/integration/test_document_backup_restore.py backend/tests/integration/test_einvoice_conformance.py -q`

Expected: PASS.

Run: `npm.cmd run test -- --run src/__tests__/api/documentManagementApi.test.ts src/__tests__/components/settings/documents src/__tests__/pages/DocumentSettingsFlow.test.tsx src/__tests__/pages/SettingsPage.test.tsx`

Workdir: `frontend`

Expected: PASS.

- [ ] **Step 7: Run repository quality gates**

Run: `.venv\Scripts\python.exe -m ruff check backend/app backend/tests`

Expected: `All checks passed!`

Run: `.venv\Scripts\python.exe -m pytest backend/tests -q`

Expected: PASS.

Run: `npm.cmd run lint`

Workdir: `frontend`

Expected: PASS.

Run: `npm.cmd run test:run`

Workdir: `frontend`

Expected: PASS, including i18n parity.

Run: `npm.cmd run build`

Workdir: `frontend`

Expected: TypeScript and Vite production build succeed.

- [ ] **Step 8: Perform browser acceptance at desktop and mobile widths**

Verify `http://127.0.0.1:8000/settings?tab=orders-calculation&sub=documents` at 1440×900 and 390×844. Confirm two columns collapse to one, no horizontal overflow, all fields retain labels, keyboard focus follows readiness findings, permission-denied controls explain their state, and no generic `Not found` message appears.

- [ ] **Step 9: Commit integration completion**

```bash
git add backend/tests/integration/test_document_workflow_e2e.py backend/tests/integration/test_document_backup_restore.py backend/tests/integration/test_einvoice_conformance.py frontend/src/__tests__/pages/DocumentSettingsFlow.test.tsx backend/app/services/local_backup.py backend/app/services/github_backup.py docs/document-management.md docs/order-management.md
git commit -m "test(documents): complete workflow and conformance coverage"
```

## Appendix A: Exact Default Text Resources

The `de.json` and `en.json` resources use the following exact text. Empty cells mean that the purpose is not applicable and must not be emitted as an empty block.

### German

| Dokumenttyp | Betreff | Einleitung | Abschluss |
| --- | --- | --- | --- |
| Angebot | `Angebot {DOCUMENT_NUMBER}` | `vielen Dank für Ihre Anfrage. Gerne bieten wir Ihnen die nachfolgend beschriebenen Leistungen an.` | `Dieses Angebot ist bis zum {VALID_UNTIL} gültig. Bei Rückfragen stehen wir Ihnen gerne zur Verfügung.` |
| Auftragsbestätigung | `Auftragsbestätigung {DOCUMENT_NUMBER}` | `vielen Dank für Ihren Auftrag. Wir bestätigen die Ausführung mit den nachfolgenden Positionen und Bedingungen.` | `Bitte prüfen Sie diese Auftragsbestätigung und teilen Sie uns Abweichungen unverzüglich mit.` |
| Lieferschein | `Lieferschein {DOCUMENT_NUMBER}` | `Die nachfolgend aufgeführten Positionen wurden für die angegebene Lieferung bereitgestellt.` | `Bitte prüfen Sie die Lieferung auf Vollständigkeit und erkennbare Transportschäden.` |
| Anzahlungsrechnung | `Anzahlungsrechnung {DOCUMENT_NUMBER}` | `für den Auftrag {ORDER_REFERENCE} berechnen wir die vereinbarte Anzahlung.` | `Bitte überweisen Sie den Zahlbetrag unter Angabe der Rechnungsnummer bis zum {DUE_DATE}.` |
| Abschlagsrechnung | `Abschlagsrechnung {DOCUMENT_NUMBER}` | `für die bis zum {SERVICE_DATE} erbrachten Teilleistungen berechnen wir den nachfolgenden Abschlag.` | `Bitte überweisen Sie den Zahlbetrag unter Angabe der Rechnungsnummer bis zum {DUE_DATE}.` |
| Schlussrechnung | `Schlussrechnung {DOCUMENT_NUMBER}` | `für die vollständig erbrachten Leistungen stellen wir die Schlussrechnung unter Berücksichtigung aller Anzahlungen und Abschläge.` | `Der verbleibende Zahlbetrag ist unter Angabe der Rechnungsnummer bis zum {DUE_DATE} zu überweisen.` |
| Rechnung | `Rechnung {DOCUMENT_NUMBER}` | `für die erbrachten Leistungen berechnen wir die nachfolgend aufgeführten Positionen.` | `Bitte überweisen Sie den Zahlbetrag unter Angabe der Rechnungsnummer bis zum {DUE_DATE}.` |
| Stornorechnung | `Stornorechnung {DOCUMENT_NUMBER} zu {ORIGINAL_DOCUMENT_NUMBER}` | `die Rechnung {ORIGINAL_DOCUMENT_NUMBER} wird aus dem angegebenen Grund vollständig storniert.` | `Diese Stornorechnung ist gemeinsam mit dem referenzierten Originalbeleg aufzubewahren.` |
| Rechnungskorrektur | `Rechnungskorrektur {DOCUMENT_NUMBER} zu {ORIGINAL_DOCUMENT_NUMBER}` | `die Rechnung {ORIGINAL_DOCUMENT_NUMBER} wird aus dem angegebenen Grund korrigiert.` | `Diese Rechnungskorrektur ist gemeinsam mit dem referenzierten Originalbeleg aufzubewahren.` |
| Kaufmännische Gutschrift | `Gutschrift {DOCUMENT_NUMBER}` | `für den referenzierten Geschäftsvorgang schreiben wir Ihnen den nachfolgenden Betrag gut.` | `Die Gutschrift wird mit offenen Forderungen verrechnet oder auf die vereinbarte Zahlungsart erstattet.` |
| Zahlungserinnerung | `Zahlungserinnerung zu {ORIGINAL_DOCUMENT_NUMBER}` | `bei der Prüfung unseres Kontos konnten wir für die Rechnung {ORIGINAL_DOCUMENT_NUMBER} noch keinen vollständigen Zahlungseingang feststellen.` | `Bitte begleichen Sie den offenen Betrag von {OPEN_AMOUNT} {CURRENCY} bis zum {DUE_DATE}. Falls Sie bereits gezahlt haben, betrachten Sie dieses Schreiben bitte als gegenstandslos.` |
| Mahnung | `Mahnung Stufe {DUNNING_LEVEL} zu {ORIGINAL_DOCUMENT_NUMBER}` | `die Rechnung {ORIGINAL_DOCUMENT_NUMBER} ist trotz Fälligkeit noch nicht vollständig ausgeglichen.` | `Bitte begleichen Sie den ausgewiesenen Gesamtbetrag bis zum {DUE_DATE}.` |
| Self-Billing | `Gutschrift {DOCUMENT_NUMBER}` | `als Leistungsempfänger rechnen wir die nachfolgend bezeichneten Leistungen im vereinbarten Gutschriftverfahren ab.` | `Bitte prüfen Sie diese Abrechnung und teilen Sie uns einen begründeten Widerspruch unverzüglich mit.` |

Common German payment block: `Zahlbar bis zum {DUE_DATE} ohne Abzug, sofern im Dokument keine abweichende Skontoregel ausgewiesen ist.`

### English

| Document type | Subject | Introduction | Closing |
| --- | --- | --- | --- |
| Quotation | `Quotation {DOCUMENT_NUMBER}` | `Thank you for your enquiry. We are pleased to offer the goods and services described below.` | `This quotation is valid until {VALID_UNTIL}. Please contact us if you have any questions.` |
| Order confirmation | `Order confirmation {DOCUMENT_NUMBER}` | `Thank you for your order. We confirm fulfillment with the items and terms listed below.` | `Please review this order confirmation and notify us promptly of any discrepancy.` |
| Delivery note | `Delivery note {DOCUMENT_NUMBER}` | `The items listed below have been prepared for the stated delivery.` | `Please check the delivery for completeness and visible transport damage.` |
| Advance invoice | `Advance invoice {DOCUMENT_NUMBER}` | `We charge the agreed advance payment for order {ORDER_REFERENCE}.` | `Please transfer the amount due by {DUE_DATE}, quoting the invoice number.` |
| Progress invoice | `Progress invoice {DOCUMENT_NUMBER}` | `We charge the following progress payment for partial services completed by {SERVICE_DATE}.` | `Please transfer the amount due by {DUE_DATE}, quoting the invoice number.` |
| Final invoice | `Final invoice {DOCUMENT_NUMBER}` | `We issue the final invoice for the completed services, including all advance and progress payments.` | `Please transfer the remaining amount due by {DUE_DATE}, quoting the invoice number.` |
| Invoice | `Invoice {DOCUMENT_NUMBER}` | `We charge the following items for the goods and services supplied.` | `Please transfer the amount due by {DUE_DATE}, quoting the invoice number.` |
| Cancellation invoice | `Cancellation invoice {DOCUMENT_NUMBER} for {ORIGINAL_DOCUMENT_NUMBER}` | `Invoice {ORIGINAL_DOCUMENT_NUMBER} is cancelled in full for the stated reason.` | `Keep this cancellation invoice together with the referenced original document.` |
| Invoice correction | `Invoice correction {DOCUMENT_NUMBER} for {ORIGINAL_DOCUMENT_NUMBER}` | `Invoice {ORIGINAL_DOCUMENT_NUMBER} is corrected for the stated reason.` | `Keep this invoice correction together with the referenced original document.` |
| Commercial credit note | `Credit note {DOCUMENT_NUMBER}` | `We credit the following amount for the referenced business transaction.` | `The credit will be offset against outstanding receivables or refunded using the agreed payment method.` |
| Payment reminder | `Payment reminder for {ORIGINAL_DOCUMENT_NUMBER}` | `Our records show that invoice {ORIGINAL_DOCUMENT_NUMBER} has not yet been paid in full.` | `Please pay the outstanding amount of {OPEN_AMOUNT} {CURRENCY} by {DUE_DATE}. If payment has already been made, please disregard this reminder.` |
| Dunning notice | `Dunning notice level {DUNNING_LEVEL} for {ORIGINAL_DOCUMENT_NUMBER}` | `Invoice {ORIGINAL_DOCUMENT_NUMBER} remains unpaid in full after its due date.` | `Please pay the stated total amount by {DUE_DATE}.` |
| Self-billing | `Self-billed invoice {DOCUMENT_NUMBER}` | `As the recipient of the supply, we account for the services listed below under the agreed self-billing arrangement.` | `Please review this self-billed invoice and notify us promptly of any reasoned objection.` |

Common English payment block: `Payment is due by {DUE_DATE} without deduction unless the document states a separate early-payment discount.`

Tax/legal text is not copied from these resources. `tax_decision.py` generates the applicable structured legal reason from the recorded tax treatment and rule version so that a user-edited template cannot contradict the tax result.

## Plan Self-Review

- **Specification coverage:** Tasks 1-6 cover catalog, permissions, relational versioned settings, inheritance, text/payment/dunning, readiness, customer preferences, and tax. Tasks 7-9 cover every document type, status, immutable snapshots, audit, references, numbering, and issuance. Tasks 10-14 cover pinned standards, canonical semantics, XRechnung, ZUGFeRD XML, local validation, storage, and APIs. Tasks 15-18 cover the complete approved settings UX. Task 19 covers migration evidence, backup, conformance, regression, and browser acceptance.
- **Scope boundary:** No task creates PDF layout, preview, PDF/A-3, XML embedding, transport, or automatic dunning execution.
- **Type consistency:** `DocumentType`, configuration statuses, readiness statuses, sourced values, tax decisions, canonical invoice types, and rule-version strings are defined before their consumers.
- **Failure coverage:** The plan explicitly tests incomplete drafts, publication blockers, optimistic conflicts, authorization, tax ambiguity, invalid placeholders, invalid XML, number gaps, idempotent retries, artifact corruption, and missing rules.
- **Standards lock:** EN-16931 1.3.16, XRechnung 3.0.2 bundle 2026-01-31, and ZUGFeRD 2.5 are fixed and recorded in every artifact.
- **Completeness scan:** The plan contains no unfinished marker, deferred implementation instruction, or remaining product decision.
