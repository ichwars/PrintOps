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

## Umgebungstrocknung erst bei anhaltend hoher Luftfeuchtigkeit

Öffne **Einstellungen → Lager & Material → Filament** und aktiviere die
Umgebungstrocknung. Das Feld **Anhaltend hohe Luftfeuchtigkeit (Minuten)**
legt fest, wie lange die Feuchtigkeit über dem jeweils wirksamen AMS-Grenzwert
liegen muss. Erlaubt sind ganze Zahlen von 0 bis 240. Der Standardwert 0 startet
wie bisher sofort; beispielsweise 15 wartet auf 15 Minuten anhaltend hohe Werte.

Jeder Drucker und jede AMS-Einheit sammelt die Zeit getrennt. Ein Wert am oder
unter dem Grenzwert, ein Grenzwert- oder Materialwechsel, eine Unterbrechung der
Verbindung und das Deaktivieren der Umgebungstrocknung starten die Wartezeit neu.
Fehlende Sensorwerte zählen nicht als niedrige Feuchtigkeit und können keinen
Start auslösen. Fehlen Beobachtungen länger als vier Scheduler-Intervalle
(mindestens 120 Sekunden), beginnt die Wartezeit ebenfalls von vorn. Nach einem
Neustart wird erneut gewartet. Eine gestartete oder bereits laufende Trocknung
verbraucht die gesammelte Zeit; die eingestellte Trocknungsdauer läuft ohne
vorzeitigen Feuchtigkeitsstopp weiter.

Trocknung vor geplanten Warteschlangendrucken bleibt von dieser Wartezeit
unabhängig. Ist ausschließlich Trocknung beim Drucken aktiv, startet sie weiterhin
sofort auf geeigneter Hardware. Sind Umgebungstrocknung und Trocknung beim Drucken
zusammen aktiv, gilt die Wartezeit auch während des Druckens; die reduzierte
Trocknungstemperatur bleibt wirksam. Druckerreservierungen, freie Druckplatten,
Druckerzustand, Firmware und Leistungsgrenzen bleiben Voraussetzung für einen
Start. Manuell gestartete Zyklen werden nicht als automatische Zyklen übernommen
und nicht von der automatischen Steuerung gestoppt.

Zum Schutz manueller Trocknung erhält ein neu automatisch gestarteter Zyklus
keine automatische Stop-Berechtigung. Eine erfolgreiche MQTT-Veröffentlichung,
eine Bestätigung und später gemeldete Restzeit reichen nicht aus, um ihn von
einem inzwischen manuell gestarteten Zyklus sicher zu unterscheiden. Auch eigene
automatische Zyklen laufen deshalb bis zum Ende der Firmware-Dauer weiter:
Das Deaktivieren der Automatik oder das Entfernen künftiger geplanter Drucke
stoppt sie nicht. Explizite manuelle Bedienung und separat reservierte
Trocknungspläne behalten ihre bisherigen Abläufe.

Bei `queue_drying_block=false` kann ein Drucker im Zustand `PAUSE` dadurch bis zum
Ende der Trocknung warten; die Automatik unterbricht diesen unklar zugeordneten
Zyklus nicht mehr für einen Warteschlangendruck. Meldet der Drucker `IDLE`, kann
die vorhandene Zustandsprüfung weiterhin einen Druckstart auswählen, ohne zuvor
die Trocknung zu stoppen. Das beschreibt die Softwareentscheidung und garantiert
keinen erfolgreichen physischen Druckstart während der Trocknung.

Solange nach einer Startveröffentlichung noch kein laufender Zyklus gemeldet
wurde, unterdrückt PrintOps weitere Startbefehle für dieselbe AMS-Einheit für
vier Scheduler-Intervalle, mindestens 120 Sekunden. Während dieser begrenzten
Unsicherheit bleibt auch das Warmhalten des Druckbetts gesperrt, selbst bei
noch gemeldeter Restzeit 0. Positive Trocknungsrestzeit sperrt das Warmhalten
weiterhin unabhängig davon. Nach Ablauf der Unsicherheit kann ein neuer Versuch
folgen; Umgebungstrocknung mit Wartezeit benötigt dafür erneut frische Messungen
über die volle eingestellte Dauer.

## Python unter macOS für das lokale Netzwerk freigeben

Bei nativer macOS-Installation prüft PrintOps nach dem Aufbau der Python-Umgebung
und bei abgeschlossenen macOS-Updates die Signatur des tatsächlichen
Python-Interpreters und einer vorhandenen Framework-App. Nur eindeutig
unsignierte Ziele erhalten eine Ad-hoc-Signatur. Vorhandene Ad-hoc- und
Developer-ID-Signaturen bleiben erhalten; ein unbekannter Prüffehler verändert
das Ziel nicht. Ein Homebrew-Python-Upgrade kann einen neuen Interpreterpfad
verwenden, deshalb erfolgt die Prüfung bei jedem ausgeführten Update erneut.
Auch die erste Aktualisierung einer älteren nativen Installation bereitet die
Identität nach erfolgreicher PDF-Runtime-Prüfung vor dem Dienstneustart vor.

Die Signatur bereitet die Identität vor. Bestätige die Netzwerkfreigabe selbst
im macOS-Dialog oder unter **Systemeinstellungen → Datenschutz & Sicherheit →
Lokales Netzwerk** für den betreffenden Python-Eintrag. Nach einem Python-Upgrade
kann eine neue Freigabe nötig sein. Fehlende Signierwerkzeuge und fehlgeschlagene
Signierungen erzeugen Warnungen, ohne Installation oder Update abzubrechen.
Ein ansonsten kompatibler älterer Branch ohne Signierhilfe bleibt installierbar;
eine Warnung verweist für die automatische Vorbereitung auf einen neueren Branch.

Die [native Installationsanleitung](../install/README.md#macos-local-network-access)
beschreibt die Wiederholung als Installationsbenutzer und die Prüfung bei
Warnungen. Die Softwaretests verwenden gemockte Befehle; eine reale macOS-
Netzwerkfreigabe und Druckerkommunikation wurden damit nicht geprüft.

Diese Erweiterung gehört zu [O09 / Issue #208](https://github.com/ichwars/PrintOps/issues/208).

## O12: Objekte auf der Bauplatte überspringen

Öffne während eines laufenden oder pausierten Drucks mit mehreren erkannten
Objekten die Objektauswahl auf der Druckerkarte oder in der Kameraansicht.
Klicke ein Objekt in der Bauplattenvorschau oder in der Liste an; ein erneuter
Klick hebt die Auswahl auf. Die vergrößerte Vorschau verwendet dieselbe Auswahl.
Bereits übersprungene Objekte lassen sich nicht erneut auswählen. Ist keine
Auswahlmaske verfügbar, bleibt die Auswahl über die Objektliste möglich.

„Ausgewählte überspringen“ öffnet zunächst eine Bestätigung. Bei Auswahl aller
verbleibenden Objekte warnt sie vor dem Ende des Drucks. Der Befehl wird erst
nach der Bestätigung gesendet. Die Objektdaten werden alle fünf Sekunden
aktualisiert: Verschwundene oder inzwischen übersprungene Objekte fallen aus
der Auswahl, auch bei bereits geöffneter Bestätigung. Andere aktive Auswahlen
bleiben erhalten. Ohne verbleibende Auswahl ist die Bestätigung gesperrt.

Die Oberfläche erlaubt das Überspringen erst nach der ersten Druckschicht und
mit `printers:control`. Objektlisten benötigen `printers:read`; beide
Objekt-Endpunkte beachten zusätzlich die Druckerfreigaben des Benutzers oder
API-Keys. Eine leere Freigabeliste erlaubt keinen Drucker. Die vorhandenen
Prüfungen auf einen verbundenen Drucker, bekannte Objekt-IDs und eine
Trocknungsreservierung bleiben wirksam. Der MQTT-Befehl ist nur im Zustand
`RUNNING` oder `PAUSE` möglich. Objekt-IDs und Vorschauen stammen aus den vom
Drucker beziehungsweise Slicer bereitgestellten Daten; die Softwareprüfung
ersetzt keine Abnahme mit konkretem Druckermodell und Firmware.

Die Bauplattenauswahl war bereits vorhanden. O12 ergänzt die Prüfung des
gerenderten Ablaufs und behebt veraltete Auswahlen sowie die Druckerbindung der
beiden Objekt-Endpunkte. Die Softwaretests und Browserfixtures verwenden
ausschließlich simulierte Transportantworten und steuern keinen Drucker.

Diese Prüfung gehört zu [O12 / Issue #214](https://github.com/ichwars/PrintOps/issues/214).

## Kartentext und Symbole (O13a)

Auf der Druckerseite lässt sich unter „Ansicht“ beziehungsweise in der
Ansichtsleiste „Kartentext und Symbole“ auf 90, 100, 110 oder 120 Prozent
einstellen. 100 Prozent ist der unveränderte Standard. Die Auswahl verändert
Text und kleine Symbole im Karteninhalt unabhängig von den Kartengrößen
S/M/L/XL. Überschriften, Vorschaubilder, Dialoge und Kamerafenster behalten
ihre eigenen Größen. Die Kamerawand hat keine Kartenskalierung.

Die Auswahl wird nur in diesem Browser für das angemeldete Konto gespeichert.
Ein anderes oder neu angelegtes Konto übernimmt sie nicht; auch eine
wiederverwendete numerische Benutzer-ID ändert das nicht. Dafür ergänzt die
Benutzerantwort ein öffentliches, dauerhaftes `sub` aus der bereits vorhandenen
Kontoidentität. Ohne Anmeldung bei ausdrücklich deaktivierter Authentifizierung
gilt die Auswahl für diesen Browser und diese Installation. Während die
Anmeldung lädt sowie für synthetische API-Key-Benutzer ohne Kontoidentität ist
die Einstellung gesperrt. Das gilt auch nach einer fehlgeschlagenen Abfrage des
Authentifizierungsstatus, bis eine erneute Abfrage erfolgreich ist.
Blockierter Browserspeicher erlaubt die Auswahl
weiterhin im aktuellen Tab. Die Auswahl von 100 Prozent entfernt die
gespeicherte Abweichung.

Die Softwareprüfung verwendet simulierte Druckerdaten und steuert keinen
physischen Drucker. Sie gehört zu [O13a / Issue #216](https://github.com/ichwars/PrintOps/issues/216).

## Externe Spule auf Druckerkarten ausblenden (O13b)

Bei Druckern mit AMS und externer Spule lässt sich die externe Spulendarstellung
über das Augensymbol rechts in der Filament-Kopfzeile ausblenden. Standardmäßig
bleibt sie sichtbar. Dasselbe Symbol blendet sie wieder ein und ist auch per
Tastatur erreichbar. Ohne aktuell gemeldetes AMS erscheint die externe Spule
stets, selbst wenn sie vorher ausgeblendet wurde. Meldet sich das AMS wieder,
gilt die gespeicherte Auswahl erneut.

Die Einstellung gilt nur für diese Browserinstallation, diesen Server, das
verifizierte Benutzerkonto und die Druckerseriennummer. Bei deaktivierter
Authentifizierung gilt sie für die lokale Appliance-Ansicht. Ungeklärter
Anmeldestatus oder fehlende Seriennummer lassen die externe Spule sichtbar;
bei gesperrtem Browserspeicher gilt die Auswahl nur bis zum Neuladen.
Kartengröße S/M/L/XL sowie die unabhängige Text- und Symbolskalierung bleiben
separat einstellbar.

Ausgeblendet wird ausschließlich die Darstellung. Um deren bisherige Aktionen
(Laden, Entladen, Konfigurieren und Spulenzuweisung) zu erreichen, zunächst
„Externe Spule anzeigen“ wählen. Berechtigungen, Zuordnungen, Bestand und
Druckerstatus ändern sich dadurch nicht. Tag-Verknüpfungen und deren Aufhebung
bleiben an den bestehenden Einstellungs-/Inventar-Einstiegen verfügbar.
Die Anzeigeoption sendet keine Befehle an den Drucker und gehört zu
[O13b / Issue #218](https://github.com/ichwars/PrintOps/issues/218).

## PostgreSQL-Pool prüfen (O14)

Beim Start warnt PrintOps, wenn der konfigurierte Pool eines Worker-Prozesses
mehr Verbindungen öffnen könnte als PostgreSQL außerhalb seiner bekannten
Reserven erlaubt. Die Warnung nennt Poolgröße, Überlauf und Servergrenze sowie
die Einstellungen `DB_POOL_SIZE` und `DB_MAX_OVERFLOW`. Abfragefehler bleiben
eine kurze Warnung; SQLite benötigt keine PostgreSQL-Abfrage.

Die Standards bleiben PostgreSQL `20 + 20` und SQLite `20 + 200`. Eine passende
Poolgröße für einen Worker garantiert keine Kapazität für weitere Worker und
andere Clients. Details und Grenzen stehen in der
[Datenbank-Poolkonfiguration](database-pool-configuration.md).
Die Ergänzung gehört zu [O14 / Issue #224](https://github.com/ichwars/PrintOps/issues/224).

## Orca-Sidecar nativ auf ARM64 betreiben

Für 64-Bit-ARM-Linux steht eine lokal baubare OrcaSlicer-Variante bereit. Starte
den optionalen Sidecar mit `docker-compose.yml` und `compose.native.yml` aus
`slicer-api/`. Die genaue Installation und die gepinnten Quellen stehen in der
[Sidecar-Anleitung](../slicer-api/README.md). Aktiviere anschließend unter
**Einstellungen → Slicer** die Slicer-API und trage die vom PrintOps-Backend
erreichbare Sidecar-URL ein. Die bisherige AMD64-Konfiguration bleibt verfügbar.

Die native Variante verwendet den vorhandenen HTTP-Wrapper mit expliziten
Drucker-, Prozess- und Filamentprofilen samt Vererbungsauflösung. Sie erweitert
nur OrcaSlicer; Bambu Studio erhält dadurch keine ARM64-Unterstützung.
Speicherbedarf und Laufzeit hängen vom Modell ab; ein Betrieb mit 2 GB RAM wurde
nicht gemessen. Bei ungeeigneter Hardware kannst du den Sidecar auf einem
separaten Linux-Rechner betreiben oder den lokalen Desktop-Slicer verwenden.

Die Ergebnisse und Grenzen aller ausgewählten optionalen Erweiterungen stehen
im [optionalen Umsetzungsbericht](optional-upstream-implementation-2026-10-14.md).
