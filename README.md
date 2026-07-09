# PrintOps

<p align="center">
  <img src="static/img/printops_logo.svg" alt="PrintOps Logo" width="360">
</p>

PrintOps ist ein Fork von [Bambuddy](https://github.com/maziggy/bambuddy) und wird als lokale, selbst gehostete Arbeitsplattform fuer 3D-Druckbetriebe weiterentwickelt. Die technische Basis bleibt bewusst nah am upstream-Projekt; die fachliche Richtung erweitert sie Schritt fuer Schritt um Lager, Auftraege, Kalkulation, Angebote und Rechnungen.

## Aktueller Stand

- Fork-Remote: `https://github.com/ichwars/PrintOps`
- Upstream: `https://github.com/maziggy/bambuddy`
- Basis: lokale Druckersteuerung, Inventar, Queue, Archiv, Dateien und Bambu-Lab-nahe Workflows aus Bambuddy
- PrintOps-Erweiterung: erste Navigation und Grundseiten fuer `Lager` und `Auftraege`
- Logo-Assets: transparente SVGs fuer Icon und Wortmarke

## Projektziel

PrintOps soll die operative Arbeit rund um 3D-Druckauftraege zusammenfuehren:

- Drucker, Warteschlange und Archiv verwalten
- Filament und Materialbestand nachverfolgen
- Kunden, Auftraege, Angebote und Rechnungen vorbereiten
- Kalkulationen und Reservierungen in den Druckprozess integrieren
- bestehende Bambuddy-Funktionen ohne harte Migration weiter nutzbar halten

## Entwicklung

```bash
cd frontend
npm install
npm run build
```

Der Frontend-Build schreibt nach `static/`, wo das Backend die fertigen Assets ausliefert.

## Lizenz und Herkunft

PrintOps basiert auf Bambuddy und uebernimmt dessen Lizenzmodell. Der Code steht unter der `AGPL-3.0`-Lizenz; Details stehen in [LICENSE](LICENSE).

Bei Veroeffentlichung, Bereitstellung oder Netzwerkzugriff auf eine modifizierte Version muessen die korrespondierenden Quelltexte gemaess AGPL bereitgestellt werden.
