# Responsive PrintOps Dark-UI Logo

## Ziel

Das breite PrintOps-Logo wird als sauberes, handgeführtes SVG für die dunkle Benutzeroberfläche neu aufgebaut. Es muss bei der realen Anmeldegröße von etwa 178 × 58 Pixeln klar, ruhig und lesbar bleiben. Inhalt, Wortlaut und grundlegende Anordnung des bestehenden Logos bleiben erhalten.

## Visuelles System

- Der Schriftzug bleibt exakt `PrintOps`, links das Drucker-/Schicht-/Prüfzeichen-Symbol und rechts die Wortmarke.
- `Print` und die tragenden Konturen des Symbols verwenden `#F4F7FA`.
- `Ops`, Pfeile, obere Druckfläche und Prüfzeichen verwenden `#FFB71B`.
- Der Haken im Prüfzeichen bleibt dunkel, damit er auf der orangefarbenen Fläche klar erkennbar ist.
- Fast schwarze Füllflächen werden entfernt oder transparent ausgeführt, damit sie nicht mit dem App-Hintergrund `#171B21` verschmelzen.
- Verläufe, Texturen, Schatten, Leuchteffekte und zusätzliche Buchstabenkonturen sind ausgeschlossen.

## SVG-Aufbau

- Das Asset wird als echtes SVG mit einem eng zugeschnittenen `viewBox` erstellt.
- Symbol und Wortmarke bestehen aus nachvollziehbaren Gruppen mit aussagekräftigen IDs.
- Die Wortmarke wird als Pfad ausgegeben; zur Laufzeit ist keine Schriftdatei erforderlich.
- Pfade und Konturen werden auf ein notwendiges Minimum reduziert. Automatisch erzeugte Pfad-Suppe oder eingebettete Rasterbilder sind ausgeschlossen.
- Die kleinste Kontur wird so dimensioniert, dass sie bei 178 × 58 Pixeln mindestens ungefähr 1,5 physische CSS-Pixel breit erscheint.
- Das Seitenverhältnis bleibt für die vorhandenen breiten Logo-Flächen geeignet.

## Responsive Verwendung

- Das neue breite Dark-UI-SVG ersetzt zunächst nur die breite Logo-Darstellung in der lokalen Vorschau.
- Die bestehende kompakte Bildmarke bleibt für eingeklappte oder sehr schmale Flächen separat.
- Die Darstellung verwendet `object-fit: contain`; das SVG selbst enthält keinen künstlichen Außenabstand.
- Eine dauerhafte Einbindung in Login, Setup, Stream-Overlay und Sidebar erfolgt erst nach visueller Freigabe.

## Prüfung

Das SVG wird auf `#171B21` mindestens in folgenden Größen beurteilt:

- 178 × 58 Pixel: aktuelle Login-Darstellung
- 240 × 78 Pixel: größere Login-/Setup-Darstellung
- 256 × 83 Pixel: Sidebar-Darstellung

Bei jeder Größe müssen `PrintOps`, Pfeile, Schichtmotiv und Prüfzeichen eindeutig erkennbar sein. Zusätzlich werden transparente Flächen, enger `viewBox`, fehlende Rasterbilder und fehlende Filter technisch geprüft. Die erste Beurteilung erfolgt als rein lokale Browser-Vorschau ohne dauerhaften Austausch bestehender Assets.

## Nicht im Umfang

- Änderung des Markennamens oder der Symbolbedeutung
- Neugestaltung von Favicons oder PWA-Icons
- Änderung der allgemeinen PrintOps-Farbpalette
- Sofortiger dauerhafter Austausch aller bestehenden Logo-Dateien
