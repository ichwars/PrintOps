# Shared NumberField and Calculation Dialog — Design QA

- Source visual truth: the ten annotated screenshots supplied by the user, especially `codex-clipboard-b13cad6b-574e-4810-8bf7-20617e0de433.png` (spool units/stepper), `codex-clipboard-939c375b-9363-4f01-88bb-4640005f0e76.png` (calculation dialog header), and the eight NumberField examples across calculation, customers, and device settings.
- Implementation screenshots:
  - `C:\Users\droth\Documents\GitHub\PrintOps\docs\design-qa-controls-after-dialog.png`
  - `C:\Users\droth\Documents\GitHub\PrintOps\docs\design-qa-controls-after-spool.png`
  - `C:\Users\droth\Documents\GitHub\PrintOps\docs\design-qa-controls-after.png`
- Viewport: 1778 × 1011 desktop browser session.
- States: Add Calculation dialog open; Add Spool dialog open; Settings → Devices → Printers & Production.

## Full-view comparison evidence

The repaired calculation dialog remains fully bounded by the viewport: measured height 953.54 px in a 1011 px viewport, with a 73.09 px header, an independently scrolling 812.34 px content region, and a 65.89 px footer. The header and footer no longer overlap the form while scrolling. The existing PrintOps colors, type hierarchy, spacing rhythm, field grid, and button treatments are preserved.

The spool form keeps its existing modal width and vertical flow. Its `g` and `%` units now occupy reserved space inside the shared field, before the stepper, instead of colliding with the arrows.

## Focused comparison evidence

- NumberField: across calculation and device settings, the stepper is inset by 0.99 px at the top and bottom of the input border and renders at 28.78 px in the desktop capture (32 px logical width). The arrows are centered in equal-height halves.
- Spool units: the `g` suffix ends at x=985.73 and the stepper starts at x=988.35, leaving a visible 2.62 px separation with no overlap. The same component path covers `%`.
- Calculation dialog: the reference showed a header overlapping section 1. The repaired header ends at y=102.99 and the dedicated content viewport starts at exactly y=102.99.
- Responsive interaction area: touch layouts retain a wider 44 px stepper target while desktop fields remain compact.

## Required fidelity surfaces

- Fonts and typography: passed; existing PrintOps families, weights, sizes, labels, and value treatments were retained.
- Spacing and layout rhythm: passed; consumer-specific top margins were moved to the NumberField wrapper, keeping input and stepper in one coordinate system.
- Colors and visual tokens: passed; shared background, border, muted text, focus, hover, and disabled tokens are unchanged.
- Image quality and asset fidelity: passed/not applicable; these controls use existing Lucide icons and contain no new raster or brand assets.
- Copy and content: passed; labels, units, values, validation text, and actions are unchanged.

## Comparison history

1. P1 — Calculation modal header could cover the first form section because the entire page-height overlay scrolled around sticky header/footer elements. Fixed with a bounded flex dialog and a dedicated ScrollArea between non-sticky header and footer.
2. P2 — Input-only `mt-1` consumer classes displaced inputs from the absolutely positioned shared stepper. Fixed by adding `containerClassName` and applying spacing to the wrapper.
3. P2 — Desktop steppers were visually oversized in all ten marked contexts. Fixed centrally with a compact 32 px desktop stepper, centered 12 px icons, and a 44 px mobile target.
4. P2 — External `g` and `%` labels overlapped the stepper in spool forms. Fixed with a shared `suffix` slot and reserved input padding.
5. Post-fix evidence — targeted component tests, all 2,542 frontend tests, lint, translation parity, production build, browser geometry, interactions, and console inspection passed. Browser console contained no errors; only the pre-existing duplicate Three.js warnings remained.

## Browser interaction coverage

- Opened Add Calculation, verified dialog semantics, scrolling region, header/footer placement, and all visible NumberFields.
- Opened Add Spool, verified suffix spacing and the affected weight fields.
- Opened printer/production settings, verified all five device cost NumberFields.
- Checked the browser console for runtime errors.

## Follow-up polish

No actionable P0, P1, or P2 differences remain for the reported defects.

final result: passed

---

# Material, Lieferanten und Beschaffung - Design QA

- Referenz: gelieferte ForgeDesk-Aufnahmen fuer `Material hinzufuegen` und die markierte PrintOps-Materialliste.
- Geprueft: `Lager > Material`, `Lager > Lieferanten` und Filament-Bestandsprognose auf Desktop und 390 px Mobilbreite.
- Umgebung: `http://127.0.0.1:8000` mit isolierter QA-Datenbank.
- Screenshots: `output/playwright/task10-suppliers-desktop.png`, `task10-material-dialog-desktop.png`, `task10-material-overview-desktop.png`, `task10-filament-procurement-desktop.png`, `task10-material-dialog-mobile.png`, `task10-supplier-dialog-mobile.png` und `task10-filament-mobile.png`.

## Vergleich und Interaktionen

- Sichtbare Terminologie ist systemweit `Material`; interne Bezeichner bleiben kompatibel.
- Der Materialdialog uebernimmt Artikel, Bestand, Beschaffung, Verbrauchsgrund und interne Notiz. Mobil ist das Raster einspaltig; Dialog und Aktionen bleiben erreichbar.
- Die Materialsuche folgt den gemeinsamen Feldregeln. `Nur niedriger Bestand` hat genau eine visuelle Umrandung.
- Lieferanten dienen als bevorzugte oder alternative Bezugsquelle fuer Material und Filament. Standardlieferzeit und Angebotswerte wurden geprueft.
- Ein Material wurde vollstaendig angelegt, gespeichert und nach Neuladen kontrolliert. In der leeren QA-Konfiguration wurde zuvor einmalig `Stueck` ueber die vorhandene API angelegt.
- Fokus, Dialogschliessen, Suche, Speichern, erneutes Oeffnen und responsive Darstellung wurden ausgefuehrt. Die Browserkonsole meldete 0 Fehler und 0 Warnungen.

## Vergleichshistorie

1. P1 - Der mobil nur als Icon sichtbare Prognose-Button hatte keinen zugaenglichen Namen. Ein Regressionstest reproduzierte den Fehler; ein explizites `aria-label` behebt ihn. Beide Bezugsquellen sind mobil erreichbar.
2. P2 - Keine offenen Abweichungen. Dialogbegrenzung, Aktionsbereich, Abstaende, Farben, Typografie und Feldtokens entsprechen den PrintOps-Designregeln.

Keine offenen P0-, P1- oder P2-Befunde.

final result: passed
