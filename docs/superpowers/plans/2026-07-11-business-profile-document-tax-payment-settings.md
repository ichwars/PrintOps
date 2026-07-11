# Business Profile Document, Tax, and Payment Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist and manage international tax settings, PayPal.Me, offer-QR preference, and secure per-profile logos with previews and table thumbnails.

**Architecture:** Structured settings remain columns on `business_profiles`; binary logos live under the configured PrintOps data directory and are exposed through dedicated version-checked endpoints. Existing profile create/update services remain the canonical owner for structured data, while a focused logo storage service owns file validation and atomic replacement.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, SQLite/PostgreSQL upgrade migration, React 19, TypeScript, TanStack Query, Vitest/MSW, pytest.

## Global Constraints

- PNG and JPEG only, maximum 2 MB, validated by file signature and decoded image metadata.
- No binary or Base64 logo data in profile list/detail JSON.
- Tax modes are exactly `standard`, `exempt`, and `none`.
- `exempt` and `none` force `default_tax_rate=0` and `input_tax_deductible=false`.
- PayPal.Me accepts HTTPS URLs only on `paypal.me` or `www.paypal.me`.
- QR preference is persisted but no PDF or offer generation is added.
- All eleven frontend locales remain in parity.

---

### Task 1: Persist structured profile settings and enforce invariants

**Files:**
- Modify: `backend/app/models/business_profile.py`
- Modify: `backend/app/schemas/business_profile.py`
- Modify: `backend/app/services/business_profile.py`
- Modify: `backend/app/core/database.py`
- Modify: `frontend/src/api/client.ts`
- Test: `backend/tests/integration/test_business_profiles_api.py`
- Test: `backend/tests/integration/test_order_foundation_schema.py`

**Interfaces:**
- Produces profile fields `tax_mode`, `default_tax_rate`, `cash_accounting`, `input_tax_deductible`, `show_offer_qr`, `paypal_me_url`, `logo_media_type`, and `logo_version`.
- Produces Pydantic validation that normalizes blank PayPal values to `None` and rejects non-PayPal HTTPS hosts.

- [ ] **Step 1: Write failing schema and API tests**

```python
def test_exempt_profile_forces_zero_tax_and_disables_input_tax():
    payload = valid_profile_payload(
        tax_mode="exempt", default_tax_rate="19.00", input_tax_deductible=True
    )
    parsed = BusinessProfileCreate.model_validate(payload)
    assert parsed.default_tax_rate == Decimal("0.00")
    assert parsed.input_tax_deductible is False

def test_paypal_me_rejects_non_paypal_host():
    with pytest.raises(ValidationError):
        BusinessProfileCreate.model_validate(
            valid_profile_payload(paypal_me_url="https://example.com/name")
        )
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/integration/test_business_profiles_api.py backend/tests/integration/test_order_foundation_schema.py -q`

Expected: FAIL because the new columns and schema fields do not exist.

- [ ] **Step 3: Add model columns, checks, schema fields, and canonical validation**

```python
tax_mode: Literal["standard", "exempt", "none"] = "standard"
default_tax_rate: Decimal = Field(default=Decimal("0.00"), ge=0, le=100, decimal_places=2)
cash_accounting: bool = False
input_tax_deductible: bool = True
show_offer_qr: bool = False
paypal_me_url: HttpUrl | None = None

@model_validator(mode="after")
def enforce_tax_mode(self) -> Self:
    if self.tax_mode in {"exempt", "none"}:
        self.default_tax_rate = Decimal("0.00")
        self.input_tax_deductible = False
    return self
```

Add idempotent `ALTER TABLE` migration statements and country-aware backfill: German profiles receive `19.00`; all others `0.00`.

- [ ] **Step 4: Update service mapping and TypeScript interfaces**

Ensure create/update copies every new structured field and responses expose nullable logo metadata without file content.

- [ ] **Step 5: Run focused backend tests and Ruff**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/integration/test_business_profiles_api.py backend/tests/integration/test_order_foundation_schema.py -q`

Run: `.venv/Scripts/python.exe -m ruff check backend/app/models/business_profile.py backend/app/schemas/business_profile.py backend/app/services/business_profile.py backend/app/core/database.py`

Expected: PASS.

### Task 2: Add secure managed logo storage and endpoints

**Files:**
- Create: `backend/app/services/business_profile_logo.py`
- Modify: `backend/app/api/routes/business_profiles.py`
- Modify: `backend/app/services/business_profile.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/integration/test_business_profile_logo_api.py`
- Test: `backend/tests/unit/test_business_profile_logo.py`

**Interfaces:**
- Produces `validate_logo(content: bytes, declared_media_type: str | None) -> Literal["image/png", "image/jpeg"]`.
- Produces `logo_path(profile_id: int, media_type: str) -> Path` rooted below `settings.business_profile_logo_dir`.
- Produces `PUT /business-profiles/{id}/logo?version=N`, `GET /business-profiles/{id}/logo?v=N`, and `DELETE /business-profiles/{id}/logo?version=N`.

- [ ] **Step 1: Write failing unit tests for signature, decode, size, and safe path**

```python
def test_rejects_declared_png_with_jpeg_signature(): ...
def test_rejects_truncated_image_even_with_valid_magic_bytes(): ...
def test_rejects_logo_over_two_megabytes(): ...
def test_generated_logo_path_stays_below_configured_root(): ...
```

- [ ] **Step 2: Run unit tests and confirm RED**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/unit/test_business_profile_logo.py -q`

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement bounded read, Pillow verification, and atomic replacement**

```python
MAX_LOGO_BYTES = 2 * 1024 * 1024
ALLOWED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg"}

def validate_logo(content: bytes, declared_media_type: str | None) -> str:
    if len(content) > MAX_LOGO_BYTES:
        raise InvalidBusinessProfileLogo("logo_too_large")
    with Image.open(BytesIO(content)) as image:
        image.verify()
        media_type = ALLOWED_FORMATS.get(image.format or "")
    if media_type is None or declared_media_type not in {None, media_type}:
        raise InvalidBusinessProfileLogo("invalid_logo_type")
    return media_type
```

Write to a random temporary sibling, `fsync`, then `os.replace`; never use the upload filename.

- [ ] **Step 4: Write failing integration tests for permissions, version conflict, upload/read/replace/delete**

Assert response caching headers, correct media type, version increment, old-file retirement, and 404 for missing files.

- [ ] **Step 5: Implement endpoints and cleanup on profile deletion**

Use `order_settings:manage` for PUT/DELETE, `order_settings:read` for GET, and reuse the existing profile-version conflict response contract.

- [ ] **Step 6: Run focused logo tests**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/unit/test_business_profile_logo.py backend/tests/integration/test_business_profile_logo_api.py -q`

Expected: PASS.

### Task 3: Add editor controls and client upload flow

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/settings/BusinessProfileEditorModal.tsx`
- Modify: `frontend/src/components/settings/BusinessProfileSettings.tsx`
- Modify: `frontend/src/__tests__/components/BusinessProfileSettings.test.tsx`

**Interfaces:**
- Consumes structured fields and logo endpoints from Tasks 1-2.
- Produces client methods `uploadBusinessProfileLogo(id, version, file)`, `deleteBusinessProfileLogo(id, version)`, and `businessProfileLogoUrl(id, logoVersion)`.

- [ ] **Step 1: Write failing editor tests**

Cover localized German `exempt` label, forced tax dependencies, QR persistence, PayPal validation feedback, upload preview, replacement, deletion, and preservation of unsaved form data after upload failure.

- [ ] **Step 2: Run the focused Vitest file and confirm RED**

Run: `npx.cmd vitest run src/__tests__/components/BusinessProfileSettings.test.tsx`

Expected: FAIL on missing controls and API calls.

- [ ] **Step 3: Extend the editor with three bounded sections**

```tsx
<DocumentAppearanceSection logo={logo} showOfferQr={draft.show_offer_qr} />
<TaxSettingsSection countryCode={draft.country_code} taxMode={draft.tax_mode} />
<PaymentSettingsSection paypalMeUrl={draft.paypal_me_url} bankAccounts={draft.bank_accounts} />
```

Keep structured changes in the existing profile submit. Logo mutations run only for persisted profiles; for a newly created profile, create first and then upload the selected file using the returned ID/version.

- [ ] **Step 4: Implement client methods and mutation cache invalidation**

Invalidate both profile list variants and profile options after successful upload/delete; append `logo_version` to image URLs.

- [ ] **Step 5: Run focused frontend tests and TypeScript build**

Run: `npx.cmd vitest run src/__tests__/components/BusinessProfileSettings.test.tsx`

Run: `npm.cmd run build`

Expected: PASS.

### Task 4: Add table thumbnail, localization, and full verification

**Files:**
- Modify: `frontend/src/components/settings/BusinessProfileSettings.tsx`
- Modify: `frontend/src/i18n/locales/en.ts`
- Modify: `frontend/src/i18n/locales/de.ts`
- Modify: `frontend/src/i18n/locales/es.ts`
- Modify: `frontend/src/i18n/locales/fr.ts`
- Modify: `frontend/src/i18n/locales/it.ts`
- Modify: `frontend/src/i18n/locales/ja.ts`
- Modify: `frontend/src/i18n/locales/ko.ts`
- Modify: `frontend/src/i18n/locales/pt-BR.ts`
- Modify: `frontend/src/i18n/locales/tr.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/zh-TW.ts`
- Test: `frontend/src/__tests__/components/BusinessProfileSettings.test.tsx`
- Test: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

**Interfaces:**
- Consumes `businessProfileLogoUrl` and logo metadata.
- Produces a fixed-size thumbnail slot before each profile name with accessible alt text and a neutral placeholder.

- [ ] **Step 1: Write failing thumbnail and locale tests**

Assert versioned image URL, stable placeholder width, localized field labels, and translated validation messages.

- [ ] **Step 2: Implement the thumbnail and all eleven locale leaves**

Use `h-10 w-10 shrink-0 rounded object-contain` and keep profile text in `min-w-0` so long names truncate without moving other columns.

- [ ] **Step 3: Run frontend verification**

Run: `npm.cmd run test:run`

Run: `npm.cmd run lint`

Run: `npm.cmd run check:i18n`

Run: `npm.cmd run build`

Expected: all commands PASS; the existing large-chunk warning may remain.

- [ ] **Step 4: Run backend verification**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/integration/test_business_profiles_api.py backend/tests/integration/test_business_profile_logo_api.py backend/tests/unit/test_business_profile_logo.py -q`

Run: `.venv/Scripts/python.exe -m ruff check backend/app backend/tests/integration/test_business_profile_logo_api.py backend/tests/unit/test_business_profile_logo.py`

Expected: all commands PASS.

- [ ] **Step 5: Confirm clean generated-artifact boundary**

Run: `git diff --check` and `git status --short`.

Remove only build-generated `static/` changes; retain source, tests, spec, and this plan.
