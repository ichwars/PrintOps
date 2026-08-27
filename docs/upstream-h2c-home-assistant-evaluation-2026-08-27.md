# Bewertung optionaler H2C- und Home-Assistant-Funktionen

- Stand: 27. August 2026
- PrintOps-Basis: `315f73252`
- Bambuddy-Basis: `59d2713ac`

## Ziel und Leitplanken

Diese Bewertung beantwortet Issue #96. Sie gleicht die optionalen
Upstream-Funktionen mit dem tatsächlichen PrintOps-Gerätebestand und der
vorhandenen Home-Assistant-Anbindung ab. Hardwarelogik wird nur übernommen,
wenn ein passendes Gerät und ein belastbarer Validierungsweg vorhanden sind.
Home Assistant bleibt eine optionale Integration; ohne Konfiguration muss
PrintOps vollständig bedienbar bleiben.

## Ausgangslage

Die lokale PrintOps-Datenbank enthält zwei aktive Drucker: einen P2S und einen
X1C. Ein Gerät der H2C-Familie ist nicht registriert. PrintOps normalisiert die
rohen Bambu-Modellcodes O1C und O1C2 beide zum Anzeigenamen H2C; O1C2 ist dabei
als Dual-Nozzle-Variante dokumentiert. Firmwarestände und rohe Modellcodes
werden im aktuellen Druckermodell nicht dauerhaft gespeichert, sodass es lokal
auch keinen H2C-Firmwarestand oder Gerätecode zu bewerten gibt.

Home Assistant ist in der Laufzeitumgebung konfiguriert. Die bestehende
Integration unterstützt schaltbare Entitäten, Energie-Sensoren und
Benachrichtigungen. In der lokalen Datenbank ist jedoch kein Smart Plug und
keine generische Sensorbindung hinterlegt. Die neue Sensor-Leseschicht ist
damit modellunabhängig sinnvoll, benötigt aber eine explizite Konfiguration
und einen getesteten Ausfallpfad.

## Kurzentscheidung

| Kandidat | Gerätebezug | Entscheidung | Folgeissue |
| --- | --- | --- | --- |
| Erweiterte H2C-Düsenrack- und Schlittenauswahl | H2C-Familie; lokal nicht vorhanden | Zurückstellen; vorhandenen Dispatch vor Inbetriebnahme auditieren | [#126](https://github.com/ichwars/PrintOps/issues/126) |
| Zusätzliche Home-Assistant-Sensoren auf Druckerkarten | Modellunabhängig; P2S und X1C profitieren | Selektiv annehmen | [#123](https://github.com/ichwars/PrintOps/issues/123) |
| Home-Assistant-Interlocks vor dem Druckstart | Modellunabhängig; optional pro Drucker | Getrennt und enger annehmen | [#124](https://github.com/ichwars/PrintOps/issues/124) |

## 1. H2C-Düsenrack und Schlittenauswahl

### Upstream-Befund

Die Upstream-Arbeit ab `ec26cba92` löst eine H2C-Düsenauswahl erst beim
Dispatch gegen die Live-Telemetrie auf. Die nachfolgenden Korrekturen
`e9d9e51a8`, `dfeac792f` und `45dc139c4` zeigen, dass die Zuordnung nicht aus
logischen Extruderindizes abgeleitet werden darf: Der feste linke Hotend hat
die physische ID 1, der rechte Rack-Schlitten ist Extruder 1 und die sechs
Rackpositionen verwenden physische IDs 16 bis 21. Nicht eindeutig auflösbare
Mappings werden bewusst weggelassen, weil eine falsche physische ID zu einem
falschen Reinigungs-/ABL-Ablauf und Drucken in der Luft führen kann.

Die endgültige Zuordnung wurde an einem echten H2C mit Firmware 01.02.00.00
für gemischte und feste Hotend-Jobs bestätigt. Der Nachweis beschreibt einen
Dual-Nozzle-H2C mit Vortek-Rack und entspricht damit fachlich der in PrintOps
als O1C2 dokumentierten Variante; der rohe, vom Gerät gemeldete Modellcode ist
im Upstream-Nachweis jedoch nicht genannt und darf nicht nachträglich geraten
werden. Das ist ein validierter Einzelstand, aber kein belegter
Mindest-Firmwarestand und kein Nachweis für jeden auf H2C normalisierten Code.
Die explizite Rackpositionsauswahl aus `3954d3a7e` vergrößert zusätzlich
Datenmodell, API, Slicer-Mapping und UI.

### Entscheidung

**Die neue Rack- und Schlittenauswahl zurückstellen.** PrintOps portiert sie
nicht vorsorglich für Hardware, die im tatsächlichen Bestand nicht existiert.
Ohne reales Gerät könnten weder Live-Telemetrie, Firmwaregrenzen noch
physische Wechsel und Z-Höhen sicher geprüft werden.

Neu bewertet wird die Funktion erst, wenn mindestens ein H2C/O1C/O1C2
registriert werden soll. Vor einer Umsetzung sind Modellcode, Firmwarestand,
Live-Rack-IDs sowie feste, reine Rack- und gemischte Testdrucke zu erfassen.
PrintOps besitzt allerdings bereits den mit #1780 eingeführten
Virtual-Printer-Pfad, der ein physisches `nozzle_mapping` aus der
Bambu-Studio-Payload in die Queue übernimmt und bei Dual-Nozzle-Druckern wieder
versendet. Dieser bestehende Dispatch ist keine neue Upstream-Übernahme, muss
wegen derselben Hardwaregefahr aber vor der ersten H2C-Registrierung
modellgenau auditiert und bis zur Hardwarevalidierung sicher begrenzt werden.
Das verpflichtende Folgeissue #126 erfasst Modellcode, Firmware, Payloadformen
und reale feste, Rack- und gemischte Testdrucke. Die neue UI-Auswahl bleibt
weiterhin zurückgestellt.

## 2. Sensoren auf Druckerkarten

### Unterstützte Geräte und Zustände

Die Sensoranzeige hängt nicht vom Druckermodell ab und gilt daher für den
vorhandenen P2S und X1C sowie spätere Drucker. #123 nimmt ausschließlich
explizit pro Drucker gebundene Entitäten an:

- `binary_sensor.*` für `door`, `opening`, `window`, `garage_door`,
  `occupancy`, `motion`, `presence`, `smoke`, `gas`, `moisture`, `problem`
  und `safety`;
- `sensor.*` für numerische Werte, zunächst `temperature`, `humidity` und
  `pressure`, jeweils mit Einheit;
- `unknown`, `unavailable`, fehlende Entitäten, Timeouts und
  Verbindungsfehler als ausdrücklich nicht verfügbar.

Die Anzeige bleibt rein lesend. Ein Sensorzustand auf der Druckerkarte darf
weder Queue noch Dispatch beeinflussen. Bei fehlender Konfiguration oder
nicht erreichbarem Home Assistant bleibt die vollständige Druckerkarte
bedienbar und kennzeichnet lediglich den betroffenen Wert als nicht verfügbar.
Damit ist dieser Pfad immer **fail-open**.

### Abgrenzung zu Upstream

Upstream-Commit `cd004df81` bündelt Anzeige, Benachrichtigungen und
Queue-Blockierung in einer großen Änderung. PrintOps trennt diese
Verantwortungen. #123 übernimmt nur die validierte Leseschicht und Darstellung;
Interlocks erhalten mit #124 ein eigenes Datenmodell, eigene Berechtigungen
und eigene Scheduler-Tests.

## 3. Interlocks vor dem Druckstart

Interlocks werden ausschließlich opt-in pro Drucker und Sensor eingerichtet.
Ein sicher gelesener unsicherer Zustand hält den Queue-Eintrag als `pending`
mit einem verständlichen Wartegrund. Nach Rückkehr zum sicheren Zustand wird
der Eintrag erneut bewertet. Alte Messwerte dürfen nicht als aktueller Zustand
gelten.

| Sensorklasse | Sicherer Zustand | Verhalten bei sicher gelesenem Alarm | Standard bei HA-Ausfall |
| --- | --- | --- | --- |
| `door`, `opening`, `window`, `garage_door` | geschlossen / `off` | Druckstart zurückhalten | Fail-open |
| `occupancy`, `motion`, `presence` | frei / `off` | Druckstart zurückhalten | Fail-open |
| `smoke`, `gas`, `moisture` | normal / `off` | Druckstart zurückhalten | Fail-closed |
| `problem`, `safety` | normal / `off` | Druckstart zurückhalten | Fail-closed |

Die Ausfallstrategie wird je Interlock ausdrücklich gespeichert und in der
Oberfläche angezeigt. Operative Bereitschaftssensoren sind standardmäßig
fail-open, damit ein HA-Ausfall keine Produktionsqueue strandet. Bewusst als
kritisch konfigurierte Zustände sind standardmäßig fail-closed; ein Ausfall
hält dann nur den betroffenen Drucker zurück. Eine berechtigte manuelle
Übersteuerung verlangt einen Grund und wird auditiert.

Home Assistant und PrintOps sind kein primäres Brand-, Gas- oder
Maschinenschutzsystem. Physische Schutzschaltungen und Home-Assistant-
Automationen müssen unabhängig funktionieren. Ohne konfigurierte Interlocks
entsteht keine Laufzeitabhängigkeit zu Home Assistant und PrintOps bleibt
vollständig bedienbar.

## Ergebnis

Die neue H2C-Erweiterung bleibt mangels passender Hardware und belastbarer
Firmwaregrenze außerhalb von PrintOps; #126 macht die Prüfung und sichere
Begrenzung des bereits vorhandenen #1780-Dispatchs zur Voraussetzung einer
späteren H2C-Inbetriebnahme. Die beiden modellunabhängigen Home-Assistant-
Funktionen werden getrennt umgesetzt: #123 liefert eine best-effort
Sensoranzeige, #124 ergänzt ausdrücklich konfigurierte Interlocks mit
nachvollziehbarer Fail-open-/Fail-closed-Entscheidung, Wartegrund, Tests und
Fallbacks.
