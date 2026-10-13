# Neue Druck-, Lager- und Dateifunktionen bedienen

Diese Anleitung beschreibt die wichtigsten Bedienänderungen aus dem
[Upstream-Abgleich](upstream-implementation-2026-10-11.md). Bestehende Aufträge,
Reservierungen, Beschaffungsregeln und Kalkulationen bleiben maßgeblich.

## Qualität eines abgeschlossenen Drucklaufs bestätigen

Nach einem abgeschlossenen Druck kann PrintOps eine Qualitätsbestätigung
anfordern. Öffne den Hinweis oder den Druckverlauf des betreffenden Archivs und
bewerte den konkreten Drucklauf. Erfasse die Gut- und Ausschussmenge im Dialog.
Ein bereits gestarteter Folgedruck verdrängt die Bewertung des vorherigen
Laufs nicht. Historische Abfragen aus einer Benachrichtigung öffnen die
angemeldete Oberfläche; öffentliche Aktionslinks sind an den passenden aktuellen
Lauf gebunden.

Die Qualitätsmengen beziehen sich auf Teile. Eigene Batch-Ziele und
Nachproduktion zählen weiterhin Druckläufe. Eine Qualitätsbestätigung führt
keine automatische Lager-, Auftragslieferungs- oder Versandbuchung aus.
Diese Schritte bleiben im bestehenden Auftrags- und Lagerablauf.

## Gefilterte Warteschlange umsortieren

Ziehe einen sichtbaren Auftrag an seine gewünschte Stelle oder verwende die
Sortieraktion auf dem Mobilgerät. Bei einem Standort-, Besitzer- oder
Druckerfilter werden die sichtbaren Aufträge in ihren bisherigen Plätzen der
gesamten Warteschlange neu geordnet. Ausgeblendete Aufträge behalten ihren
Platz. Bereits zum Druckstart übernommene Aufträge lassen sich dabei nicht
mehr verschieben. Druckerrechte und die eigenen Batch-Zuordnungen bleiben
wirksam.

## Materialnummern und Bestandswarnungen

In der Filamentübersicht lassen sich Spulen nach Materialidentität gruppieren.
Die Materialnummer gehört zur Kombination aus Material, Untertyp, Marke und
Farbe. Mehrere Spulen derselben Kombination teilen diese Nummer. Bereits
vorhandene Beschaffungsangebote und Einstellungen bleiben erhalten, auch wenn
ältere Einträge leere Werte unterschiedlich gespeichert haben.

Bearbeite die Materialnummer über die Bestandsübersicht. Die Änderung behält
Vorlaufzeit, Sicherheitsmarge und den Ruhemodus der Beschaffungsregel bei.
Filament, Kleinteile und Lagerartikel verwenden den gemeinsamen Nummernkreis;
manuell vergebene Nummern können deshalb nicht parallel für einen anderen
Artikel beansprucht werden. Das Anzeigen oder Drucken eines Etiketts vergibt
keine neue Materialnummer.

Bestellpunkt-, Stock-Break- und Low-Filament-Ereignisse verwenden die vorhandenen
Bestands-, Reservierungs- und Forecast-Daten. Aktiviere die gewünschten
Ereignisse bei deinem Benachrichtigungsanbieter. Ruhezeiten und Digest bleiben
wirksam. Bei einer fehlgeschlagenen Zustellung wiederholt PrintOps nur die noch
offenen Anbieter. Anbieter mit bereits erfolgreicher Zustellung erhalten
dieselbe Warnung nicht erneut.

Low-Filament-Warnungen behalten erfolgreiche Zustellungen und bereits
angelegte Digest-Einträge auch nach einem Neustart. Eine vorübergehend
deaktivierte Benachrichtigung oder ein ausgefilterter Drucker löscht diese
Historie nicht. Sobald PrintOps eine Erholung des Füllstands oder einen
Spulenwechsel beobachtet, kann eine neue Low-Filament-Warnung entstehen.

Beim ersten Lauf nach dem Upgrade kann eine ältere Bestandswarnung einmalig
erneut erscheinen: Alte globale Warnungseinträge enthalten keinen Nachweis
einer erfolgreichen Zustellung pro Anbieter.

Im Spoolman-Modus stammen Netto-, Tara- und Anfangsgewicht sowie Produktlinie
weiterhin aus Spoolman. Das Zurücksetzen des Verbrauchszählers setzt die
Verbrauchsbasis zurück und verändert das tatsächliche Spulengewicht nicht.

## Etiketten vorbereiten und exportieren

Wähle die Spulen oder Kleinteile aus und öffne den Etikettendialog. Wähle eine
Vorlage und die gewünschten Datenfelder; die Vorschau aktualisiert sich mit
der Auswahl. Die verfügbaren Felder umfassen unter anderem Materialnummer,
Gewicht, Temperatur, Lagerort und Notiz. Deine Auswahl bleibt lokal gespeichert.

PDF eignet sich für den bisherigen Druckablauf. PNG exportiert einzelne
Etiketten; mehrere Bilder werden gemeinsam als ZIP heruntergeladen. Für PNG
stehen 203, 300 und 600 dpi zur Verfügung. Der Schwarzweißmodus unterstützt
Thermodrucker. Bei Avery-Bögen kannst du die Startposition auf einem bereits
teilweise verwendeten Blatt wählen.

## Dateien, externe Links und Fotos

In der Dateiverwaltung kannst du bei einer Library-Datei einen externen Link
und eigene Ergebnisfotos ergänzen. Die Links öffnen externe Projektseiten;
die Datei bleibt im bisherigen Projekt- und Besitzerkontext. Löschen oder
Bearbeiten setzt weiterhin die jeweiligen Datei- und Projektberechtigungen
voraus.

Für unterstützte Bild-, PDF- und Tabellendateien öffnet die Vorschau den Inhalt
direkt im Browser. Zoome bei Bedarf oder wechsle in den Vollbildmodus.
PDF-Vorschauen zeigen mehrere Seiten; Tabellenvorschauen unterstützen die
freigegebenen Tabellenformate. STEP-Dateien werden in einer eigenen
3D-Vorschau verarbeitet. Sehr große oder zu komplexe Dateien können die
Vorschaugrenzen überschreiten und werden dann mit einer Fehlermeldung beendet.

Wähle mehrere STL-Quelldateien und öffne die Kombinieren-Aktion. Im Dialog
kannst du Kopien festlegen; die Objekte werden in einer gemeinsamen 3MF-Datei
positioniert. Die neu erzeugte Datei ergänzt die Library; die
Quellen bleiben erhalten. Prüfe die Platte anschließend im Slicer, bevor du
sie für einen Druck einplanst.

Desktop-Slicer können unterstützte Quelldateien über einen kurz gültigen Link
mehrfach abrufen. Ein solcher Link gibt nur die ausgewählte Ressource frei.
Nach dem Löschen einer Library-Datei ist sie auch mit einem zuvor ausgestellten
Slicer-Link nicht mehr abrufbar.

## Druckverlauf und Benachrichtigungen

Im Druckverlauf kannst du Kosten- und Energiespalten ein- oder ausblenden und
die unterstützten Spalten sortieren. Kosten verwenden weiterhin die eigene
Währung und Kalkulationsgrundlage. Mengen und Qualitätsdaten bleiben dem
jeweiligen Drucklauf zugeordnet.

Bei Benachrichtigungen lässt sich die Fotoübertragung je Anbieter aktivieren.
Deaktivierte Fotoübertragung entfernt auch Fotoverweise aus Textvariablen.
Fotos geben keine allgemeinen Kamera- oder Dateirechte frei. Die vorhandenen
Kamera- und Benutzerberechtigungen gelten weiter.

Fortschrittsmeldungen beginnen erst mit der ersten tatsächlichen Druckschicht.
Vorheizen und vorbereitende Schritte zählen nicht als Druckfortschritt.
ntfy-Ereignisse verwenden die konfigurierte Ereignispriorität.

## AMS, RFID und Druckeralarme

Ein abgelehnter RFID-Refresh wird sichtbar gemeldet. Der zusätzliche
Legacy-Fallback steht nur bei unterstützten Modellen im Leerlauf zur
Verfügung. RFID-Konflikte zeigen die bereits zugeordnete Spule; die Tray-UUID
kann unabhängig von der Tag-UID gelöscht werden.

AMS-Belegung wird anhand der Statusmeldung geführt. Eine Spule wird nicht
allein wegen einer leeren Herstellerkennung als entfernt behandelt.
Kalibrierungsprofile bleiben an Druckermodell, Düsen- und Flow-Kontext gebunden.

HMS-Alarme zeigen den Herstellertext und die tatsächliche Alarmstufe.
Unbekannte Fehler bleiben mit ihrem vollständigen Code einsehbar. Eigene
Aktionsdaten und die Zuordnung zum Druckauftrag bleiben erhalten. Die zwölf
bisherigen Oberflächensprachen werden weiterhin unterstützt.

## Nach dem Upgrade

Die Datenbankerweiterungen werden beim Start additiv angewendet. Vorhandene
Bestands- und Auftragsdaten sowie historische Material-IDs bleiben bestehen.
Führe vor einem produktiven Upgrade die übliche Datensicherung durch.

Die einzelnen Änderungen, ihre Grenzen und die softwareseitigen Prüfergebnisse
stehen im [Umsetzungsbericht](upstream-implementation-2026-10-11.md). Die dort
dokumentierten API-, MQTT- und Browserprüfungen ersetzen keine Abnahme eines
physischen Druckers mit seiner konkreten Firmware.

## Orca-Cloud-Filamente im AMS konfigurieren

Verbinde dein Orca-Cloud-Konto und öffne auf der Druckerkarte oder in SpoolBuddy
„Slot konfigurieren“. Wähle das Orca-Filament und ein dazu passendes K-Profil.
PrintOps verwendet die eigene Filament-ID des Profils. Fehlt sie, sucht es in den
übergeordneten Profilen und anschließend im bekannten Bambu-Katalog. So kann
OrcaSlicer beim Synchronisieren der Filamente den passenden Preset erkennen.

Wenn keine nutzbare ID gefunden wird, erhält der Slot das generische Filament
für das Material. Ein Hinweis erklärt, ob die ID fehlt, die Cloud-Abfrage
fehlgeschlagen ist oder die Orca-Berechtigung fehlt. Eine vorhandene
Cloud-Verknüpfung wird durch diesen Hintergrundzugriff nicht gelöscht.

Beim Wechsel auf ein anderes Filament wird das bisher aktive K-Profil nicht
automatisch übernommen. Du kannst ein passendes Kalibrierungsprofil auswählen.
Lokale und Spoolman-Spulen verwenden denselben Orca-ID-Abgleich; ihre bestehenden
Material-, Bestands- und Trocknungsregeln gelten weiterhin.

Änderst du den Slot später am Drucker oder in OrcaSlicers Device-Ansicht, blendet
PrintOps einen gespeicherten Presetnamen aus, sobald der Drucker eine andere
Filament-ID meldet. Alte Zuordnungen ohne aufgezeichnete ID bleiben lesbar.
Eine erneute Konfiguration speichert die tatsächlich verwendete ID.

Diese Erweiterung gehört zu [O02 / Issue #200](https://github.com/ichwars/PrintOps/issues/200).


Bei einer Orca-Vorlage ohne Filament-ID verwenden die Slot-Konfiguration und die Kalibrierung dieselbe vollständige generische Filamentliste, einschließlich PPS-CF, PPA-CF/PPA-GF, BVOH, PHA und EVA. Die Warnung nennt das tatsächlich konfigurierte Material. Gibt es keine sichere generische ID, etwa für PEEK ohne eigene Drucker-ID, bleibt die Slot-Konfiguration unverändert und zeigt einen Fehler; Inventarzuweisungen bleiben ausstehend. RFID-Abgleich und spätere Einlegevorgänge behalten eine bereits vom Drucker gemeldete Filament-ID und deren Kalibrierung, ohne auf die Orca-Zugangsdaten anderer Benutzer zuzugreifen.

## Bei verbundenen Anwendungen mit PrintOps anmelden

Aktiviere zunächst die PrintOps-Authentifizierung. Unter **Einstellungen →
Integrationen → API & Metriken → Verbundene Anwendungen** können Nutzer mit
`settings:update` eine Anwendung samt exakter Rückruf-URL registrieren. Speichere
Client-ID und Client-Geheimnis auf dem Server der externen Anwendung. Das Geheimnis
wird nur beim Erstellen und Erneuern angezeigt; kopiere es direkt und schließe
danach die Anzeige.

Beim Aufruf der externen Anmeldung zeigt PrintOps den Anwendungsnamen, das Konto,
die bestätigte Rückruf-URL und die geteilten Identitätsdaten. Erlaube oder verweigere
die Anmeldung ausdrücklich. Geteilt werden Benutzer-ID, Benutzername, E-Mail,
Gruppen, Administratorstatus und aktuelle Berechtigungen. Die Anwendung erhält
eine Momentaufnahme dieser Daten; sie erhält weder dein PrintOps-Anmeldetoken noch
Zugriff auf die PrintOps-API. Auch eine zuvor erlaubte Anwendung fragt erneut.

Über die Anwendungsverwaltung lassen sich Name und Rückruf-URL bearbeiten,
Anwendungen deaktivieren oder löschen und Geheimnisse erneuern. Erneuern,
Deaktivieren, Löschen und Änderungen der Rückruf-URL machen ausstehende
Anmeldecodes ungültig. Nach einer Geheimniserneuerung muss die externe Anwendung
das neue Geheimnis verwenden. Die externe Anwendung verwaltet ihre eigenen
Sitzungen; deren Abmeldung wird dadurch nicht rückwirkend ausgelöst.

Die [Integrationsanleitung für Entwickler](connected-applications.md) beschreibt
PKCE, Statusprüfung und den einmaligen Code-Austausch. Die Begleit-Wiki war nicht
verfügbar; die Anleitung bleibt daher im vorhandenen Dokumentationsverzeichnis.

## O06: Streaming-Overlay und OBS-URL

Unter **Einstellungen → Integrationen → API & Metriken → Kamera-API-Tokens**
steht der Streaming-Overlay-Builder für Nutzer mit Drucker-Lesezugriff und
Kameraberechtigung. Wähle Drucker, Schriftgröße, Bildrate und die gewünschten
Felder. Modell und Temperaturen sowie die PrintOps-Gestaltung im Hoch- oder
Querformat sind optional; bestehende Overlay-URLs behalten ihre Darstellung.
Die Vorschau ist zunächst ausgeschaltet. Ein Klick startet sie, eine Änderung
der Optionen schließt sie wieder. Kopiere die Overlay-URL über den Kopierbutton neben dem URL-Feld in eine
OBS-Browserquelle. Der bestehende Kamera-Quell-URL-Builder bleibt separat.

Erstelle zum Teilen einen langlebigen Token mit dem Geltungsbereich **Overlay**
und füge ihn in das Tokenfeld ein. Anmeldetokens gehören nicht in diese URL.
Bewahre die URL wie ein Zugangsdokument auf; der Token kann im selben Bereich
widerrufen werden. Beim Neuladen bleibt der Streaming-Token in der URL, ohne
zum PrintOps-Anmeldetoken zu werden. Ein Overlay-Token erhält ausschließlich
Overlay-Daten für die aktuell für seinen Besitzer erlaubten Drucker; er öffnet
keine vollständigen Drucker-, Einstellungs- oder globalen WebSocket-APIs.

Die Temperaturanzeige zeigt vorhandene Istwerte für Druckbett, beide Düsen und
bei entsprechend ausgestatteten Modellen die Kammer. Sollwerte erscheinen nur
während des Aufheizens. Interne MQTT-Flags und Zeitstempel werden nicht geteilt.
Ohne Sensorwerte bleibt die Temperaturzeile verborgen. Kameraabbrüche werden
still mit begrenzten Wiederholungen behandelt. Da MJPEG-Bilder im Browser keine
Frame-Zeit bereitstellen, erneuert eine 60-Sekunden-Verbindungsfrist auch stumme
Verbindungen. Sie erneuert auch gesunde Kameraverbindungen alle 60 Sekunden.
Die begrenzten Fehlerwiederholungen verhindern eine schnelle Endlosschleife.
Nach drei erfolglosen Erneuerungen stoppt sie; ein erfolgreiches
Laden setzt das Wiederholungsbudget zurück.

Overlay-Links und Kameraabrufe beachten die aktuell erlaubten Drucker des
Token-Besitzers. Der Builder bietet nur diese Drucker an. Bei aktivierter
Authentifizierung ist vor Kopieren oder Vorschau ein Overlay-Token nötig;
OBS besitzt keine Browser-Anmeldesitzung. Ohne Authentifizierung bleibt der Token
optional. Der RTSP-Proxy nimmt keine Overlay-Token an, da ihm eine vertrauenswürdige
Druckerbindung fehlt; dafür bleiben die bisherigen Camera-Stream-Token verfügbar.
Beim Löschen eines Druckers werden dessen Benutzerfreigaben entfernt. Nach dem
Entfernen der letzten Freigabe bleiben keine Drucker erlaubt, auch nach Neustart
oder Benutzerbearbeitung. Uneingeschränkten Zugriff stellt ein Administrator nur
durch die ausdrückliche Auswahl „Alle Drucker“ wieder her. Eine einmalige
Startmigration erhält die bisherige uneingeschränkte Bedeutung historischer
leerer Freigabelisten. Ihre interne Migrationsmarkierung bleibt beim Zurücksetzen
der Einstellungen und in vollständigen Datenbanksicherungen erhalten. Gleichzeitige
Freigabeänderungen und Druckerlöschungen werden innerhalb der Datenbank serialisiert;
bei einem Sperrzeitlimit kann die Anfrage erneut gesendet werden.
