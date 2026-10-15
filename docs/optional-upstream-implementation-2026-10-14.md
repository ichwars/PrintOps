# Ausgewählte Upstream-Erweiterungen

Die folgenden 17 Erweiterungen wurden einzeln auf PrintOps übernommen. Die
verlinkten Pull Requests enthalten die Codeänderungen, Reviews und tatsächlichen
Prüfläufe. Die Bedienung beschreibt der [Funktionsleitfaden](upstream-features-guide.md).
Dieses Register enthält dauerhafte Integrationsentscheidungen; temporäre
Arbeitskopien, Agentenprotokolle und lokale Testchroniken werden hier nicht geführt.

## Gelieferte Erweiterungen

| Punkt | Funktion | Pull Request |
| --- | --- | --- |
| O02 | Orca-Filamentprofile und eng begrenzte Preset-Integration | [#201](https://github.com/ichwars/PrintOps/pull/201) |
| O05 | Verbundene Anwendungen und kontrollierte Übergabe an externe Clients | [#203](https://github.com/ichwars/PrintOps/pull/203) |
| O06 | Kamera-Overlay für Streaming-Anwendungen | [#205](https://github.com/ichwars/PrintOps/pull/205) |
| O07 | Anhaltende AMS-Luftfeuchte als Trocknungsauslöser | [#207](https://github.com/ichwars/PrintOps/pull/207) |
| O09 | Schonende Ad-hoc-Signierung für native macOS-Installationen | [#209](https://github.com/ichwars/PrintOps/pull/209) |
| O10 | Geringerer Speicherdruck beim Frontend-Build | [#211](https://github.com/ichwars/PrintOps/pull/211) |
| O11 | Einheitlicher Modellanbieter-Vertrag mit MakerWorld-Implementierung | [#213](https://github.com/ichwars/PrintOps/pull/213) |
| O12 | Objektwahl auf 3MF-Platten | [#215](https://github.com/ichwars/PrintOps/pull/215) |
| O13a | Druckerkarten unabhängig von der Rastergröße skalieren | [#217](https://github.com/ichwars/PrintOps/pull/217) |
| O13b | Anzeige externer Spulen pro Drucker steuern | [#219](https://github.com/ichwars/PrintOps/pull/219) |
| O13c | Kamera-Platzierung über geteilte Schaltfläche wählen | [#221](https://github.com/ichwars/PrintOps/pull/221) |
| O13d | Nächsten autorisierten Queue-Kandidaten anzeigen | [#223](https://github.com/ichwars/PrintOps/pull/223) |
| O14 | Warnung bei übergroßem PostgreSQL-Verbindungspool | [#225](https://github.com/ichwars/PrintOps/pull/225) |
| O15 | Theme-Nachrichten für eingebettete Sidebar-Apps | [#227](https://github.com/ichwars/PrintOps/pull/227) |
| O16 | App-Nachrichten über eigene, begrenzte API-Schlüssel | [#229](https://github.com/ichwars/PrintOps/pull/229) |
| O17 | Qualitätsbestätigung über Telegram | [#231](https://github.com/ichwars/PrintOps/pull/231) |
| O18 | Nativ gebauter OrcaSlicer-Sidecar für ARM64 und AMD64 | [#233](https://github.com/ichwars/PrintOps/pull/233) |

## Erhaltene Integrationsgrenzen

- Aufträge, Kalkulation, Lexware, Warenlager, Reservierungen und eigene Batch-Ziele
  bleiben PrintOps-Funktionen. Qualitätsbestätigungen buchen keinen Lagerzugang
  und keine Lieferung automatisch.
- Manuelle Trocknung hat nach der ausdrücklich gewählten Priorität Vorrang.
  Ein nicht sicher zuordenbarer Trocknungslauf wird nicht automatisch gestoppt
  oder pausiert. Deshalb können Queue-Aufträge warten. Bei bereits gemeldetem
  `IDLE` kann die Queue einen Druck auswählen, ohne zuvor einen Trocknungsstopp
  zu senden. Siehe [Trocknungsabläufe](scheduled-ams-drying.md).
- API-Schlüssel, Kamera-/Medien-Token, Datei-/Projektbesitz und Druckerfreigaben
  bleiben getrennt. Anzeigeeinstellungen und externe Anwendungen erweitern keine
  Berechtigungen. Der angezeigte nächste Queue-Kandidat ist eine autorisierte
  Momentaufnahme und keine Zusage des nächsten tatsächlich gestarteten Drucks.
- Die Modellanbieter-Abstraktion liefert MakerWorld; sie behauptet keine bereits
  implementierte Unterstützung beliebiger weiterer Plattformen.
- Die PostgreSQL-Poolwarnung betrachtet einen Worker. Sie ist keine globale
  Kapazitätsgarantie für zusätzliche Worker oder andere Datenbank-Clients.
- Der native ARM64-Sidecar betrifft OrcaSlicer, nicht Bambu Studio. Speicherbedarf
  und Geschwindigkeit hängen vom Modell ab; ein Betrieb mit 2 GB RAM ist nicht
  nachgewiesen. Quellen, Lizenzen und Installation stehen in der
  [Sidecar-Anleitung](../slicer-api/README.md).

Software- und Containerprüfungen ersetzen keine physische Drucker-, Kamera-,
Trocknungs- oder Firmwareabnahme. Deren Anforderungen stehen in
[Geräteabnahme und Telemetrie-Nachweisen](hardware-acceptance.md).

Historische fehlgeschlagene und abgebrochene CI-Läufe bleiben in GitHub erhalten.
Die Korrektur des zeitabhängigen Upload-Tests und der CI-Gesamtzeitlimits ist in
[PR #235](https://github.com/ichwars/PrintOps/pull/235) dokumentiert. Eine grüne
PR-Prüfung und eine erfolgreiche Prüfung des anschließenden main-Commits sind
separate Nachweise; maßgeblich sind die tatsächlichen GitHub-Läufe des jeweiligen
Commits.
