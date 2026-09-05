# Dynamischer Seitentitel für den Auftragsbereich

## Ziel

Die obere Kopfzeile der gemeinsamen Auftragsseite zeigt den Inhalt der aktuell geöffneten Unterseite. Dadurch steht auf der Rechnungsansicht nicht länger die allgemeine Überschrift „Aufträge“.

## Verhalten

`OrdersPage` verwendet für Titel, Beschreibung und Icon dieselbe bereits vorhandene Konfiguration wie die aktive Inhaltskarte:

- `/orders` zeigt „Auftragsübersicht“.
- `/orders/calculation` zeigt „Kalkulation“.
- `/orders/offers` zeigt „Angebote“.
- `/orders/invoices` zeigt „Rechnungen“.

Das Verhalten gilt entsprechend für die englische Oberfläche. Navigation, Karteninhalt, Filter und Datenabfragen bleiben unverändert.

## Umsetzung

Die feste Modulüberschrift in `OrdersPage` wird durch `copy.page[activeSection]` und das bereits ermittelte `ActiveIcon` ersetzt. Es wird keine neue Zustandsquelle und keine zusätzliche Übersetzung eingeführt.

## Prüfung

Ein Komponententest rendert mindestens die Rechnungsroute und prüft den passenden Haupttitel. Die betroffenen Frontendtests, TypeScript-Prüfung und eine Browserkontrolle der Rechnungsseite sichern die Änderung ab.
