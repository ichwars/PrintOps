# Einheitliche UI-Grundkomponenten und Einstellungsmigration

Datum: 17. Juli 2026

## Ziel

PrintOps erhält eine zentrale, typisierte UI-Grundlage für wiederkehrende interaktive Elemente. Fehlende Bausteine orientieren sich funktional an ForgeDesk, werden jedoch für PrintOps neu umgesetzt und vollständig an dessen Farben, Dichte, Themes und Interaktionsmuster angepasst.

Die erste Umsetzungsetappe erstellt die Grundkomponenten und migriert die vollständige Einstellungsoberfläche. Weitere Anwendungsbereiche folgen später in getrennten Etappen.

## Ausgangslage

PrintOps besitzt bereits wiederverwendbare Komponenten wie `Button`, `Toggle` und `Card`, verwendet Formelemente jedoch überwiegend direkt in Seiten und Fachkomponenten. Allein in den zentralen Einstellungsmodulen befinden sich derzeit 41 native Selects, 160 Inputs, 3 Textareas und 44 Buttons. Labels, Hilfetexte, Fehlerzustände, Fokusdarstellung und Dropdown-Logik sind dadurch uneinheitlich und häufig lokal dupliziert.

Scrollbars werden punktuell über `.scrollbar-hide` und `.calendar-scroll` beeinflusst. Eine allgemeine `ScrollArea`-Komponente existiert nicht. Der größte Teil der Anwendung nutzt `overflow-y-auto` mit der jeweiligen Browserdarstellung.

ForgeDesk dient als Referenz für eine kleine zentrale Komponentenbibliothek. Code und CSS werden nicht blind kopiert, da die APIs, Gestaltung und einige Tastaturinteraktionen nicht vollständig zu PrintOps passen.

## Freigegebene Designrichtung

- Eigenes hybrides PrintOps-Designsystem ohne zusätzliche UI-Bibliothek
- Native Browsersemantik bleibt innerhalb eigener Komponenten erhalten, wo sie sinnvoll ist
- Komplexe Oberflächen wie Select und Kalender werden vollständig selbst dargestellt
- PrintOps-Optik bleibt erhalten; ForgeDesk liefert Architektur- und Verhaltensideen
- Migration erfolgt etappenweise
- Erste Etappe umfasst alle Einstellungen und die dort eingebundenen Einstellungsdialoge
- Responsive, ausgewogene Dichte: 38 Pixel auf Desktop und mindestens 44 Pixel auf Touch-Geräten
- Checkbox-Symbole und Beschriftungen werden vertikal zentriert

## Komponentenarchitektur

Neue Grundkomponenten liegen unter `frontend/src/components/ui/`. Sie kennen weder Einstellungsdaten noch API-Aufrufe oder Übersetzungsschlüssel. Verbraucher übergeben bereits übersetzte Labels, Werte, Zustände und Ereignisbehandler.

### FormField

`FormField` bildet den gemeinsamen Rahmen für:

- sichtbares Label
- optionale Pflichtkennzeichnung
- Hilfetext
- Fehlermeldung
- konsistente Abstände
- Verknüpfung über `aria-describedby`
- `aria-invalid` bei Fehlern

Die Komponente führt keine fachliche Validierung durch.

### TextField

`TextField` kapselt native Inputs für Text, Passwort, E-Mail, Suche, Telefonnummern, URLs und Zahlen. Relevante native Eigenschaften wie `min`, `max`, `step`, `autoComplete`, `inputMode`, `readOnly` und `disabled` bleiben verfügbar.

### TextArea

`TextArea` nutzt dieselben Feldzustände und dieselbe `FormField`-Integration wie `TextField`. Automatische Größenänderung ist nicht Teil der ersten Etappe.

### Select

`Select` ist ein vollständig eigener Dropdown. Er verwendet einen Trigger-Button, ein per Portal gerendertes Menü und eine gemeinsame Floating-Layer-Infrastruktur auf Basis des bereits installierten Floating UI.

Die API unterstützt typisierte String- und Zahlenwerte, deaktivierte Optionen, optionale Gruppen, Platzhalter und eine benutzerdefinierte Wertdarstellung. Ein unbekannter bestehender Wert wird nicht automatisch zurückgesetzt; er bleibt als aktueller Wert sichtbar, bis der Benutzer eine gültige Option auswählt.

### Checkbox

`Checkbox` verwendet intern ein natives Checkbox-Input und stellt die sichtbare Box selbst dar. Unterstützte Zustände:

- nicht ausgewählt
- ausgewählt
- `indeterminate`
- Hover
- Fokus
- Fehler
- deaktiviert
- schreibgeschützt

Häkchen und Indeterminate-Strich werden als SVG in einem quadratischen Flex-Container dargestellt. `align-items: center`, `justify-content: center` und `line-height: 0` verhindern Verschiebungen durch Schriftmetriken. Checkbox und Beschriftung sind ebenfalls vertikal zentriert.

### Switch

Der vorhandene `Toggle` wird zu einem semantisch konsistenten `Switch` weiterentwickelt. Intern bleibt ein Checkbox-Input beziehungsweise eine gleichwertige Switch-Semantik erhalten. Bestehende Importe außerhalb der ersten Migrationsetappe werden über einen Kompatibilitäts-Reexport geschützt.

### RadioGroup

`RadioGroup` kapselt native Radios, Gruppierungssemantik, Labels, Hilfetext und Pfeiltastensteuerung. Einzelne Radioelemente werden nicht als unabhängige frei positionierbare Komponente verwendet.

### DatePicker und Calendar

`DatePicker` verwendet einen vollständig eigenen Kalender-Popover. Der sichtbare Wert wird lokalisiert, während der kontrollierte Datenwert stabil als `YYYY-MM-DD` übertragen wird.

Der Kalender unterstützt:

- Monatsnavigation
- direkte Heute-Aktion
- Tage aus angrenzenden Monaten
- `min` und `max`
- deaktivierte Tage
- fokussierten, heutigen und ausgewählten Tag
- sprachabhängige Monats- und Wochentagsnamen
- sprachabhängigen Wochenanfang

Datum-only-Werte werden nicht durch Zeitzonenkonvertierung verschoben.

### DateTimePicker

`DateTimePicker` kombiniert den eigenen Kalender mit einem einheitlichen Zeitfeld im Format `HH:MM`. Es wird kein nativer Browser-DateTime-Picker geöffnet. Datum und Uhrzeit werden über getrennte kontrollierte Werte und Callbacks geführt; eine Zeitzonenumrechnung findet nur statt, wenn der jeweilige Verbraucher sie ausdrücklich vornimmt.

### ScrollArea

`ScrollArea` behält das native Scrollverhalten und standardisiert ausschließlich Darstellung, Scrollbar-Gutter und optionale Varianten:

- normale sichtbare Scrollbar
- dünne Scrollbar
- versteckte Scrollbar bei weiterhin möglichem Scrollen
- vertikal, horizontal oder beide Richtungen

Es wird keine JavaScript-basierte künstliche Scrollmechanik eingeführt.

### Button und IconButton

Die vorhandene `Button`-Komponente wird weiterverwendet und um fehlende konsistente Zustände ergänzt. `IconButton` erzwingt ein zugängliches Label, einen klaren Fokuszustand und optional `aria-pressed` für umschaltbare Aktionen.

Bestehende Importe werden über Kompatibilitäts-Reexports geschützt, damit die erste Etappe keine nicht migrierten Seiten bricht.

### Modal

`Modal` standardisiert Hintergrund, Panel, Titel, Schließen-Aktion und Inhaltsbereiche. Er unterstützt:

- Fokusfalle
- Escape zum Schließen
- Fokus-Rückgabe an den Auslöser
- optionales Schließen über den Hintergrund
- beschriftete Dialogsemantik
- begrenzte Höhe mit definierter interner `ScrollArea`

### Tabs

`Tabs` verbindet Tablist, Tabs und Panels semantisch. Pfeiltasten wechseln den aktiven Tab automatisch; Home und End aktivieren den ersten beziehungsweise letzten Tab. Der kontrollierte Wert wird über `onValueChange` gemeldet.

### Gemeinsame interne Infrastruktur

`FloatingLayer` ist eine interne, nicht fachliche Hilfe für Select- und Kalender-Popover. Sie übernimmt Portal, Kollisionsbehandlung, Größenbegrenzung, Scroll- und Resize-Aktualisierung sowie Fokus-Rückgabe.

Gemeinsame Tokens beziehungsweise Klassen definieren:

- Höhen und Innenabstände
- Rahmen und Radien
- Text-, Hintergrund- und Akzentfarben
- Hover-, Fokus-, Fehler- und Disabled-Zustände
- helle und dunkle Themes
- responsive Touch-Ziele

## Interaktion und Barrierefreiheit

Alle Komponenten sind kontrolliert. Werte werden durch den Verbraucher gehalten; Änderungen werden über wertorientierte Callbacks wie `onValueChange` oder `onCheckedChange` gemeldet. API-Aufrufe und Speichervorgänge bleiben unverändert außerhalb der Komponenten.

### Select-Tastatursteuerung

- Enter oder Leertaste öffnet und bestätigt
- Pfeil auf/ab bewegt die aktive Option
- Home und End springen an Anfang beziehungsweise Ende
- Texteingabe führt eine zeitlich begrenzte Präfixsuche aus
- Escape schließt ohne Auswahl
- Tab schließt und setzt die normale Fokusreihenfolge fort
- nach Auswahl oder Escape kehrt der Fokus zum Trigger zurück
- Semantik über `combobox`, `listbox`, `option`, `aria-expanded` und aktiven Nachfolger

### Kalender-Tastatursteuerung

- Pfeiltasten bewegen den fokussierten Tag
- Home und End springen an den Wochenanfang beziehungsweise das Wochenende
- Bild-auf und Bild-ab wechseln den Monat
- Umschalt plus Bild-auf beziehungsweise Bild-ab wechselt das Jahr
- Enter oder Leertaste wählt den Tag
- Escape schließt und gibt den Fokus an den Trigger zurück
- deaktivierte Tage sind nicht auswählbar

### Checkbox-, Radio- und Switch-Steuerung

Die native Eingabesemantik übernimmt Leertaste, Fokus und Formularverhalten. Visuelle Elemente sind nicht selbst zusätzliche Fokusziele. Die gesamte zugehörige Beschriftung bleibt anklickbar.

### Modal- und Tab-Steuerung

Modals halten den Fokus innerhalb des Dialogs und stellen ihn nach dem Schließen wieder her. Tabs verwenden die erwartete ARIA-Zuordnung zwischen Trigger und Panel und bieten Pfeil-, Home- und End-Navigation.

## Visuelles System

Die freigegebene Variante ist „responsive ausgewogen“:

- Desktop-Steuerelemente verwenden standardmäßig 38 Pixel Höhe
- Touch- beziehungsweise kleine Geräte verwenden mindestens 44 Pixel hohe Ziele
- Checkboxen wachsen auf Touch-Geräten mit
- lange Einstellungsseiten behalten auf Desktop eine hohe Informationsdichte
- Popover nutzen PrintOps-Dunkelflächen, vorhandene Rahmenfarben und grünen Akzent
- helle und dunkle Themes erhalten eigene, geprüfte Kontraste
- Fokus wird nicht ausschließlich über Farbe kommuniziert

## Umfang der ersten Etappe

Die erste Etappe umfasst:

1. gemeinsame Zustandsklassen und `FormField`
2. `TextField`, `TextArea`, `Checkbox`, `Switch` und `RadioGroup`
3. `Select` und `FloatingLayer`
4. `Calendar`, `DatePicker` und `DateTimePicker`
5. `ScrollArea`, `Button`, `IconButton`, `Modal` und `Tabs`
6. Migration von `SettingsPage`
7. Migration aller von der Einstellungsoberfläche eingebundenen Einstellungsbereiche und -dialoge
8. Entfernung ersetzter Inline-Klassen und lokaler Dropdown-Implementierungen innerhalb dieses Umfangs

Die Migration ändert keine Einstellungswerte, API-Verträge, Berechtigungen, Übersetzungsschlüssel oder Speicherzeitpunkte.

## Nicht Bestandteil der ersten Etappe

- Datei-Uploads
- Farbwähler
- Range- beziehungsweise Slider-Eingaben
- Migration von Lager, Aufträgen, Druckdialogen oder sonstigen Seiten
- automatische Textarea-Höhenanpassung
- eine externe UI-Komponentenbibliothek
- JavaScript-basierte künstliche Scrollbars

Spezialisierte native Eingaben innerhalb der Einstellungen bleiben erhalten, bis dafür eigene, fachlich passende Komponenten entworfen werden.

## Migrationsstrategie

Jeder oben genannte Baustein wird separat implementiert und geprüft. Bestehende `Button`- und `Toggle`-Importpfade bleiben zunächst als Reexports bestehen. Die Einstellungsbereiche werden anschließend in nachvollziehbaren Gruppen migriert, damit Reviews und Rücksetzungen begrenzt bleiben.

Die Migration erfolgt nicht über einen unkontrollierten globalen Textersatz. Jede Verwendung wird hinsichtlich Werttyp, Label, Hilfetext, Fehlerzustand, Speicherauslöser und Sonderverhalten geprüft.

Nach erfolgreicher Einstellungsmigration folgen Lager, Aufträge, Druckdialoge und übrige Seiten als getrennte Design-, Planungs- und Implementierungsetappen.

## Fehlerbehandlung

UI-Komponenten werfen keine fachlichen Netzwerk- oder Speicherfehler. Verbraucher übergeben Fehlermeldungen und Disabled-Zustände.

- ungültige Select-Werte werden nicht stillschweigend verändert
- ungültige Datumswerte lösen keine automatische Zeitzonenkorrektur aus
- Popover begrenzen sich am Viewport und bleiben scrollbar
- ein fehlender optionaler Hilfetext erzeugt keine leeren ARIA-Verweise
- Komponenten ohne zugängliches Label werden in Entwicklung und Tests als fehlerhafte Verwendung behandelt

## Tests und Verifikation

### Komponententests

- Rendering aller visuellen und semantischen Zustände
- kontrollierte Werte und Änderungscallbacks
- Label-, Hilfetext- und Fehlerverknüpfung
- Disabled- und Read-only-Verhalten
- Checkbox-Indeterminate und vertikale SVG-Ausrichtung

### Interaktionstests

- vollständige Select-Tastatursteuerung und Präfixsuche
- Kalendernavigation, Monats- und Jahreswechsel
- Datumsgrenzen, deaktivierte Tage und Schaltjahre
- Fokusfalle und Fokus-Rückgabe im Modal
- Tab- und RadioGroup-Pfeiltastensteuerung
- Escape- und Outside-Click-Verhalten der Floating-Layer

### Regressionstests

- bestehende Einstellungswerte bleiben beim Rendern erhalten
- Speichervorgänge senden unveränderte Nutzdaten
- keine zusätzlichen API-Aufrufe
- unbekannte Select-Werte werden nicht gelöscht
- bestehende Berechtigungs- und Sichtbarkeitslogik bleibt erhalten

### Gesamtprüfung

- vollständige Frontend-Tests
- ESLint
- TypeScript- und Produktions-Build
- Browser-QA auf Desktop und Mobil
- helles und dunkles Theme
- Scrollbar-Prüfung mindestens in Chromium und Firefox
- Tastaturdurchlauf der zentralen Einstellungsabläufe

## Abnahmekriterien

Die erste Etappe ist abgeschlossen, wenn:

- alle beschriebenen Grundkomponenten vorhanden und getestet sind
- die vollständige Einstellungsoberfläche diese Komponenten verwendet, soweit der Feldtyp im Umfang liegt
- keine ersetzten nativen Selects, Standard-Checkboxen oder duplizierten Basisfeldklassen im migrierten Umfang verbleiben
- Checkbox-Symbole und Labels vertikal mittig ausgerichtet sind
- der eigene Kalender vollständig per Maus und Tastatur bedienbar ist
- bestehende Einstellungsdaten und Speicherabläufe unverändert funktionieren
- alle automatisierten Prüfungen und die Browser-QA erfolgreich sind
