# Document Format and PDF Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Einen vollständigen Bereich „Einstellungen → Auftragsverwaltung → Format & Vorschau“ liefern, der versionierte semantische Dokumentlayouts automatisch speichert, echte serverseitig erzeugte PDF-Seiten darstellt und fachlich vollständige, nachprüfbare PDF/A-3u-, ZUGFeRD- und XRechnungs-Ausgaben aus unveränderlichen Dokument-Snapshots erzeugt.

**Architecture:** Ein eigener Layout-Aggregate liegt neben der bestehenden fachlichen Dokumentkonfiguration. Ein Resolver bildet System-, Profil-, Dokumentart- und Sprachebene auf ein typisiertes effektives Layout ab. Vorschau und endgültige Ausgabe durchlaufen dieselbe Pipeline aus Snapshot, semantischem View Model, internen Jinja-Templates, WeasyPrint, pikepdf und veraPDF. Das React-Frontend verwendet den zentralen 500-ms-Autosave-Mechanismus, zeigt links das vom Server erzeugte PDF über PDF.js und rechts einen kompakten gegliederten Editor.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic 2, SQLite/PostgreSQL, WeasyPrint 69.0, pikepdf 10.10.0, fonttools 4.63.0, veraPDF Greenfield 1.30.2, React 19, TypeScript 5.9, TanStack Query 5, pdfjs-dist 6.1.200, Vitest, pytest und Playwright 1.61.1.

## Global Constraints

- Die freigegebene Spezifikation in `docs/superpowers/specs/2026-07-23-document-format-preview-design.md` ist verbindlich; dieser Plan darf ihren Funktionsumfang nicht verkleinern.
- Format und Vorschau bleiben ein eigener Menüpunkt direkt nach „Dokumente“; die fachliche Dokumentkonfiguration wird nicht mit Darstellungswerten vermischt.
- Der Client sendet ausschließlich IDs, Versionen, typisierte Patches und Vorschaumodus. HTML, CSS, JavaScript, URLs, beliebige Pfade und vollständige Snapshotobjekte werden an keiner öffentlichen API akzeptiert.
- Alle endgültigen kaufmännischen PDFs sind PDF/A-3u. ZUGFeRD bettet ausschließlich das bereits validierte CII-D22B-Artefakt ein; XRechnung bleibt das eigenständige Original-XML.
- Vorschau und endgültige Ausgabe verwenden denselben Serverrenderer. Eine Browser-Nachbildung des Dokuments ist nicht zulässig.
- Layouts, Assets, Snapshots, endgültige PDFs und Prüfberichte sind nach Freigabe beziehungsweise Verwendung append-only.
- Rendering bleibt vollständig offline. Ein fehlender veraPDF-Runtime erlaubt eine deutlich als ungeprüft markierte Vorschau, blockiert aber Freigabe, Ausstellung und Export.
- Die vorhandene zentrale Verzögerung von 500 ms, Abbruchlogik, Sequenzierung und Statusanzeige des Settings-Autosaves werden in einen gemeinsam verwendeten Hook extrahiert; es entsteht keine zweite Autosave-Implementierung.
- Erst die vom Server bestätigte `lock_version` darf eine Vorschau anstoßen. Abgebrochene oder ältere Antworten dürfen keinen neueren Zustand überschreiben.
- Jede Aufgabe beginnt mit einem fehlschlagenden Test, enthält eine enge Verifikation und endet mit einem kleinen Commit. Tests dürfen keine Internetverbindung benötigen.
- Befehle werden aus `C:\Users\droth\Documents\GitHub\PrintOps\.worktrees\document-management-einvoice` ausgeführt.

---

## File Map

### Neu anzulegende Backend-Dateien

- `backend/app/models/document_layout.py` – Layoutversionen, typisierte 1:1-Bereiche, Assetreferenzen, Publikation, Previewjobs und Renderbelege.
- `backend/app/schemas/document_layout.py` – API-Verträge, Patches, effektive Werte, Befunde, Vorschau- und Exportantworten.
- `backend/app/services/document_layout_catalog.py` – unterstützte Vorlagen, Formate, Dokumentarten, Optionen und stabile Renderer-/Validatorversionen.
- `backend/app/services/document_layout_defaults.py` – typisierte Systemdefaults und drei vollständig definierte Vorlagen.
- `backend/app/services/document_layouts.py` – Lifecycle, optimistisches Locking, Vererbung, Autosave-Audit und Readiness.
- `backend/app/services/document_layout_assets.py` – inhaltsadressierte Ablage und Preflight für Logos, Briefpapier-PDFs und TTF/OTF.
- `backend/app/services/document_layout_samples.py` – deterministische deutsche und englische Beispieldokumente aller Dokumentarten.
- `backend/app/services/document_view_model.py` – Snapshot/Entwurf in ein escaptes semantisches Render-View-Model überführen.
- `backend/app/services/document_renderer.py` – Orchestrierung, Limits, Cache, Vorschau und endgültige Ausgabe.
- `backend/app/services/document_preview_jobs.py` – persistente, ablaufende Previewjob-Zustände und Restart-Recovery.
- `backend/app/services/pdfa.py` – PDF/A-3u-Metadaten, Output Intent, Letterhead-Merge und ZUGFeRD-Anhang.
- `backend/app/services/verapdf.py` – lokale CLI-Erkennung, begrenzter Prozessaufruf und strukturierter Prüfbericht.
- `backend/app/api/routes/document_layouts.py` – interne Editor-, Preview-, Lifecycle- und Asset-Endpunkte.
- `backend/app/api/routes/document_render.py` – stabile externe Render-/Export-API auf Basis veröffentlichter IDs.
- `backend/app/templates/documents/base.html` – gemeinsamer semantischer Dokumentrahmen.
- `backend/app/templates/documents/classic.html` – klassische Vorlage.
- `backend/app/templates/documents/modern.html` – moderne Vorlage.
- `backend/app/templates/documents/compact.html` – kompakte Vorlage.
- `backend/app/templates/documents/print.css` – feste Seiten-, Umbruch-, Tabellen- und PDF/A-taugliche Druckregeln.
- `backend/app/resources/pdf/sRGB.icc` – geprüfter sRGB-Output-Intent mit dokumentierter Herkunft und Hash.
- `backend/app/resources/pdf/runtime-manifest.json` – Pins, URLs, Signaturfingerprint und SHA-256 der PDF-Runtimes.
- `scripts/vendor_pdf_runtime.py` – reproduzierbares Herunterladen, Signatur-/Hashprüfung und CLI-only-Staging von veraPDF.
- `backend/tests/unit/services/test_document_layout_catalog.py`
- `backend/tests/unit/services/test_document_layouts.py`
- `backend/tests/unit/services/test_document_layout_assets.py`
- `backend/tests/unit/services/test_document_view_model.py`
- `backend/tests/unit/services/test_document_renderer.py`
- `backend/tests/unit/services/test_document_preview_jobs.py`
- `backend/tests/unit/services/test_pdfa.py`
- `backend/tests/unit/services/test_verapdf.py`
- `backend/tests/integration/test_document_layout_schema.py`
- `backend/tests/integration/test_document_layout_api.py`
- `backend/tests/integration/test_document_render_api.py`
- `backend/tests/integration/test_document_pdf_conformance.py`
- `backend/tests/integration/test_document_layout_backup_restore.py`
- `backend/tests/fixtures/document_layouts/` – erwartete effektive Layouts und Beispieldokumente.

### Neu anzulegende Frontend-Dateien

- `frontend/src/hooks/useAutosaveDraft.ts` – eine zentrale debouncte, abbrechbare, sequenzierte Autosave-Implementierung.
- `frontend/src/api/documentLayouts.ts` – typisierte Layout-, Asset-, Preview- und Export-API.
- `frontend/src/components/settings/document-layout/DocumentLayoutSettings.tsx` – Seitencontainer und Datenfluss.
- `frontend/src/components/settings/document-layout/LayoutContextBar.tsx` – Profil, Dokumentart, Sprache, Version und Quelle.
- `frontend/src/components/settings/document-layout/PdfPreviewPane.tsx` – PDF.js-Seiten, Zoom, Navigation und Status.
- `frontend/src/components/settings/document-layout/LayoutControlPanel.tsx` – sticky Accordion und Abschnittsstatus.
- `frontend/src/components/settings/document-layout/controls/PageControls.tsx`
- `frontend/src/components/settings/document-layout/controls/HeaderControls.tsx`
- `frontend/src/components/settings/document-layout/controls/TypographyControls.tsx`
- `frontend/src/components/settings/document-layout/controls/PositionControls.tsx`
- `frontend/src/components/settings/document-layout/controls/TotalsControls.tsx`
- `frontend/src/components/settings/document-layout/controls/FooterControls.tsx`
- `frontend/src/components/settings/document-layout/controls/AssetControls.tsx`
- `frontend/src/components/settings/document-layout/LayoutLifecycleBar.tsx` – Autosave, Readiness, Freigabe, Terminierung, Rücknahme und Klonen.
- `frontend/src/components/settings/document-layout/LayoutFindings.tsx` – gruppierte Blocker/Warnungen mit Feldnavigation.
- `frontend/src/__tests__/hooks/useAutosaveDraft.test.tsx`
- `frontend/src/__tests__/components/settings/document-layout/DocumentLayoutSettings.test.tsx`
- `frontend/src/__tests__/components/settings/document-layout/PdfPreviewPane.test.tsx`
- `frontend/src/__tests__/components/settings/document-layout/LayoutControlPanel.test.tsx`
- `frontend/src/__tests__/pages/DocumentLayoutSettingsFlow.test.tsx`
- `frontend/e2e/document-layout.spec.ts`
- `frontend/playwright.config.ts`

### Zu ändernde Dateien

- `requirements.txt`, `frontend/package.json`, `frontend/package-lock.json` – exakt gepinnte Renderer-, PDF.js- und Playwright-Abhängigkeiten.
- `Dockerfile`, `Dockerfile.test` – native WeasyPrint-Bibliotheken, Java Runtime und veraPDF CLI.
- `install/install.sh` – native PDF-Runtime für manuelle Linux-Installationen.
- `installers/windows/build.py`, `installers/windows/README.md` – Pango/GTK-Runtime und veraPDF/JRE im Windows-Staging.
- `backend/app/core/config.py`, `backend/app/core/database.py`, `backend/app/core/permissions.py` – Datenpfade, Tabellenregistrierung/Migration und Rechte.
- `backend/app/main.py` – beide neuen Router registrieren.
- `backend/app/models/commercial_document.py` – endgültigen PDF-Beleg mit Layout-/Validatorprovenienz ergänzen.
- `backend/app/services/document_snapshot.py`, `backend/app/services/document_readiness.py` – Layoutauflösung und PDF-Readiness in die Ausstellung integrieren.
- `backend/app/services/einvoice/artifacts.py`, `backend/app/services/einvoice/zugferd.py` – validiertes CII-Artefakt unverändert an PDF/A anbinden.
- `backend/app/api/routes/commercial_documents.py`, `backend/app/api/routes/einvoices.py` – Ausstellung und Export um PDF-Artefakte erweitern.
- `backend/app/services/local_backup.py`, `backend/app/services/github_backup.py`, `backend/app/api/routes/settings.py` – Layoutdaten, Assets, PDFs und Prüfberichte sichern/wiederherstellen.
- `frontend/src/pages/SettingsPage.tsx`, `frontend/src/lib/settingsNavigation.ts` – neuer Subtab direkt nach Dokumente und gemeinsamer Autosave-Hook.
- `frontend/src/api/documentManagement.ts` – PDF-/E-Rechnungsartefakte in die Dokumentansichten aufnehmen.
- `frontend/src/i18n/locales/{de,en,es,fr,it,ja,ko,pt-BR,tr,zh-CN,zh-TW}.ts` – vollständige, paritätsgeprüfte Texte.
- Bestehende Dokument-, Backup-, Permission-, Navigation- und Settings-Tests – neue Regeln als Regression absichern.

---

## Task Interfaces and Invariants

Die folgenden Schnittstellen werden früh festgelegt und in späteren Aufgaben nicht still verändert:

```python
class LayoutScope(BaseModel):
    business_profile_id: int
    document_type: DocumentType | None = None
    language: str | None = None

class LayoutPatchCommand(BaseModel):
    lock_version: int = Field(ge=1)
    edit_session_id: UUID
    patch: dict[str, PagePatch | TypographyPatch | HeaderPatch | PositionPatch | TotalsPatch | FooterPatch]

class RenderRequest(BaseModel):
    layout_id: int
    layout_lock_version: int
    source_kind: Literal["sample", "document"]
    source_id: str | int
    mode: Literal["preview", "final"]
```

`LayoutPatchCommand.patch` wird vor Serviceaufruf aus einer discriminated union validiert und anschließend in einen expliziten Feldpfad-Patch überführt; das öffentliche Schema ist niemals ein freies JSON-/CSS-Speicherformat.

```python
@dataclass(frozen=True)
class RenderInput:
    canonical_document_json: str
    document_sha256: str
    effective_layout: EffectiveDocumentLayout
    asset_receipts: tuple[AssetReceipt, ...]
    renderer_version: str

@dataclass(frozen=True)
class RenderedPdf:
    content: bytes
    sha256: str
    page_count: int
    pdfa_report: PdfaValidationReport
    embedded_xml_sha256: str | None
```

Der Cache-Key lautet `sha256(document_sha256 + layout_effective_sha256 + renderer_version + validator_version + mode)`. Zeitstempel, IDs und Zufallswerte werden vor dem Rendern aus dem visuellen View Model entfernt oder auf Snapshotwerte fixiert.

```ts
export interface AutosaveAdapter<TDraft, TConfirmation> {
  save(signal: AbortSignal, draft: TDraft, sequence: number): Promise<TConfirmation>;
  confirmedVersion(value: TConfirmation): number;
}

export type AutosaveState =
  | { status: 'idle' | 'saved'; confirmedVersion: number | null }
  | { status: 'saving'; sequence: number; confirmedVersion: number | null }
  | { status: 'error'; error: Error; confirmedVersion: number | null };
```

Nur `status === 'saved'` und eine gegenüber der letzten Vorschau neue `confirmedVersion` lösen `POST /api/document-layouts/preview` aus.

---

### Task 1: Renderer-Abhängigkeiten und reproduzierbare Runtime bereitstellen

**Files:**
- Modify: `requirements.txt`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `backend/app/resources/pdf/runtime-manifest.json`
- Create: `scripts/vendor_pdf_runtime.py`
- Modify: `Dockerfile`
- Modify: `Dockerfile.test`
- Modify: `install/install.sh`
- Modify: `installers/windows/build.py`
- Modify: `installers/windows/README.md`
- Create: `backend/tests/unit/services/test_pdf_runtime.py`

- [ ] Einen fehlschlagenden Runtime-Test schreiben, der `weasyprint.__version__ == "69.0"`, `pikepdf.__version__ == "10.10.0"`, `fontTools.__version__ == "4.63.0"`, den manifestierten veraPDF-Pin `1.30.2`, die feste GPG-Fingerprint-Zeichenfolge `13DD102B4DD69354D12DE5A83184863278B17FE7` und das Vorhandensein eines sRGB-Profils prüft.
- [ ] Den Test isoliert ausführen: `pytest backend/tests/unit/services/test_pdf_runtime.py -q`; erwartetes Ergebnis: FAIL wegen fehlender Module beziehungsweise Manifestdatei.
- [ ] `requirements.txt` um `weasyprint==69.0`, `pikepdf==10.10.0`, `fonttools==4.63.0` und `jinja2==3.1.6` ergänzen; `pdfjs-dist` mit `npm install --save-exact pdfjs-dist@6.1.200` und den E2E-Runner mit `npm install --save-dev --save-exact @playwright/test@1.61.1` installieren und Lockfile übernehmen.
- [ ] `runtime-manifest.json` mit Version, offizieller `https://software.verapdf.org/rel/1.30/verapdf-greenfield-1.30.2-installer.zip`-Quelle, Signaturquelle, Fingerprint, installierter CLI-Pfad, Lizenzdateien und dem beim geprüften Download ermittelten SHA-256 anlegen.
- [ ] `scripts/vendor_pdf_runtime.py` implementieren: Download nur von der fest codierten HTTPS-Quelle, GPG-Signatur gegen den fest codierten Fingerprint prüfen, SHA-256 gegen das Manifest prüfen, CLI-only unattended installieren und exakt `verapdf --version` gegen `1.30.2` testen. Ein Hash- oder Signaturfehler beendet das Skript ohne Staging.
- [ ] `Dockerfile` und `Dockerfile.test` um `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz-subset0`, `libjpeg62-turbo`, `libopenjp2-7`, `default-jre-headless` sowie das verifizierte veraPDF-CLI-Staging ergänzen; keine Runtime wird beim Containerstart heruntergeladen.
- [ ] `install/install.sh` um dieselben distributionsgerecht benannten nativen Bibliotheken, Java und den Aufruf des verifizierenden Vendor-Skripts ergänzen; nicht unterstützte Distributionen brechen mit einer konkreten Installationsanweisung ab.
- [ ] `installers/windows/build.py` um feste Pango/GTK- und veraPDF/JRE-Stagingfunktionen mit Hashprüfung ergänzen; README dokumentiert Herkunft, Lizenzen, Upgradeablauf und Offline-Smoketest.
- [ ] Die Runtime- und Build-Smoketests ausführen: `pytest backend/tests/unit/services/test_pdf_runtime.py -q` und `npm --prefix frontend run build`; erwartet: PASS und ein erfolgreicher TypeScript/Vite-Build.
- [ ] Commit erstellen: `git add requirements.txt frontend/package.json frontend/package-lock.json Dockerfile Dockerfile.test install/install.sh installers/windows backend/app/resources/pdf scripts/vendor_pdf_runtime.py backend/tests/unit/services/test_pdf_runtime.py && git commit -m "build(documents): pin PDF rendering runtime"`.

### Task 2: Rechte, Datenpfade und relationales Layoutmodell anlegen

**Files:**
- Create: `backend/app/models/document_layout.py`
- Modify: `backend/app/models/commercial_document.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/database.py`
- Modify: `backend/app/core/permissions.py`
- Modify: `backend/tests/unit/test_permissions.py`
- Modify: `backend/tests/unit/test_order_management_permissions.py`
- Create: `backend/tests/integration/test_document_layout_schema.py`

- [ ] Zuerst Schema- und Permission-Tests schreiben: neue Rechte sind in Admin/Manager-Zuordnung enthalten; `language` ohne `document_type` wird per Check Constraint abgewiesen; pro Scope/Version existiert nur eine Layoutversion; aktive/verwendete Layouts, Assets und Renderbelege verweigern Update/Delete.
- [ ] Tests ausführen: `pytest backend/tests/integration/test_document_layout_schema.py backend/tests/unit/test_permissions.py backend/tests/unit/test_order_management_permissions.py -q`; erwartet: FAIL wegen fehlender Modelle/Rechte.
- [ ] In `Permission` ergänzen:

```python
DOCUMENT_LAYOUTS_READ = "document_layouts:read"
DOCUMENT_LAYOUTS_MANAGE = "document_layouts:manage"
```

und sie den Kategorien sowie den bestehenden administrativen/auftragsbezogenen Rollen fachlich passend zuweisen, ohne Leserechte automatisch zu Schreibrechten zu erweitern.
- [ ] `config.py` um `document_layout_asset_dir` und `document_render_artifact_dir` unter `resolve_data_dir()` ergänzen; beide Verzeichnisse werden bei Start mit restriktiven Rechten erzeugt und niemals als StaticFiles gemountet.
- [ ] `document_layout.py` implementieren mit `DocumentLayoutConfiguration`, neun typisierten 1:1-Tabellen (`LayoutPageRules`, `LayoutTypographyRules`, `LayoutHeaderRules`, `LayoutTitleRules`, `LayoutPositionRules`, `LayoutTotalsRules`, `LayoutTechnicalRules`, `LayoutNotesRules`, `LayoutFooterRules`), `DocumentLayoutAsset`, `DocumentLayoutAssetLink`, `DocumentLayoutPublication`, `DocumentLayoutAuditReceipt` und `DocumentPreviewJob`.
- [ ] Für `DocumentLayoutConfiguration` `business_profile_id`, optionale Dokumentart/Sprache, Version, `template_key`, `page_format`, `orientation`, die Zustände `draft|scheduled|active|superseded|withdrawn`, `(business_profile_id, document_type, language, version)`-Eindeutigkeit mit nullsicherem `scope_key`, `lock_version`, `effective_from`, Actor-/Zeit-, Renderer-/Prüffelder und die Regel `language IS NULL OR document_type IS NOT NULL` abbilden. Profilstandard ist `(document_type=None, language=None)`.
- [ ] Assets inhaltsadressiert und unveränderlich modellieren: Typ `logo|letterhead_first|letterhead_following|font`, MIME, Größe, SHA-256, relativer Storage-Key, Preflightstatus/-bericht, PDF-Seitenmaße beziehungsweise Font-Metadaten, Ersteller/Zeitpunkt; Assetlinks referenzieren eine konkrete Asset-ID und Rolle.
- [ ] Previewjobs mit zufälliger öffentlicher UUID, Actor/Profile/Layout/Lock-Version/Source-Referenz, Cache-Key, Status `queued|running|ready|failed|expired`, Ergebnis-Storage-Key/-SHA, Befund, Erstell-/Ablaufzeit und ohne Dokumentinhalt modellieren. Jobs sind nach Ablauf nur noch auditierbar, ihr Cacheartefakt wird entfernt.
- [ ] `DocumentArtifact` um `layout_configuration_id`, `layout_version`, `layout_effective_sha256`, `asset_receipts`, `renderer_version`, `validator_version` und `render_receipt` erweitern. `kind="pdf"` nutzt weiterhin die bestehende Eindeutigkeit `(document_id, kind)`; ZUGFeRD-XML bleibt ein separates bestehendes Artefakt.
- [ ] SQLAlchemy-Events so registrieren, dass freigegebene Layouts und verwendete Assets sowie `DocumentArtifact`/Prüfbelege unveränderlich sind; Draft-Untertabellen dürfen ausschließlich über den Lifecycle-Service verändert werden.
- [ ] Modelle in `init_db()` importieren und idempotente SQLite/PostgreSQL-Startup-Migrationen für neue Tabellen/Spalten/Indizes sowie Rechte-Backfill ergänzen. Fresh install und Upgrade werden getrennt getestet.
- [ ] Tests erneut ausführen; erwartet: alle genannten Tests PASS.
- [ ] Commit erstellen: `git add backend/app/models backend/app/core backend/tests/unit/test_permissions.py backend/tests/unit/test_order_management_permissions.py backend/tests/integration/test_document_layout_schema.py && git commit -m "feat(documents): add relational layout model"`.

### Task 3: Typisierte Layoutverträge, Katalog und vollständige Defaults definieren

**Files:**
- Create: `backend/app/schemas/document_layout.py`
- Create: `backend/app/services/document_layout_catalog.py`
- Create: `backend/app/services/document_layout_defaults.py`
- Create: `backend/tests/unit/services/test_document_layout_catalog.py`
- Create: `backend/tests/fixtures/document_layouts/effective-classic-a4.json`
- Create: `backend/tests/fixtures/document_layouts/effective-modern-letter.json`

- [ ] Katalogtests schreiben, die drei Vorlagen (`classic`, `modern`, `compact`), A4/Letter nur Hochformat, 4–30-mm-Ränder, 7–16-pt-Basisschrift, Hex-Akzentfarbe, alle vorhandenen `DocumentType`-Werte, `de`/`en` und jeden konfigurierbaren Abschnitt vollständig abdecken.
- [ ] Tests ausführen: `pytest backend/tests/unit/services/test_document_layout_catalog.py -q`; erwartet: FAIL wegen fehlender Katalogmodule.
- [ ] Pydantic-Schemas als explizite Modelle implementieren. Beispiel für die öffentliche Seitenkonfiguration:

```python
class PageRulesDraft(BaseModel):
    template_key: Literal["classic", "modern", "compact"] = "classic"
    page_format: Literal["A4", "Letter"] = "A4"
    orientation: Literal["portrait"] = "portrait"
    margin_top_mm: Decimal = Field(default=Decimal("18"), ge=4, le=30)
    margin_right_mm: Decimal = Field(default=Decimal("18"), ge=4, le=30)
    margin_bottom_mm: Decimal = Field(default=Decimal("18"), ge=4, le=30)
    margin_left_mm: Decimal = Field(default=Decimal("18"), ge=4, le=30)
```

- [ ] Für alle neun Abschnitte eigene `Draft`, `Patch`, `Effective` und `SourcedValue`-Modelle anlegen; Patchmodelle nutzen `model_fields_set`, damit „nicht gesetzt“ und „Override entfernen“ (`null`) unterscheidbar bleiben. Zusätzliche Felder sind mit `extra="forbid"` verboten.
- [ ] Lifecycle-, Asset-, Preview-, Report-, Audit- und External-Render-Schemas ergänzen. `PreviewRequest` akzeptiert genau Layout-ID/Lock-Version, `sample|document`, Source-ID und optional Zoom/Seitenlimit, aber keine Dokumentinhalte.
- [ ] `document_layout_catalog.py` liefert zulässige Optionen, Seitenmaße in mm, Renderer `weasyprint-69.0+pikepdf-10.10.0`, Validator `verapdf-1.30.2`, Templateversionen und Beschreibungen als unveränderliche Werte.
- [ ] `document_layout_defaults.py` definiert jeden Wert für Systemstandard und die drei Vorlagen. Unterschiede betreffen nur typisierte Werte wie Abstände, Akzent, Tabellenraster, Headerposition und Footeraufteilung; kein CSS wird gespeichert.
- [ ] Fixture-Serialisierung prüfen: `EffectiveDocumentLayout.model_validate_json(...)` muss beide Fixtures ohne Default-Nachfüllung laden; ein Test entfernt je einen Abschnitt und erwartet Validierungsfehler.
- [ ] Tests erneut ausführen; erwartet: PASS.
- [ ] Commit erstellen: `git add backend/app/schemas/document_layout.py backend/app/services/document_layout_catalog.py backend/app/services/document_layout_defaults.py backend/tests/unit/services/test_document_layout_catalog.py backend/tests/fixtures/document_layouts && git commit -m "feat(documents): define typed layout contracts"`.

### Task 4: Lifecycle, Vererbung, Autosave-Audit und Readiness implementieren

**Files:**
- Create: `backend/app/services/document_layouts.py`
- Modify: `backend/app/services/document_audit.py`
- Create: `backend/tests/unit/services/test_document_layouts.py`
- Create: `backend/tests/integration/test_document_layout_service.py`

- [ ] Tests für die komplette Zustandsmaschine schreiben: Draft anlegen, Patch mit optimistischem Lock, Konflikt 409, Klonen mit Pflichtgrund, sofortige/terminierte Freigabe, Aktivierung fälliger Versionen, Supersede, Rücknahme und Verbot von Änderungen an veröffentlichten Versionen.
- [ ] Vererbungstests für exakt `system → profile → document_type → language` schreiben. Ein auf `null` gesetzter Patchwert entfernt den Override; Herkunft und Quell-ID jedes effektiven Feldes müssen nachvollziehbar sein. Sprache ohne Dokumentart und mehr als ein wirksamer Profilstandard sind Blocker.
- [ ] Audittests schreiben: mehrere Autosaves derselben `edit_session_id` werden zu einem stabilen Bearbeitungsbeleg mit erstem/letztem Zeitpunkt, Actor und sortierten geänderten Feldpfaden zusammengeführt; fachliche Gründe sind nur bei Neuerstellung/Klonen/Freigabe/Rücknahme Pflicht.
- [ ] Tests ausführen: `pytest backend/tests/unit/services/test_document_layouts.py backend/tests/integration/test_document_layout_service.py -q`; erwartet: FAIL wegen fehlendem Service.
- [ ] `create_draft`, `clone_version`, `patch_draft`, `resolve_effective`, `check_readiness`, `publish`, `activate_due_versions` und `withdraw` mit Transaktionen, `SELECT ... FOR UPDATE` beziehungsweise atomarem `UPDATE ... WHERE lock_version = :expected` implementieren.
- [ ] Patches ausschließlich über eine feste Feldpfad-Map anwenden, zum Beispiel:

```python
PATCH_TARGETS = {
    "page.template_key": (DocumentLayoutConfiguration, "template_key"),
    "page.page_format": (DocumentLayoutConfiguration, "page_format"),
    "page.margin_top_mm": (LayoutPageRules, "margin_top_mm"),
    "typography.body_font_asset_id": (LayoutTypographyRules, "body_font_asset_id"),
    "header.show_logo": (LayoutHeaderRules, "show_logo"),
    "positions.show_technical_data": (LayoutPositionRules, "show_technical_data"),
    "footer.show_page_numbers": (LayoutFooterRules, "show_page_numbers"),
}
```

Unbekannte, schreibgeschützte oder typfalsche Pfade liefern einen stabilen `LAYOUT_PATCH_INVALID`-Befund.
- [ ] Effektive Werte als `SourcedValue(value, source_scope, source_layout_id)` materialisieren und zusätzlich einen kanonischen, sortierten JSON-Hash `effective_sha256` erzeugen. Dieser Hash ist Teil jedes Preview- und Renderbelegs.
- [ ] Readiness-Befunde als `severity`, `code`, `field_path`, lokalisierbaren Message-Key, Korrekturhinweis und optionale externe Regel-ID ausgeben. Mindestens Wertebereiche, Profilstandard, Assets, Runtime, Briefpapierformat, Fontglyphen und E-Rechnungsanforderungen prüfen.
- [ ] Den bestehenden `append_audit`-Dienst um eine atomare `append_or_merge_edit_session`-Operation ergänzen; Vorschau mit echten Dokumenten, Asset-Löschversuche und fehlgeschlagene Integritätsprüfungen bleiben einzelne Events.
- [ ] Tests erneut ausführen; erwartet: PASS einschließlich deterministischer Herkunft und 409-Konflikt.
- [ ] Commit erstellen: `git add backend/app/services/document_layouts.py backend/app/services/document_audit.py backend/tests/unit/services/test_document_layouts.py backend/tests/integration/test_document_layout_service.py && git commit -m "feat(documents): implement layout lifecycle"`.

### Task 5: Sichere, versionierte Layoutassets und Preflight umsetzen

**Files:**
- Create: `backend/app/services/document_layout_assets.py`
- Modify: `backend/app/core/paths.py`
- Create: `backend/tests/unit/services/test_document_layout_assets.py`
- Create: `backend/tests/fixtures/document_layouts/letterhead-a4.pdf`
- Create: `backend/tests/fixtures/document_layouts/letterhead-letter.pdf`
- Create: `backend/tests/fixtures/document_layouts/active-content.pdf`
- Create: `backend/tests/fixtures/document_layouts/test-font.ttf`

- [ ] Tests schreiben für Magic-Byte-Erkennung statt Endung, maximale Größen, inhaltsadressierten Pfad, Deduplizierung innerhalb eines Profils, Cross-Profile-Verbot, Pfadtraversal, verschlüsselte/mehrseitige/aktive PDF-Dateien, falsches Seitenformat, beschädigte Fonts, fehlende Pflichtglyphen sowie Löschverbot bei Referenz.
- [ ] Tests ausführen: `pytest backend/tests/unit/services/test_document_layout_assets.py -q`; erwartet: FAIL wegen fehlendem Assetservice.
- [ ] Uploadlimits fest implementieren: Logo 5 MiB, einseitiges Briefpapier 20 MiB, Font 10 MiB. Akzeptierte Inhalte: PNG/JPEG/SVG nur für Logo nach sicherer SVG-Sanitization, PDF genau eine Seite für Briefpapier, TTF/OTF ohne variable/collection/executable Bestandteile für Fonts.
- [ ] Storage-Key ausschließlich aus Profil-ID, Assettyp und SHA-256 bilden:

```python
relative_key = Path("document-layout-assets") / str(profile_id) / asset_type / digest[:2] / digest
target = safe_join(resolve_data_dir(), relative_key)
```

Originalname bleibt nur Metadatum. Schreiben erfolgt atomar über temporäre Datei, `fsync`, Hash-Nachprüfung und Rename.
- [ ] PDF-Preflight mit pikepdf implementieren: keine Verschlüsselung, Aktionen, JavaScript, AcroForm, RichMedia, eingebetteten Dateien, Launch/URI-Aktionen oder externe Streams; exakt eine Seite; MediaBox/CropBox muss mit 1-mm-Toleranz zum Layoutformat passen.
- [ ] Font-Preflight mit fonttools implementieren: Familien-/Stilname, Gewicht, Embedding-Lizenzbit `fsType`, Glyphenabdeckung für Basic Latin, Latin-1 Supplement, Euro, deutsche Sonderzeichen und die im gewählten Beispieldokument tatsächlich verwendeten Codepoints. Nicht einbettbare Fonts sind Blocker.
- [ ] Logos dekodieren und neu serialisieren, Metadaten entfernen, Pixel-/Dimensionenlimit prüfen und SVG über eine feste Element-/Attribut-Allowlist in ein internes Rasterbild überführen.
- [ ] `store_asset`, `preflight_asset`, `link_asset`, `read_asset`, `delete_unreferenced_asset` implementieren; Statusfolge `uploaded → valid|invalid`, Prüfbericht und Asset-SHA sind unveränderlich.
- [ ] Tests erneut ausführen; erwartet: PASS, zusätzlich `pytest backend/tests/unit/services/test_document_layout_assets.py -q --basetemp .cache/pytest-assets` ohne außerhalb des Testpfads geschriebene Datei.
- [ ] Commit erstellen: `git add backend/app/services/document_layout_assets.py backend/app/core/paths.py backend/tests/unit/services/test_document_layout_assets.py backend/tests/fixtures/document_layouts && git commit -m "feat(documents): add secure layout assets"`.

### Task 6: Deterministische Beispieldokumente und semantisches View Model bauen

**Files:**
- Create: `backend/app/services/document_layout_samples.py`
- Create: `backend/app/services/document_view_model.py`
- Modify: `backend/app/services/document_snapshot.py`
- Create: `backend/tests/unit/services/test_document_view_model.py`
- Create: `backend/tests/fixtures/document_layouts/sample-documents.json`

- [ ] Tests schreiben, die für jede in `DOCUMENT_CAPABILITIES` registrierte Dokumentart je ein deutsches und englisches Sample verlangen und lange Bezeichnungen, technische 3D-Druckdaten, mehrere Steuersätze, Rabatt, Skonto, Seitenumbruch, Bankdaten und Kleinunternehmerhinweis abdecken.
- [ ] Sicherheits- und Determinismustests ergänzen: `<script>`, HTML und Unicode-Sonderzeichen bleiben Text; gleicher Snapshot plus gleiches Layout erzeugt bytegleiches kanonisches View-Model-JSON; aktuelle Uhrzeit und Locale des Hosts verändern es nicht.
- [ ] Tests ausführen: `pytest backend/tests/unit/services/test_document_view_model.py -q`; erwartet: FAIL.
- [ ] `sample-documents.json` mit festen IDs, Datum `2026-07-23`, stabilen Nummern, Beträgen und Adressen erstellen. Samples enthalten keine produktiven Kundendaten und sind über stabile Schlüssel wie `quotation-de-standard` adressierbar.
- [ ] `document_layout_samples.py` lädt Fixtures über `importlib.resources`, validiert sie gegen die bestehenden `CommercialDocumentSnapshot`-Schemas und liefert Katalogmetadaten getrennt vom Inhalt.
- [ ] `document_view_model.py` definiert frozen Dataclasses/Pydantic-Modelle für Sender, Empfänger, Dokumentkopf, Positionen, technische Details, Steuern, Summen, Zahlung, Texte und Footer. Formatierung von Datum, Decimal, Währung und Einheiten erfolgt explizit für `de` und `en`.
- [ ] Das View Model ausschließlich aus einem unveränderlichen Snapshot oder einem serverseitig geladenen, leseberechtigten Draft erzeugen. Für Drafts wird zuerst der bestehende Snapshotbuilder im Previewmodus verwendet; der Client liefert keine Feldwerte.
- [ ] Templatewerte durch Jinja Autoescape plus explizite Plaintext-Normalisierung schützen. URLs, Dateipfade und HTML-Markup sind keine View-Model-Feldtypen.
- [ ] `render_context_sha256` aus kanonischem View Model, effektivem Layout und Assetreceipts berechnen und im Ergebnis zurückgeben.
- [ ] Tests erneut ausführen; erwartet: PASS für alle Dokumentarten/Sprachen und zweimal identischen SHA-256.
- [ ] Commit erstellen: `git add backend/app/services/document_layout_samples.py backend/app/services/document_view_model.py backend/app/services/document_snapshot.py backend/tests/unit/services/test_document_view_model.py backend/tests/fixtures/document_layouts/sample-documents.json && git commit -m "feat(documents): build semantic render model"`.

### Task 7: Interne Templates und robuste Seitenumbruchregeln erstellen

**Files:**
- Create: `backend/app/templates/documents/base.html`
- Create: `backend/app/templates/documents/classic.html`
- Create: `backend/app/templates/documents/modern.html`
- Create: `backend/app/templates/documents/compact.html`
- Create: `backend/app/templates/documents/print.css`
- Modify: `backend/app/services/document_layout_defaults.py`
- Create: `backend/tests/unit/services/test_document_templates.py`

- [ ] Template-Tests schreiben: jede Vorlage rendert jedes View Model, nutzt nur erlaubte Kontextschlüssel, enthält keine externen URLs/Inline-Skripte, wiederholt Tabellenköpfe, hält Summenblöcke zusammen, zeigt technische Daten konditional und gibt Seitenzahlen als `Seite x/y` beziehungsweise `Page x/y` aus.
- [ ] Tests ausführen: `pytest backend/tests/unit/services/test_document_templates.py -q`; erwartet: FAIL wegen fehlender Templates.
- [ ] `base.html` als semantische Struktur mit klaren Blocks für Briefkopf, Absenderzeile, Empfänger, Metadaten, Titel, Intro, Positionstabelle, Summen/Steuern/Zahlung, Abschluss, Hinweise und Footer implementieren. Jinja `StrictUndefined` und Autoescape sind zwingend.
- [ ] `classic`, `modern` und `compact` erweitern ausschließlich diese Blocks und verwenden CSS Custom Properties, die der Renderer aus validierten typisierten Werten generiert. Keine Vorlage liest Datenbankmodelle oder Dateien.
- [ ] `print.css` implementieren mit `@page` für A4/Letter, `thead { display: table-header-group; }`, `tfoot`, `break-inside: avoid` für Position, Summen und Hinweisblöcke, kontrolliertem Wortumbruch und Folgeseitenkopf/-footer.
- [ ] Regeln für Grenzfälle festlegen: Eine einzelne zu lange Position darf umbrechen, aber Bezeichnung und erster Datenabschnitt bleiben zusammen; Summenblock beginnt vollständig auf neuer Seite; Footer überlappt nie Inhalt; 10 Seiten sind erlaubt, über dem konfigurierten Hardlimit entsteht `RENDER_PAGE_LIMIT`.
- [ ] CSS-Werte ausschließlich durch eine Mappingfunktion erzeugen, beispielsweise `mm`/`pt`/validierte Hexfarbe; freie Strings aus Layout oder Dokument gelangen nicht in `<style>`.
- [ ] Snapshot-Tests der normalisierten HTML-Struktur für alle drei Templates hinzufügen, ohne erzeugte Binär-PDFs ins Git aufzunehmen.
- [ ] Tests erneut ausführen; erwartet: PASS.
- [ ] Commit erstellen: `git add backend/app/templates/documents backend/app/services/document_layout_defaults.py backend/tests/unit/services/test_document_templates.py && git commit -m "feat(documents): add semantic PDF templates"`.

### Task 8: Gemeinsame, begrenzte WeasyPrint-Renderpipeline implementieren

**Files:**
- Create: `backend/app/services/document_renderer.py`
- Modify: `backend/app/core/config.py`
- Create: `backend/tests/unit/services/test_document_renderer.py`
- Create: `backend/tests/integration/test_document_render_determinism.py`

- [ ] Tests für echten PDF-Output schreiben: `%PDF-`-Magic, erwartete Seitengröße A4/Letter, 1-/10-Seiten-Dokument, lange Position, keine Netzwerkzugriffe, kein Lesen willkürlicher `file:`-URLs, 2-s-Previewziel bei warmem Cache, Timeout, 12-Seiten-Hardlimit und deterministischer SHA-256.
- [ ] Tests ausführen: `pytest backend/tests/unit/services/test_document_renderer.py backend/tests/integration/test_document_render_determinism.py -q`; erwartet: FAIL.
- [ ] `DocumentRenderer` mit `render_preview(RenderRequest) -> RenderedPdf` und `render_final(RenderInput, einvoice_artifact=None) -> RenderedPdf` implementieren. Beide Methoden rufen denselben privaten Pipelinepfad auf; `mode` verändert nur Persistenz, Wasserzeichen und Validierungsblockade.
- [ ] Jinja-Environment über `PackageLoader`, `StrictUndefined`, Autoescape und eine feste Template-Key-Map konfigurieren. WeasyPrint `url_fetcher` verweigert `http`, `https`, `ftp`, allgemeine `file`- und `data`-URLs und bedient nur zuvor registrierte `asset://<sha256>`-Handles aus dem aktuellen RenderInput.
- [ ] Rendering in einem begrenzten Workerprozess mit 10-s-Timeout, 512-MiB-Arbeitsspeicherziel, 12-Seiten-/25-MiB-Ausgabelimit und korrelationsgebundener temporärer Arbeitsmappe ausführen. Nach Erfolg und Fehler wird die Mappe entfernt.
- [ ] Kanonische Metadaten setzen: Creation/ModificationDate aus Dokument-Snapshot, feste Producer-Version, normalisierte XMP-ID aus Renderhash. pikepdf speichert deterministisch ohne zufällige IDs; Tests frieren Zeit und vergleichen zwei SHA-256.
- [ ] Kurzlebigen Previewcache unter `document-render-cache/` implementieren: Schlüssel gemäß Interface, atomare Datei plus Metadaten, maximale Lebensdauer 30 Minuten, LRU-Größe 250 MiB, Berechtigungsprüfung erfolgt vor jedem Cache-Hit.
- [ ] Rendererfehler in stabile Codes übersetzen: `RENDER_INPUT_INVALID`, `RENDER_ASSET_UNAVAILABLE`, `RENDER_TIMEOUT`, `RENDER_MEMORY_LIMIT`, `RENDER_PAGE_LIMIT`, `RENDER_ENGINE_FAILED`; interne Pfade/Stacktraces erscheinen nur im Serverlog.
- [ ] Tests erneut ausführen; erwartet: PASS; Performance-Test markiert den kalten Lauf separat und verlangt beim warmen Sample `p95 <= 2.0s` auf dem CI-Referenzprofil.
- [ ] Commit erstellen: `git add backend/app/services/document_renderer.py backend/app/core/config.py backend/tests/unit/services/test_document_renderer.py backend/tests/integration/test_document_render_determinism.py && git commit -m "feat(documents): add unified PDF renderer"`.

### Task 9: Briefpapier, Fonts und PDF/A-3u-Nachbearbeitung implementieren

**Files:**
- Create: `backend/app/resources/pdf/sRGB.icc`
- Create: `backend/app/services/pdfa.py`
- Modify: `backend/app/services/document_renderer.py`
- Create: `backend/tests/unit/services/test_pdfa.py`
- Create: `backend/tests/integration/test_document_pdf_conformance.py`

- [ ] Tests schreiben für Output Intent, XMP `pdfaid:part=3`/`pdfaid:conformance=U`, eingebettete und Unicode-taugliche Fonts, ToUnicode-CMaps, Seitengröße, erste/folgende Briefpapierseite, leere Vordergrundfläche des Briefpapiers, Metadaten und erneute Hashbildung nach Merge.
- [ ] Tests ausführen: `pytest backend/tests/unit/services/test_pdfa.py backend/tests/integration/test_document_pdf_conformance.py -q`; erwartet: FAIL wegen fehlender PDF/A-Nachbearbeitung.
- [ ] Das sRGB-ICC-Profil aus einer lizenzkompatiblen offiziellen Distribution übernehmen, Herkunft/Lizenz/SHA im Runtime-Manifest dokumentieren und im Test gegen den festen Hash prüfen.
- [ ] `prepare_pdfa3u` implementieren: PDF-Version, XMP, Dokumentinfo, Output Intent, Unicode-Sprachangabe, MarkInfo/ViewerPreferences und eindeutige AF-Beziehungen setzen, ohne die sichtbare Seite neu zu rasterisieren.
- [ ] Letterhead-Merge mit pikepdf implementieren: erste Layoutseite nutzt `letterhead_first`, Folgeseiten `letterhead_following` oder denselben Fallback; Briefpapier bleibt Hintergrund, der Renderinhalt Vordergrund. MediaBox/CropBox/Rotation müssen vor Merge identisch sein.
- [ ] Eigene Fonts über WeasyPrint `FontConfiguration` und lokale `asset://`-Auflösung registrieren; nach Rendern prüft pikepdf, dass jede verwendete Schrift eingebettet ist und Unicode-Mapping besitzt. Fehlende Glyphen oder Substitution sind Blocker, keine stille Fallbackentscheidung.
- [ ] PDF/A-Metadaten nach jedem Merge/Anhangsschritt erneut anwenden und den endgültigen SHA ausschließlich aus den finalen Bytes berechnen.
- [ ] Einen internen Strukturprüfer ergänzen, der vor veraPDF offensichtliche Fehler als konkrete Befunde meldet; er ersetzt veraPDF nicht.
- [ ] Tests erneut ausführen; erwartet: lokale Struktur- und Integrationstests PASS. Der Test prüft hier die vorbereitete PDF/A-Struktur mit dem internen Prüfer; die unabhängige veraPDF-Konformitätsbehauptung wird erst in Task 10 hinzugefügt.
- [ ] Commit erstellen: `git add backend/app/resources/pdf backend/app/services/pdfa.py backend/app/services/document_renderer.py backend/tests/unit/services/test_pdfa.py backend/tests/integration/test_document_pdf_conformance.py && git commit -m "feat(documents): produce PDF-A-3u documents"`.

### Task 10: veraPDF-Prüfung und Runtime-Readiness vollständig integrieren

**Files:**
- Create: `backend/app/services/verapdf.py`
- Modify: `backend/app/services/document_layouts.py`
- Modify: `backend/app/services/document_renderer.py`
- Modify: `backend/app/services/document_readiness.py`
- Create: `backend/tests/unit/services/test_verapdf.py`
- Modify: `backend/tests/integration/test_document_pdf_conformance.py`

- [ ] Tests schreiben für CLI-Erkennung, Versionsabweichung, Timeout, nicht parsebares Ergebnis, valides PDF/A-3u, absichtlich ungültige PDF-Datei und normalisierte veraPDF-Befunde mit stabilen Regel-IDs.
- [ ] Tests ausführen: `pytest backend/tests/unit/services/test_verapdf.py backend/tests/integration/test_document_pdf_conformance.py -q -m requires_verapdf`; erwartet: FAIL.
- [ ] `VeraPdfRunner` implementieren: CLI-Pfad ausschließlich aus Konfiguration/Runtime-Manifest, keine Shell, feste Argumentliste für PDF/A-3u und maschinenlesbares XML/JSON, 30-s-Timeout, begrenzte Ausgabe, temporäre Datei mit restriktiven Rechten.
- [ ] Ergebnis in `PdfaValidationReport` normalisieren:

```python
class PdfaValidationReport(BaseModel):
    compliant: bool
    profile: Literal["PDF/A-3U"]
    validator_version: str
    ruleset: str
    findings: list[LayoutFinding]
    raw_report_sha256: str
```

Der vollständige Rohbericht wird als unveränderliches Artefakt gespeichert; API-Antworten liefern nur den normalisierten Bericht und eine autorisierte Report-ID.
- [ ] Previewverhalten: Ist veraPDF nicht verfügbar, wird das PDF erzeugt und erhält `validation_status="unvalidated"` plus Warnung `PDF_VALIDATOR_UNAVAILABLE`. Readiness, Freigabe, endgültige Ausstellung und Export erhalten denselben Befund als Blocker.
- [ ] Nach jedem finalen PDF-Schritt veraPDF ausführen. Ein nicht konformes PDF wird nicht als `valid` gespeichert und nie als endgültiges Artefakt ausgeliefert.
- [ ] Health-/Readinessstatus um Renderer-, Pango-, ICC- und veraPDF-Versionen erweitern; sensible lokale Pfade bleiben aus der Antwort entfernt.
- [ ] Tests erneut ausführen; erwartet: alle Unit- und markierten Conformance-Tests PASS und der ungültige Fixturefall liefert mindestens eine externe veraPDF-Regel-ID.
- [ ] Commit erstellen: `git add backend/app/services/verapdf.py backend/app/services/document_layouts.py backend/app/services/document_renderer.py backend/app/services/document_readiness.py backend/tests/unit/services/test_verapdf.py backend/tests/integration/test_document_pdf_conformance.py && git commit -m "feat(documents): validate PDF-A with veraPDF"`.

### Task 11: ZUGFeRD korrekt einbetten und XRechnung eindeutig getrennt halten

**Files:**
- Modify: `backend/app/services/pdfa.py`
- Modify: `backend/app/services/einvoice/zugferd.py`
- Modify: `backend/app/services/einvoice/artifacts.py`
- Modify: `backend/app/services/document_renderer.py`
- Modify: `backend/app/models/commercial_document.py`
- Create: `backend/tests/integration/test_document_hybrid_pdf.py`
- Modify: `backend/tests/integration/test_einvoice_artifacts.py`
- Modify: `backend/tests/integration/test_einvoice_conformance.py`

- [ ] Tests schreiben, dass ausschließlich ein bereits `validation_status="valid"` gespeichertes CII-D22B-ZUGFeRD-Artefakt eingebettet werden kann, sein SHA-256 unverändert bleibt, Dateiname/AFRelationship/XMP-Profil korrekt sind und die finale PDF/A-Prüfung nach Einbettung erneut erfolgt.
- [ ] XRechnungstests schreiben: UBL/CII-XML bleibt das Originalartefakt, paralleles PDF trägt weder ZUGFeRD-XMP noch eingebettetes Rechnungs-XML, Exportmanifest benennt `legal_original="xml"` und `visual_copy="pdf"`.
- [ ] Tests ausführen: `pytest backend/tests/integration/test_document_hybrid_pdf.py backend/tests/integration/test_einvoice_artifacts.py backend/tests/integration/test_einvoice_conformance.py -q`; erwartet: FAIL.
- [ ] `attach_zugferd_xml` in `pdfa.py` mit pikepdf-Attachment-API implementieren: standardkonformer Dateiname `factur-x.xml`, MIME `text/xml`, AFRelationship `Alternative`, korrekte Factur-X/ZUGFeRD-XMP-Felder und UTC-Snapshotzeit. XML wird bytegenau aus dem bestehenden validierten Artifact gelesen.
- [ ] Vor und nach Einbettung SHA-256 des XML vergleichen; Abweichung erzeugt `ZUGFERD_XML_HASH_MISMATCH`, Audit und Abbruch. Dokument-/Profilzuordnung des XML muss zum Snapshot passen.
- [ ] `render_final` erhält eine discriminated E-Rechnungsreferenz: `zugferd_artifact_id` oder `xrechnung_artifact_id`, niemals rohe XML-Bytes. Nur ZUGFeRD führt zur Attachmentphase.
- [ ] Das PDF-Artefakt speichert XML-ID/-SHA/-Profil und PDF-A-Report im `render_receipt`. XRechnung speichert die Querverbindung im Exportmanifest, nicht als PDF-Anhang.
- [ ] Nach ZUGFeRD-Einbettung sowohl bestehenden XML-Validator als auch veraPDF erneut ausführen. Nur wenn beide Reports gültig sind, wird das PDF-Artefakt `valid`.
- [ ] Tests erneut ausführen; erwartet: PASS, inklusive negativer Hash-/Profil-/Dokumentzuordnungstests.
- [ ] Commit erstellen: `git add backend/app/services/pdfa.py backend/app/services/einvoice backend/app/services/document_renderer.py backend/app/models/commercial_document.py backend/tests/integration/test_document_hybrid_pdf.py backend/tests/integration/test_einvoice_artifacts.py backend/tests/integration/test_einvoice_conformance.py && git commit -m "feat(documents): embed validated ZUGFeRD XML"`.

### Task 12: Interne Layout-API und abgesicherte externe Render-/Export-API liefern

**Files:**
- Create: `backend/app/api/routes/document_layouts.py`
- Create: `backend/app/api/routes/document_render.py`
- Create: `backend/app/services/document_preview_jobs.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_document_layout_api.py`
- Create: `backend/tests/integration/test_document_render_api.py`
- Create: `backend/tests/unit/services/test_document_preview_jobs.py`
- Modify: `backend/tests/integration/test_ownership_permissions.py`

- [ ] API-Vertragstests für Katalog, effektives Layout, Liste/Detail, Draft/Clone/Patch, Readiness, Publish/Schedule/Withdraw, Audit, Assets, Samplekatalog, lesbare reale Drafts, Preview erstellen/Status/PDF/Report sowie endgültiges Rendern und Export schreiben.
- [ ] Permissiontests für User und API-Key ergänzen: `document_layouts:read`, `document_layouts:manage`, `commercial_documents:read`, `commercial_documents:export`, `order_audit:read`; Cross-Profile-Zugriffe, erratene IDs und direkte Cachepfade liefern 403/404 ohne Datenleck.
- [ ] Tests ausführen: `pytest backend/tests/integration/test_document_layout_api.py backend/tests/integration/test_document_render_api.py backend/tests/integration/test_ownership_permissions.py -q`; erwartet: FAIL.
- [ ] Internen Router unter `/api/document-layouts` implementieren. Preview-POST antwortet synchron mit `202` und Job-ID oder mit einem Cache-Hit `200`; Status und PDF-Download prüfen bei jedem Zugriff Benutzerrecht, Profilzugriff, Ablaufzeit und Source-ID.
- [ ] `document_preview_jobs.py` als DB-gestützten, begrenzten Jobservice implementieren: `enqueue`, atomar `queued→running→ready|failed`, `expire`, Cache-Hashprüfung und Startup-Recovery (`running` wird mit `PREVIEW_INTERRUPTED` beendet). Rendering läuft über den bestehenden begrenzten Worker; mehrere Prozesse koordinieren über atomare Statusupdates.
- [ ] Externen Router unter `/api/document-render` implementieren. Endgültiges Rendern akzeptiert nur `document_snapshot_id`, `published_layout_id` oder deterministisch aufzulösenden veröffentlichten Scope, optional validierte E-Rechnungsartifact-ID und eine Idempotency-ID. Draftlayouts und mutable Dokumente werden abgewiesen.
- [ ] Preview-Request streng halten:

```python
class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layout_id: int = Field(gt=0)
    layout_lock_version: int = Field(gt=0)
    source_kind: Literal["sample", "document"]
    source_id: str
```

Für `source_kind="document"` wird `source_id` serverseitig als positive ID validiert und mit `commercial_documents:read` geladen.
- [ ] Assetdownloads senden `Content-Disposition: attachment`, `nosniff`, restriktive CSP und nur die gespeicherte erkannte MIME-Art. Vorschau-PDFs erhalten `private, no-store`; unveränderliche finale Artefakte ETag aus SHA-256.
- [ ] Domainfehler einheitlich abbilden: 409 Lock/State, 422 typisierte Befunde, 424 fehlende Runtime/abhängiges Artefakt, 413 Größe/Seitenlimit, 504 Timeout. Korrelation-ID erscheint in Antwort und Audit.
- [ ] Router in `main.py` registrieren und OpenAPI-Test sicherstellen, dass kein Requestschema Felder `html`, `css`, `url`, `path`, `content` oder freies `snapshot` enthält.
- [ ] Tests erneut ausführen; erwartet: PASS.
- [ ] Commit erstellen: `git add backend/app/api/routes/document_layouts.py backend/app/api/routes/document_render.py backend/app/services/document_preview_jobs.py backend/app/main.py backend/tests/unit/services/test_document_preview_jobs.py backend/tests/integration/test_document_layout_api.py backend/tests/integration/test_document_render_api.py backend/tests/integration/test_ownership_permissions.py && git commit -m "feat(documents): expose layout render APIs"`.

### Task 13: Ausstellung, Artefaktdownload und Dokumentworkflow integrieren

**Files:**
- Modify: `backend/app/services/document_snapshot.py`
- Modify: `backend/app/services/document_readiness.py`
- Modify: `backend/app/api/routes/commercial_documents.py`
- Modify: `backend/app/api/routes/einvoices.py`
- Modify: `frontend/src/api/documentManagement.ts`
- Modify: `backend/tests/integration/test_document_issuance.py`
- Modify: `backend/tests/integration/test_document_workflow_e2e.py`
- Modify: `backend/tests/integration/test_commercial_documents_api.py`

- [ ] Workflowtests schreiben: Ausstellung löst das zum Ausstellungsdatum wirksame Layout auf, friert dessen ID/Version/effective-SHA/assets/Renderer/Validator ein, rendert genau einmal idempotent, speichert `kind="pdf"` und liefert es in der Artifactliste aus.
- [ ] Tests für fehlendes veröffentlichtes Profilstandardlayout, invalides Asset, fehlendes veraPDF, nicht konformes PDF, erneuten Issuance-Request und historischen Download nach späterem Layoutwechsel schreiben.
- [ ] Tests ausführen: `pytest backend/tests/integration/test_document_issuance.py backend/tests/integration/test_document_workflow_e2e.py backend/tests/integration/test_commercial_documents_api.py -q`; erwartet: FAIL.
- [ ] Readiness um `layout_resolution`, Assetpreflight, PDF-Runtime, PDF/A und dokumentartspezifische E-Rechnungsprüfung erweitern. Die bestehende Ausstellungstransaktion reserviert keine Nummer endgültig, bevor alle Vorbedingungen außer dem finalen Rendern erfüllt sind.
- [ ] Beim Issuance-Ablauf zuerst bestehenden kanonischen Snapshot persistieren, dann veröffentlichtes Layout für Profil/Dokumentart/Sprache/Ausstellungsdatum auflösen, final rendern/validieren, Artifact atomar speichern und Nummernreservierung konsumieren. Fehler nutzen den bestehenden Wiederanlauf-/Void-Mechanismus.
- [ ] `DocumentArtifact`-Storage für PDF in `document-render-artifacts/<document_id>/<sha256>.pdf` ergänzen; DB-Insert erfolgt erst nach atomarem Schreiben und Hashprüfung. Wiederholte Idempotency-ID liefert denselben Artifactbeleg.
- [ ] Dokument- und E-Rechnungsrouten um `GET /commercial-documents/{id}/artifacts`, `GET .../artifacts/{artifact_id}/download` und ein Exportmanifest ergänzen. XRechnung kennzeichnet XML als Original, ZUGFeRD kennzeichnet das Hybrid-PDF als Original.
- [ ] Frontend-API-Typen so erweitern, dass bestehende Dokumentansichten PDF, XML, Validierungsstatus, Originalrolle und SHA anzeigen können; noch keine Layouteditor-UI in dieser Aufgabe.
- [ ] Audit für Renderstart/-erfolg/-fehler, Export und Integritätsfehler ergänzen; erneuter Download prüft Datei-SHA vor Auslieferung und setzt bei Abweichung den Beleg nicht durch Update um, sondern schreibt ein neues Integrity-Audit und blockiert.
- [ ] Tests erneut ausführen; erwartet: PASS, inklusive Download eines historischen PDFs nach Aktivierung einer neuen Layoutversion.
- [ ] Commit erstellen: `git add backend/app/services/document_snapshot.py backend/app/services/document_readiness.py backend/app/api/routes/commercial_documents.py backend/app/api/routes/einvoices.py frontend/src/api/documentManagement.ts backend/tests/integration/test_document_issuance.py backend/tests/integration/test_document_workflow_e2e.py backend/tests/integration/test_commercial_documents_api.py && git commit -m "feat(documents): render immutable issued PDFs"`.

### Task 14: Backup, Restore und Erst-Migration vollständig erweitern

**Files:**
- Modify: `backend/app/services/local_backup.py`
- Modify: `backend/app/services/github_backup.py`
- Modify: `backend/app/api/routes/settings.py`
- Modify: `backend/app/core/database.py`
- Create: `backend/tests/integration/test_document_layout_backup_restore.py`
- Modify: `backend/tests/integration/test_document_backup_restore.py`
- Modify: `backend/tests/unit/test_local_backup.py`
- Modify: `backend/tests/unit/test_github_backup_schemas.py`

- [ ] Tests schreiben, dass lokale ZIP- und private Git-Backups Layouttabellen, Publikationen, Auditbelege, Assetbytes, finale PDFs, veraPDF-Rohberichte, Renderer-/Validatorreceipts und XML-Verknüpfungen enthalten. Öffentliche Repositories bleiben durch das bestehende Credential/Evidence-Gate blockiert.
- [ ] Restoretests schreiben für intakte Hashes, fehlendes Asset, manipuliertes PDF, manipulierten Report und alte Backups ohne Layouttabellen. Fehlerhafte Evidenz bleibt erhalten, wird aber über einen neuen Integrity-Beleg als ungültig markiert und nie ausgeliefert.
- [ ] Migrationstests schreiben: für jedes bestehende Unternehmensprofil entsteht genau ein `classic`/A4/portrait-Profildraft Version 1; es wird nicht automatisch veröffentlicht; erneuter Start dupliziert nichts; neue Profile erhalten denselben Draft über den Profil-Erstellungsservice.
- [ ] Tests ausführen: `pytest backend/tests/integration/test_document_layout_backup_restore.py backend/tests/integration/test_document_backup_restore.py backend/tests/unit/test_local_backup.py backend/tests/unit/test_github_backup_schemas.py -q`; erwartet: FAIL.
- [ ] `stage_document_evidence` um `document-layout-assets`, `document-render-artifacts` und `document-validation-reports` erweitern. Ein kanonisches `document-layout-manifest.json` listet relativen Pfad, Typ, Profil/Document-ID, SHA-256, Größe und referenzierende DB-ID.
- [ ] Restore verifiziert zunächst ZIP-Pfadgrenzen und anschließend jeden Manifesthash, bevor Dateien in den Datenbereich kopiert werden. Kopieren ist atomar; bestehende unterschiedliche Dateien werden nicht überschrieben.
- [ ] Git-Backup serialisiert neue relationale Tabellen deterministisch und legt binäre Assets/PDFs unter inhaltsadressierten Pfaden ab. Große Dateien werden nicht base64 in JSON eingebettet; Manifest und `.gitattributes` behandeln sie als binary.
- [ ] Idempotenten Seed `ensure_default_document_layout_drafts` in `database.py` nach Tabellenmigration und Business-Profile-Seed ausführen. Der Service erzeugt typisierte Childrows und ein Audit `layout_migrated_as_draft`, aber keine Publikation.
- [ ] Backup-/Restore-Berichte um Anzahl und Integritätsstatus der Layoutartefakte ergänzen; Geheimnisse und absolute Pfade bleiben ausgeschlossen.
- [ ] Tests erneut ausführen; erwartet: PASS für aktuelles, altes und manipuliertes Backup.
- [ ] Commit erstellen: `git add backend/app/services/local_backup.py backend/app/services/github_backup.py backend/app/api/routes/settings.py backend/app/core/database.py backend/tests/integration/test_document_layout_backup_restore.py backend/tests/integration/test_document_backup_restore.py backend/tests/unit/test_local_backup.py backend/tests/unit/test_github_backup_schemas.py && git commit -m "feat(documents): back up layout evidence"`.

### Task 15: Bestehenden Settings-Autosave in einen gemeinsamen Hook extrahieren

**Files:**
- Create: `frontend/src/hooks/useAutosaveDraft.ts`
- Create: `frontend/src/__tests__/hooks/useAutosaveDraft.test.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

- [ ] Mit Fake Timers fehlschlagende Hooktests schreiben: exakt 500 ms Debounce, letzte Änderung gewinnt, laufende ältere Anfrage wird per `AbortController` abgebrochen, Sequenzen verhindern stale completion, identischer bestätigter Draft speichert nicht erneut, Fehler ist retrybar und Unmount räumt Timer/Request auf.
- [ ] Regressionstest für die vorhandene SettingsPage ergänzen: bisherige allgemeine Einstellungen speichern weiterhin nach 500 ms, zeigen Speichern/Gespeichert/Fehler und verlieren keine Eingabe während einer laufenden Anfrage.
- [ ] Tests ausführen: `npm --prefix frontend test -- --run src/__tests__/hooks/useAutosaveDraft.test.tsx src/__tests__/pages/SettingsPage.test.tsx`; erwartet: FAIL wegen fehlendem Hook.
- [ ] `useAutosaveDraft` mit einer stabilen Adapter-Schnittstelle implementieren:

```ts
export function useAutosaveDraft<TDraft, TConfirmation>({
  draft,
  enabled,
  debounceMs = 500,
  fingerprint,
  adapter,
  onConfirmed,
}: UseAutosaveDraftOptions<TDraft, TConfirmation>): AutosaveController {
  // Timer, AbortController, monotone sequence and confirmed fingerprint
}
```

Der Hook besitzt intern genau einen Timer und einen aktiven Controller; nur die höchste Sequenz darf `onConfirmed` oder Status `saved/error` setzen.
- [ ] Den Block um `saveTimeoutRef`, `isSavingRef` und den 500-ms-Effect in `SettingsPage.tsx` auf den Hook umstellen. Die bestehende fachliche Feldselektion/Mutation bleibt erhalten und wird als Adapter übergeben; Initialload und Query-Refresh werden über `enabled`/Fingerprint behandelt.
- [ ] Hookstatus an die vorhandene Settings-Statusanzeige anbinden, sodass es keine zweite UX oder parallele Implementierung gibt.
- [ ] Tests erneut ausführen; erwartet: PASS. Zusätzlich `npm --prefix frontend run lint`; erwartet: keine neuen Hook-Dependency- oder TypeScript-Fehler.
- [ ] Commit erstellen: `git add frontend/src/hooks/useAutosaveDraft.ts frontend/src/__tests__/hooks/useAutosaveDraft.test.tsx frontend/src/pages/SettingsPage.tsx frontend/src/__tests__/pages/SettingsPage.test.tsx && git commit -m "refactor(settings): centralize draft autosave"`.

### Task 16: Frontend-API, Navigation und vollständige Übersetzungen ergänzen

**Files:**
- Create: `frontend/src/api/documentLayouts.ts`
- Modify: `frontend/src/lib/settingsNavigation.ts`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/__tests__/lib/settingsNavigation.test.ts`
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`
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

- [ ] Navigationstests schreiben: `format-preview` ist ein gültiger `OrderManagementSubTab`, steht exakt zwischen `documents` und `calculation`, ist über `?tab=orders-calculation&sub=format-preview` direkt adressierbar und besitzt Search-Registry-Einträge.
- [ ] API-Typ- und MSW-Tests schreiben für Katalog, Layoutdetail, typisierten Patch mit `edit_session_id`, Assets per `FormData`, Preview-Job-Polling, PDF-Blob, Readiness, Lifecycle und External-Export. Fehlende Berechtigung wird als erklärter Read-only-Zustand typisiert.
- [ ] Tests ausführen: `npm --prefix frontend test -- --run src/__tests__/lib/settingsNavigation.test.ts src/__tests__/pages/SettingsPage.test.tsx`; erwartet: FAIL.
- [ ] In `settingsNavigation.ts` den Typ auf `'business-profile' | 'documents' | 'format-preview' | 'calculation'` erweitern und Parser/Serializer ergänzen. In `SettingsPage.tsx` Metadaten, Menüfolge, Search-Registry und Renderzweig direkt nach Dokumente einfügen.
- [ ] `documentLayouts.ts` ohne `any` implementieren. Alle Fetches verwenden vorhandenen API-Client/Authpfad; PDF-Downloads werden als Blob behandelt, Preview-Polling akzeptiert AbortSignal und ETag, 409 liefert eine eigene `LayoutVersionConflictError`.
- [ ] Deutsche und englische Texte redaktionell vollständig ausformulieren: Titel, Beschreibung, alle Bereiche/Felder/Hilfen, Herkunft, Status, Blocker, Assetpreflight, PDF/A, ZUGFeRD/XRechnung, Lifecycle und mobile Aktionen. Die übrigen neun Locale-Dateien erhalten vollständige Schlüssel mit dem vorhandenen englischen Fallbacktext, bis fachlich übersetzt wird.
- [ ] I18n-Parität prüfen: `npm --prefix frontend run check:i18n`; erwartet: PASS ohne fehlende oder zusätzliche Keys.
- [ ] Navigation/Build erneut prüfen: `npm --prefix frontend test -- --run src/__tests__/lib/settingsNavigation.test.ts src/__tests__/pages/SettingsPage.test.tsx && npm --prefix frontend run build`; erwartet: PASS.
- [ ] Commit erstellen: `git add frontend/src/api/documentLayouts.ts frontend/src/lib/settingsNavigation.ts frontend/src/pages/SettingsPage.tsx frontend/src/__tests__/lib/settingsNavigation.test.ts frontend/src/__tests__/pages/SettingsPage.test.tsx frontend/src/i18n/locales && git commit -m "feat(settings): add format preview navigation"`.

### Task 17: Echte PDF.js-Vorschau links implementieren

**Files:**
- Create: `frontend/src/components/settings/document-layout/PdfPreviewPane.tsx`
- Create: `frontend/src/components/settings/document-layout/LayoutContextBar.tsx`
- Create: `frontend/src/__tests__/components/settings/document-layout/PdfPreviewPane.test.tsx`
- Modify: `frontend/src/api/documentLayouts.ts`

- [ ] Komponententests schreiben: PDF wird nur nach bestätigter `lock_version` angefordert; ältere Job-/Blobantworten werden verworfen; Blob-URLs werden widerrufen; Lade-, leerer, ungeprüfter, Fehler- und bereit-Zustand; Seitenzahl, Vor/Zurück, Zoom Fit/75/100/125/150 %, A4/Letter-Seitenverhältnis und Neuversuch.
- [ ] Tests ausführen: `npm --prefix frontend test -- --run src/__tests__/components/settings/document-layout/PdfPreviewPane.test.tsx`; erwartet: FAIL.
- [ ] PDF.js-Worker lokal aus `pdfjs-dist` bündeln und `getDocument({ data })` verwenden. Remote Worker/CDN, externe CMaps und URLs sind deaktiviert; PDF-Daten stammen ausschließlich aus dem autorisierten Blob-Endpoint.
- [ ] `PdfPreviewPane` rendert jede PDF-Seite in ein eigenes Canvas mit devicePixelRatio-Skalierung und einer weißen Papierfläche im dunklen Previewbereich. Seiten werden lazy gerendert; bei Layoutwechsel wird jede laufende `RenderTask` abgebrochen.
- [ ] Toolbar kompakt umsetzen: Sample/realer lesbarer Draft, Dokumentart, Sprache und Samplefall in `LayoutContextBar`; Previewtoolbar zeigt Papierformat, Seiten `x/y`, Zoom, PDF/A-Status, Aktualisieren und Download der Vorschau.
- [ ] Vorschau-Orchestrierung implementieren: nach Autosavebestätigung Previewjob erstellen, Status mit TanStack Query und AbortSignal pollen, bei `ready` Blob plus Report laden, ETag/Sequenz prüfen und erst dann sichtbare PDF ersetzen. Die bisherige Vorschau bleibt während eines Updates mit „wird aktualisiert“ sichtbar.
- [ ] Reale Draftquelle nur anbieten, wenn API `commercial_documents:read` bestätigt. Auswahl zeigt Dokumentnummer/Kunde, aber sendet ausschließlich die Dokument-ID; jede reale Vorschauerzeugung wird serverseitig auditiert.
- [ ] Canvas mit zugänglichem Seitentext (`aria-label`), Tastatursteuerung und sichtbarem Fokus ergänzen; bei PDF.js-Fehler bleibt der direkte autorisierte PDF-Download verfügbar.
- [ ] Tests erneut ausführen und Bundle prüfen: `npm --prefix frontend test -- --run src/__tests__/components/settings/document-layout/PdfPreviewPane.test.tsx && npm --prefix frontend run build`; erwartet: PASS ohne CDN-Referenz im gebauten Bundle.
- [ ] Commit erstellen: `git add frontend/src/components/settings/document-layout/PdfPreviewPane.tsx frontend/src/components/settings/document-layout/LayoutContextBar.tsx frontend/src/__tests__/components/settings/document-layout/PdfPreviewPane.test.tsx frontend/src/api/documentLayouts.ts frontend/package.json frontend/package-lock.json && git commit -m "feat(documents): show real PDF preview"`.

### Task 18: Komplette gegliederte Layoutsteuerung und Lifecycle-UI rechts umsetzen

**Files:**
- Create: `frontend/src/components/settings/document-layout/DocumentLayoutSettings.tsx`
- Create: `frontend/src/components/settings/document-layout/LayoutControlPanel.tsx`
- Create: `frontend/src/components/settings/document-layout/LayoutLifecycleBar.tsx`
- Create: `frontend/src/components/settings/document-layout/LayoutFindings.tsx`
- Create: `frontend/src/components/settings/document-layout/controls/PageControls.tsx`
- Create: `frontend/src/components/settings/document-layout/controls/HeaderControls.tsx`
- Create: `frontend/src/components/settings/document-layout/controls/TypographyControls.tsx`
- Create: `frontend/src/components/settings/document-layout/controls/PositionControls.tsx`
- Create: `frontend/src/components/settings/document-layout/controls/TotalsControls.tsx`
- Create: `frontend/src/components/settings/document-layout/controls/FooterControls.tsx`
- Create: `frontend/src/components/settings/document-layout/controls/TitleControls.tsx`
- Create: `frontend/src/components/settings/document-layout/controls/TextControls.tsx`
- Create: `frontend/src/components/settings/document-layout/controls/AssetControls.tsx`
- Create: `frontend/src/components/settings/document-layout/LayoutHistoryDrawer.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Create: `frontend/src/__tests__/components/settings/document-layout/DocumentLayoutSettings.test.tsx`
- Create: `frontend/src/__tests__/components/settings/document-layout/LayoutControlPanel.test.tsx`
- Create: `frontend/src/__tests__/pages/DocumentLayoutSettingsFlow.test.tsx`

- [ ] Tests für alle Bereiche schreiben: Vorlage/Seite/Ränder, Briefpapier erste/Folgeseite, Typografie/Akzent, Logo/Absender/Empfänger, Titel/Metadaten, Positionen/technische Druckdaten, Summen/Steuer/Zahlung, Hinweise/Textbausteine, Footer/Spalten/Seitenzahlen sowie PDF/A-/E-Rechnungsstatus.
- [ ] Interaktionstests ergänzen: geerbter Wert/Herkunft, Override setzen/entfernen, 500-ms-Autosave, Konfliktreload, Assetupload/Preflight, Blockernavigation, Clone, Publish jetzt/terminiert mit Pflichtgrund, Withdraw mit Pflichtgrund und Read-only bei fehlendem Manage-Recht.
- [ ] Tests ausführen: `npm --prefix frontend test -- --run src/__tests__/components/settings/document-layout/DocumentLayoutSettings.test.tsx src/__tests__/components/settings/document-layout/LayoutControlPanel.test.tsx src/__tests__/pages/DocumentLayoutSettingsFlow.test.tsx`; erwartet: FAIL.
- [ ] `DocumentLayoutSettings` als Query-/Mutation-Owner implementieren: Profil/Scope/Version laden, stabilen UUID-Edit-Session-Key pro geöffnetem Draft halten, lokalen typisierten Draft verwalten, gemeinsamen `useAutosaveDraft` anbinden und Preview ausschließlich über bestätigte Version informieren.
- [ ] Desktoplayout als `grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr)` aufbauen: links Preview mit mindestens 680 px nutzbarer Höhe, rechts `position: sticky` und eigene vertikale Scrollfläche. Der Seitenkopf mit Kontext/Lifecycle bleibt außerhalb beider Spalten.
- [ ] Accordion standardmäßig mit „Basislayout“, „Kopf & Tabelle“ und „Fußzeile“ offen aufbauen; weitere fachliche Abschnitte bleiben kompakt einklappbar. Jede Überschrift zeigt geänderte Werte, Blocker/Warnungen und Vererbungsstatus.
- [ ] Alle Controls als typisierte Inputs implementieren. Einheitliche Feldzeile enthält Label, Hilfetext, Wert, Einheit, Herkunftsbadge und „Override entfernen“. Unzulässige Kombinationen werden lokal erklärt, aber Serverreadiness bleibt autoritativ.
- [ ] AssetControls mit Drag-and-drop plus Dateiauswahl, Größen-/Typ-Hinweis vor Upload, Fortschritt, SHA-Kurzbeleg, Preflightdetails, Vorschau, konkrete Zuweisung erste/Folgeseite/Logo/Body-/Heading-Font und Löschverbot bei Verwendung implementieren.
- [ ] `LayoutLifecycleBar` trennt Statusachsen: Autosave, Preview, Readiness, PDF/A und E-Rechnung. Freigabe bleibt disabled, bis neuester bestätigter Draft geprüft und blockerfrei ist. Dialoge verlangen bei Klonen/Freigabe/Rücknahme Grund; Terminierung verlangt Datum.
- [ ] `LayoutHistoryDrawer` zeigt Versionen, Wirksamkeitszeiträume und Audit. Ohne `order_audit:read` bleiben nur Versionsmetadaten sichtbar; mit Recht werden Actor, Zeitpunkt, Grund, Edit-Session und geänderte Feldpfade nachgeladen.
- [ ] Mobile CSS bei `< 900px`: eine Spalte, Preview zuerst, Controls danach, sticky deaktiviert; auf 390×844 kein Element breiter als Viewport, Toolbar wrappt, Canvas skaliert auf Container, Touchziele mindestens 44 px. Desktop behält echte Papierproportionen.
- [ ] SettingsPage-Renderzweig mit `DocumentLayoutSettings` verbinden und Error Boundary/Skeleton ergänzen. Ein einzelner Previewfehler darf den Controlbereich nicht unmounten oder ungespeicherte Eingabe löschen.
- [ ] Tests erneut ausführen; erwartet: PASS. Zusätzlich `npm --prefix frontend run lint && npm --prefix frontend run build`; erwartet: PASS.
- [ ] Commit erstellen: `git add frontend/src/components/settings/document-layout frontend/src/__tests__/components/settings/document-layout frontend/src/__tests__/pages/DocumentLayoutSettingsFlow.test.tsx frontend/src/pages/SettingsPage.tsx && git commit -m "feat(documents): add complete layout editor"`.

### Task 19: Browser-Abnahme, Conformance-Matrix, Sicherheit und Dokumentation abschließen

**Files:**
- Create: `frontend/e2e/document-layout.spec.ts`
- Create: `frontend/playwright.config.ts`
- Modify: `backend/tests/integration/test_document_pdf_conformance.py`
- Modify: `backend/tests/integration/test_document_render_api.py`
- Modify: `backend/tests/integration/test_document_layout_backup_restore.py`
- Modify: `docs/superpowers/specs/2026-07-23-document-format-preview-design.md`
- Modify: `README.md`
- Modify: `UPDATING.md`
- Modify: `CHANGELOG.md`

- [ ] Eine parametrische Backend-Conformance-Matrix schreiben: jede unterstützte Dokumentart × `de/en` × A4/Letter × `classic/modern/compact`; jede Ausgabe muss rendern, veraPDF PDF/A-3u bestehen, eingebettete Fonts/Unicode besitzen und den erwarteten E-Rechnungstyp korrekt behandeln.
- [ ] Grenz- und Sicherheitstests ergänzen: 10 Seiten, extrem lange Wörter/Positionen, leere optionale Werte, mehrere Steuersätze, schadhafte Assets, Path Traversal, SSRF-Versuch, HTML/CSS-Injection, große Uploads, Job-ID-Enumeration, Cross-Profile, API-Key-Rechtematrix, Timeout und Cacheberechtigungen.
- [ ] Playwright-Abnahme schreiben und mit Testdaten durchführen:

```ts
test.use({ viewport: { width: 1440, height: 1000 } });
test('preview left and compact controls right', async ({ page }) => { /* full workflow */ });

test.use({ viewport: { width: 390, height: 844 } });
test('mobile stacks preview before controls without overflow', async ({ page }) => { /* assertions */ });
```

Die Tests prüfen direkten Menüpfad, 2:1-Desktopaufteilung, echte Canvas-PDF-Seite, Autosave, Refresh-Persistenz, Assetpreflight, Publishblocker, Freigabe, historische Version, Sample/realen Draft und `document.documentElement.scrollWidth === innerWidth` mobil.
- [ ] ZUGFeRD-/XRechnung-Browserfall ergänzen: Hybrid-PDF zeigt „PDF ist Original“ plus XML-Profil/Hash; XRechnung zeigt „XML ist Original“ plus getrennten PDF-Download ohne ZUGFeRD-Behauptung.
- [ ] Performance- und Ressourcenmessung ausführen: 20 warme Standardpreviews, p95 ≤ 2,0 s; 10-Seiten-PDF innerhalb 10 s; Previewcache ≤ 250 MiB; keine verwaisten Tempdateien/Prozesse nach Fehlern.
- [ ] Gesamte Backend-Suite ausführen: `pytest backend/tests/unit/services/test_document_layout_catalog.py backend/tests/unit/services/test_document_layouts.py backend/tests/unit/services/test_document_layout_assets.py backend/tests/unit/services/test_document_view_model.py backend/tests/unit/services/test_document_renderer.py backend/tests/unit/services/test_pdfa.py backend/tests/unit/services/test_verapdf.py backend/tests/integration/test_document_layout_schema.py backend/tests/integration/test_document_layout_api.py backend/tests/integration/test_document_render_api.py backend/tests/integration/test_document_pdf_conformance.py backend/tests/integration/test_document_hybrid_pdf.py backend/tests/integration/test_document_layout_backup_restore.py -q`; erwartet: PASS, keine Skips außer explizit plattformfremde Installerchecks.
- [ ] Bestehende Dokumentregressionen ausführen: `pytest backend/tests/integration/test_document_configuration_api.py backend/tests/integration/test_document_issuance.py backend/tests/integration/test_document_workflow_e2e.py backend/tests/integration/test_einvoice_conformance.py backend/tests/integration/test_document_backup_restore.py -q`; erwartet: PASS.
- [ ] Frontend vollständig prüfen: `npm --prefix frontend run test:run && npm --prefix frontend run lint && npm --prefix frontend run build`; erwartet: PASS einschließlich i18n-Parität.
- [ ] `frontend/playwright.config.ts` mit lokalem Backend-/Vite-Webserver, Chromiumprojekt, Trace nur bei Fehlern und ohne externe Basis-URL anlegen. Browser-Suite ausführen: `npm --prefix frontend exec playwright test e2e/document-layout.spec.ts`; erwartet: PASS für Desktop und 390×844.
- [ ] Container-/Packaging-Smoke ausführen: `docker build -f Dockerfile.test --target backend-test .` und danach veraPDF-/WeasyPrint-Smoke im Image; Windows-Buildskript mit `--verify-runtime-only` auf Windows CI. Erwartet: gepinnte Versionen, keine Laufzeitdownloads.
- [ ] README um Funktionsüberblick und Runtimehinweise, UPDATING um Daten-/Runtime-Migration und CHANGELOG um Nutzerfunktionen ergänzen. In der Spezifikation die Implementierungsreferenzen/erreichten Abnahmekriterien verlinken, ohne die freigegebenen Entscheidungen umzuschreiben.
- [ ] `git diff --check`, `rg -n "TODO|TBD" backend/app/services/document_layout* backend/app/services/document_renderer.py backend/app/services/pdfa.py frontend/src/components/settings/document-layout` und `git status --short` ausführen; erwartet: keine Whitespacefehler, keine offenen Markierungen im neuen Code und nur beabsichtigte Änderungen.
- [ ] Abschlusscommit erstellen: `git add frontend/e2e/document-layout.spec.ts backend/tests docs README.md UPDATING.md CHANGELOG.md && git commit -m "test(documents): verify format and PDF preview"`.

---

## Final Acceptance Checklist

- [ ] Menüpunkt steht unmittelbar nach „Dokumente“, URL/Back/Forward/Search funktionieren und Rechte erzeugen einen erklärten Read-only-Zustand.
- [ ] Desktop zeigt links echte PDF-Seiten und rechts kompakte sticky Controls; 390×844 zeigt Preview vor Controls ohne horizontalen Overflow.
- [ ] Alle fachlichen Layoutbereiche sind typisiert, vollständig editierbar, geerbt/überschreibbar und über denselben 500-ms-Autosave gespeichert.
- [ ] Autosave, Preview, Readiness, PDF/A und E-Rechnung besitzen unabhängige sichtbare Status; stale Antworten können keinen neueren Zustand ersetzen.
- [ ] Classic, Modern und Compact funktionieren für alle Dokumentarten in Deutsch/Englisch sowie A4/Letter einschließlich 10 Seiten.
- [ ] Briefpapier erste/Folgeseite, Logo und einbettbare TTF/OTF werden sicher geprüft, versioniert, inhaltsadressiert und historisch unverändert referenziert.
- [ ] Vorschau und endgültige Ausgabe verwenden denselben offline Renderer und akzeptieren keine fremden URLs, Pfade, HTML oder CSS.
- [ ] Alle endgültigen kaufmännischen PDFs bestehen veraPDF als PDF/A-3u. Fehlender Validator blockiert Freigabe/Ausstellung/Export, nicht die klar markierte ungeprüfte Vorschau.
- [ ] ZUGFeRD enthält bytegenau das bereits validierte CII-D22B-XML mit korrekten Metadaten; XRechnung bleibt eigenständiges Original-XML und das PDF eine klar bezeichnete visuelle Kopie.
- [ ] Ausgestellte PDFs speichern Layout-/Asset-/Snapshot-/Renderer-/Validatorprovenienz und bleiben nach späteren Änderungen unverändert herunterladbar.
- [ ] Interne und externe APIs erzwingen Benutzer-/API-Key-Rechte, Profilgrenzen, Idempotenz, Limits und unveränderliche veröffentlichte Eingaben.
- [ ] Lokales und privates Git-Backup sichern Layouts, Assets, PDFs, XML-Verknüpfungen und Prüfberichte; Restore prüft jeden Hash und blockiert beschädigte Evidenz.
- [ ] Migration erzeugt pro vorhandenem Profil einen Classic/A4-Draft, veröffentlicht ihn nicht und ist bei Wiederholung idempotent.
- [ ] Backend-, Frontend-, Browser-, Conformance-, Security-, Performance- und Packagingtests laufen grün; Dokumentation enthält keine offenen fachlichen oder technischen Punkte.
