# Anwendungsweite Migration auf PrintOps-UI-Komponenten

Datum: 17. Juli 2026

## Ziel

Die bereits freigegebene PrintOps-Komponentenarchitektur wird von den Einstellungen auf die gesamte Frontend-Anwendung ausgedehnt. Sichtbare Browser-Standardsteuerelemente werden aus Seiten und Fachkomponenten entfernt. Datenmodelle, API-Verträge, Validierung, Berechtigungen, Speicherzeitpunkte und fachliche Ereignisabläufe bleiben unverändert.

Die Anweisung zur direkten Ausführung ohne weitere Rückfragen gilt als Freigabe dieser Fortsetzung der bestehenden Designspezifikation `2026-07-17-unified-ui-components-settings-design.md`.

## Umfang

Die Migration umfasst alle Dateien unter `frontend/src/pages/` und `frontend/src/components/`, ausgenommen die Implementierungen in `frontend/src/components/ui/` selbst.

Ersetzt werden:

- native `select` durch den eigenen `Select`; `LegacySelect` erhält vorhandene `option`-Strukturen und ereignisbasierte Callbacks während der Migration;
- sichtbare Text-, Such-, Passwort-, E-Mail-, Telefon- und URL-Inputs durch `TextField`;
- native Textareas durch `TextArea`;
- Checkboxen durch `Checkbox` und einzelne Radios durch eine neue eigene `Radio`-Komponente;
- Datums- und Datumszeitfelder durch `DatePicker` beziehungsweise `DateTimePicker`;
- native Zeitfelder durch ein textbasiertes `TimeField` im stabilen Format `HH:MM`;
- Datei-Inputs durch `FileInput`, wobei das native Input nur innerhalb der UI-Komponente für Datei- und Formularsemantik verbleibt;
- Farbeingaben durch `ColorInput` mit zentraler PrintOps-Darstellung;
- Range-Eingaben durch `Slider` mit zentralen Track-, Thumb-, Fokus- und Disabled-Zuständen.

`input[type="hidden"]` ist kein sichtbares Browser-Control und darf nur mit dokumentierter Formularnotwendigkeit verbleiben. Numerische Eingaben verwenden weiterhin ausschließlich `NumberField`.

## Architektur

Alle öffentlich verwendbaren Grundkomponenten liegen in `frontend/src/components/ui/` und werden über dessen `index.ts` exportiert. Native Semantik darf innerhalb dieser Komponenten erhalten bleiben; Seiten und Fachkomponenten verwenden keine direkten Browser-Tags für Formsteuerelemente mehr.

`FormField` rendert seinen Wrapper nur, wenn Label, Hilfetext, Fehler oder eine Wrapper-Klasse vorhanden sind. Dadurch können `TextField` und `TextArea` bestehende kompakte Grid- und Inline-Layouts ohne zusätzliche DOM-Ebene übernehmen.

Kompatibilitätskomponenten bewahren während der Migration bestehende Ereignisverträge:

- `LegacySelect` erzeugt weiterhin ein select-ähnliches `onChange`-Ereignis;
- `LegacyDatePicker` meldet einen stabilen `YYYY-MM-DD`-Wert über einen input-ähnlichen Change-Callback;
- `TimeField` meldet `HH:MM` unverändert;
- `FileInput`, `ColorInput`, `Slider` und `Radio` reichen native Eingabeereignisse unverändert weiter.

Diese Brücken enthalten keine Fachlogik. Neue Komponenten sollen bevorzugt wertorientierte Callbacks verwenden.

## Visuelles und Interaktion

- Desktop-Grundhöhe bleibt 38 Pixel, kleine Ansichten erhalten mindestens 44 Pixel große Ziele.
- Fokus-, Fehler-, Disabled-, Read-only-, Hell- und Dunkelzustände folgen den vorhandenen PrintOps-Tokens.
- Checkbox- und Radio-Symbole sind horizontal und vertikal zentriert.
- Select und Kalender bleiben vollständig eigene Popover mit Tastatursteuerung und Viewport-Kollisionserkennung.
- Slider verwenden einen einheitlichen grünen Akzent, einen klaren Fokus-Ring und touchfähige Thumb-Größen.
- Datei-Inputs sind visuell über die jeweiligen vorhandenen Auslöser bedienbar; das eigentliche native Input bleibt verborgen oder zentral gestylt.
- Farbeingaben besitzen einen einheitlichen Rahmen, Radius und Fokuszustand; der Wert bleibt im bestehenden Hex-Format.

## Migration

Die Umstellung erfolgt kontrolltypweise und anschließend bereichsweise:

1. fehlende Grundkomponenten und Kompatibilitäts-APIs ergänzen;
2. Selects und Textareas anwendungsweit migrieren;
3. Text-, Such- und Authentifizierungsfelder migrieren;
4. Checkboxen, Radios, Datum und Zeit migrieren;
5. Datei-, Farb- und Range-Eingaben kapseln;
6. Quellcode-Audit, Regressionstests, Lint, Produktions-Build und Browser-QA durchführen.

Mechanische Tag- und Importänderungen dürfen per TypeScript-AST-Codemod erfolgen. Wertumwandlungen, Spezialzustände und Datumslogik werden anschließend je Verbraucher geprüft. Der Codemod wird nicht als Laufzeitabhängigkeit ausgeliefert.

## Barrierefreiheit

- Jeder sichtbare Control behält oder erhält einen zugänglichen Namen.
- Hilfetexte und Fehler werden über `aria-describedby` zusammengeführt statt überschrieben.
- Checkboxen und Radios behalten native Fokus- und Formularsemantik innerhalb eigener Visuals.
- Select, Kalender und DateTimePicker behalten die bereits getestete Tastatursteuerung und Fokus-Rückgabe.
- Icon-only-Auslöser benötigen ein `aria-label` oder eine eindeutige bestehende Beschriftung.

## Tests und Abnahme

Neue Komponententests decken Ereigniskompatibilität, Fokus, Disabled-Zustände, zentrierte Symbole sowie Slider-, Datei-, Farb- und Zeitverhalten ab.

Ein AST-basierter Migrationstest durchsucht die gesamte Anwendungsquelle und schlägt fehl bei:

- direkten `select`, `textarea` oder sichtbaren `input` außerhalb von `components/ui`;
- `TextField` mit `number`, `checkbox`, `radio`, `date`, `datetime-local`, `time`, `file`, `color` oder `range`;
- direkten numerischen Inputs außerhalb von `NumberField`.

Die Etappe ist abgeschlossen, wenn der Audit ohne nicht dokumentierte Ausnahme grün ist, alle Frontend-Tests und Sprachparitätsprüfungen bestehen, ESLint und Produktions-Build erfolgreich sind und zentrale Seiten in Desktop-/Mobilansicht sowie Hell-/Dunkelmodus keine Überläufe oder Browser-Standardcontrols zeigen.

