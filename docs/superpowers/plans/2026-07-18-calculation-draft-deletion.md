# Calculation Draft Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically discard a draft created only to upload a 3MF when the new-calculation dialog is cancelled, and add an explicit delete action for existing draft calculations.

**Architecture:** A version-checked backend DELETE command is the only authority allowed to remove calculations and rejects every non-draft status. `CalculationWorkspace` records whether the current dialog session created an upload-only draft, so cancel/close can distinguish it from a pre-existing draft; both automatic discard and confirmed manual deletion use the same API client method.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, pytest/httpx, React 19, TypeScript, Vitest, Testing Library, MSW, Tailwind CSS.

## Global Constraints

- Deletion is allowed only when `Calculation.status == "draft"`.
- `Abbrechen` and `X` delete only the draft created by the current new-calculation dialog's first 3MF upload, immediately and without confirmation.
- Closing a calculation that existed before the dialog opened never deletes it.
- Manual deletion always uses `ConfirmModal` and is shown only for an existing draft.
- Approved, superseded, and archived calculations remain traceable and cannot be deleted.
- All delete commands require `expected_version` and `CALCULATIONS_UPDATE`.
- Database deletion is authoritative; filesystem cleanup runs after commit, is path-contained below `<base_dir>/calculations`, and logs cleanup failures without resurrecting the deleted record.
- Do not stage generated `static/` assets, local `calculations/` data, session handoff files, or unrelated working-tree changes.

---

## File Structure

- `backend/app/services/order_errors.py`: define the domain error representing a state conflict that maps to HTTP 409.
- `backend/app/services/calculation.py`: enforce version and draft-only invariants and delete the ORM aggregate.
- `backend/app/api/routes/calculations.py`: expose DELETE, commit the transaction, and safely clean the calculation directory.
- `backend/tests/integration/test_calculations_api.py`: cover version, state, not-found, and successful API behavior.
- `backend/tests/integration/test_calculation_project_files_api.py`: prove project-file rows and files are removed with the draft.
- `frontend/src/api/calculations.ts`: expose `calculationsApi.remove(id, expectedVersion): Promise<void>`.
- `frontend/src/__tests__/api/calculationsApi.test.ts`: lock the DELETE method and query serialization.
- `frontend/src/components/orders/CalculationWorkspace.tsx`: own the upload-session marker, automatic discard, manual delete confirmation, busy state, and error handling.
- `frontend/src/__tests__/components/CalculationWorkspace.test.tsx`: cover cancel, close, retryable errors, existing drafts, status visibility, and manual confirmation.

---

### Task 1: Draft-only deletion endpoint and owned-file cleanup

**Files:**
- Modify: `backend/app/services/order_errors.py`
- Modify: `backend/app/services/calculation.py`
- Modify: `backend/app/api/routes/calculations.py`
- Test: `backend/tests/integration/test_calculations_api.py`
- Test: `backend/tests/integration/test_calculation_project_files_api.py`

**Interfaces:**
- Produces: `InvalidStateConflictError(OrderDomainError)`.
- Produces: `delete_calculation(session: AsyncSession, calculation_id: int, expected_version: int) -> None`.
- Produces: `DELETE /api/v1/calculations/{calculation_id}?expected_version={version}` returning HTTP 204.
- Consumes: existing `_load(..., for_update=True)`, `_raise_http`, `app_settings.base_dir`, ORM delete-orphan cascades, and `Permission.CALCULATIONS_UPDATE`.

- [ ] **Step 1: Add failing API tests for version, status, not-found, aggregate deletion, and directory cleanup**

Add `import pytest` and `from backend.app.models.calculation import Calculation` to `backend/tests/integration/test_calculations_api.py`, then add:

```python
async def test_delete_calculation_enforces_version_and_not_found(async_client, db_session):
    profile = await _profile(db_session)
    created = await async_client.post("/api/v1/calculations/", json=_payload(profile.id))
    calculation = created.json()

    stale = await async_client.delete(
        f"/api/v1/calculations/{calculation['id']}", params={"expected_version": 99}
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    missing = await async_client.delete(
        "/api/v1/calculations/999999", params={"expected_version": 1}
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "not_found"


@pytest.mark.parametrize("blocked_status", ["approved", "superseded", "archived"])
async def test_delete_calculation_rejects_every_non_draft_status(
    async_client, db_session, blocked_status
):
    profile = await _profile(db_session)
    created = await async_client.post("/api/v1/calculations/", json=_payload(profile.id))
    calculation_id = created.json()["id"]
    calculation = await db_session.get(Calculation, calculation_id)
    calculation.status = blocked_status
    await db_session.commit()

    response = await async_client.delete(
        f"/api/v1/calculations/{calculation_id}", params={"expected_version": 1}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_state"
    assert await db_session.get(Calculation, calculation_id) is not None
```

Extend the imports in `backend/tests/integration/test_calculation_project_files_api.py` with `CalculationProjectFile` and `from backend.app.api.routes import calculations as calculation_routes`, then add:

```python
@pytest.mark.asyncio
async def test_delete_draft_removes_project_file_rows_and_storage(
    async_client, db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(app_settings, "base_dir", tmp_path)
    profile = BusinessProfile(
        name="Delete draft issuer",
        legal_name="Delete draft issuer GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    calculation = Calculation(
        business_profile_id=profile.id,
        title="Temporary 3MF draft",
        request_kind="single",
        quantity=1,
        currency="EUR",
    )
    db_session.add(calculation)
    await db_session.commit()

    uploaded = await async_client.post(
        f"/api/v1/calculations/{calculation.id}/project-files",
        files={
            "file": (
                "project.3mf",
                _project_file(),
                "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
            )
        },
    )
    assert uploaded.status_code == 201
    project_file_id = uploaded.json()["id"]
    storage_dir = tmp_path / "calculations" / str(calculation.id)
    assert storage_dir.is_dir()

    deleted = await async_client.delete(
        f"/api/v1/calculations/{calculation.id}", params={"expected_version": 1}
    )

    assert deleted.status_code == 204
    db_session.expire_all()
    assert await db_session.get(Calculation, calculation.id) is None
    assert await db_session.get(CalculationProjectFile, project_file_id) is None
    assert not storage_dir.exists()


@pytest.mark.asyncio
async def test_delete_draft_keeps_database_result_when_storage_cleanup_fails(
    async_client, db_session, tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(app_settings, "base_dir", tmp_path)
    profile = BusinessProfile(
        name="Cleanup failure issuer",
        legal_name="Cleanup failure issuer GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    calculation = Calculation(
        business_profile_id=profile.id,
        title="Cleanup failure draft",
        request_kind="single",
        quantity=1,
        currency="EUR",
    )
    db_session.add(calculation)
    await db_session.commit()
    storage_dir = tmp_path / "calculations" / str(calculation.id)
    storage_dir.mkdir(parents=True)
    (storage_dir / "leftover.3mf").write_bytes(b"3mf")

    def fail_cleanup(_path):
        raise OSError("filesystem busy")

    monkeypatch.setattr(calculation_routes.shutil, "rmtree", fail_cleanup)
    deleted = await async_client.delete(
        f"/api/v1/calculations/{calculation.id}", params={"expected_version": 1}
    )

    assert deleted.status_code == 204
    db_session.expire_all()
    assert await db_session.get(Calculation, calculation.id) is None
    assert storage_dir.exists()
    assert "Failed to remove calculation storage directory" in caplog.text
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/integration/test_calculations_api.py backend/tests/integration/test_calculation_project_files_api.py -q
```

Expected: the new tests fail because DELETE currently returns `405 Method Not Allowed`.

- [ ] **Step 3: Add the state-conflict error and domain deletion command**

Add to `backend/app/services/order_errors.py`:

```python
class InvalidStateConflictError(OrderDomainError):
    pass
```

Import it in `backend/app/services/calculation.py`, then add immediately before `archive_calculation`:

```python
async def delete_calculation(
    session: AsyncSession,
    calculation_id: int,
    expected_version: int,
) -> None:
    calculation = await _load(session, calculation_id, for_update=True)
    if calculation.version != expected_version:
        raise VersionConflictError(f"Calculation {calculation_id} has changed")
    if calculation.status != "draft":
        raise InvalidStateConflictError(f"Calculation {calculation_id} is not a draft")
    await session.delete(calculation)
    await session.flush()
```

- [ ] **Step 4: Expose DELETE and clean the contained storage directory after commit**

In `backend/app/api/routes/calculations.py`, add imports:

```python
import logging
import shutil

from fastapi import Response
from backend.app.services.order_errors import InvalidStateConflictError
```

Create the module logger below the router:

```python
logger = logging.getLogger(__name__)
```

Extend `_raise_http` before the generic branch:

```python
elif isinstance(error, InvalidStateConflictError):
    code, status_code = "invalid_state", status.HTTP_409_CONFLICT
```

Add the route immediately before the archive route:

```python
@router.delete("/{calculation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calculation(
    calculation_id: int,
    expected_version: int = Query(gt=0),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CALCULATIONS_UPDATE),
) -> Response:
    try:
        await calculation_service.delete_calculation(db, calculation_id, expected_version)
        await db.commit()
    except OrderDomainError as exc:
        await db.rollback()
        _raise_http(exc)

    calculations_root = (Path(app_settings.base_dir) / "calculations").resolve()
    storage_dir = (calculations_root / str(calculation_id)).resolve()
    if storage_dir.is_relative_to(calculations_root) and storage_dir.exists():
        try:
            shutil.rmtree(storage_dir)
        except OSError:
            logger.exception("Failed to remove calculation storage directory %s", storage_dir)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 5: Run targeted backend tests and verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/integration/test_calculations_api.py backend/tests/integration/test_calculation_project_files_api.py -q
```

Expected: all tests in both files pass; the new deletion tests report HTTP 204, 404, and 409 exactly as asserted.

- [ ] **Step 6: Commit the backend deletion boundary**

```powershell
git add -- backend/app/services/order_errors.py backend/app/services/calculation.py backend/app/api/routes/calculations.py backend/tests/integration/test_calculations_api.py backend/tests/integration/test_calculation_project_files_api.py
git commit -m "feat(calculations): add draft deletion endpoint"
```

---

### Task 2: Typed frontend deletion client

**Files:**
- Modify: `frontend/src/api/calculations.ts`
- Test: `frontend/src/__tests__/api/calculationsApi.test.ts`

**Interfaces:**
- Consumes: Task 1 endpoint `DELETE /calculations/{id}?expected_version={version}`.
- Produces: `calculationsApi.remove(id: number, expectedVersion: number): Promise<void>`.

- [ ] **Step 1: Add the DELETE request to the API contract test**

In the MSW handler, return an empty 204 response for DELETE so the central request client's no-content path is exercised:

```ts
if (request.method === 'DELETE') return new HttpResponse(null, { status: 204 });
```

Call the wished-for method after `update`:

```ts
await calculationsApi.remove(7, 3);
```

Insert this expected request after the PUT entry:

```ts
'DELETE /api/v1/calculations/7?expected_version=3',
```

- [ ] **Step 2: Run the API test and verify RED**

Run:

```powershell
cd frontend
npm.cmd exec -- vitest run src/__tests__/api/calculationsApi.test.ts --reporter=dot
```

Expected: TypeScript/Vitest fails because `calculationsApi.remove` does not exist.

- [ ] **Step 3: Implement the typed client method**

Add after `update` in `frontend/src/api/calculations.ts`:

```ts
remove: (id: number, expectedVersion: number) =>
  request<void>(`/calculations/${id}?expected_version=${expectedVersion}`, { method: 'DELETE' }),
```

- [ ] **Step 4: Run the API test and verify GREEN**

Run:

```powershell
cd frontend
npm.cmd exec -- vitest run src/__tests__/api/calculationsApi.test.ts --reporter=dot
```

Expected: the test passes and records the exact DELETE URL with a null body.

- [ ] **Step 5: Commit the frontend API boundary**

```powershell
git add -- frontend/src/api/calculations.ts frontend/src/__tests__/api/calculationsApi.test.ts
git commit -m "feat(calculations): expose draft deletion client"
```

---

### Task 3: Automatic discard and confirmed manual deletion in the workspace

**Files:**
- Modify: `frontend/src/components/orders/CalculationWorkspace.tsx`
- Test: `frontend/src/__tests__/components/CalculationWorkspace.test.tsx`

**Interfaces:**
- Consumes: `calculationsApi.remove(id: number, expectedVersion: number): Promise<void>` from Task 2.
- Consumes: existing `ConfirmModal`, `Trash2`, `onClose`, and `onSaved` callbacks.
- Produces: session-only `autoSavedDraft: { id: number; version: number } | null` state.
- Produces: `closeWorkspace(): Promise<void>` shared by `Abbrechen` and `X`.
- Produces: `deleteExistingDraft(): Promise<void>` behind a confirmation dialog.

- [ ] **Step 1: Extend the mocked API and add common test data**

Extend the mock in `CalculationWorkspace.test.tsx`:

```ts
vi.mock('../../api/calculations', () => ({
  calculationsApi: {
    previewBatch: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(),
    revisions: vi.fn(), effectiveDefaults: vi.fn(), availabilityPreview: vi.fn(),
    uploadProjectFile: vi.fn(), projectFiles: vi.fn(),
  },
}));
```

Import the detail type and Testing Library helper:

```ts
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { calculationsApi, type CalculationDetail } from '../../api/calculations';
```

Add a complete existing draft fixture:

```ts
const existingDraft: CalculationDetail = {
  id: 42,
  business_profile_id: 2,
  customer_id: null,
  project_id: null,
  request_kind: 'single' as const,
  quantity: 1,
  position_description: null,
  special_terms: null,
  commercial_overrides: {},
  customer_display_name: null,
  business_profile_name: 'Main',
  title: 'bracket',
  status: 'draft' as const,
  currency: 'EUR',
  notes: null,
  version: 1,
  created_at: '2026-07-18T12:00:00Z',
  updated_at: '2026-07-18T12:00:00Z',
  variants: [{
    name: 'Standard', is_preferred: true, sort_order: 0,
    price_method: 'target_margin' as const, price_rate: '0.35',
    lines: [], operations: [], plates: [], small_parts: [],
  }],
  current_revision: null,
  production_cost: null,
  selling_price: null,
};
```

Add the complete shared dependency setup and call it at the beginning of every test, overriding individual values only where a test needs a special response:

```ts
function mockWorkspaceDependencies() {
  vi.clearAllMocks();
  vi.mocked(api.getBusinessProfileOptions).mockResolvedValue([
    {
      id: 2, name: 'Main', legal_name: 'Main GmbH', country_code: 'DE',
      default_currency: 'EUR', is_active: true, is_default: true, version: 1,
    },
  ]);
  vi.mocked(api.getSettings).mockResolvedValue({
    calculation_defaults: '{}', default_filament_cost: 25, energy_cost_per_kwh: 0.3,
  } as never);
  vi.mocked(api.getPrinters).mockResolvedValue([]);
  vi.mocked(api.getEquipment).mockResolvedValue([]);
  vi.mocked(api.getCustomers).mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
  vi.mocked(api.getProjects).mockResolvedValue([]);
  vi.mocked(api.getSpools).mockResolvedValue([]);
  vi.mocked(calculationsApi.effectiveDefaults).mockResolvedValue({});
  vi.mocked(calculationsApi.availabilityPreview).mockResolvedValue({
    lines: [], reservation_state: 'not_reserved', checked_at: '2026-07-18T12:00:00Z',
  });
  vi.mocked(calculationsApi.projectFiles).mockResolvedValue([]);
  vi.mocked(calculationsApi.revisions).mockResolvedValue([]);
  vi.mocked(calculationsApi.previewBatch).mockResolvedValue({
    total_runs: 0, material_cost: '0', material_markup: '0', machine_cost: '0',
    energy_cost: '0', labor_cost: '0', consumables: '0', packaging: '0',
    additional_costs: '0', additive_materials: '0', scrap_cost: '0', risk_cost: '0',
    production_cost: '0', shipping: '0', selling_price: '0', net_price: '0',
    contribution: '0', effective_margin: '0', tax: '0', gross_price: '0',
    unit_price: '0', breakdown: [],
  });
}
```

- [ ] **Step 2: Add failing tests for upload-session cancel, close, and delete failure**

Add these behavior tests:

```ts
it.each([
  ['Cancel', () => screen.getByRole('button', { name: 'Cancel' })],
  ['Close', () => screen.getByRole('button', { name: 'Close' })],
])('discards an upload-only draft through %s without confirmation', async (_label, closeControl) => {
  mockWorkspaceDependencies();
  vi.mocked(calculationsApi.create).mockResolvedValue(existingDraft);
  vi.mocked(calculationsApi.uploadProjectFile).mockResolvedValue({
    id: 7, calculation_id: 42, revision_number: 1, original_filename: 'bracket.3mf',
    sha256: 'abc', size_bytes: 3, analysis_status: 'completed', analysis_error: null,
    printer_metadata: {}, created_at: '2026-07-18T12:00:00Z', plates: [],
  });
  vi.mocked(calculationsApi.remove).mockResolvedValue(undefined);
  const confirm = vi.spyOn(window, 'confirm');
  const onSaved = vi.fn();
  render(<CalculationWorkspace calculation={null} locale="en-US" onClose={vi.fn()} onSaved={onSaved} />);
  await waitFor(() => expect(api.getCustomers).toHaveBeenCalled());

  const file = new File(['3mf'], 'bracket.3mf', { type: 'model/3mf' });
  fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, {
    target: { files: [file] },
  });
  await waitFor(() => expect(calculationsApi.uploadProjectFile).toHaveBeenCalledWith(42, file));
  fireEvent.click(closeControl());

  await waitFor(() => expect(calculationsApi.remove).toHaveBeenCalledWith(42, 1));
  expect(confirm).not.toHaveBeenCalled();
  expect(onSaved).toHaveBeenCalledTimes(1);
  confirm.mockRestore();
});

it('keeps the upload-only draft open when automatic deletion fails', async () => {
  mockWorkspaceDependencies();
  vi.mocked(calculationsApi.create).mockResolvedValue(existingDraft);
  vi.mocked(calculationsApi.uploadProjectFile).mockResolvedValue({
    id: 7, calculation_id: 42, revision_number: 1, original_filename: 'bracket.3mf',
    sha256: 'abc', size_bytes: 3, analysis_status: 'completed', analysis_error: null,
    printer_metadata: {}, created_at: '2026-07-18T12:00:00Z', plates: [],
  });
  vi.mocked(calculationsApi.remove).mockRejectedValue(new Error('Delete failed'));
  const onSaved = vi.fn();
  render(<CalculationWorkspace calculation={null} locale="en-US" onClose={vi.fn()} onSaved={onSaved} />);
  await waitFor(() => expect(api.getCustomers).toHaveBeenCalled());
  fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, {
    target: { files: [new File(['3mf'], 'bracket.3mf')] },
  });
  await waitFor(() => expect(calculationsApi.uploadProjectFile).toHaveBeenCalled());

  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

  expect(await screen.findByText('Delete failed')).toBeInTheDocument();
  expect(screen.getByRole('dialog', { name: 'bracket' })).toBeInTheDocument();
  expect(onSaved).not.toHaveBeenCalled();
});

it('stops treating an upload-only draft as temporary after explicit save', async () => {
  mockWorkspaceDependencies();
  vi.mocked(calculationsApi.create).mockResolvedValue(existingDraft);
  vi.mocked(calculationsApi.update).mockResolvedValue(existingDraft);
  vi.mocked(calculationsApi.uploadProjectFile).mockResolvedValue({
    id: 7, calculation_id: 42, revision_number: 1, original_filename: 'bracket.3mf',
    sha256: 'abc', size_bytes: 3, analysis_status: 'completed', analysis_error: null,
    printer_metadata: {}, created_at: '2026-07-18T12:00:00Z', plates: [],
  });
  const onClose = vi.fn();
  render(<CalculationWorkspace calculation={null} locale="en-US" onClose={onClose} onSaved={vi.fn()} />);
  await waitFor(() => expect(api.getCustomers).toHaveBeenCalled());
  fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, {
    target: { files: [new File(['3mf'], 'bracket.3mf')] },
  });
  await waitFor(() => expect(calculationsApi.uploadProjectFile).toHaveBeenCalled());

  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(calculationsApi.update).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

  expect(calculationsApi.remove).not.toHaveBeenCalled();
  expect(onClose).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 3: Add failing tests for existing-draft close, visibility, and confirmed deletion**

Import `within` from Testing Library, then add:

```ts
it('closes an existing draft without deleting it', async () => {
  mockWorkspaceDependencies();
  const onClose = vi.fn();
  render(<CalculationWorkspace calculation={existingDraft} locale="en-US" onClose={onClose} onSaved={vi.fn()} />);

  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

  expect(onClose).toHaveBeenCalledTimes(1);
  expect(calculationsApi.remove).not.toHaveBeenCalled();
});

it('confirms deletion for an existing draft and hides delete for approved calculations', async () => {
  mockWorkspaceDependencies();
  vi.mocked(calculationsApi.remove).mockResolvedValue(undefined);
  const onSaved = vi.fn();
  const view = render(
    <CalculationWorkspace calculation={existingDraft} locale="en-US" onClose={vi.fn()} onSaved={onSaved} />,
  );

  fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
  const confirmation = screen.getByRole('dialog', { name: 'Delete calculation?' });
  expect(confirmation).toHaveTextContent('project files will be permanently removed');
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Delete' }));
  await waitFor(() => expect(calculationsApi.remove).toHaveBeenCalledWith(42, 1));
  expect(onSaved).toHaveBeenCalledTimes(1);

  view.unmount();
  render(
    <CalculationWorkspace
      calculation={{ ...existingDraft, status: 'approved', version: 2 }}
      locale="en-US"
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Archive' })).toBeInTheDocument();
});

it('keeps manual deletion retryable after an API error', async () => {
  mockWorkspaceDependencies();
  vi.mocked(calculationsApi.remove)
    .mockRejectedValueOnce(new Error('Delete failed'))
    .mockResolvedValueOnce(undefined);
  const onSaved = vi.fn();
  render(
    <CalculationWorkspace calculation={existingDraft} locale="en-US" onClose={vi.fn()} onSaved={onSaved} />,
  );

  fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
  let confirmation = screen.getByRole('dialog', { name: 'Delete calculation?' });
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Delete' }));
  expect(await screen.findByText('Delete failed')).toBeInTheDocument();
  confirmation = screen.getByRole('dialog', { name: 'Delete calculation?' });

  fireEvent.click(within(confirmation).getByRole('button', { name: 'Delete' }));

  await waitFor(() => expect(calculationsApi.remove).toHaveBeenCalledTimes(2));
  expect(onSaved).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 4: Run the workspace tests and verify RED**

Run:

```powershell
cd frontend
npm.cmd exec -- vitest run src/__tests__/components/CalculationWorkspace.test.tsx --reporter=dot
```

Expected: the new tests fail because cancel calls `onSaved` without DELETE, the manual Delete button/confirmation do not exist, and deletion errors are not rendered.

- [ ] **Step 5: Track the upload-only draft and share automatic discard between Cancel and X**

Import `ConfirmModal`, then add state beside `persistedCalculation`:

```ts
const [autoSavedDraft, setAutoSavedDraft] = useState<{ id: number; version: number } | null>(null);
const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
```

After `setPersistedCalculation(created)` in `ensureCalculationForUpload`, add:

```ts
setAutoSavedDraft({ id: created.id, version: created.version });
```

Replace `closeWorkspace` with:

```ts
const closeWorkspace = async () => {
  if (!autoSavedDraft) {
    onClose();
    return;
  }
  setSaving(true);
  setMessage(null);
  try {
    await calculationsApi.remove(autoSavedDraft.id, autoSavedDraft.version);
    setAutoSavedDraft(null);
    onSaved();
  } catch (error) {
    setMessage(error instanceof Error ? error.message : 'Error');
  } finally {
    setSaving(false);
  }
};
```

Bind both closing controls to it and prevent duplicate clicks:

```tsx
<button
  type="button"
  onClick={() => void closeWorkspace()}
  disabled={saving}
  aria-label={de ? 'Schließen' : 'Close'}
  className="rounded p-2 text-bambu-gray hover:bg-bambu-dark disabled:opacity-50"
>
  <X />
</button>
```

```tsx
<button
  type="button"
  onClick={() => void closeWorkspace()}
  disabled={saving}
  className="h-10 rounded-lg bg-bambu-dark px-4 text-white disabled:opacity-50"
>
  {de ? 'Abbrechen' : 'Cancel'}
</button>
```

In the successful `save` branch, call `setAutoSavedDraft(null)` immediately before `onSaved()`.

- [ ] **Step 6: Add confirmed deletion for pre-existing drafts**

Add:

```ts
const deleteExistingDraft = async () => {
  if (!calculation || !persistedCalculation || persistedCalculation.status !== 'draft') return;
  setSaving(true);
  setMessage(null);
  try {
    await calculationsApi.remove(persistedCalculation.id, persistedCalculation.version);
    setDeleteConfirmOpen(false);
    onSaved();
  } catch (error) {
    setMessage(error instanceof Error ? error.message : 'Error');
  } finally {
    setSaving(false);
  }
};
```

In the left footer action area, render Delete for a pre-existing draft and retain Archive for approved/superseded records:

```tsx
{calculation && persistedCalculation?.status === 'draft' && (
  <button
    type="button"
    onClick={() => setDeleteConfirmOpen(true)}
    disabled={saving}
    className="mr-auto inline-flex h-10 items-center gap-2 rounded-lg border border-red-500/60 px-4 text-red-300 hover:bg-red-500/10 disabled:opacity-50"
  >
    <Trash2 className="h-4 w-4" />
    {de ? 'Löschen' : 'Delete'}
  </button>
)}
{persistedCalculation && ['approved', 'superseded'].includes(persistedCalculation.status) && (
  <button
    type="button"
    onClick={() => void archive()}
    disabled={saving}
    className="mr-auto inline-flex h-10 items-center gap-2 rounded-lg border border-bambu-dark-tertiary px-4 text-bambu-gray hover:text-white disabled:opacity-50"
  >
    <Archive className="h-4 w-4" />
    {de ? 'Archivieren' : 'Archive'}
  </button>
)}
```

Wrap the existing workspace root and the confirmation in a fragment so the modal is a sibling of the calculation overlay. Change the start of the current return from:

```tsx
return <div className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-black/70 p-3 md:p-8">
```

to:

```tsx
return <>
  <div className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-black/70 p-3 md:p-8">
```

Then replace the current final `</div></div>;` with this exact suffix:

```tsx
  </div></div>
  {deleteConfirmOpen && persistedCalculation && (
    <ConfirmModal
      title={de ? 'Kalkulation löschen?' : 'Delete calculation?'}
      message={de
        ? 'Die Kalkulation und alle hochgeladenen Projektdateien werden endgültig gelöscht.'
        : 'The calculation and all uploaded project files will be permanently removed.'}
      confirmText={de ? 'Löschen' : 'Delete'}
      variant="danger"
      isLoading={saving}
      onCancel={() => setDeleteConfirmOpen(false)}
      onConfirm={() => void deleteExistingDraft()}
    />
  )}
</>;
```

- [ ] **Step 7: Run workspace and page tests and verify GREEN**

Run:

```powershell
cd frontend
npm.cmd exec -- vitest run src/__tests__/components/CalculationWorkspace.test.tsx src/__tests__/pages/CalculationsPage.test.tsx --reporter=dot
```

Expected: both test files pass; automatic discard calls DELETE without confirmation, existing cancel calls only `onClose`, and manual delete requires confirmation.

- [ ] **Step 8: Commit the workspace behavior**

```powershell
git add -- frontend/src/components/orders/CalculationWorkspace.tsx frontend/src/__tests__/components/CalculationWorkspace.test.tsx
git commit -m "feat(calculations): discard and delete draft calculations"
```

---

### Task 4: Cross-layer verification and local UI proof

**Files:**
- Verify only; do not stage generated `static/` output.

**Interfaces:**
- Consumes: all interfaces from Tasks 1–3.
- Produces: verified backend, frontend, and local-browser behavior.

- [ ] **Step 1: Run focused backend regression tests**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/integration/test_calculations_api.py backend/tests/integration/test_calculation_project_files_api.py -q
```

Expected: both files pass with no failed tests.

- [ ] **Step 2: Run the complete frontend suite**

```powershell
cd frontend
npm.cmd run test:run
```

Expected: Vitest reports zero failures and the i18n parity check reports all locales in parity.

- [ ] **Step 3: Run lint and production build**

```powershell
cd frontend
npm.cmd run lint
npm.cmd run build
```

Expected: both commands exit with code 0.

- [ ] **Step 4: Verify the local workflow in the in-app browser**

At `http://127.0.0.1:8000/orders/calculation`:

1. Open `Kalkulation hinzufügen`, upload a valid 3MF, note the new `K-` identifier, click `Abbrechen`, and verify that identifier is absent from the refreshed list.
2. Open a pre-existing draft, click `Abbrechen`, and verify it remains in the list.
3. Reopen that draft, click `Löschen`, cancel the confirmation once, then confirm it and verify the draft disappears.
4. Open an approved calculation and verify `Archivieren` is present while `Löschen` is absent.

- [ ] **Step 5: Inspect the final scoped diff and commit history**

```powershell
git diff --check
git status --short
git log -4 --oneline
```

Expected: the three implementation commits are present; only known unrelated/generated local changes remain unstaged.
