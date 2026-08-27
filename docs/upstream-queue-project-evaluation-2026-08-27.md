# Bewertung optionaler Upstream-Queue- und Projektfunktionen

- Stand: 27. August 2026
- PrintOps-Basis: `fe0d6f4ce`
- Bambuddy-Basis: `16e9bfaa9`

## Ziel und Leitplanken

Diese Bewertung beantwortet Issue #94. Sie betrachtet vier größere
Bambuddy-Funktionen danach, ob sie einen eigenständigen PrintOps-Workflow
verbessern, ohne die vorhandenen Auftrags-, Kalkulations-, Dokument- und
Archivdomänen zu duplizieren.

Keiner der Kandidaten soll als unveränderter Upstream-Merge übernommen werden.
Alle angenommenen Kandidaten werden selektiv gegen den dann aktuellen
PrintOps-Stand implementiert. Dabei gelten insbesondere die geschützten
Domänengrenzen aus dem [Upstream Integration Guard](upstream-integration-guard.md).

## Kurzentscheidung

| Kandidat | Nutzen | Konfliktrisiko | Aufwand | Entscheidung | Folgeissue |
| --- | --- | --- | --- | --- | --- |
| Queue-Job mit Varianten für mehrere Druckermodelle | Hoch | Mittel | Hoch | Selektiv annehmen | [#116](https://github.com/ichwars/PrintOps/issues/116) |
| Batch-Mengen beziehungsweise Mengen pro Platte | Hoch | Hoch | Hoch | Als Druckbatch selektiv annehmen | [#117](https://github.com/ichwars/PrintOps/issues/117) |
| Selektive Wiederherstellung aus Git-Backups | Hoch | Hoch | Sehr hoch | Mit enger Sicherheitsgrenze annehmen | [#118](https://github.com/ichwars/PrintOps/issues/118) |
| Verschachtelte beziehungsweise Master-Projekte | Mittel bis hoch | Mittel | Mittel bis hoch | Nur für Produktionsprojekte annehmen | [#119](https://github.com/ichwars/PrintOps/issues/119) |

Kein Kandidat wird vollständig verworfen, weil jeder eine klar abgrenzbare
operative Lücke schließt. Verworfen werden jeweils die Teile der
Upstream-Implementierung, die PrintOps-Domänen duplizieren oder umgehen würden:
Batch Orders und Kostenmodelle, kaufmännische Projektsummen, pauschale
Datenbank-Restores sowie generierte oder inzwischen abweichende
Upstream-Artefakte. Diese Teilverwerfungen sind in den Einzelbewertungen
begründet.

## 1. Queue-Varianten für mehrere Druckermodelle

### Verbesserter Workflow

In einer gemischten Druckerflotte kann derselbe fachliche Auftrag bereits für
mehrere Modelle geslict vorliegen. Heute muss ein Bediener dafür mehrere
Queue-Einträge anlegen oder sich vorab auf ein Modell festlegen. Ein Queue-Job
mit technischen Varianten kann stattdessen den ersten verfügbaren kompatiblen
Drucker nutzen, ohne den Auftrag doppelt zu zählen.

### Zuständige PrintOps-Modelle

- `LibraryFile` besitzt Datei- und Slicer-Metadaten.
- `PrintQueueItem` bleibt der einzelne fachliche Queue-Job.
- `SlicerPipeline` kann modellbezogene Ausgaben erzeugen.
- `Printer` und Druckerklassen liefern die tatsächlichen Ausführungsziele.

Die Varianten sind ausschließlich technische Produktionsalternativen. Sie sind
keine `CalculationVariant` und dürfen keine Preis- oder Angebotslogik übernehmen.

### Upstream-Befund und Konflikte

Die Upstream-Arbeit verteilt sich mindestens auf die Commits `da07c5884`,
`752e345d1`, `a9b57ccd3`, `ef7c1b21f` und `ea63355fd`. Sie berührt Datenmodell,
Rückfüllung, Queue-Scheduler, Library- und Queue-APIs, Papierkorb, Druckdialog,
Dateimanager und Darstellung. Die Testfläche umfasst Migration, API, Scheduler
und Frontend.

Das Konfliktrisiko ist mittel: Die Funktion passt zur Queue-Domäne, trifft aber
auf inzwischen abweichende PrintOps-Pipelines, Berechtigungen, Löschschutz und
Queue-Identitätsregeln. Ein direkter Merge würde außerdem generierte Assets und
Upstream-spezifische Zwischenstände einbringen.

### Aufwand und Entscheidung

- Migration: hoch; neue Gruppierungs- und Kandidatendaten sowie eine
  idempotente Rückfüllung sind nötig.
- UI: hoch; Gruppierung, Priorisierung, Validierung und Namen müssen in
  Dateimanager, Druckdialog und Queue verständlich bleiben.
- Tests: hoch; insbesondere Scheduler-Rennen, Retry, Löschung und
  Modellkompatibilität.

**Entscheidung:** selektiv annehmen. Nicht übernommen werden feste
Upstream-Modellannahmen, generierte Assets sowie Billing- oder
Cost-Centre-Bezüge. Die Umsetzung ist in #116 abgegrenzt.

## 2. Plattenspezifische Mengen in Druckbatches

### Verbesserter Workflow

Der aktuelle Druckdialog kann mehrere Platten wählen, verwendet aber eine
gemeinsame Menge. Für einen Satz mit beispielsweise Platte 1 einmal, Platte 2
zweimal und Platte 3 sechsmal muss der Bediener heute mehrere Vorgänge anlegen
und Restmengen selbst verfolgen. Plattenspezifische Sollmengen schließen diese
operative Lücke.

### Zuständige PrintOps-Modelle

- `PrintBatch` gruppiert bereits mehrere Queue-Einträge und hält eine flache
  Gesamtmenge.
- `PrintQueueItem` bildet die tatsächlichen Druckläufe ab.
- `CalculationVariantPlate` besitzt bereits kaufmännisch relevante Mengen und
  Ausschussannahmen für Kalkulationen.
- Kundenauftrag, Angebot und Dokumente bleiben die kaufmännische Wahrheit.

Das neue Modell darf daher nur das operative Drucksoll eines Batches verfolgen.
Es darf weder Preise berechnen noch eine zweite Auftragsverwaltung eröffnen.

### Upstream-Befund und Konflikte

Commit `71a06f363` führt sogenannte Batch Orders, Plattenziele,
Erfüllungsfortschritt, Nachreihen, Kostenattribution und eine eigene UI ein. Der
erste Umfang liegt bei rund 3.600 hinzugefügten Quell- und Testzeilen. Nutzen
und Testabdeckung sind hoch, die Begriffe Order und Cost kollidieren jedoch
direkt mit der ausgeprägten PrintOps-Kalkulations- und Auftragsdomäne.

### Aufwand und Entscheidung

- Migration: hoch; bestehende flache Batches müssen kompatibel auf
  Plattenziele abgebildet werden.
- UI: mittel bis hoch; Menge je Platte und ein eigener Batch-Fortschritt sind
  nötig.
- Tests: hoch; Erfüllung, Abbruch, Fehler, Nachreihen, Besitz und Migration.

**Entscheidung:** funktionalen Kern selektiv annehmen, Upstream-Batch-Order und
Kostenmodell verwerfen. In PrintOps heißt das Objekt weiterhin Druckbatch und
enthält keine kaufmännischen Summen. Die Umsetzung ist in #117 beschrieben.

## 3. Selektive Wiederherstellung aus Git-Backups

### Verbesserter Workflow

Git-Backups sind derzeit ein Schreibpfad. Für eine Wiederherstellung müssen
Administratoren Dateien manuell aus dem Repository laden oder auf eine lokale
Vollsicherung ausweichen. Eine an eine konkrete Commit-SHA gebundene Vorschau
mit auswählbaren Kategorien ermöglicht eine nachvollziehbare Teilrettung.

### Zuständige PrintOps-Modelle

- `GitHubBackupConfig`, `GitHubBackupLog` und die Provider-Backends besitzen
  Konfiguration, Verlauf und Schreibzugriff.
- `LocalBackupService` bleibt für lokale Vollsicherungen und die Integrität von
  Dokumentartefakten zuständig.
- Archive, Spulen, Einstellungen und K-Profile behalten ihre eigenen
  Berechtigungen und Identitätsregeln.

### Upstream-Befund und Konflikte

Die Basisimplementierung in `6a239314d` umfasst rund 4.400 hinzugefügte
Quell- und Testzeilen. Danach folgte eine lange Reihe von Korrekturen unter
#2656, unter anderem zu Fremdschlüsseln, Besitzern, Geheimnissen, Berechtigungen,
Transaktionen, Provider-Paginierung und K-Profil-Zuordnung. Diese Nacharbeiten
zeigen, dass die Funktion sicherheits- und datenintegritätskritisch ist.

Ein unveränderter Port würde nicht automatisch die inzwischen zusätzlichen
PrintOps-Auftrags-, Dokument- und Archivbeziehungen schützen. Ebenso dürfen
ältere Backups keine Credentials oder Authentifizierungsrichtlinien
zurückschreiben.

### Aufwand und Entscheidung

- Migration: niedrig für Tabellen, hoch für fachliche Zuordnung und natürliche
  Schlüssel.
- UI: hoch; Commitwahl, Vorschau, Kategorien, Warnungen und Ergebnisbericht.
- Tests: sehr hoch; vier Provider, Wiederholung, Konflikte, Teilfehler,
  Berechtigungen und Secret-Denylist.

**Entscheidung:** mit enger Kategorie- und Sicherheitsgrenze annehmen. Verworfen
werden ein pauschaler Datenbank-Restore, das Wiederherstellen geschützter
Einstellungen und jede stillschweigende Beschädigung von PrintOps-Beziehungen.
Die Umsetzung ist in #118 beschrieben.

## 4. Hierarchische Produktionsprojekte

### Verbesserter Workflow

Große Fertigungsvorhaben bestehen häufig aus Baugruppen oder Lieferlosen. Ein
Master-Projekt kann diese operativen Teilprojekte zusammenhalten und ihren
Fortschritt über Drucke, Teile, Zeit und Material als zusätzliche Sicht
aggregieren.

### Zuständige PrintOps-Modelle

Die operative `Project`-Entität besitzt bereits `parent_id`, Parent- und
Child-Beziehungen sowie eine grundlegende API- und Detaildarstellung. Dagegen
sind `Calculation`, `CalculationVariant` und die Auftragsdokumente eigenständige
kaufmännische Aggregate. Die vorhandene Hierarchie ist daher der richtige Ort,
muss aber strikt auf Produktionsdaten begrenzt bleiben.

### Upstream-Befund und Konflikte

Commit `afa0ba0dc` macht die vorhandene Parent-Struktur in der UI erreichbar,
verhindert Zyklen, aggregiert Teilbäume und definiert das Verhalten beim Löschen
eines Zwischenknotens. Der Umfang liegt bei rund 1.570 hinzugefügten und 300
geänderten beziehungsweise entfernten Zeilen einschließlich Tests.

Das Konfliktrisiko ist mittel. Das Datenmodell ist bereits vorhanden, aber die
PrintOps-Projekt-API enthält zusätzliche BOM-, Datei-, Archiv- und
Produktionspfade. Aggregierte Kosten dürfen nicht mit Kalkulationskosten oder
freigegebenen kaufmännischen Revisionen vermischt werden.

### Aufwand und Entscheidung

- Migration: niedrig; `parent_id` existiert bereits. Datenzyklen müssen dennoch
  defensiv behandelt werden.
- UI: mittel bis hoch; Parent-Picker, Baumdarstellung und getrennte Roll-up-Karte.
- Tests: mittel bis hoch; tiefe Bäume, Filter, Ziele, Löschen und Zyklen.

**Entscheidung:** selektiv für operative Produktionsprojekte annehmen.
Kalkulations-, Angebots-, Auftrags- und Dokumenthierarchien sowie deren Summen
werden ausdrücklich verworfen. Die Umsetzung ist in #119 beschrieben.

## Reihenfolgeempfehlung

1. #116 Queue-Varianten, weil sie eine abgeschlossene technische Queue-Funktion
   bilden und spätere Batch-Ziele auf derselben Auswahl aufbauen können.
2. #117 plattenspezifische Druckbatches, nach Stabilisierung der erweiterten
   Queue-Identität.
3. #119 Projekthierarchie, da das Datenmodell schon vorhanden und weitgehend
   unabhängig von Backup-Arbeiten ist.
4. #118 Git-Restore zuletzt und in kleinen Inkrementen, weil die
   Sicherheits-, Provider- und Datenintegritätsfläche am größten ist.

Diese Reihenfolge ist eine technische Empfehlung. Jedes Folgeissue bleibt
eigenständig umsetzbar und benötigt einen eigenen PR mit vollständiger Prüfung.
