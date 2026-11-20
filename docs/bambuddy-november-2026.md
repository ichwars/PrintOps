# Druckbetrieb, Spulen und Geräte / Printing, spools and devices

## Deutsch

### Warteschlange und Archiv

Im Dateimanager mehrere geslicte 3MF-Dateien markieren und **Drucken** wählen. **Einzelaufträge** erzeugt je ausgewählter Datei einen Auftrag. Platte, Reihenfolge, Zielgerät oder Modell und Menge vor dem Absenden prüfen. Bei einem Teilfehler zeigt die Auswahl die noch ausstehenden Dateien. Erneutes Absenden setzt dort fort. **Alternativen** bündelt Dateien für verschiedene Druckermodelle in einem Auftrag. Die erste passende Maschine übernimmt ihn.

Bei einer Modellzuweisung haben Kompatibilität, verfügbarer Drucker, Standort, Filament und erzwungene Farbübereinstimmung Vorrang. Bei gleich geeigneten Maschinen entscheiden die wenigsten Betriebsstunden einschließlich Wartungsoffset, dann die Geräte-ID. Bei einem fest zugewiesenen Gerät bleibt die Auswahl verbindlich. Ist kein geeignetes Gerät online, kann die Warteschlange einen passenden Drucker über seine ausdrücklich zugeordnete, für Auto-Ein aktivierte Stromversorgung starten. Nach dem Aufwecken prüft der nächste Warteschlangendurchlauf Material, Farbe und Menge anhand der aktuellen Druckerdaten. Nach einem fehlgeschlagenen Einschaltversuch wartet sie für diesen Drucker fünf Minuten.

Ein nach Pause oder Stromausfall fortgesetzter Druck behält seine Auftragszuordnung, sofern Datei und Lauf identifizierbar sind. Meldet die 3MF für einen Slot ausdrücklich null Gramm, bucht PrintOps für diesen Slot beim Frühabbruch keinen geschätzten Verbrauch aus dem Reststand. Bei aktivierter automatischer Zeitrafferarchivierung versucht PrintOps auch nach einem Fehldruck oder Abbruch, das zum Lauf gehörende Druckervideo abzurufen. Die Verfügbarkeit hängt vom Drucker und seiner SD-Karte ab.

Beim erneuten Öffnen einer exportierten 3MF in Bambu Studio bleiben unterstützte, abweichende Prozesseinstellungen gegenüber dem Standardprofil als Änderungen gekennzeichnet. Dies gilt auch für öffentliche Standardprofile aus der Cloud. Beim Wiederherstellen eines Windows-Backups auf Linux werden unterstützte relative Dateipfade an das Zielsystem angepasst.

### SpoolBuddy, AMS und Kalibrierung

Im SpoolBuddy-Kiosk das zugehörige Gerät auswählen. Die Auswahl wird in diesem Browser gespeichert. Zum Schreiben den Tag bis zum Abschluss der Rückleseprüfung am Leser lassen. Bei einer fehlenden Bestätigung den Vorgang mit demselben Tag erneut ausführen. Ein bereits verknüpfter Tag kann einer anderen Spule zugewiesen werden. Dabei wird die alte Verknüpfung gelöst, auch an archivierten Spulen. NTAG213 verwendet OpenTag3D v1. Bei ausreichender gemeldeter Kapazität verwenden NTAG215 und NTAG216 OpenTag3D 2.004. Für das neue Format auch den SpoolBuddy-Daemon aktualisieren.

Bei A1 und A1 mini bleiben bereits gemeldete Felder der externen Spule bei Teilmeldungen erhalten. Für A2L mit unterschiedlichen AMS-Typen werden Einheiten numerisch geordnet. Bei einem stehenden Timer eines automatisch gestarteten Trockenzyklus kann PrintOps nach der Wartezeit erneut starten. Wiederholtes Ausbleiben des Fortschritts löst eine Druckerfehlermeldung aus.

Der H3C verwendet neun Plätze im AMS 3H und externe Eingänge je Hotend. Auch über einen fest zugeordneten virtuellen Drucker eingereichte Slicer-Aufträge behalten die Auswahl des externen Eingangs. Für Lagerzuordnungen die angezeigte Slotnummer verwenden. Die AMS-3H-Trockenzone umfasst die vom Drucker gemeldeten Plätze. Die Karte zeigt die Temperatur am montierten Werkzeug. Modellspezifische kalendarische Wartungsintervalle beginnen mit dem Anlagedatum. Beim H2C zeigt die Düsenansicht zusätzlich die vom Gerät gemeldeten Nutzungsstunden. Das PrintOps-Freigabeverfahren für den H2C-Dispatch sowie für K-Profile auf P2S/X1C ist in der [Hardwareabnahme](hardware-acceptance.md) dokumentiert.

### Kamera, WLED und Profilvorgaben

In der Kamerawand lassen sich Steuerelemente bei Bedarf oder dauerhaft einblenden. Angemeldete Bediener sehen die für sie erlaubten Aktionen. Der Kioskzugang dient der Anzeige. Druckerstörungen werden nach einem Neustart weiterhin entprellt. Bei Supportexporten bleibt die Modellbezeichnung lesbar.

Unter **Einstellungen → Integrationen → Smart Home** den Drucker und die lokale HTTP(S)-Adresse des WLED-Controllers angeben. Verbindung testen, vorhandene Presets laden und den gewünschten Zuständen zuordnen. Ein Preset-Test schaltet die LEDs sofort. Die automatische Anzeige muss für jeden Drucker aktiviert werden. Eine leere Zuordnung überspringt diesen Zustand. Der optionale Fertig-Timer wechselt anschließend zum zugewiesenen Leerlauf-Preset. Verwaltung erfordert das Recht zum Bearbeiten des betreffenden Druckers.

Unter **Lager und Material → Kataloge** können bearbeitbare Filamentprofil-Vorgaben für den aktiven Lagermodus gesammelt angewendet werden. Die Rückmeldung zeigt erfolgreiche Anwendungen und Fehler. Änderungen an Düsenkalibrierungen auf echten Geräten weiterhin nach der Hardwareabnahme prüfen.

## English

### Queue and archive

Select several sliced 3MF files in File Manager and choose **Print**. **Separate jobs** creates an independent job per file. Check each plate, the list order, target printer or model, and quantity before submitting. If a submission fails partway through, the remaining selection can be retried. **Alternatives** groups files sliced for different printer models into one job for the first suitable printer.

Model assignments respect availability, location, material and forced color matches. Equally suitable machines are ranked by operating hours including the maintenance offset, then by printer ID. An explicit printer assignment retains its target. If no eligible printer is online, the queue can start a matching printer through its assigned, auto-on power supply. After wake-up, the next queue pass checks material, colour and quantity against fresh printer data. After a failed power-on attempt, it waits five minutes before retrying that printer.

When a print resumes after a pause or power interruption, PrintOps retains the queue association if it can identify the file and run. An explicit zero-gram value for a 3MF slot prevents estimated remaining-spool consumption from being charged after an early failure. With automatic timelapse archiving enabled, a failed or aborted run can also retrieve its own video if the printer SD card provides one.

Supported process overrides in exported 3MFs are marked as modified when reopened in Bambu Studio, including overrides against public cloud stock presets. Restoring a Windows backup on Linux converts supported relative file paths for the destination system.

### SpoolBuddy, AMS and calibration

Choose the local device on each SpoolBuddy kiosk. The browser remembers the selection. Keep the tag on the reader until verification finishes. If confirmation fails, retry with the same tag. Reassigning a tag clears the previous spool link, including links on archived spools. NTAG213 uses OpenTag3D v1. NTAG215 and NTAG216 use OpenTag3D 2.004 when their reported capacity permits. Update the SpoolBuddy daemon to write the new format.

Partial A1 and A1 mini updates retain previously reported external spool fields. Mixed A2L configurations order AMS units numerically. PrintOps can retry a stalled countdown after a waiting period for a drying cycle it started automatically. Repeated lack of progress generates a printer error notification.

The H3C has nine AMS 3H slots and per-hotend external inputs. Slicer jobs submitted through a virtual printer bound to that H3C retain the selected external input. Use the displayed slot number when assigning spools. The printer reports which slots share its drying zone. The printer card shows the mounted hotend temperature. Model-specific calendar maintenance starts on the date the printer was added. On H2C the nozzle display shows usage hours when the firmware reports them. The [hardware acceptance guide](hardware-acceptance.md) tracks H2C dispatch and P2S/X1C calibration verification.

### Cameras, WLED and profile defaults

Camera wall controls can appear on demand or stay visible. Signed-in operators see actions permitted for their printers. The kiosk link provides viewing access. Printer fault notification deduplication survives restarts. Support exports retain the printer model name.

In **Settings → Integrations → Smart Home**, select a printer and enter the local HTTP(S) controller address. Test connectivity, load the existing presets and map them to states. Testing a preset immediately changes the LEDs. Enable automatic updates per printer. Unmapped states are skipped. An optional finished timer switches to the mapped idle preset. Management requires permission to update the selected printer.

In **Warehouse and material → Catalogs**, apply writable filament profile defaults together for the active inventory mode. The result reports successful applications and failures. Follow the hardware acceptance guide when validating nozzle calibration changes on real printers.

## Änderungen nach Priorität / Changes by priority

Die Nummern lassen sich einzeln mit dem jeweiligen Bambuddy-Commit abgleichen. Die Anleitung oben beschreibt die Bedienung. Each number links to the corresponding Bambuddy change. The sections above explain how to use it.

| Nr. | Deutsch | English |
| --- | --- | --- |
| [1](https://github.com/maziggy/bambuddy/commit/baaaf0c9e5793e1cec8e0388f0808a943690dfba) | Verbrauch beim Frühabbruch für ausdrücklich mit 0 g geslicte Slots korrigiert. | Skip remaining-weight estimates for explicitly zero-gram slots after an early failure. |
| [2](https://github.com/maziggy/bambuddy/commit/a071344f72cabdea66b3a6c2aba44a22e5d7b93c) | Dateinamen eines fortgesetzten Drucks der bestehenden Warteschlangenposition zuordnen. | Match the resumed filename to the existing queue item. |
| [3](https://github.com/maziggy/bambuddy/commit/f34f939215517cf00e114147b11f95f2b719e796) | Druckbeginn auch beim Übergang von einer Startpause in den laufenden Druck erfassen. | Recognize a print starting when its initial pause ends. |
| [4](https://github.com/maziggy/bambuddy/commit/d510138502887bc9e5d92c00632d27eb181227a7) | SQLite-Verbindung bei abgebrochenen Kameralesevorgängen zuverlässig schließen. | Close the SQLite connection reliably after a cancelled camera read. |
| [5](https://github.com/maziggy/bambuddy/commit/b5321c141a90ad9fbc4166fb867ba9dfc1970afd) | SQLite-Kompatibilitätskorrektur auch mit älteren Treibern ohne Stop-Methode starten. | Allow startup with older SQLite drivers that lack the stop method. |
| [6](https://github.com/maziggy/bambuddy/commit/5297f53d2b8e96aabfdcdafdcad9a88023f48ab3) | Kameralesevorgänge und Sitzungsfreigabe gegen Abbruch abschirmen und typprüfen. | Type-check the cancellation shields around camera database access and session cleanup. |
| [7](https://github.com/maziggy/bambuddy/commit/2cead599db47ac17cf49044d92f975897578362f) | Relative Dateipfade nach vollständiger Windows-Wiederherstellung auf Linux oder macOS übertragen. | Translate relative paths after a full Windows backup restore on Linux or macOS. |
| [8](https://github.com/maziggy/bambuddy/commit/b6be777e875bb057e6932c7887e45a474e86da20) | Die feste Liste der Restore-Tabellen und Spalten für die statische SQL-Prüfung dokumentieren. | Document the fixed restore tables and columns for static SQL analysis. |
| [9](https://github.com/maziggy/bambuddy/commit/a2079371ad9cf8590881bd8d5c1511c052e4e3f8) | NFC-Nutzdaten ab der korrekten Speicherseite schreiben. | Write NFC payloads starting on the correct memory page. |
| [10](https://github.com/maziggy/bambuddy/commit/da963731cca8a55496bdfdab4553296c0076d1cc) | Tag-Kennung vor dem Schreiben und Daten beim Rücklesen prüfen. | Verify the tag identity before writing and read back the payload. |
| [11](https://github.com/maziggy/bambuddy/commit/d6b006cb0543f3e45c8f4abc7f732794e85a58d9) | Tagbindung von einer alten oder archivierten Spule auf die neue Spule übertragen. | Transfer a tag association even when the previous spool is archived. |
| [12](https://github.com/maziggy/bambuddy/commit/a5f15313c25e8caa18211cf92b4a2ea2684469e3) | Den SpoolBuddy-Kiosk an das gewählte Gerät binden. | Bind the SpoolBuddy kiosk to the selected device. |
| [13](https://github.com/maziggy/bambuddy/commit/ebfc0efa859e6d993444830ab5083400b9d36524) | Bei A1 und A1 mini frühere Spulendaten bei Teilmeldungen erhalten. | Preserve A1 and A1 mini external spool fields across partial updates. |
| [14](https://github.com/maziggy/bambuddy/commit/e6b2b6f7e99bd62d03b59b68a9065aa76111a6fd) | Gemischte AMS-Einheiten beim A2L zuordnen und Speichereinschränkungen kenntlich machen. | Handle mixed AMS units on the A2L and identify unsupported storage. |
| [15](https://github.com/maziggy/bambuddy/commit/5be58d7f14fe00732e34dad7e5165fdafdd201d6) | Eigene automatische Trocknung bei stehendem Countdown begrenzt neu versuchen. | Retry a stalled automatic drying cycle started by PrintOps, with a bounded retry. |
| [16](https://github.com/maziggy/bambuddy/commit/e0955820fcc02ba9caf497a2a0d525fd843a7f85) | Erledigte Druckerfehler beim Statuswert null aus der Anzeige entfernen. | Clear resolved printer errors when the reported error resets to zero. |
| [17](https://github.com/maziggy/bambuddy/commit/7dbf02632ebff6b1bce92a673ed88f1c512dcd51) | Bereits gemeldete HMS-Fehler speichern und betroffene Baugruppen korrekt benennen. | Persist previously notified HMS faults and identify the affected modules. |
| [18](https://github.com/maziggy/bambuddy/commit/c691d2e90584ecf191ee7bd1fbffa6efa7bdd977) | Den HMS-Meldestatus auch in einer neuen Datenbank beim Anwendungsstart anlegen. | Create the HMS notification table on startup for new databases. |
| [19](https://github.com/maziggy/bambuddy/commit/0ef31fb43e0f46975e0dbe5fc15b21d675f76635) | Automatischen Zeitrafferabruf auch nach Fehldruck und Abbruch versuchen. | Attempt automatic timelapse retrieval for failed and cancelled prints. |
| [20](https://github.com/maziggy/bambuddy/commit/c147ec6e9a86067dac34da0c00abdc5ba075f7fc) | Abweichungen vom mitgelieferten Standard-Prozessprofil in der exportierten 3MF kennzeichnen. | Record process overrides against bundled stock presets in exported 3MF files. |
| [21](https://github.com/maziggy/bambuddy/commit/f3f58c57c4cc9718842518fa906462db6a76a3d7) | Die Kennzeichnung für öffentliche Bambu-Standardprofile aus der Cloud ergänzen. | Extend override tracking to Bambu stock presets from the cloud. |
| [22](https://github.com/maziggy/bambuddy/commit/1f6b709075a8d2e359ff2335ab63ed8ce02e373a) | Mehrere geslicte Dateien als getrennte Aufträge einreihen und einen Teilfehler fortsetzen. | Queue separate jobs for multiple sliced files and resume after partial success. |
| [23](https://github.com/maziggy/bambuddy/commit/a9f752ea63bbc25ed460393b9aa3c2e00705c48f) | Bei gleich geeigneten Modelldruckern die Maschine mit den wenigsten Betriebsstunden wählen. | Select the least-used printer among equally eligible model matches. |
| [24](https://github.com/maziggy/bambuddy/commit/c8fb2c7ead7c46b8452d3a4b4be2305aa674e468) | H3C mit neun AMS-3H-Slots, Werkzeugplätzen und externen Eingängen abbilden. | Represent the H3C with nine AMS 3H slots, tool positions and external inputs. |
| [25](https://github.com/maziggy/bambuddy/commit/6481f81ac2f81654a044d324a223fd7f40cea518) | H3C-Fehlertexte in den lokalen HMS-Katalog aufnehmen. | Include H3C messages in the local HMS catalogue. |
| [26](https://github.com/maziggy/bambuddy/commit/f533e608d2b726535a5a473a68d60c48d01915a7) | H3C-Slotzustände aus Teilmeldungen und Tray-IDs in älteren Warteschlangenpositionen berücksichtigen. | Handle partial H3C slot states and migrate tray IDs in older queue items. |
| [27](https://github.com/maziggy/bambuddy/commit/f71e29f879afdefa2a05512ed8655b90f40c8580) | Die angezeigte Temperatur dem montierten H3C-Hotend zuordnen. | Associate the displayed temperature with the mounted H3C hotend. |
| [28](https://github.com/maziggy/bambuddy/commit/0ca2a9b545474138c2aea819ae3266808bed0b84) | Im Rack das montierte und die geparkten Hotends anhand ihrer Position unterscheiden. | Distinguish the mounted and docked hotends by position in the rack view. |
| [29](https://github.com/maziggy/bambuddy/commit/3318469ba94b1aef3318662b6bb1a4fb41b83b2c) | Kamerawand um Druckstatus und berechtigte Bedienelemente erweitern. | Show print status and permission-aware controls on the camera wall. |
| [30](https://github.com/maziggy/bambuddy/commit/0bf86c29478979744eba533ad349c398f3c450cd) | Vorhandene WLED-Presets im lokalen Netz je Drucker auf Statuswechsel abbilden. | Map printer state changes to existing presets on a local WLED controller. |
| [31](https://github.com/maziggy/bambuddy/commit/6c0f8fc6b8bbe9fefbc08dea5883217d6e2cb89a) | Editierbare Filamentprofil-Vorgaben im aktiven Lager gemeinsam anwenden. | Apply editable filament profile defaults together for the active inventory. |
| [32](https://github.com/maziggy/bambuddy/commit/6443e73c457f4bd954d4573df9d61c47018a7d87) | Von der Firmware gemeldete Laufzeit je H2C-Düse anzeigen. | Display the per-nozzle runtime reported by H2C firmware. |
| [33](https://github.com/maziggy/bambuddy/commit/92ef6c16a0386a59236ef3c556015273c8cc7dd8) | Das Druckermodell in anonymisierten Supportdaten für die Diagnose erhalten. | Retain the printer model in redacted support exports. |
| [34](https://github.com/maziggy/bambuddy/commit/7f24f58e7682585ad544ed3fa0ad19137ce2bfd0) | OpenTag3D v2.004 auf ausreichend großen NFC-Tags und das kompakte Format auf kleinen Tags verwenden. | Use OpenTag3D v2.004 on sufficiently large NFC tags and the compact format on smaller tags. |

### Geräteabnahme / Hardware acceptance

Für die automatische H2C-Düsenwahl fehlen in PrintOps Vergleichsdrucke mit festem Hotend, Rack und gemischter Bestückung. Für Rack und FTS ist die Filamentauswahl während eines vollständigen Drucklaufs offen. Bei den Kalibrierungsprofilen fehlen die anonymisierten P2S- und X1C-Aufzeichnungen für die betroffenen Düsenkontexte. Die Betriebsstundenanzeige ist unabhängig von diesen Freigaben.

PrintOps still needs comparison prints using the fixed hotend, rack only and mixed configurations for automatic H2C nozzle selection. Rack and FTS selection still needs verification throughout a complete print. Calibration profile validation requires anonymized P2S and X1C recordings for the affected nozzle contexts. Displaying nozzle operating hours is independent of these acceptance tests. [H2C dispatch #126](https://github.com/ichwars/PrintOps/issues/126) · [Rack/FTS #150](https://github.com/ichwars/PrintOps/issues/150) · [Calibration #149](https://github.com/ichwars/PrintOps/issues/149)
