# Druckerstatus und Filamentkennungen

REST-Abfragen und laufende WebSocket-Updates verwenden dieselbe AMS-Darstellung.

Bei LAN- und Displaystarts ohne echte Auftragskennung kann die Statusanzeige
das passende laufende Archiv anhand seines Namens verlinken. Objektlisten zur
Steuerung benötigen eine echte Kennung oder die explizite Bindung dieses
Druckers. Lokale Archivdateien versorgen Vorschaubild und Objektliste auch nach
einem Neustart, ohne bereits übersprungene Objekte zurückzusetzen. Wechselt der
Druck während des Nachladens, wird das Ergebnis verworfen. Die Startzeit wird
bei der Starterkennung erfasst, bevor ein langsamer Dateiabruf beginnt.

Die Suche nach der Druckdatei versucht einen fehlgeschlagenen FTP-Pfad nicht
erneut beim anschließenden Verzeichnislesen. Exakte Dateinamen haben Vorrang,
mehrdeutige ähnliche Namen werden nicht ausgewählt. Meldet „Erneut drucken“ am
Display nur den internen Titel, kann eine vorhandene 3MF desselben Druckers
verwendet werden. Titel und G-Code-Pfad müssen übereinstimmen, bekannte
Schichtzahlen dürfen sich nicht widersprechen. Platten- und Materialprüfungen
bleiben aktiv. Eine auf der Karte gefundene Datei mit fehlgeschlagenem Transfer
wird nicht durch eine ältere Archivdatei ersetzt. Die Herkunft einer
wiederverwendeten Datei steht in den Metadaten des neuen Archivs.

Auch ohne 3MF zeigt das Archiv gültige AMS-Farben als Farbfelder. Die Zuordnung
berücksichtigt AMS HT. Sobald PrintOps die passende 3MF eines laufenden Drucks
nachträgt, kann es die Kosten aus den zugeordneten Spulen schätzen. Die
Düsentemperatur stammt bei bekannter Platte aus deren verwendetem Filament.

Ein beim Neustart bereits beendeter Druck wird als erfolgreich oder fehlgeschlagen
übernommen, wenn die echte Auftragskennung mit dem laufenden Archiv übereinstimmt.
Ohne diesen Nachweis bleibt sein Ergebnis unbestimmt. Ein erfolgreicher Offline-Druck
kann eine geschätzte Endzeit aus Start und Plattenprognose erhalten, höchstens bis
zum Wiederverbinden. Solche Zeiten zählen nicht als Messwerte für Zeitgenauigkeit.

Ein Offline-Stopp in der Warteschlange erzeugt einen abgebrochenen Drucklauf mit
unbekanntem Verbrauch. Das Archiv wird nur geschlossen, wenn es keinem anderen
laufenden Drucker dient. Ein später gemeldetes Ergebnis korrigiert denselben
identifizierten Protokolleintrag. Wiederholte identische Meldungen erhalten
bewertete Stückzahlen, Projektzuordnung und bereits erfasste Kosten.
Physische Anwesenheit, leere Slots, gespeicherte Kalibrierungswerte und die
Trocknungsphase bleiben dadurch konsistent. Änderungen an Luftführung,
Düsenrack und Firmware erreichen die Oberfläche auch im Leerlauf.

Eine abgezogene AMS-Einheit verschwindet erst bei einem eindeutigen
Abwesenheitssignal des Druckers. Eine unvollständige Meldung entfernt keine
anderen Einheiten. Meldet ein Drucker mit einer Düse ausdrücklich kein AMS,
verwendet der Druckstart den externen Halter. Bei zwei Düsen bleibt die
Düsenzuordnung maßgeblich.

H2D-Slots werden mit den Düsendaten derselben Meldung ausgewertet. Alte,
abweichende Düsendaten überstimmen keinen neu gemeldeten Slot. Bleibt die
AMS-Einheit mehrdeutig, hält PrintOps den zuletzt belastbar erkannten Slot,
bis neue Daten ihn auflösen. Ein Mapping des laufenden Drucks kann dabei
helfen; ein altes Mapping im Leerlauf reicht nicht aus.

Die AMS Lite erhält Seriennummer und Firmware auch dann, wenn die
Versionsmeldung vor den Slotdaten eintrifft. Alte Slotnamen unter einer
Druckerposition bleiben nach Bekanntwerden der Seriennummer sichtbar. Eine
spätere Änderung oder Löschung entfernt den alten Positionsnamen.

Bei älteren Druckern ohne `cfg` wird der Filament-Backup-Status nach der ersten
vollständigen Statusmeldung auch aus späteren kleinen Meldungen gelesen.
Sobald der Drucker `cfg` liefert, bleibt diese Quelle maßgeblich.
Befehlsbestätigungen verändern diesen Status nicht.

## Filament-Preset und Kennung im Slot

Bambu unterscheidet die Filamentkennung im Drucker (`tray_info_idx`) vom
Slicer-Preset (`setting_id`). Meist unterscheiden sie sich durch einen
zusätzlichen Buchstaben. SUNLU und einige P1-/X1-Presets folgen anderen Regeln.
PrintOps verwendet deren konkrete Zuordnung und erhält die vollständige
Preset-Referenz bei einer manuellen Slotkonfiguration. Eine bereits belegte
Slotidentität wird beim erneuten Speichern eines mehrdeutigen alten Presets
beibehalten.

Bekannte Filamentkennungen aus OrcaSlicer-Systemprofilen werden vor einem
Druckerbefehl in die entsprechende Bambu-Kennung übersetzt. Eine unbekannte
Orca-Kennung wird nicht an den Drucker weitergereicht. Bestehende
Modellvorgaben und die Grenzen der Kalibrierungszuordnung bleiben erhalten.

Die Zuordnung eines laufenden Drucks wird bei einem Neustart aus seiner
persistierten Sitzung wiederhergestellt. Eine inzwischen neu erfasste
Zuordnung hat Vorrang; eine Sitzung mit abweichender Druckidentität wird
weiterhin verworfen.

Die Verhaltenstests verwenden gespeicherte beziehungsweise synthetische
Gerätemeldungen. Sie ersetzen keine Abnahme an der jeweiligen Hardware und Firmware.

## Geräteaktionen und Rückmeldungen

Ein Stop-Befehl im bekannten Leerlauf markiert keinen späteren Druck als vom
Benutzer abgebrochen. Bei einem laufenden oder noch unbekannten Druckzustand
bleibt die bisherige Abbruchzuordnung erhalten.

Kann PrintOps die Filamenteinstellungen senden, einen zusätzlich eingegebenen
K-Wert jedoch nicht veröffentlichen, zeigt es dafür einen eigenen Hinweis.
Eine veröffentlichte Einstellung und ihre spätere Rücklesebestätigung bleiben
getrennte Rückmeldungen.

Laden aus einer AMS-HT verwendet die globale Einheitsnummer 128 bis 135.
AMS-Lite-Slots 24 bis 27 werden für den Ladebefehl als physische Einheit 16 mit
lokalem Slot adressiert. Beim Entladen bleibt die tatsächlich geladene Einheit
als Quelle erhalten.

Bei K-Profilen unterscheiden sich drei Rückmeldungen: eine gelesene leere Tabelle,
eine fehlende Antwort und ein gesendeter, noch unbestätigter Schreibbefehl.
Eine fehlende Antwort erscheint als Lesefehler mit Wiederholungsmöglichkeit. Sie
löscht keinen Profilcache und löst beim GitHub-Restore keine doppelten Profile aus.
Profiländerungen auf Druckern mit einer Düse werden nachgelesen; eine echte
Abweichung wird als Fehler gemeldet. Eine AMS-Änderung überschreibt keine bewusst
gewählte Kalibrierung. Nur die bestehende Prüfung im Leerlauf stellt eine
verlorene Auswahl unter ihren bisherigen Zuordnungsgrenzen wieder her.

Abgelehnte Objektübersprünge werden protokolliert und aus der vorläufigen Anzeige
entfernt. Eine spätere Ablehnung eines älteren Befehls nimmt keinen neueren
Übersprung zurück. Erst die echte Objektliste des Druckers bestätigt die Aktion.
Ein Trocknungsstopp meldet deshalb ebenfalls zunächst den gesendeten Befehl.

Beim Filament-Backup entscheidet die vom Drucker gemeldete Filamentkennung mit
Farbe, welche geladenen Spulen zusammengehören. Unterschiedliche lokale
Preset-Referenzen verhindern dann kein zulässiges Backup. Bedarf und Vorrat
verwenden denselben Identitätssnapshot. Die vorhandenen Grenzen für tatsächliche
Belegung und getrennte Düsen bleiben erhalten; externe Halter werden nicht in
den automatischen AMS-Backup-Pool aufgenommen.

## Farben, Durchfluss und Lüfter

Die Farbe eines AMS-Slots wird zuerst innerhalb seiner Bambu-Produktlinie
benannt. Ohne RFID kann die gemeldete Filamentkennung die Produktlinie liefern.
Eine geringfügige Farbabweichung der Druckeranzeige wird dem nächsten
Bambu-Katalogeintrag innerhalb eines engen Wahrnehmungsabstands zugeordnet.
Gespeicherte lesbare Farbnamen einer eigenen Spule bleiben maßgeblich.

Im K-Profil-Picker bleiben Standard- und High-Flow-Kalibrierungen auch bei
identischem Namen und K-Wert getrennt. Die Kennzeichnungen `[S]` und `[HF]`
sowie gegebenenfalls der Extruder unterscheiden sie. Eine automatische
Vorauswahl verwendet den bestehenden, vom Backend bestätigten
Kalibrierungskontext. Ohne eindeutigen Kontext wählt sie nicht zwischen
verschiedenen Düsen oder Durchflusstypen. Die Kalibrierungsgrenzen für
mehrere Hotends bleiben bestehen.

Auf X2D-Druckern ist der zweite Zusatzlüfter (`aux2`, Teil 10) rechts und der
erste (`aux`, Teil 2) links. Bei P2S liegt der zweite links. Die Oberfläche
ordnet beide entsprechend ihrer Seite an. Der zweite Lüfter erscheint nur
nach einer passenden Druckermeldung; eine fehlende Meldung berechtigt nicht
zum Steuerbefehl. Kleine Teilmeldungen entfernen keinen bereits erkannten
Zusatzlüfter. Status und Befehlsrückmeldung verwenden dieselbe Bezeichnung.

## Teilmeldungen und pausierte Drucke

Eine reguläre AMS bleibt bei einer Meldung mit nur einem Fach eine reguläre
AMS. AMS-HT wird anhand der Einheitsnummer 128 bis 135 erkannt. Die Anzeige
ordnet ein gemeldetes Fach nach seiner Fachnummer zu. Fehlen unterscheidbare
Fachnummern vollständig, bleibt die bisherige Positionszuordnung erhalten.

Ein Runout-Hinweis kann eine lokale Fachnummer anhand der Verkabelung zur
aktiven Düse eingrenzen. Bei unbekannter Verkabelung oder einem Filament
Track Switch unterbleibt diese Schlussfolgerung. Beide externen Halter eines
Druckers mit zwei gemeldeten Düsen bleiben auch ohne AMS in der
Filamentauswahl verfügbar.

Die Rotationsoption beim Trocknen berücksichtigt zusätzlich zum Fachzustand
den aktiven Tray und die vorhandenen Filamentpfade beider Düsen. Ein geladener
Pfad der inaktiven Düse verhindert damit ebenfalls eine Spulenrotation.
