# Geräteabnahme und Telemetrie-Nachweise

Diese Referenz trennt die Software-Abnahme von einer Gerätefreigabe. **PASS**
bedeutet, dass das genannte Kriterium durch Code und Regressionstests erfüllt ist.
**FAIL** benötigt einen beobachteten Widerspruch zum erwarteten Verhalten.
**BLOCKED** bedeutet, dass ein ausdrücklich erforderlicher Gerätenachweis fehlt;
fehlende Hardware ist kein fehlgeschlagener Test. **Nicht durchgeführt** bezeichnet
eine zusätzliche empfohlene Live-Prüfung ohne verpflichtendes Hardwarekriterium.

Die Bewertung bezieht sich auf den integrierten Stand `4d8db877` und die
Akzeptanzkriterien der unten verlinkten Issues. Sie ist keine Behauptung über
erfolgreich ausgeführte Druck-, Heiz- oder Trocknungsversuche.

## Abnahmematrix

| Issue | Erfüllte Software-Kriterien | Geräte-Nachweis | Entscheidung |
| --- | --- | --- | --- |
| [#126](https://github.com/ichwars/PrintOps/issues/126) | **PASS:** Displaymodell, Rohmodellcode und Firmware getrennt; 8-/32-elementige physische Arrays von kompakten, gruppierten, ungültigen und unparsebaren Werten unterschieden; unbestätigte Rack-IDs am MQTT-Dispatch unterdrückt; früher und verspäteter VP-Eingang getestet. | **BLOCKED:** Für jedes freizugebende `O1C`/`O1C2` fehlen Rohtelemetrie und erfolgreiche native/PrintOps-A/B-Drucke für feste, Rack- und gemischte Platten. | Offen lassen. Die leere H2C-Capability-Tabelle ist die erforderliche Produktionsgrenze. |
| [#150](https://github.com/ichwars/PrintOps/issues/150) | **PASS:** Die Voraussetzung #126 bleibt eigenständig; unbestätigte/mehrdeutige Mappings werden nicht versendet. Die neue Rack-/FTS-Bedien- und Routingfunktion ist nicht freigegeben. | **BLOCKED:** Gleiche drei A/B-Fälle sowie physische Rackposition, Hotend und AMS-/FTS-Zuführung fehlen. | Offen lassen. Keine neue Rack-/FTS-Auswahl ohne #126-Freigabe aktivieren. |
| [#147](https://github.com/ichwars/PrintOps/issues/147) | **PASS:** Ein dauerhafter Claim pro Plan/Tag, exklusive Druckerreservierung, passende Modell-/Firmware-/AMS-Grenzen, Konfliktgründe, echte Start-/Endbeobachtung, DST, Neustart, doppelte Ticks und deaktivierte Pläne. Der bestehende Trocknungsbefehl wird mit unveränderten Geräteparametern verwendet; nur Tagespläne nutzen QoS 0 gegen Wiederholung. | P2S/AMS 2 Pro: **nicht durchgeführt**. X1C/klassisches AMS: absichtlich ungeeignet; Sunlu gehört nicht zu dieser Funktion. | Software-Kriterien erfüllt; das Issue kann in diesem Umfang geschlossen werden. Eine lokale Geräteprüfung ergänzt den Nachweis, ist aber kein zusätzliches Issue-Kriterium. |
| [#148](https://github.com/ichwars/PrintOps/issues/148) | **PASS:** Standardmäßig aus; passende Folgeplatten und tatsächlich verwendete Filamente; absolute Höchstdauer ohne Verlängerung; Freigabe bei Queue-Ende, Abbruch, Fehler und übersprungenem Dispatch; manuelle Heizsitzungen erhalten; SmartPlug-Schutz getestet. | P2S/X1C: **nicht durchgeführt**. | Software-Kriterien erfüllt; das Issue kann geschlossen werden. Der begrenzte Bett-Warmhaltepfad erfüllt das Ziel einer passiv warmen Kammer. Ein aktiver Kammerheizer oder ein Live-Test wird im Issue nicht verlangt. |
| [#149](https://github.com/ichwars/PrintOps/issues/149) | **PASS:** Presets je Modell, lokale/Spoolman-Zuordnung, eindeutiger Kontext aus Drucker/Extruder/Durchmesser/HS/HH, mehrere Tabellen im Cache, unbekannte/mehrdeutige Kontexte gesperrt; Düsentausch und Migration/Fallback getestet. | **BLOCKED:** Das Issue verlangt ausdrücklich dokumentierte Telemetrie hardwareabhängiger Pfade. Der Betreiber kann die Geräteprüfung derzeit nicht durchführen; für P2S/X1C fehlen reale Antworten und Zuordnungsnachweise. H2-Hotend-/Racknummern bleiben unbestätigt. | Offen lassen. Softwarefortschritt vollständig dokumentieren; keine unbekannte physische Hotendnummer ableiten. |

Für #147 ist die geplante Freigabe strenger als die allgemeine Anzeige
`supports_drying`: Ein Eintrag in der bestehenden Mindestfirmware-Tabelle,
eine gültige vierteilige Version und ein in der aktuellen Verbindung tatsächlich
gemeldetes Heiz-AMS sind erforderlich. Eine erfolgreiche Veröffentlichung oder
ein positives Command-Receipt erfüllt weder „Trocknung läuft“ noch „Druck läuft“.

## Exakte Vergleichskonfigurationen

| Vergleich | Angegebener Stand | Zu erfassender Nachweis | Erwartete Grenze |
| --- | --- | --- | --- |
| P2S + AMS 2 Pro | Drucker `01.03.00.00`, AMS `05.00.22.22` | Displaymodell `P2S`, tatsächlich gemeldeter Rohcode (Registry-Alias `N7` nur bei realem Nachweis), `ota.sw_ver`, `n3f/<id>.sw_ver`, explizite AMS-ID und Restzeit. | Kandidat für bestehende native Trocknung: P2S-Minimum `01.02.00.00`, `n3f` ID 0–3, 45–65 °C. Fehlende/alte Beobachtung sperrt den Start. Bett-Warmhalten ist modellseitig zulässig. |
| X1C + klassisches AMS + separater Sunlu | Drucker `01.12.00.00`; AMS-Firmware noch nicht belegt | Displaymodell `X1C`, tatsächlicher Rohcode (Registry-Alias `BL-P001` nur bei realem Nachweis), `ota.sw_ver`, `ams/<id>.sw_ver`, Düsen-/Kalibrierungsantworten. | Die Druckerfirmware allein erlaubt keinen Plan für das klassische `ams`-Modul: `unsupported_ams`. Sunlu wird weder angesteuert noch als Heiz-AMS ausgegeben. Bett-Warmhalten ist modellseitig zulässig. |
| H2C/O1C | Kein Gerät verfügbar | `H2C` und tatsächliches `O1C`, exakte Firmware, feste/Rack/gemischte native Payloads und A/B-Drucke. | Kein freigegebenes physisches `nozzle_mapping`. |
| H2C/O1C2 | Kein Gerät verfügbar | `H2C` und tatsächliches `O1C2`, exakte Firmware, feste/Rack/gemischte native Payloads und A/B-Drucke. | Eigenständige Freigabe erforderlich; ein O1C-Nachweis gilt nicht automatisch für O1C2. |

Die upstream erwähnte H2C-Firmware `01.02.00.00` ist keine PrintOps-Freigabe und
kein nachgewiesenes Minimum für Rack-IDs. Die Firmwaregrenze bleibt für jeden
Rohcode leer, bis der [H2C-Dispatch-Audit](h2c-nozzle-mapping-dispatch-audit.md)
vollständig erfüllt ist. Für HS/HH und Düsendurchmesser werden die tatsächlich
gemeldeten Werte festgehalten; Modellnamen ersetzen diese Daten nicht.

## Lesende Erhebung auf der erreichbaren lokalen Installation

Die Erhebung erfolgt auf einem Rechner, der die bestehende PrintOps-Installation
erreicht. Ein Timeout aus einer entfernten Entwicklungsumgebung beweist keinen
Gerätefehler. Ein erneuter Test derselben nicht erreichbaren LAN-Strecke liefert
keinen Abnahmenachweis.

Das folgende Python-Programm fragt die vorhandenen GET-Endpunkte ab. Es aktiviert
keine Protokollierung, stellt keine Temperatur ein, startet keinen Druck und
sendet keinen Trocknungs- oder Bewegungsbefehl. URL und vorhandener Bearer-Token
werden verdeckt eingegeben und nicht ausgegeben. Leere Token-Eingabe ist für
Installationen ohne aktivierte Authentifizierung möglich. Bestehende TLS-Prüfung
und Berechtigungen bleiben wirksam; benötigt wird `printers:read`.

```bash
python - <<'PY'
import getpass
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

base = getpass.getpass("PrintOps-Basis-URL inklusive /api/v1: ").rstrip("/")
parsed = urlparse(base)
if parsed.scheme not in ("http", "https") or not parsed.netloc:
    raise SystemExit("Ungültige Basis-URL")
printer_id = getpass.getpass("Lokale Drucker-ID: ").strip()
if not printer_id.isdigit():
    raise SystemExit("Die Drucker-ID muss numerisch sein")
token = getpass.getpass("Vorhandener Bearer-Token (sonst leer): ")
headers = {"Accept": "application/json"}
if token:
    headers["Authorization"] = "Bearer " + token
capture = Path(tempfile.mkdtemp(prefix="printops-private-capture-"))
os.chmod(capture, 0o700)
for label, suffix in [("model", ""), ("status", "/status"),
                      ("drying", "/drying/schedules"), ("mqtt", "/logging")]:
    request = Request(base + "/printers/" + printer_id + suffix, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            value = json.load(response)
    except HTTPError as error:
        print(label + ": HTTP " + str(error.code))
        continue
    except (URLError, TimeoutError):
        print(label + ": Verbindung nicht verfügbar")
        continue
    if label == "model":
        value = {key: value.get(key) for key in ("model", "model_code", "firmware_version")}
    envelope = {"captured_at": datetime.now(timezone.utc).isoformat(), "data": value}
    with os.fdopen(os.open(capture / (label + ".json"),
                           os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
        json.dump(envelope, output, ensure_ascii=False, indent=2)
print("Privater Nachweisordner: " + str(capture))
PY
```

`status` ist eine zusammengeführte Sicht und ersetzt keine explizite
Firmwaremeldung. `mqtt` enthält nur vorhandene, begrenzte Logeinträge. Wenn
`logging_enabled` falsch ist oder die relevanten Frames fehlen, ist der Nachweis
unvollständig. Der Gerätebetreiber kann die bestehende MQTT-Protokollierung in
PrintOps lokal einschalten; das ändert die Logerfassung und sendet keinen
Heiz-/Bewegungsbefehl. Direkte Publish-Pfade sind dort nicht vollständig als
ausgehende Frames erfasst. Insbesondere die vollständige Trocknungs-Sendmeldung
und Geräteantwort stehen im bestehenden Anwendungslog auf INFO; der bestehende
Bett-G-Code wird auf DEBUG protokolliert. Aus fehlenden Logzeilen darf kein
Nachweis „kein Befehl gesendet“ abgeleitet werden.

Eine Status-Aktualisierung mit `pushall`/`get_version` oder eine K-Profil-Abfrage
ist eine zusätzliche lesende Geräteabfrage. Sie benötigt eine erreichbare
MQTT-Verbindung. Der bestehende Endpunkt
`GET /api/v1/printers/{id}/kprofiles/?nozzle_diameter=0.4` benötigt
`kprofiles:read` und sendet `extrusion_cali_get`; er verändert keine Kalibrierung.
Für #149 nacheinander `0.4`, `0.6`, anschließend nochmals `0.4` abfragen und die
jeweilige Geräteantwort samt Sequenz-ID aufzeichnen. Die Anzeige nach der
anderen Durchmesserabfrage muss weiterhin den tatsächlich eingebauten Kontext
auflösen. Leere Antworten und unbekannte Metadaten nicht mit erfundenen
Kalibrierungen auffüllen.

### Anonymisierung vor Veröffentlichung

Der Nachweisordner bleibt privat. Die Status- und Logdateien können Geräte- und
AMS-Seriennummern, MQTT-Topics sowie benannte Jobs/Presets enthalten. Für jeden
Vergleich eine gesonderte veröffentlichbare Kopie erstellen und kontrollieren:

1. IPs, Hostnamen, URLs mit Zugangsdaten, Zugangscodes, API-/Cloud-Token,
   Autorisierungsheader und Benutzerkennungen vollständig entfernen.
2. Drucker-, AMS- und Düsenseriennummern, RFID-Tag-/Spulen-UUIDs und den seriellen
   Teil von MQTT-Topics durch stabile Aliase ersetzen, z. B. `printer-A`,
   `ams-A`, `hotend-A`, `job-A`. Eigene Datei-, Job-, Profil- und Materialnamen
   ebenfalls anonymisieren. Dieselbe Identität erhält in A und B denselben
   Alias; Rohcode und Displaymodell sind keine Seriennummern.
3. Für den technischen Vergleich Zeitstempel, Sequenz-IDs, numerische
   AMS-/Tray-/Extruder-/Rackpositionen, Arraylänge und -reihenfolge, `-1`,
   Firmwareversionen, Durchmesser, ausdrücklich gemeldete HS-/HH-Kennungen,
   K-Werte, Command-Namen und Ergebnis-/Hinderungsfelder erhalten. Fehlende
   Felder fehlen auch in der Kopie; nicht in `0`, `false` oder `[]` umwandeln.
4. Nur die relevanten JSON-Frames und eine anonymisierte Zuordnungstabelle
   veröffentlichen, keine Support-Bundles oder vollständigen privaten Ordner.
   Freitext, unerkannte Felder und eingebettete URLs ebenfalls prüfen. Eine
   native Bambu-Studio-Aufzeichnung folgt denselben Regeln.

Eine Datei mit Platzhalterwerten illustriert nur das Format und ist kein
Gerätenachweis. Die unveränderte private Aufzeichnung bleibt die Quelle für die
anonymisierte Kopie.

## Erwartete Receipts und Zustandsfolgen

| Fall | Zu vergleichen | PASS / FAIL |
| --- | --- | --- |
| Geräteidentität | `info.command = get_version`, `module[].name`, `sw_ver`; Rohmodellcode aus realer Discovery/Geräteauskunft separat zur gespeicherten Modellangabe. | **PASS:** exakter Stand und Heiz-AMS eindeutig. **BLOCKED:** keine Antwort, Modellcode fehlt oder nur ein gespeicherter Wert liegt vor. |
| Geplante Trocknung | Ein `print.command = ams_filament_drying` mit Ziel-AMS, `temp`, `duration`, `mode = 1`, `rotate_tray`, `close_power_conflict = false`; korrespondierende Firmwareantwort samt `result`/Hinderungsfeldern. | Receipt/Publish allein bestätigt keinen Start. **PASS:** nach Claim/Publish frische explizite positive `dry_time` derselben Einheit, später frische explizite `dry_time = 0`; Lauf `awaiting_ack → running → completed`. **FAIL:** Wiederholung desselben Tagesclaims oder Start auf ungeeigneter Einheit. |
| Unklarer Trocknungsstart | Fehlende Startbestätigung, Verbindungsabbruch oder widersprüchliche Meldung. | **PASS:** `uncertain` mit Grund, Reservierung bleibt, kein automatischer Retry/erzwungener Stopp. Ein aktueller Nullwert ohne vorherigen Start wird nicht als erfolgreicher Abschluss ausgegeben. |
| Bett-Warmhalten | Bestehender `gcode_line` mit `M140 S<ausgewählter Bettwert>` und nach Freigabe `M140 S0`; Eigentumsdatei mit absolutem `expires_at` und `purpose = keep_warm`. | **PASS:** ein Hold, kein erneuertes Zeitbudget; Gerät meldet den Zielwert bzw. anschließend 0. Auf P2S/X1C kein zusätzlicher `M141`-/Düsenbefehl. **FAIL:** neue Hold-Frist durch gewöhnlichen Tick oder weiter gehaltene eigene Heizung nach endgültiger Freigabe. |
| Dispatch-Übergabe | `project_file` und nachfolgender realer Gerätestatus `PREPARE`, `SLICING`, `RUNNING` oder `PAUSE`. | **PASS:** Ownership wird erst durch den tatsächlichen Druckstart übergeben; Upload/Publish allein genügt nicht. Danach keine Abschaltung der Druckheizung. |
| K-Profile | `extrusion_cali_get` nach Durchmesser; Antwort mit Sequenz-ID, `nozzle_diameter`, `filaments[].cali_idx`, `extruder_id`, `nozzle_id`, `k_value`; installierte Düse und berichtete Flow-Kennung. | **PASS:** andere Durchmesser bleiben im Cache, K nur im eindeutig passenden Kontext. **FAIL:** gleicher Index wählt anderen Extruder/Durchmesser/Flow. Fehlende Zuordnung bleibt ohne automatische Auswahl. |
| H2C-Routing | Native `project_file`, VP-Eingang, gespeicherter Queuewert und PrintOps-Publish je fester/Rack/gemischter Platte. | Vor Freigabe **PASS** der Grenze nur bei fehlendem physischem `nozzle_mapping` und sichtbarem Fallback. **BLOCKED** für produktive Gerätefreigabe, bis alle drei realen A/B-Drucke erfolgreich sind. |

Der MQTT-Timestamp beweist für Trocknung nur dann einen neuen Zustand, wenn der
Frame selbst das relevante `dry_time` enthält. Zusammengeführte Cachewerte,
Restlaufzeit anderer AMS, verstrichene Planzeit oder „90 % fertig“ sind keine
Start-/Endbestätigung. Status-Zieltemperaturen können unmittelbar nach einem
Befehl lokal optimistisch sein; für die Gerätewirkung einen neuen eingehenden
Frame oder die tatsächliche Geräteanzeige dokumentieren.

## Lokale, vom Betreiber beaufsichtigte Vergleichsschritte

Diese Schritte sind eine Anleitung für einen späteren kontrollierten Versuch,
kein automatisch ausgeführter Geräteauftrag. Der Betreiber wählt bekannte,
bereits funktionierende Dateien, passende Materialien und deren vorhandene
Temperaturvorgaben; es werden keine Temperaturen für die Abnahme erfunden.

1. **Lesende Basis:** Obige Erhebung durchführen, reale Versionen und Modularten
   vergleichen. Bei Offline-, unbekanntem oder altem Zustand bleibt der Versuch
   gesperrt. Klassisches X1C-AMS und Sunlu nicht in einen nativen Heiztest aufnehmen.
2. **P2S-Trocknung, optional für #147:** Erst auf physisch freiem, ruhendem Gerät
   mit bestätigtem AMS 2 Pro und deaktivierten konkurrierenden Trocknungsmodi
   einen Plan über die vorhandene Oberfläche einrichten. Parameter nach der
   vorhandenen Material-/Gerätefreigabe wählen. Vorher deaktiviert speichern
   und nachweisen, dass dies keinen Gerätebefehl auslöst; dann bewusst aktivieren.
   Einen Termin beobachten, Receipt sowie Start/Endtelemetrie erfassen. Ohne
   Startnachweis nicht erneut senden. Bei unklarem Lauf erst Gerät prüfen und
   gegebenenfalls über die vorhandenen Bedienelemente stoppen; Reservierung nur
   nach frischen Leerlauf-/Nullmeldungen ausdrücklich freigeben. DST/Crash und
   Netzunterbrechungen bleiben Softwaretests; keinen laufenden Heizversuch dafür
   absichtlich unterbrechen.
3. **P2S/X1C-Warmhalten, optional für #148:** Zunächst Opt-in aus lassen und
   bisherigen Ablauf beobachten. Für den zweiten Vergleich gewöhnliche
   Vorheizung und Plate-clear-Bestätigung einschalten, zwei bekannte kompatible
   Folgeplatten zuweisen, Opt-in bewusst einschalten und maximal eine Minute
   Hold wählen. Nach dem ersten tatsächlichen FINISH wartet die Folgeplatte auf
   Plate-clear; den Hold und seine unveränderte Deadline beobachten. In getrennten
   Durchläufen Zeitbudget ablaufen lassen, Folgejob entfernen oder abbrechen;
   jeweils bed-eigenen Zielwert 0 und freigegebene Ownership erwarten. Die Platte
   nur am Gerät prüfen/freigeben; keine Bewegung automatisiert auslösen. Bei einer
   unklaren Ownership nach Neustart das Gerät selbst prüfen und den vorhandenen
   Temperaturregler verwenden, statt eine fremde Heizsitzung auszuschalten.
4. **P2S/X1C-K-Kontext, verpflichtend für #149:** Lesende Tabellenabfragen mit den
   tatsächlich vorhandenen Kalibrierungen vergleichen. Für lokale Zuordnung,
   RFID-/Tag und Spoolman getrennt den gespeicherten Kontext und die ausgesendete
   Auswahl dokumentieren. Fehlender K-Kontext muss auf keine automatische
   Kalibrierung fallen. HS/HH oder Düsentausch nur testen, wenn die passende
   Hardware tatsächlich vorhanden ist; einen Tausch nach Herstellerablauf am
   abgekühlten Gerät vornehmen. Kein fehlendes High-Flow-Hotend simulieren und
   anschließend als Hardware-PASS melden. H2-Rack-Kontexte bleiben gesperrt.
5. **H2C, verpflichtend für #126/#150:** Ohne Gerät endet die Abnahme bei
   **BLOCKED**. Auf zukünftiger Hardware zuerst Modell/Rohcode/Firmware sowie
   die drei nativen Payloads lesend erfassen. Vor dem PrintOps-A/B-Druck den
   vollständigen Dispatch-Audit und eine auf diesen Rohcode/Firmwarestand
   begrenzte Änderung prüfen. Die Produktionsgrenze nicht allein zu Testzwecken
   umgehen. Der reale Vergleich muss Cleaning, ABL, richtige Düse/Zuführung,
   erste Schicht und endgültige Teileplatzierung zeigen. Jede neue freigegebene
   Variante benötigt ihre eigene nachvollziehbare Vergleichsaufzeichnung.

## Wiederholbare Softwareprüfung

Die relevanten vorhandenen Suites verwenden synthetische MQTT-Frames, Mock-
Transporte und isolierte Datenbanken. Sie senden keine physischen Gerätebefehle.
Aus dem Repository-Stamm mit der eingerichteten Testumgebung ausführen:

```bash
python -m pytest -q \
  backend/tests/unit/test_h2c_nozzle_mapping_guard.py \
  backend/tests/unit/services/test_bambu_mqtt.py::TestStartPrintNozzleMappingDispatch \
  backend/tests/unit/services/test_virtual_printer.py::TestVirtualPrinterInstance::test_add_to_print_queue_captures_nozzle_mapping \
  backend/tests/unit/services/test_virtual_printer.py::TestVirtualPrinterInstance::test_on_print_command_late_mqtt_retroactively_stamps_queue_item \
  backend/tests/unit/services/test_virtual_printer.py::TestVirtualPrinterInstance::test_add_to_print_queue_catches_mqtt_stashed_post_wait_timeout \
  backend/tests/unit/test_calibration_context_149.py \
  backend/tests/integration/test_spool_filament_presets_149.py \
  backend/tests/unit/test_queue_keep_warm.py \
  backend/tests/unit/test_queue_keep_warm_lifecycle.py \
  backend/tests/unit/test_preheat_ownership.py \
  backend/tests/unit/test_preheat_rollback.py \
  backend/tests/unit/test_preheat_used_slots.py \
  backend/tests/unit/test_preheat_smart_plug_guard.py \
  backend/tests/unit/test_drying_heater_crossflow.py \
  backend/tests/unit/services/test_scheduled_drying.py \
  backend/tests/unit/services/test_scheduled_drying_time.py \
  backend/tests/unit/services/test_scheduled_drying_telemetry.py \
  backend/tests/unit/services/test_drying_ownership.py \
  backend/tests/integration/test_drying_schedules_api.py \
  backend/tests/integration/test_queue_keep_warm_settings.py
```

Zusätzlich deckt `backend/tests/postgres/test_issue_149_k_profile_contexts.py`
die PostgreSQL-Migration ab; hierfür ist die separate isolierte PostgreSQL-
Testumgebung erforderlich. Datenbank-/Transporttests sind kein Ersatz für die
in #126, #150 und #149 ausdrücklich geforderten Gerätenachweise.
