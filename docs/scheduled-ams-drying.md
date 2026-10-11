# Tägliche AMS-Trocknung

Die [Abnahmematrix](hardware-acceptance.md) dokumentiert die erfüllten
Software-Kriterien von #147 und die zusätzliche, bisher nicht durchgeführte
Geräteprüfung. Sie enthält die genaue P2S/AMS-2-Pro- und X1C/klassisches-AMS-
Abgrenzung sowie eine lesende, privat zu anonymisierende Erhebung.

Unter **Einstellungen → Lager und Material → Filament → Geplante AMS-Trocknung**
kann pro Drucker ein täglicher Plan angelegt werden. Ein Plan enthält die lokale
Uhrzeit, eine IANA-Zeitzone, AMS-ID, Material, Temperatur, Dauer und optionales
Drehen des Fachs. Neue Pläne sind deaktiviert. Speichern eines deaktivierten Plans
sendet keinen Druckerbefehl. Die Vorlagen der bisherigen Feuchtigkeitssteuerung
bleiben separat; ein Tagesplan speichert seine eigenen Werte.

## Voraussetzungen

Aktivieren und jeder einzelne Start prüfen die tatsächliche Geräteverfügbarkeit:

- Aktiver, verbundener Drucker mit einem Modell und einer Firmware, die bereits
  von der bestehenden nativen Trocknungsfunktion unterstützt werden. Unbekannte
  Modelle oder fehlende beziehungsweise ungültige Firmware werden abgewiesen.
- Eine echte Firmware-Auskunft in der aktuellen MQTT-Verbindung identifiziert
  AMS 2 Pro (`n3f`, IDs 0–3) oder AMS HT (`n3s`, IDs 128–135) einschließlich
  AMS-Firmware. Beim Neuverbinden wird dieser Nachweis gelöscht. Ändert sich die
  Modulliste, werden die bisherigen Trocknungsbeobachtungen ungültig.
- Eine explizite Drucker-Leerlaufmeldung und ein expliziter Trocknungsstatus des
  Ziel-AMS dürfen höchstens 60 Sekunden alt sein. Das Ziel meldet `dry_time = 0`
  und eine leere, tatsächlich mitgesendete Liste von Trocknungshindernissen.
  Auch andere bekannte Heiz-AMS müssen frisch als gestoppt beobachtet sein.
  Fehlende Felder aus Teilmeldungen werden nicht als Leerlauf interpretiert.
- Kein Druck, keine Vorbereitung/Kalibrierung, kein passender wartender oder
  bereits beanspruchter Druckauftrag und keine andere Trocknungsreservierung.
  Andere automatische Trocknungsmodi müssen zunächst deaktiviert sein.

Für AMS 2 Pro gelten 45–65 °C, für AMS HT 45–85 °C; die Dauer beträgt 1–24 Stunden.
Materialname, Uhrzeit, Zeitzone, Ganzzahlen und boolesche Optionen werden auch auf
dem Server geprüft. Bereits gespeicherte Konfigurationen durchlaufen dieselbe
Validierung vor jedem Start.

Das **P2S mit Firmware 01.03.00.00 und AMS 2 Pro mit Firmware 05.00.22.22** ist ein
Kandidat für diese vorhandene native Funktion. Eine gespeicherte Modell- oder
Firmwareangabe ersetzt keine Live-Auskunft. Das **X1C mit Firmware 01.12.00.00
und klassischem AMS** darf keine native Heizung planen. Ein separater Sunlu-
Trockner wird durch diese Funktion weder gesteuert noch als AMS ausgegeben.
Mit nicht erreichbaren Geräten bleibt eine Aktivierung gesperrt. Die Softwaretests
ersetzen keine Prüfung der realen Trocknung auf der jeweiligen Hardware.

## Zeitzone, Zeitumstellung und verpasste Termine

Die Uhrzeit gilt in der gespeicherten IANA-Zeitzone, etwa `Europe/Berlin`, unabhängig
von der Server- oder Browserzeitzone. Die Docker-Laufzeit enthält `tzdata`;
Windows verwendet die bereits vorhandene Python-Abhängigkeit. Eine unbekannte
Zeitzone wird abgewiesen.

| Situation | Verhalten |
| --- | --- |
| Normaler Tag | Ein Startversuch im Fenster bis fünf Minuten nach der Uhrzeit. |
| Drucker/AMS fehlt, Warteschlange belegt oder andere Sperre | Der heutige Lauf wird mit Grund übersprungen. Kein späterer Nachholversuch. |
| Zeitumstellung im Frühjahr, z. B. Berlin 02:30 am 29.03.2026 | Die nicht existierende Uhrzeit wird übersprungen (`dst_gap`). |
| Zeitumstellung im Herbst, z. B. Berlin 02:30 am 25.10.2026 | Nur die erste Ausprägung der Uhrzeit zählt. Die zweite löst keinen weiteren Start aus. |
| PrintOps startet mehr als fünf Minuten nach dem Termin | Der heutige Lauf wird als verpasst protokolliert (`missed`). |
| Plan wird nach einem bereits protokollierten heutigen Lauf geändert oder erneut aktiviert | Für diesen Plan und lokalen Kalendertag entsteht kein zweiter Versuch. |
| Plan wird deaktiviert oder gelöscht | Zukünftige Läufe entfallen. Bereits beanspruchte Läufe und deren Reservierung bleiben nachvollziehbar. |

Das Fünf-Minuten-Fenster gilt auch über Mitternacht: ein Start um 00:00 für einen
23:59-Plan gehört zum vorherigen lokalen Tag. Es gibt keine Nachholung mehrerer
vergangener Tage. Nach einem längeren Ausfall protokolliert der erste Takt höchstens
den bereits fälligen aktuellen lokalen Tag.
Die Uhr des Servers muss stimmen. Zeitzonenregeln stammen aus der installierten
IANA-Datenbank; Betriebssystemupdates können zukünftige Regeln aktualisieren.

## Startbestätigung, Abschluss und Neustarts

Vor dem Senden wird der Lauf samt Parametern und exklusiver Druckerreservierung
in der Datenbank beansprucht. Die Kombination aus Plan und lokalem Kalendertag
ist eindeutig, ebenso die aktive Druckerreservierung. Druckauftrag-Claims,
manuelle Gerätesteuerung und automatische Trocknung verwenden dieselbe
Druckersperre. Ein Neustart darf einen bereits beanspruchten Lauf nicht erneut
senden, selbst wenn er zwischen Datenbank-Commit und MQTT-Veröffentlichung lag.
Manuelle Gerätesteuereingriffe entwerten den vorherigen Leerlauf- und
Trocknungsnachweis; danach muss neue Telemetrie die Verfügbarkeit bestätigen.

Nur für Tagespläne wird der bestehende `ams_filament_drying`-Befehl einmal mit
MQTT QoS 0 veröffentlicht. Dadurch gibt es keine QoS-1-Wiederholung nach einem
Verbindungsabbruch. Dieser bewusste Verzicht auf Zustellwiederholung kann einen
Start verlieren. Die bisherigen manuellen Befehle behalten ihren bisherigen QoS.
Es werden keine zusätzlichen Hardwarebefehle oder geänderten Temperaturprofile
eingeführt; `close_power_conflict` bleibt `false`.

Eine erfolgreiche Veröffentlichung bedeutet **noch nicht „Läuft“**. Erst eine
frische explizite positive Restzeit des Ziel-AMS, neuer als Beanspruchung und
Veröffentlichung, bestätigt einen laufenden Zyklus. Andere AMS-Einheiten,
zusammengeführte Cachewerte oder fehlende Restzeit bestätigen keinen Start.
Modultyp und AMS-Firmware müssen zur beanspruchten Einheit passen. Der Abschluss
benötigt anschließend eine neue explizite Meldung `dry_time = 0`. Verstrichene
Planzeit, 90 % der Dauer oder ein fehlender Wert gelten nicht als Abschluss.

Ohne Startbestätigung innerhalb von zwei Minuten, bei unklarer Veröffentlichung,
Verbindungsverlust oder unklaren Meldungen eines laufenden Zyklus lautet der
Status **Unklar**. Die Reservierung bleibt bestehen. Es erfolgt keine automatische
Wiederholung und keine erzwungene Unterbrechung des Druckers.

Die Drucker-/AMS-Stoppsteuerung bleibt für einen ausdrücklichen Stopp verfügbar.
Ein unklarer Lauf kann anschließend über **Reservierung freigeben** abgeschlossen
werden, sobald frische Meldungen Druckerleerlauf und gestoppte AMS bestätigen.
Diese Freigabe sendet keinen Gerätebefehl und zeichnet keinen erfolgreichen
Trocknungsabschluss auf. Ein aktueller Nullwert ohne vorher beobachteten Start
wird nur durch diese ausdrückliche Freigabe aufgelöst.

## Stromversorgung und Grenzen der Koordination

Alle automatischen SmartPlug-Abschaltwege prüfen die dauerhafte Reservierung:
Uhrzeitplan, verzögertes Abschalten, Temperaturabschaltung und Wiederaufnahme nach
einem Neustart. Ein für die Druckerversorgung markierter Plug bleibt eingeschaltet,
auch wenn der Drucker `IDLE` und eine kalte Düse meldet. Zubehörsteckdosen, die keine
Druckerversorgung steuern, folgen weiterhin ihrer eigenen Konfiguration. Eine
blockierte Abschaltung garantiert keinen neuen Abschalttermin nach Freigabe;
die Steckdose kann bis zur nächsten vorhandenen Automation eingeschaltet bleiben.

Die Reservierung koordiniert PrintOps. Druckertouchscreen, Bambu Studio, externe
MQTT-Clients, manuelle SmartPlug-Schalter und externe Hausautomationen können
außerhalb dieser Sperre handeln. Ein externer Druck führt zu einem unklaren Lauf;
PrintOps sendet deshalb keinen automatischen Stopp. Physische AMS-Wechsel und
gleichzeitige externe Bedienung benötigen weiterhin eine Prüfung am Gerät.

## API und Berechtigungen

Die Endpunkte liegen unter `/api/v1/printers/{printer_id}/drying/schedules`:
`GET` liefert Pläne, aktuelle Fähigkeiten und die letzten 30 Läufe; `POST` legt
einen Plan an; `PUT /{schedule_id}` ersetzt seine Konfiguration; `DELETE
/{schedule_id}` deaktiviert und entfernt den Plan aus der Liste. `POST
/runs/{run_id}/resolve` gibt eine nachweislich inaktive unklare Reservierung frei.

Lesen benötigt `printers:read`, Änderungen und Freigaben `printers:control`.
Benutzer- und API-Schlüsselbeschränkungen auf einzelne Drucker werden geprüft.
Authentifizierung, TLS und bestehende manuelle Modellgrenzen bleiben erhalten.

Beispiel eines gespeicherten, deaktivierten Plans; bei aktivierter Authentifizierung
ist ein dafür berechtigter Bearer-Token beziehungsweise API-Schlüssel erforderlich:

```json
{
  "ams_id": 0,
  "local_time": "06:30",
  "timezone": "Europe/Berlin",
  "filament": "PLA",
  "temperature": 45,
  "duration_hours": 4,
  "rotate_tray": false,
  "enabled": false
}
```
