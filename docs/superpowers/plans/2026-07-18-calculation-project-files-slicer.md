# Calculation Project Files and Slicer Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the calculation workspace around revisioned 3MF project files, selectable plate previews, productive sidecar slicing, explicit estimates, warehouse-backed small parts, visible effective defaults, and derived offer positions.

**Architecture:** Keep `Calculation` and its immutable approval revisions as the aggregate root, but add normalized project-file, plate, variant-plate, and variant-small-part records. A server-side analyzer owns trusted 3MF metadata and thumbnails; calculation slicing reuses `SlicerApiService`, `resolve_preset_ref`, and the existing background dispatcher, then persists/cache-keys results per file/plate/profile revision. The React workspace is split into focused sections and a sticky summary while the Decimal calculation engine remains the only price authority.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic v2, Python `zipfile`/XML, Decimal, existing Orca/Bambu sidecars, React 19, TypeScript, TanStack Query, Tailwind CSS, Vitest, Testing Library.

## Global Constraints

- Do not build a new slicer engine; use existing productive Orca/Bambu sidecars and CLI integration.
- Use embedded 3MF thumbnails first, the existing PrintOps renderer second, and a neutral text fallback third.
- A ForgeDesk-derived geometry estimate is allowed only after productive slicing fails or is unavailable and must be labelled `estimate` with the failure reason.
- One project file can feed many variants; variants store plate selections and overrides, not duplicate file bytes.
- Active editing variant is UI state; exactly one persisted variant remains `is_preferred=true`.
- Manual Position rows are removed from the workspace. Customer-facing positions are derived from selected plates.
- Keep internal `Numeric(18, 6)`/Decimal precision. Display integers for counts, up to one decimal for grams, up to two for hours/percent, and exactly two for money.
- Effective settings values must be visible inputs with source and per-field reset; blank placeholders are not acceptable.
- Preserve legacy calculations and immutable revisions; ambiguous migrated fields remain manual with provenance `migration`.
- This plan consumes `SmallPart`, `SmallPartCombobox`, and `smallPartsApi` from `2026-07-18-small-parts-inventory.md`.

## File Structure

- `backend/app/models/calculation_project.py`: project-file revisions, plates, variant selections, and small-part requirements.
- `backend/app/schemas/calculation_project.py`: upload, plate, slicing, effective-default, and availability-neutral read contracts.
- `backend/app/services/calculation_project.py`: file revision storage, 3MF analysis, matching, and derived operation/line mapping.
- `backend/app/services/calculation_estimator.py`: tested Python port of ForgeDesk geometry and fallback formulas.
- `backend/app/services/calculation_slicing.py`: cache key, preset resolution, sidecar call, fallback, and result persistence.
- `backend/app/api/routes/calculation_projects.py`: file/plate/thumbnail/slice endpoints.
- `frontend/src/components/orders/calculation/VariantStrip.tsx`: active vs preferred variant controls.
- `frontend/src/components/orders/calculation/ProjectFileSection.tsx`: device fields, upload, plate cards, and slice state.
- `frontend/src/components/orders/calculation/PlateDetailEditor.tsx`: editable per-plate values and provenance.
- `frontend/src/components/orders/calculation/SmallPartsEditor.tsx`: warehouse-backed requirements.
- `frontend/src/components/orders/calculation/EffectiveValuesEditor.tsx`: complete defaults and reset controls.
- `frontend/src/components/orders/calculation/CalculationSummary.tsx`: sticky cost/status panel.
- `frontend/src/utils/calculationFormatting.ts`: locale-safe display helpers.

---

### Task 1: Persist Project Files, Plates, and Variant Requirements

**Files:**
- Create: `backend/app/models/calculation_project.py`
- Create: `backend/app/schemas/calculation_project.py`
- Modify: `backend/app/models/calculation.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/integration/test_calculation_project_schema.py`

**Interfaces:**
- Produces `CalculationProjectFile`, `CalculationProjectPlate`, `CalculationVariantPlate`, and `CalculationVariantSmallPart`.
- `Calculation.project_files` owns file revisions; `CalculationVariant.plates` and `.small_parts` own variant-specific selections.
- Stable plate identity is `stable_key = sha256(plate_index + object ids + plate name)`; `plate_index` remains the slicer-facing 1-based index.

- [ ] **Step 1: Write the failing schema and relationship test**

```python
EXPECTED = {
    "calculation_project_files",
    "calculation_project_plates",
    "calculation_variant_plates",
    "calculation_variant_small_parts",
}


def test_variant_plate_uniqueness_contract():
    names = {constraint.name for constraint in CalculationVariantPlate.__table__.constraints}
    assert "uq_calculation_variant_plate" in names
    assert "ck_calculation_variant_plate_counts" in names
```

Add an async persistence case that stores one file with four plates, selects plates 1 and 3 in Variant A, plates 2 and 4 in Variant B, and references one `SmallPart` without duplicating the source file.

- [ ] **Step 2: Run the schema test and verify missing models**

Run `python -m pytest backend/tests/integration/test_calculation_project_schema.py -q` and expect FAIL.

- [ ] **Step 3: Implement normalized models**

```python
class CalculationProjectFile(Base):
    __tablename__ = "calculation_project_files"
    __table_args__ = (UniqueConstraint("calculation_id", "revision_number", name="uq_calculation_project_file_revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_id: Mapped[int] = mapped_column(ForeignKey("calculations.id", ondelete="CASCADE"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    analysis_status: Mapped[str] = mapped_column(String(24), default="pending")
    analysis_error: Mapped[str | None] = mapped_column(Text)
    printer_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    plates: Mapped[list["CalculationProjectPlate"]] = relationship(cascade="all, delete-orphan", lazy="selectin", order_by="CalculationProjectPlate.plate_index")


class CalculationProjectPlate(Base):
    __tablename__ = "calculation_project_plates"
    __table_args__ = (
        UniqueConstraint("project_file_id", "plate_index", name="uq_calculation_project_plate_index"),
        UniqueConstraint("project_file_id", "stable_key", name="uq_calculation_project_plate_key"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    project_file_id: Mapped[int] = mapped_column(ForeignKey("calculation_project_files.id", ondelete="CASCADE"), index=True)
    plate_index: Mapped[int] = mapped_column(Integer)
    stable_key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    object_count: Mapped[int] = mapped_column(Integer, default=0)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    detected_materials: Mapped[list] = mapped_column(JSON, default=list)
    detected_grams: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    detected_hours: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    geometry: Mapped[dict] = mapped_column(JSON, default=dict)


class CalculationVariantPlate(Base):
    __tablename__ = "calculation_variant_plates"
    __table_args__ = (
        UniqueConstraint("variant_id", "project_plate_id", name="uq_calculation_variant_plate"),
        CheckConstraint("good_parts >= 0 AND parts_per_print > 0 AND scrap_prints >= 0", name="ck_calculation_variant_plate_counts"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("calculation_variants.id", ondelete="CASCADE"), index=True)
    project_plate_id: Mapped[int] = mapped_column(ForeignKey("calculation_project_plates.id", ondelete="RESTRICT"), index=True)
    good_parts: Mapped[int] = mapped_column(Integer, default=1)
    parts_per_print: Mapped[int] = mapped_column(Integer, default=1)
    scrap_prints: Mapped[int] = mapped_column(Integer, default=0)
    material_code: Mapped[str | None] = mapped_column(String(120))
    grams_per_print: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    hours_per_print: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CalculationVariantSmallPart(Base):
    __tablename__ = "calculation_variant_small_parts"
    __table_args__ = (UniqueConstraint("variant_id", "small_part_id", name="uq_calculation_variant_small_part"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("calculation_variants.id", ondelete="CASCADE"), index=True)
    small_part_id: Mapped[int] = mapped_column(ForeignKey("small_parts.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    description_snapshot: Mapped[str] = mapped_column(String(255))
    unit_code_snapshot: Mapped[str] = mapped_column(String(16))
    unit_cost_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
```

- [ ] **Step 4: Register models and strict read/write schemas**

Define separate `CalculationVariantPlateInput/Read` and `CalculationVariantSmallPartInput/Read`; inputs use IDs and Decimal strings, reads include plate/article snapshots. Extend `CalculationVariantInput` with `plates=[]` and `small_parts=[]` while retaining legacy `lines` and `operations` for migration compatibility.

- [ ] **Step 5: Run tests and commit**

Run the focused schema test and expect PASS.

```powershell
git add backend/app/models/calculation_project.py backend/app/schemas/calculation_project.py backend/app/models/calculation.py backend/app/models/__init__.py backend/app/core/database.py backend/tests/conftest.py backend/tests/integration/test_calculation_project_schema.py
git commit -m "feat(calculations): add project-file plate model"
```

---

### Task 2: Analyze Real 3MF Plates, Geometry, and Thumbnails

**Files:**
- Create: `backend/app/services/calculation_project.py`
- Create: `backend/app/services/calculation_estimator.py`
- Create: `backend/tests/fixtures/calculations/multi_plate.3mf`
- Create: `backend/tests/fixtures/calculations/no_thumbnail.3mf`
- Create: `backend/tests/unit/test_calculation_project_analysis.py`
- Create: `backend/tests/unit/test_calculation_estimator.py`

**Interfaces:**
- Produces `analyze_project_file(path: Path) -> ProjectFileAnalysis`.
- Produces `estimate_plate(geometry: PlateGeometry, settings: EstimatorSettings, material_type: str) -> EstimateResult`.
- Reuses `count_plates_in_3mf`, `extract_filament_usage_from_3mf`, `extract_print_time_from_3mf`, `ThreeMFParser`, and existing plate PNG naming.

- [ ] **Step 1: Add deterministic fixtures and failing analysis assertions**

Assert the multi-plate fixture returns four 1-based plates, stable keys, names, per-plate object counts, materials, hours, grams, and PNG bytes where embedded. Assert missing thumbnail produces `thumbnail_bytes=None` without losing the plate.

- [ ] **Step 2: Port and test the ForgeDesk estimator math**

```python
@dataclass(frozen=True)
class BoundsMm:
    width: Decimal
    depth: Decimal
    height: Decimal


@dataclass(frozen=True)
class PlateGeometry:
    object_count: int
    triangle_count: int
    volume_cm3: Decimal
    bounds_mm: BoundsMm


@dataclass(frozen=True)
class EstimatorSettings:
    density_g_cm3: Decimal | None
    infill_percent: Decimal
    layer_height_mm: Decimal
    nozzle_mm: Decimal
    speed_mm_s: Decimal
    wall_lines: int


@dataclass(frozen=True)
class EstimateResult:
    material_grams: Decimal | None
    print_hours: Decimal | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PlateAnalysis:
    plate_index: int
    stable_key: str
    name: str
    geometry: PlateGeometry
    detected_materials: tuple[dict[str, object], ...]
    detected_grams: Decimal | None
    detected_hours: Decimal | None
    thumbnail_bytes: bytes | None


@dataclass(frozen=True)
class ProjectFileAnalysis:
    printer_metadata: dict[str, object]
    plates: tuple[PlateAnalysis, ...]


def estimate_plate(geometry: PlateGeometry, settings: EstimatorSettings, material_type: str) -> EstimateResult:
    if geometry.volume_cm3 <= 0:
        return EstimateResult(None, None, ("Model volume unavailable",))
    density = settings.density_g_cm3 or DENSITY_BY_MATERIAL.get(normalize_material(material_type), Decimal("1.24"))
    infill = clamp(settings.infill_percent / Decimal("100"), Decimal("0"), Decimal("1"))
    solid_share = min(Decimal("0.92"), Decimal("0.18") + Decimal(settings.wall_lines) * Decimal("0.055"))
    effective_cm3 = geometry.volume_cm3 * clamp(solid_share + (Decimal("1") - solid_share) * infill, Decimal("0.18"), Decimal("1"))
    grams = (effective_cm3 * density * Decimal("1.06")).quantize(Decimal("0.1"))
    flow = settings.nozzle_mm * Decimal("1.12") * settings.layer_height_mm * settings.speed_mm_s * Decimal("0.58")
    seconds = effective_cm3 * Decimal("1000") / flow + estimate_travel_seconds(geometry.bounds_mm, settings.layer_height_mm)
    return EstimateResult(grams, (seconds / Decimal("3600")).quantize(Decimal("0.01")), ("Geometry estimate",))
```

- [ ] **Step 3: Implement safe ZIP/XML analysis**

Reject path traversal entries, cap individual metadata files at 24 MB, parse `.model`, `Metadata/slice_info.config`, `Metadata/plate_N.json`, and `Metadata/plate_N.png`, and compute signed tetrahedron volume per mesh object from model vertices/triangles. Resolve each plate's model-instance object IDs from `slice_info.config`, then aggregate only those object volumes/bounds for that plate. Hash plate index, normalized object IDs, and name for `stable_key`; never trust a client-supplied plate count.

- [ ] **Step 4: Run analyzer/estimator tests and commit**

```powershell
python -m pytest backend/tests/unit/test_calculation_project_analysis.py backend/tests/unit/test_calculation_estimator.py -q
git add backend/app/services/calculation_project.py backend/app/services/calculation_estimator.py backend/tests/fixtures/calculations backend/tests/unit/test_calculation_project_analysis.py backend/tests/unit/test_calculation_estimator.py
git commit -m "feat(calculations): analyze 3mf project plates"
```

---

### Task 3: Add Revisioned Upload, Plate, and Thumbnail APIs

**Files:**
- Create: `backend/app/api/routes/calculation_projects.py`
- Modify: `backend/app/api/routes/calculations.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_calculation_project_files_api.py`

**Interfaces:**
- `POST /calculations/{id}/project-files` uploads and analyzes a 3MF, returning HTTP 201.
- `GET /calculations/{id}/project-files` lists revisions and plates.
- `GET /calculations/project-files/{file_id}/plates/{plate_id}/thumbnail` streams a safe PNG.
- Replaces the unbound `/calculations/source-files` behavior; keep that endpoint temporarily as a deprecation wrapper for legacy clients.

- [ ] **Step 1: Write failing upload and replacement tests**

Cover 3MF-only validation, stored SHA-256, revision increments, four plate records, thumbnail response, old-revision retention, stable-key remapping, and an ambiguous replacement response containing `unmatched_variant_plate_ids`.

- [ ] **Step 2: Run the focused API test and verify 404 responses**

Run `python -m pytest backend/tests/integration/test_calculation_project_files_api.py -q`.

- [ ] **Step 3: Implement storage and revision matching**

Store under `base_dir/calculations/<calculation_id>/sources/<sha256>.3mf` and thumbnails under `.../thumbnails/<file_id>-<plate_index>.png`. Use `safe_join_under` for reads and atomic temp-file replacement. Upload creates a new database revision; it never overwrites the prior file row. Rebind variant selections only on exact stable-key match and return unmatched IDs for user review.

- [ ] **Step 4: Implement routes and permissions**

Use `CALCULATIONS_UPDATE` for upload and `CALCULATIONS_READ` for list/thumbnail. Ensure the calculation owns the requested file; do not expose arbitrary paths. Return structured errors `{code, message}` for invalid archive, missing plate, and analysis failure.

- [ ] **Step 5: Run API tests and commit**

```powershell
git add backend/app/api/routes/calculation_projects.py backend/app/api/routes/calculations.py backend/app/main.py backend/tests/integration/test_calculation_project_files_api.py
git commit -m "feat(api): add calculation project files"
```

---

### Task 4: Reuse Sidecars for Per-Plate Background Slicing and Cache Results

**Files:**
- Create: `backend/app/models/calculation_slice.py`
- Create: `backend/app/services/calculation_slicing.py`
- Modify: `backend/app/services/slice_dispatch.py`
- Modify: `backend/app/api/routes/slice_jobs.py`
- Modify: `backend/app/api/routes/calculation_projects.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py`
- Create: `backend/tests/integration/test_calculation_slicing_api.py`

**Interfaces:**
- Produces `CalculationSliceResult` uniquely keyed by file SHA, plate, printer/process/material preset fingerprints, and profile revisions.
- Adds dispatcher kind `calculation_plate` and owner-aware polling metadata.
- `POST /calculations/project-files/{file_id}/slice` accepts `plate_ids`, printer/process/filament `PresetRef`s, and returns one job ID.

- [ ] **Step 1: Write failing success, cache, and fallback tests**

Mock `SlicerApiService.slice_with_profiles` to return exact grams/hours, then assert a repeated request hits the persisted cache. Mock unavailable/5xx and assert geometry estimates persist with `source="estimate"`, `fallback_reason`, and warnings. Mock a 4xx model rejection and verify it remains a failed slicer result unless geometry is valid and fallback is explicitly enabled in calculation settings.

- [ ] **Step 2: Run tests and verify the endpoint is absent**

Run `python -m pytest backend/tests/integration/test_calculation_slicing_api.py -q`.

- [ ] **Step 3: Implement cache and result model**

```python
class CalculationSliceResult(Base):
    __tablename__ = "calculation_slice_results"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_calculation_slice_cache_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_plate_id: Mapped[int] = mapped_column(ForeignKey("calculation_project_plates.id", ondelete="CASCADE"), index=True)
    cache_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    source: Mapped[str] = mapped_column(String(16))
    print_hours: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    material_grams: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    profile_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

`cache_key()` hashes canonical JSON containing `file_sha256`, `plate_index`, all preset `{source,id,revision}` values, and estimator settings revision.

- [ ] **Step 4: Implement the background runner with existing services**

Resolve profiles through `resolve_preset_ref`, call `SlicerApiService.slice_with_profiles(..., plate=plate.plate_index, export_3mf=False)`, and surface progress through `slice_dispatch.set_progress`. On success persist `source="slicer"`; on allowed fallback call `estimate_plate`. Never report `completed` until all requested plates have terminal persisted results.

- [ ] **Step 5: Run tests and commit**

```powershell
git add backend/app/models/calculation_slice.py backend/app/services/calculation_slicing.py backend/app/services/slice_dispatch.py backend/app/api/routes/slice_jobs.py backend/app/api/routes/calculation_projects.py backend/app/models/__init__.py backend/app/core/database.py backend/tests/integration/test_calculation_slicing_api.py
git commit -m "feat(calculations): slice project plates with sidecars"
```

---

### Task 5: Map Structured Requirements Through Calculation and Approval

**Files:**
- Modify: `backend/app/schemas/calculation.py`
- Modify: `backend/app/services/calculation.py`
- Modify: `backend/app/services/calculation_engine.py`
- Modify: `backend/app/api/routes/calculations.py`
- Modify: `backend/tests/unit/test_calculation_engine.py`
- Modify: `backend/tests/integration/test_calculations_api.py`

**Interfaces:**
- Produces `derive_variant_inputs(variant, defaults) -> tuple[list[VariantCostInputs], Decimal]`.
- Produces `derive_offer_positions(variant) -> list[dict]` with project file/plate traceability.
- Produces `GET /calculations/effective-defaults` returning `{key: {value, source}}`.

- [ ] **Step 1: Add failing multi-plate calculation and revision tests**

Use two selected plates, different parts-per-print, one manual grams override, one slicer hours value, two small parts, and commercial defaults. Assert required runs, material, labor, additive cost, selling price, derived positions, and snapshot provenance are identical between preview and approval.

- [ ] **Step 2: Run engine/API tests and verify structured requirements are ignored**

Run `python -m pytest backend/tests/unit/test_calculation_engine.py backend/tests/integration/test_calculations_api.py -q`.

- [ ] **Step 3: Implement canonical effective values and provenance priority**

```python
SOURCE_PRIORITY = ("manual", "slicer", "3mf", "estimate", "setting")


def effective_value(*, manual, sliced, embedded, estimated, default):
    for source, value in zip(SOURCE_PRIORITY, (manual, sliced, embedded, estimated, default), strict=True):
        if value is not None:
            return {"value": Decimal(str(value)), "source": source}
    raise ValueError("effective value has no source")
```

Return every requested field, including zero, as an actual value. Keys include setup hours, post-processing hours/unit, CAD hours, QA hours, filament EUR/kg, material markup, scrap, hourly rate, consumables, packaging, shipping, discount, dryer/printer defaults, plate preview columns/size, and estimator inputs.

- [ ] **Step 4: Derive operations and customer positions**

Create one operation per selected plate and one customer position per selected plate. The position description uses plate name; quantity is requested good parts; its provenance stores `project_file_id`, `project_file_revision`, `project_plate_id`, and `stable_key`. Preserve legacy `lines/operations` only when the variant has no structured plate rows.

- [ ] **Step 5: Include small-part costs and immutable snapshots**

Sum `quantity * unit_cost_snapshot` into `additive_materials`. Approval snapshots include the exact article ID, SKU/name/unit/cost snapshot, selected plates, effective values, and derived positions so later catalog or setting changes cannot rewrite history.

- [ ] **Step 6: Run tests and commit**

```powershell
git add backend/app/schemas/calculation.py backend/app/services/calculation.py backend/app/services/calculation_engine.py backend/app/api/routes/calculations.py backend/tests/unit/test_calculation_engine.py backend/tests/integration/test_calculations_api.py
git commit -m "feat(calculations): price structured plate requirements"
```

---

### Task 6: Add Typed Frontend State, Formatting, and Project File Components

**Files:**
- Modify: `frontend/src/api/calculations.ts`
- Create: `frontend/src/utils/calculationFormatting.ts`
- Create: `frontend/src/components/orders/calculation/VariantStrip.tsx`
- Create: `frontend/src/components/orders/calculation/ProjectFileSection.tsx`
- Create: `frontend/src/components/orders/calculation/PlateDetailEditor.tsx`
- Create: `frontend/src/components/orders/calculation/ProvenanceBadge.tsx`
- Create: `frontend/src/__tests__/components/CalculationProjectFile.test.tsx`
- Create: `frontend/src/__tests__/utils/calculationFormatting.test.ts`

**Interfaces:**
- Adds `CalculationProjectFile`, `CalculationProjectPlate`, `CalculationVariantPlate`, `CalculationVariantSmallPart`, `EffectiveValue`, and calculation slice-job contracts.
- `VariantStrip` accepts independent `activeIndex` and `preferredIndex` callbacks.
- `ProjectFileSection` supports drag/drop, file picker, multi-select cards, focused plate, and polling.

- [ ] **Step 1: Write failing formatting and interaction tests**

```ts
expect(formatCount(10, 'de-DE')).toBe('10');
expect(formatGrams(10, 'de-DE')).toBe('10');
expect(formatGrams(10.25, 'de-DE')).toBe('10,3');
expect(formatHours(4.5, 'de-DE')).toBe('4,5');
expect(formatMoney(4.5, 'de-DE', 'EUR')).toBe('4,50 €');
```

Component tests assert clicking a variant changes active only, clicking its star changes preferred only, Ctrl/Meta and checkboxes support plate multi-selection, focus changes detail without deselecting, and dropped files use the same upload path as the file input.

- [ ] **Step 2: Run focused tests and verify missing exports**

Run both new Vitest files.

- [ ] **Step 3: Implement locale formatting helpers**

Add `export interface EffectiveValue { value: string; source: 'manual' | 'slicer' | '3mf' | 'estimate' | 'setting' | 'migration' }` to `frontend/src/api/calculations.ts`. Use `Intl.NumberFormat`; never call `toFixed()` for user-visible values. Inputs retain API strings and use `NumberField` on blur, preserving raw edit state while focused.

- [ ] **Step 4: Implement variant and project-file components**

`ProjectFileSection` renders printer, dryer, and drying-duration selection above upload and plate cards. Plate cards use a checkbox for selection and a separate button surface for detail focus. Render embedded thumbnail URL when present; otherwise render plate number, name, object count, and an accessible “Keine Vorschau” fallback. Poll `/slice-jobs/{id}` until completed/failed, then invalidate project-file and preview queries.

- [ ] **Step 5: Implement provenance/reset controls**

`ProvenanceBadge` maps `manual/slicer/3mf/estimate/setting/migration` to localized text and non-color icon/text. `PlateDetailEditor` writes manual overrides and exposes reset per field by removing the override key, never copying the detected value into a new manual value.

- [ ] **Step 6: Run tests and commit**

```powershell
git add frontend/src/api/calculations.ts frontend/src/utils/calculationFormatting.ts frontend/src/components/orders/calculation/VariantStrip.tsx frontend/src/components/orders/calculation/ProjectFileSection.tsx frontend/src/components/orders/calculation/PlateDetailEditor.tsx frontend/src/components/orders/calculation/ProvenanceBadge.tsx frontend/src/__tests__/components/CalculationProjectFile.test.tsx frontend/src/__tests__/utils/calculationFormatting.test.ts
git commit -m "feat(ui): add calculation project-file controls"
```

---

### Task 7: Recompose the Calculation Workspace and Settings

**Files:**
- Create: `frontend/src/components/orders/calculation/SmallPartsEditor.tsx`
- Create: `frontend/src/components/orders/calculation/EffectiveValuesEditor.tsx`
- Create: `frontend/src/components/orders/calculation/CalculationSummary.tsx`
- Modify: `frontend/src/components/orders/CalculationWorkspace.tsx`
- Modify: `frontend/src/components/orders/calculation/CalculationSettings.tsx`
- Remove: `frontend/src/components/orders/calculation/MaterialsEditor.tsx`
- Modify: `frontend/src/__tests__/components/CalculationWorkspace.test.tsx`
- Modify: `frontend/src/__tests__/components/CalculationSettingsLayout.test.tsx`
- Modify: `frontend/src/i18n/locales/de.ts`
- Modify: `frontend/src/i18n/locales/en.ts`

**Interfaces:**
- Desktop layout: continuous left form plus sticky right `CalculationSummary`; mobile stacks summary after form.
- Section order: Request, Variants, Project file, Small parts, Labor & post-processing, Costs & prices.
- `SmallPartsEditor` consumes `SmallPartCombobox` and stores structured small-part requirements.

- [ ] **Step 1: Replace current workspace expectations with the approved layout**

Tests assert no manual “Position hinzufügen”, no spool-backed Kleinteile selector, section numbering 3–6, sticky summary, visible no-reservation note, independent active/preferred variant, selected plate details, complete effective values, correct decimal display, and keyboard operation. The per-plate labels are exactly Plattenname, erkannte Druckteile, Material, Druckteile je Druck, Ausschussdrucke, g/Druck, and h/Druck.

- [ ] **Step 2: Run focused tests and verify current UI fails**

Run `npm.cmd run test -- --run src/__tests__/components/CalculationWorkspace.test.tsx src/__tests__/components/CalculationSettingsLayout.test.tsx`.

- [ ] **Step 3: Implement `SmallPartsEditor`**

Each row stores `small_part_id`, quantity, description/unit/cost snapshots, current available quantity, and remove action. Selection from `SmallPartCombobox` fills snapshots; quantity changes never change catalog data. Show sufficient/short/unknown using icon plus text.

- [ ] **Step 4: Implement complete visible effective values**

Render all twelve approved financial/labor fields with actual effective values and provenance. Setup/CAD/QA allocate per request, post-processing per unit. Reset removes only that calculation override. Add plate preview columns/size and estimator defaults to `CalculationSettings` with conservative ranges matching estimator validation.

- [ ] **Step 5: Recompose `CalculationWorkspace`**

Split server loading into TanStack queries, keep draft state in a reducer, delete the manual lines section, and replace per-operation production cards with `ProjectFileSection` plus `PlateDetailEditor`. The right summary keeps existing CostBreakdown/PriceDecision data and adds slice status and the exact text “Prüfung ohne Reservierung”.

- [ ] **Step 6: Run tests, i18n parity, and commit**

```powershell
git add frontend/src/components/orders/calculation/SmallPartsEditor.tsx frontend/src/components/orders/calculation/EffectiveValuesEditor.tsx frontend/src/components/orders/calculation/CalculationSummary.tsx frontend/src/components/orders/CalculationWorkspace.tsx frontend/src/components/orders/calculation/CalculationSettings.tsx frontend/src/components/orders/calculation/MaterialsEditor.tsx frontend/src/__tests__/components/CalculationWorkspace.test.tsx frontend/src/__tests__/components/CalculationSettingsLayout.test.tsx frontend/src/i18n/locales/de.ts frontend/src/i18n/locales/en.ts
git commit -m "feat(calculations): rebuild project-file workspace"
```

---

### Task 8: Migrate Legacy Calculations and Verify the Deliverable

**Files:**
- Modify: `backend/app/core/database.py`
- Create: `backend/tests/integration/test_calculation_project_migration.py`
- Modify: `docs/order-management.md`
- Modify: `docs/superpowers/plans/2026-07-18-calculation-project-files-slicer.md`

**Interfaces:**
- Produces idempotent `_migrate_calculation_project_files(conn)`.
- Leaves all prior `CalculationRevision.snapshot` JSON untouched.

- [ ] **Step 1: Write a failing migration test with legacy source operations**

Seed a pre-upgrade calculation with two operations referencing the same `source_file`; run migration twice; assert one project-file row, two plate rows/selections, provenance `migration`, retained manual values, and unchanged revision JSON.

- [ ] **Step 2: Implement idempotent backfill**

Group legacy operations by calculation and normalized source path, hash files that still exist, analyze them, and map `source_plate`. When the file is absent or mapping is ambiguous, create no fabricated plate; preserve the operation and add a calculation-level migration warning returned by the detail API.

- [ ] **Step 3: Run backend verification**

```powershell
python -m pytest backend/tests/unit/test_calculation_project_analysis.py backend/tests/unit/test_calculation_estimator.py backend/tests/integration/test_calculation_project_schema.py backend/tests/integration/test_calculation_project_files_api.py backend/tests/integration/test_calculation_slicing_api.py backend/tests/unit/test_calculation_engine.py backend/tests/integration/test_calculations_api.py backend/tests/integration/test_calculation_project_migration.py -q
python -m ruff check backend/app/models/calculation_project.py backend/app/models/calculation_slice.py backend/app/services/calculation_project.py backend/app/services/calculation_estimator.py backend/app/services/calculation_slicing.py backend/app/api/routes/calculation_projects.py
```

Expected: all selected tests pass and Ruff reports no errors.

- [ ] **Step 4: Run frontend verification**

```powershell
Set-Location frontend
npm.cmd run test -- --run src/__tests__/components/CalculationProjectFile.test.tsx src/__tests__/components/CalculationWorkspace.test.tsx src/__tests__/components/CalculationSettingsLayout.test.tsx src/__tests__/utils/calculationFormatting.test.ts
npm.cmd run check:i18n
npm.cmd run build
```

Expected: all tests, parity, and build pass.

- [ ] **Step 5: Browser smoke test with a real multi-plate 3MF**

Verify drag/drop and file picker, plate thumbnails/fallbacks, multi-selection, focused detail editing, sidecar progress, explicit estimate fallback, source reset, small-part keyboard search, active/preferred variant separation, sticky summary, responsive stacking, and persisted reload.

- [ ] **Step 6: Commit migration and documentation**

```powershell
git add backend/app/core/database.py backend/tests/integration/test_calculation_project_migration.py docs/order-management.md docs/superpowers/plans/2026-07-18-calculation-project-files-slicer.md
git commit -m "feat(calculations): migrate project-file calculations"
```
