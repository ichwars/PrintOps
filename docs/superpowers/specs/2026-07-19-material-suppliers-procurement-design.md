# Material-, Lieferanten- und Beschaffungsdesign

**Datum:** 2026-07-19
**Status:** fachlich freigegeben

## Ziel

PrintOps übernimmt die brauchbaren Beschaffungsmuster aus ForgeDesk und baut sie zu einem gemeinsamen Lagerbaustein für Material und Filament aus. In der sichtbaren Oberfläche ersetzt der Begriff **Material** systemweit **Kleinteile** beziehungsweise **Small parts**. Bestehende technische Namen wie Tabellen, Python-Klassen, API-Pfade und `small_parts`-Payloads bleiben kompatibel.

## Fachliche Begriffe

- **Material:** Nicht-Filament-Verbrauchsmaterial, Zukaufteil oder Hardwareartikel mit eigenem Bestand.
- **Lieferant:** Beschaffungsquelle mit wiederverwendbaren Stamm- und Kontaktdaten.
- **Bezugsquelle:** Angebot eines Lieferanten für genau ein Material oder Filament.
- **Bevorzugte Bezugsquelle:** Standardangebot eines Artikels; pro Artikel höchstens eine.
- **Alternative Bezugsquelle:** Weitere aktive Beschaffungsmöglichkeit desselben Artikels.
- **Hersteller:** Produktmarke beziehungsweise Spoolman-Vendor; nicht mit dem Lieferanten gleichzusetzen.

## Lieferantenstamm

Unter `Lager > Lieferanten` entsteht eine eigene Seite mit Suche, Aktivfilter, Liste und Editor. Ein Lieferant enthält:

- Name/Firma und optionaler Ansprechpartner,
- E-Mail, Telefon, Website,
- Straße, Zusatz, Postleitzahl, Ort und Land,
- eigene Kundennummer,
- Zahlungsbedingungen,
- Standard-Lieferzeit in Tagen,
- interne Notizen und Aktivstatus.

Namen werden normalisiert eindeutig gehalten. Ein verwendeter Lieferant kann nicht hart gelöscht, sondern nur deaktiviert werden. Unverwendete Lieferanten dürfen gelöscht werden.

## Bezugsquellen

Ein neues Beschaffungsangebot verbindet einen Lieferanten mit einem Lagerartikel. Es enthält:

- Lieferanten-Artikelnummer,
- Bezugslink,
- Verpackungsmenge und Einheit,
- Mindestbestellmenge,
- Lieferzeit in Tagen mit Lieferantenstandard als Vorgabe,
- Einkaufspreis netto und brutto,
- bevorzugt/alternativ und Aktivstatus.

Das Datenmodell unterstützt beliebig viele Bezugsquellen. Die Oberfläche zeigt die bevorzugte und die erste aktive Alternative prominent; weitere Angebote bleiben in einer aufklappbaren Liste erreichbar. Eine Datenbankregel stellt sicher, dass es je Lagerartikel höchstens eine bevorzugte aktive Bezugsquelle gibt.

Materialien werden per Fremdschlüssel angebunden. Filament wird über eine stabile Referenz aus Bestandsquelle und Katalog-ID angebunden, damit interne Bestände und Spoolman-Kataloge unterstützt werden, ohne Herstellerdaten zu Lieferanten umzudeuten.

## Materialformular

Das bisherige Materialformular wird an die ForgeDesk-Referenz angelehnt und mit PrintOps-Komponenten umgesetzt. Der Dialog ist maximal zweispaltig, auf schmalen Ansichten einspaltig, besitzt einen scrollbaren Inhalt und einen festen Aktionsbereich.

### Artikel

- Artikelnummer und Bezeichnung (Pflicht),
- Kategorie,
- Beschreibung,
- Suchbegriffe,
- Aktivstatus beim Bearbeiten.

### Bestand

- Anfangsmenge nur beim Anlegen,
- Mindestbestand,
- Einheit (Pflicht),
- Lagerort.

Die Anfangsmenge wird in derselben Transaktion wie der Artikel als unveränderliche `opening`-Lagerbuchung gespeichert. Beim Bearbeiten erfolgt jede Bestandsänderung weiterhin ausschließlich über den Bestandsdialog.

### Beschaffung

- bevorzugte Bezugsquelle,
- alternative Bezugsquelle,
- Verwaltung weiterer Angebote,
- Netto-/Bruttopreise, Lieferzeit und Bezugsdaten aus den jeweiligen Angeboten.

Der bestehende Einzelpreis bleibt während der Migration als kompatibler Standardpreis erhalten und wird aus der bevorzugten Netto-Quelle synchronisiert, solange eine solche vorhanden ist.

### Verbrauch und interne Daten

- Standard-Verbrauchsgrund, Vorgabe `Produktion`,
- interne Notiz.

Der Standard-Verbrauchsgrund wird im manuellen Bestands-/Verbrauchsdialog vorausgefüllt, bleibt dort aber änderbar.

## Materialübersicht

Die Route `/warehouse/parts` bleibt bestehen. Sichtbar werden Titel, Navigation, Aktionen, Suche, Statusmeldungen, Einstellungen, Kalkulation und Auftragsansichten auf `Material`/`Materials` vereinheitlicht. Technische Identifikatoren und URLs werden nicht umbenannt.

Materialkarten zeigen zusätzlich bevorzugten Lieferanten, Einkaufspreis und Lieferzeit, sofern vorhanden. Suche und Niedrigbestandfilter verwenden ausschließlich die gemeinsame PrintOps-Komponentenbibliothek.

## Filamentintegration

Die Filamentansicht erhält einen Beschaffungsbereich, der denselben Lieferanten- und Bezugsquelleneditor verwendet. Hersteller/Marke, Materialtyp und Farbe bleiben Filament-Katalogdaten. Lieferant, Bestellnummer, Preis, Verpackungsmenge und Lieferzeit stammen aus den PrintOps-Bezugsquellen.

Die Integration funktioniert sowohl für internen Bestand als auch für Spoolman. Ein nicht erreichbares Spoolman-System verhindert weder Lieferantenverwaltung noch das Lesen bereits gespeicherter Beschaffungsdaten.

## API und Persistenz

Neue additive Tabellen:

- `suppliers`,
- `procurement_offers`.

`small_parts` erhält nur die artikelbezogenen Zusatzfelder für Standard-Verbrauchsgrund und interne Notiz. Anfangsmenge ist ein reines Create-Kommando und keine veränderbare Artikelspalte.

Neue API-Gruppen:

- `/api/v1/suppliers` für Lieferanten-CRUD und Suche,
- `/api/v1/procurement-offers` für Angebote nach Artikel, Lieferant und Status.

Bestehende `/api/v1/small-parts`-Verträge werden additiv erweitert. Alte Clients bleiben funktionsfähig. Alle Schreiboperationen verwenden die vorhandenen Lagerberechtigungen; Lesen benötigt `inventory:read`.

## Fehlerbehandlung

- doppelte Lieferantennamen und Angebotskonflikte: HTTP 409,
- ungültige Preise, Mengen oder Lieferzeiten: HTTP 422,
- Löschen verwendeter Lieferanten: HTTP 409 mit sichtbarer, fachlicher Meldung,
- fehlende/deaktivierte Bezugsquelle: Artikel bleibt speicherbar, Quelle wird verständlich markiert,
- atomarer Rollback, falls Artikel- oder Anfangsbestandsbuchung scheitert.

## Designregeln

- gemeinsame `Modal`, `TextField`, `TextArea`, `NumberField`, `Select`, `Checkbox`, `Button` und `ScrollArea`,
- nur `bambu-*`-Design-Tokens statt lokaler `gray-*`-/`green-*`-Overrides,
- 38-Pixel-Controls auf Desktop und mindestens 44 Pixel auf Touch-Ansichten,
- Abschnittsüberschriften mit ruhigen Trennlinien wie in der Referenz,
- keine nativen Spinner, Dropdowns oder ungestylten Checkboxen,
- sichtbare Fokuszustände, Tastaturbedienung und vollständige Labels.

## Migration und Kompatibilität

- additive, idempotente Datenbankmigration,
- bestehende `supplier_reference`-Werte bleiben als Legacy-Lieferantenreferenz sichtbar, bis ein Benutzer sie einer Bezugsquelle zuordnet; ohne bekannten Lieferanten wird kein künstliches Angebot erzeugt,
- `unit_cost` bleibt lesbar und wird nicht verlustbehaftet überschrieben,
- vorhandene Material-, Kalkulations- und Reservierungsbeziehungen ändern ihre IDs nicht,
- keine automatische Gleichsetzung von Spoolman-Vendor und PrintOps-Lieferant.

## Tests und Abnahme

- Schema- und Migrationstests für neue Tabellen, Constraints und Altbestand,
- API-Tests für Lieferanten, Angebote, Konflikte und Berechtigungen,
- Transaktionstest für Artikel plus Anfangsbestand,
- Frontendtests für Terminologie, Abschnitte, Pflichtfelder, bevorzugte/alternative Quelle und responsive Struktur,
- Regressionstests für Kalkulation, Reservierung und Lagerortschutz,
- Produktions-Build, i18n-Parität und Browser-QA auf Material-, Lieferanten- und Filamentansicht,
- Desktop- und schmale Ansicht, Dialogscrollen, Tastaturbedienung und Konsolenprüfung.

## Nicht Bestandteil

- Einkaufsbestellungen, Wareneingangsbelege oder Kreditorenbuchhaltung,
- automatische Lieferantenanlage aus Spoolman-Herstellern,
- technische Umbenennung der bestehenden `small_parts`-Domäne,
- harte Löschung historisch verwendeter Lieferanten oder Angebote.
