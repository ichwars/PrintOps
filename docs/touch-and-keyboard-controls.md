# Touch- und Tastaturbedienung

Sekundäre Aktionen an Karten und Zeilen bleiben bei einem Eingabegerät ohne
präzisen Hover-Pointer sichtbar. Das gilt auch für breite Tablets: Nicht die
Fensterbreite, sondern die Eingabefähigkeit entscheidet. Mit einer Maus werden
die Aktionen beim Überfahren eingeblendet; Tastaturfokus blendet sie ebenfalls
ein.

Das betrifft Projekt- und Dateikarten, Ordnerzeilen, Archivaktionen und
Plattennavigation, das Duplizieren von Profilvorlagen, die Tagverwaltung sowie
das Entfernen von Archivfotos und Plattenreferenzen. Bestehende Berechtigungen
gelten unverändert; eine sichtbare Aktion ist keine zusätzliche Berechtigung.

## Aktionsmenüs

Im Dateimanager und bei Projekten öffnet die Drei-Punkte-Schaltfläche das Menü.
Auf kleinen Displays steht das Ordnermenü neben der Ordnerauswahl und bezieht
sich auf den ausgewählten Ordner, nicht auf die übergeordneten Sammelansichten.

- Mit Tab zur Schaltfläche wechseln; Enter, Leertaste oder Pfeiltaste öffnen
  das Menü.
- Pfeil nach oben/unten wechselt zwischen ausführbaren Aktionen, Pos1/Ende zur
  ersten/letzten. Enter oder Leertaste führt die fokussierte Aktion aus.
- Escape schließt und setzt den Fokus auf die Schaltfläche zurück. Tab verlässt
  das Menü in der normalen Reihenfolge der Seite.
- Außenklick oder Scrollen der Seite schließt das Menü. Ein langes Menü darf
  intern scrollen, ohne sich zu schließen.

Menüs werden außerhalb der Karten-/Seitenleistenbegrenzung dargestellt und
passen ihre Position und maximale Höhe an den verfügbaren Platz an.

## Entwicklung und Regressionen

Hoverabhängiges Ausblenden verwendet die CSS-Variante `can-hover` zusammen mit
einer Fokus-Einblendung. Dekorative Overlays sind davon getrennt zu beurteilen.
Verankerte flache Aktionsmenüs verwenden `ActionMenu` und die bestehende
Positionierung von `FloatingLayer`; koordinatenbasierte Kontextmenüs verwenden
weiterhin `ContextMenu`.

`npx playwright test --config playwright.production.config.ts` prüft einen
bereits gestarteten Produktions-Preview auf Port 4184. Die Konfiguration baut
nicht selbst und überschreibt daher keine lokalen `static/`-Dateien.
