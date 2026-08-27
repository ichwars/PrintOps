# Bewertung optionaler Upstream-Slicer-Funktionen

- Stand: 27. August 2026
- PrintOps-Basis: `7cab2e49a`
- Bambuddy-Basis: `16e9bfaa9`

## Ziel und Leitplanken

Diese Bewertung beantwortet Issue #95. Sie betrachtet vier größere
Bambuddy-Slicer-Funktionen einzeln nach Nutzwert, zuverlässig unterstützten
Formaten und Plattformen, Wartungskosten sowie dem Risiko einer zweiten Quelle
der Wahrheit neben dem vorhandenen Slicer-Sidecar.

Technische Basis von PrintOps bleibt der optionale HTTP-Sidecar mit
Bambu Studio oder OrcaSlicer. Serverseitig unterstützt PrintOps bewusst nur
STL und 3MF; STEP/STP werden gespeichert, aber wegen unzuverlässiger
CLI-Unterstützung nicht angeboten. Presets bleiben im jeweiligen Slicer
beziehungsweise dessen Sidecar maßgeblich. Generierte Upstream-Artefakte werden
nicht ohne Generator, Quelle und reproduzierbare Aktualisierung übernommen.

## Kurzentscheidung

| Kandidat | Nutzen | Risiko und Aufwand | Entscheidung | Folgeissue |
| --- | --- | --- | --- | --- |
| Vollständiger Slice-Parametereditor | Niedrig bis mittel | Sehr hoch | Verwerfen | – |
| Auto-Orientierung und Auto-Anordnung | Hoch | Mittel | Selektiv annehmen | [#121](https://github.com/ichwars/PrintOps/issues/121) |
| Lokaler Desktop-Slicer | Hoch | Bereits umgesetzt | Vorhandene Lösung beibehalten | – |
| ARM64-Sidecar per QEMU oder nativ | Mittel | Hoch bis sehr hoch | QEMU verwerfen, native Variante zurückstellen | – |

Nur Auto-Orientierung und Auto-Anordnung erzeugen neue Implementierungsarbeit.
Die Desktop-Integration erfüllt den Kandidaten bereits. Für den Volleditor und
ARM64 existiert derzeit weder ein hinreichend belastbarer Nutzerbedarf noch
eine Wartungs- beziehungsweise Laufzeitbasis, die einen eigenen
Implementierungsauftrag rechtfertigt.

## 1. Vollständiger Slice-Parametereditor

### Nutzen

Ein vollständiger Editor könnte kleine Prozessänderungen ohne Wechsel in den
Desktop-Slicer ermöglichen. Für häufige PrintOps-Abläufe ist der Zusatznutzen
jedoch begrenzt: Standard-, Cloud- und lokale Presets sowie Slicer-Pipelines
decken wiederholbare Produktionskonfigurationen bereits ab. Ein Editor mit
hunderten Einzelwerten verlagert außerdem Slicer-Fachwissen in die
Produktionsoberfläche, statt einen klaren Bedienablauf zu vereinfachen.

### Upstream-Befund

Die Basis in `f0500578b` umfasst rund 2.540 neue beziehungsweise geänderte
Zeilen. Sie vendiert aus `three-slicer` extrahierte OrcaSlicer-Daten für den
gesamten Prozessbaum, ein Konfigurationsschema und Enable-Regeln und ergänzt
einen eigenen Interpreter für Abhängigkeiten. Die Folgearbeiten `f421bb816`
und `b6027b713` mussten die tatsächlichen Presetwerte über einen neuen
Sidecar-Endpunkt auflösen und verschiedene Ausfallursachen unterscheiden.
`f3b6a503b` zeigt zusätzlich, dass reale Presetwerte in nicht referenzierten
Begleitdateien liegen können.

Damit wären mindestens vier Versionen aufeinander abzustimmen: PrintOps,
Editor-Schema, Sidecar und die darin installierte Bambu-Studio- oder
OrcaSlicer-Version. Das aus OrcaSlicer erzeugte Schema ist zudem keine
verlässliche Beschreibung jeder Bambu-Studio-Version. Bereits die
Upstream-Nacharbeiten belegen, dass kompilierte Defaults und tatsächlich vom
Sidecar verwendete Werte auseinanderlaufen können.

### Entscheidung

**Verwerfen.** Der vollständige Editor würde eine zweite, versionsabhängige
Darstellung der Slicer-Konfiguration schaffen und sehr hohe Test-, Übersetzungs-
und Aktualisierungskosten verursachen. PrintOps übernimmt weder die vendierten
Schemaartefakte noch den vollständigen Parameterbaum. Sollten konkrete Nutzer
künftig wiederholt dieselben wenigen Änderungen benötigen, sind einzeln
begründete, kuratierte Optionen oder eigene Presets die kleinere und
verlässlichere Lösung.

## 2. Auto-Orientierung und Auto-Anordnung

### Nutzen

Rohe STL-Dateien und ungünstig platzierte 3MF-Modelle benötigen heute einen
Umweg über den Desktop-Slicer. Optionale Auto-Orientierung und Auto-Anordnung
schließen diese Lücke direkt im bestehenden serverseitigen Slice-Ablauf. Beide
Aktionen sind für Bediener verständlich und verändern weder Presets noch
Kalkulations- oder Projektdaten.

### Upstream-Befund und PrintOps-Passung

Commit `e95c42c02` reicht zwei pro Slice gesetzte Flags bis zum Sidecar durch.
Die Optionen sind standardmäßig aus, weil sie Geometrie beziehungsweise
absichtlich gesetzte Positionen verändern. Ein ausgeschaltetes Flag muss im
Multipart-Request fehlen: Die Zeichenkette `false` wäre im Sidecar wahr.

PrintOps besitzt bereits einen internen `arrange`-Pfad für
Cross-Nozzle-Class-Slices. Die selektive Umsetzung ergänzt daher keinen neuen
Slicing-Stack, sondern macht zwei Sidecar-Fähigkeiten kontrolliert zugänglich.
Sie bleibt auf die vorhandenen Formate STL und 3MF sowie die vorhandenen
Bambu-Studio-/OrcaSlicer-Sidecars begrenzt. Ergebnisse und Performance hängen
weiterhin von der konkret installierten Sidecar-Version ab.

### Entscheidung

**Selektiv annehmen.** Beide Optionen bleiben flüchtige, standardmäßig
deaktivierte Slice-Entscheidungen und werden weder in Presets noch Pipelines
oder Projekten gespeichert. Backend und Frontend müssen Profil- und
Embedded-Settings-Pfad, bestehendes erzwungenes Arrange-Verhalten und die
Abwesenheit ausgeschalteter Flags testen. Die Umsetzung ist in #121
abgegrenzt.

## 3. Integration eines lokalen Desktop-Slicers

### Nutzen und Ist-Stand

Der lokale Desktop-Slicer ist wichtig, wenn kein Sidecar läuft, ein Format nur
im GUI-Slicer zuverlässig verarbeitet werden kann oder ein Bediener das Modell
vor dem Slice prüfen möchte. Dieser Ablauf ist in PrintOps bereits vorhanden:

- Bambu Studio und OrcaSlicer werden über ihre plattformspezifischen
  URI-Schemata unter Windows, macOS und Linux angesprochen.
- Dateiadressen werden korrekt URL-kodiert.
- Bei aktivierter Authentifizierung verwendet der Download kurzlebige,
  einmalig nutzbare Tokens, weil Desktop-Protokollhandler keine
  Authorization-Header mitsenden können.
- `open_in_slicer` kann unabhängig vom für die API verwendeten
  `preferred_slicer` gewählt werden.
- Ohne aktivierten Sidecar fällt die Slice-Aktion auf den Desktop-Ablauf
  zurück.

Die bestehende Umsetzung entstand unter anderem mit `8d42b05f6`, `a903816b8`,
`76b997fc8` und `68877c639`. Sie ist umfangreicher und sicherer als der hier
bewertete Upstream-Ausgangspunkt `eda2e0459`.

### Entscheidung

**Vorhandene Lösung beibehalten; kein neues Folgeissue.** Der Desktop-Slicer
ist eine bewusst getrennte Ausführungsart und keine zweite Presetquelle in
PrintOps: Die geöffnete Datei und alle weiteren Einstellungen liegen im
Desktop-Slicer selbst. Zusätzliche native Bridges oder lokale HTTP-Dienste
werden nicht eingeführt.

## 4. ARM64-Slicer-Sidecar

### Nutzen

Ein ARM64-Sidecar könnte Installationen auf Raspberry Pi, ARM-Servern oder
Apple-Silicon-Linux ohne zweiten Rechner vollständig lokal betreiben. Die
Anwendung PrintOps selbst veröffentlicht bereits Container für `linux/amd64`
und `linux/arm64`; die Einschränkung betrifft die proprietären beziehungsweise
plattformgebundenen Slicer-Binaries im optionalen Sidecar.

### Upstream-Befund

Commit `b11a15f1c` stellt keine native ARM64-Ausgabe bereit. Eine Compose-
Ergänzung erzwingt `linux/amd64` und setzt funktionierendes QEMU/binfmt auf dem
Host voraus. Upstream dokumentiert etwa drei- bis sechsmal längere Slice-Zeiten
und empfiehlt weiterhin einen separaten x86_64-Rechner. Bambu Studio bietet
kein ARM64-Binary; der native OrcaSlicer-Pfad ist wegen eines
Extraktionsproblems ausgesetzt.

QEMU erhöht damit Laufzeit, Speicherbedarf und Supportvarianten gerade bei
großen Produktionsmodellen. Die zuverlässige Alternative existiert bereits:
Der Sidecar kann auf einem x86_64-System laufen und über seine konfigurierbare
URL von PrintOps genutzt werden.

### Entscheidung

**QEMU verwerfen, native Variante zurückstellen.** Eine 3–6× langsamere,
experimentelle Emulation ist für einen Produktionsablauf nicht vertretbar und
würde eine weitere Host-Voraussetzung schaffen. Eine native Variante wird erst
neu bewertet, wenn reproduzierbare ARM64-Binaries und Multi-Arch-Images für
mindestens OrcaSlicer verfügbar sind; Bambu Studio bleibt bis zu einem
Hersteller-Binary x86_64. Da diese Voraussetzung außerhalb von PrintOps noch
nicht erfüllt ist, wird kein Implementierungsissue angelegt.

## Ergebnis

PrintOps behält einen einzigen Slicing-Vertrag: Desktop-Übergabe oder der
konfigurierte Sidecar. #121 erweitert ausschließlich den bestehenden
Sidecar-Request um zwei explizite, flüchtige Layoutaktionen. Alle anderen
Kandidaten sind entweder bereits sicher umgesetzt oder würden derzeit mehr
Versions-, Plattform- und Supportkomplexität als belegten Nutzen erzeugen.
