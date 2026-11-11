# Filamentverbrauch und Druckkosten

PrintOps erfasst den Verbrauch im integrierten Inventar oder in Spoolman. Der
beim Druckstart verwendete Lagerpfad bleibt für diesen Druck maßgeblich, auch
nach einem Neustart oder einem Wechsel der Inventareinstellung.

## Verbrauch und Spulenwechsel

Eine verfügbare geslicte 3MF liefert die Filamentmengen der tatsächlich
gedruckten Platte. Gleichzeitige Drucke derselben Archivdatei werden nach
Drucker, Platte und Filamentzuordnung ausgewertet. Ungenutzte Filamentslots
werden nicht abgebucht.

Beim erneuten Druck einer anderen Platte haben die gespeicherte Drucksitzung
und der Auftrag dieses Druckers Vorrang vor der ursprünglichen Archivplatte.
Auch ein abgebrochener Auftrag bleibt dafür verwertbar. Druckprotokoll und
Kostenersatzwerte verwenden die Mengen dieser Platte; gemessener Verbrauch
und tatsächliche Spulenkosten behalten Vorrang.

Bei einem Abbruch bestimmt der Schichtfortschritt den Anteil der geslicten
Menge. Verfügbare G-Code-Daten liefern den Anteil des vorgeschobenen Filaments,
einschließlich Rückzügen. Der Teilverbrauch überschreitet die Gesamtmenge
dieses Filaments nicht. Ohne Schichtdaten wird der Anteil aus dem verfügbaren
Fortschritt geschätzt.

AMS-Ersatzspulen teilen sich den Verbrauch nach den aufgezeichneten
Traywechseln. Mehrere Filamentslots auf demselben Tray sowie die Rückkehr zu
einem früheren Tray werden berücksichtigt.

Auch ein manueller Spulenwechsel auf demselben Slot kann aufgeteilt werden:
Die neue Spule muss während des Drucks zugewiesen werden. PrintOps speichert
die Zuordnung mit der erreichten Schicht und stellt die Historie nach einem
Neustart wieder her. Eine fehlende Anfangszuordnung nachzutragen gilt zunächst
als Korrektur; erst eine weitere andere Spule erzeugt eine Aufteilung.

Ohne 3MF kann die Änderung der AMS-Restanzeige als Ersatz dienen. Nach einem
Spulenwechsel gehören Anfangs- und Endwert zu unterschiedlichen Spulen. Diese
Differenz wird nicht als gesicherter Verbrauch gebucht. Eine später gefundene
passende 3MF ergänzt die Verbrauchsdaten, ohne den ursprünglichen
Restmengen-Snapshot zu ersetzen.

## Gewichtssperren und AMS-Abgleich

Manuell eingegebene oder mit SpoolBuddy gewogene Gewichte erhalten eine
Gewichtssperre. Der automatische AMS-Abgleich überschreibt sie nicht.
Verbrauchsbuchungen addieren die verbrauchte Menge zum aktuell gespeicherten
Gewicht, damit zwischenzeitliche Korrekturen erhalten bleiben.

Die bestätigte Aktion **Gewichte vom AMS synchronisieren** dient der
Wiederherstellung: Sie ersetzt auch gesperrte Werte und hebt deren Sperre auf.
Sie verwendet verbundene Drucker mit verwertbaren Werten. Aktive Drucke und
noch laufende Verbrauchsbuchungen werden ausgelassen. Die Ergebnismeldung
nennt die deshalb unveränderten Spulen; nach dem Druck kann erneut
synchronisiert werden. Dieselbe Drucksperre gilt für Spoolman.

Archivierte und gelöschte Spulen geben ihre Slotzuordnungen frei. Eine während
des Drucks archivierte Spoolman-Spule behält ihre Zuordnung bis zum Abschluss
der Verbrauchsbuchung. Danach wird der Slot freigegeben. Der Tag einer
archivierten internen Spule wird nicht automatisch auf eine neue Spule übertragen.
Andere geöffnete Ansichten erhalten die entsprechende Änderung.

## Zuordnungen und Filament-Voreinstellungen

Im Spoolman-Modus zählen ausschließlich Spoolman-Zuordnungen. Gespeicherte
interne Zuordnungen bleiben bei einem Moduswechsel erhalten, beeinflussen aber
weder Slotanzeigen noch Spoolman-Bestände. Auch bei unterbrochener Verbindung
wird keine interne Zuordnung als Ersatz angeboten.

Liest ein neuer Slot den bekannten RFID-Tag einer Spule, entfernt PrintOps ihre
alten Slotzuordnungen. Ein bloßer Material- oder Farbtreffer reicht dafür nicht.
Melden zwei Slots gleichzeitig denselben Tag, bleiben beide Zuordnungen
zunächst erhalten, damit widersprüchliche Lesungen keine Spule verdrängen.

Ein AMS-Abgleich überschreibt keine Spule, die währenddessen manuell anders
zugewiesen wurde. Leere AMS-Meldungen werden weiterhin durch die Schonfrist
und die Druckaktivität geprüft. Eine zugewiesene Spule ohne Druckerkonfiguration
erscheint in ihrer Farbe mit einem Hinweis. Wird der Slot gerade zum Drucken
verwendet, wartet die automatische Konfiguration bis nach dem Druck.

Nach einer Zuweisung oder manuellen Slotkonfiguration prüft PrintOps spätere
Druckermeldungen auf das gewünschte Filament-Preset und die Farbe. Erst diese
Rückmeldung bestätigt die Einstellungen. Ein erwartetes K-Profil darf in einer
späteren Meldung eintreffen. Fehlt seine Bestätigung weiterhin, meldet PrintOps
das getrennt von den bestätigten Filamenteinstellungen.

Bekannte leere Slots werden noch nicht geprüft. Bleibt der Drucker still,
wird keine Bestätigung erfunden. Treffen nach Ablauf des Prüfzeitraums weitere
abweichende Meldungen ein, erscheint ein Hinweis auf die unbestätigte Zuordnung.
Eine nicht gesendete interne Vorabkonfiguration bleibt für einen späteren
Versuch offen.

Erkannte Bambu-Spulen in Spoolman behalten das Filament-Preset ihres Tags. Ein
bereits gesetztes Preset und eigene Modellvorgaben haben Vorrang. Fehlt eine
Vorgabe, kann ein vorhandenes Slot-Preset übernommen werden, wenn Material
und Finish passen. Ein Silk-Filament übernimmt kein Matte-Preset.

Die rechte externe Spule von Druckern mit zwei Haltern wird auch bei einer
fehlenden alten AMS-Zuordnung anhand der tatsächlichen Tray-Daten erkannt.
Mehrfarbdrucke ohne belastbare Zuordnung erhalten keine positionsweise
Ersatzbuchung. Teilweise ungenutzte Zuordnungen bleiben ungenutzt.

Etiketten können auch für archivierte Spoolman-Spulen erstellt werden. Die
Löschung eines Lagerorts wird bei nicht erreichbarem Spoolman abgewiesen, weil
seine Belegung nicht geprüft werden kann. Das Zurücksetzen mehrerer
Verbrauchszähler meldet fehlgeschlagene Einträge und Teilerfolge.

## Archivkosten und einzelne Druckläufe

Die Kosten einer Archivdatei beschreiben einen vollständigen Druck. Während
des ersten Drucks kann PrintOps die Anfangsschätzung anhand der zugeordneten
Spulenpreise verbessern. Die Archivkarte kennzeichnet diesen Wert mit `~`.
Eine noch laufende Schätzung wird vor der endgültigen Buchung beendet.

Teilkosten eines abgebrochenen Drucks gehören zu dessen Eintrag im
Druckverlauf. Sie ersetzen nicht den Preis der vollständigen Datei.
Wiederholungsdrucke erhalten eigene Kosten im Druckverlauf. Die Neuberechnung
und das erneute Einlesen einer 3MF summieren Wiederholungen nicht auf der
Archivkarte auf. Nicht bepreiste Mengen verwenden den konfigurierten
Standardpreis.

Tatsächlich aus Spoolman ermittelte Archivkosten behalten ihre gespeicherte
Herkunft. Ein späterer Inventarwechsel ersetzt sie nicht durch alte interne
Verbrauchseinträge. Spoolman-Teilkosten berücksichtigen erfolgreich gebuchte
Mengen und die Preise der tatsächlich belasteten Spulen.

Alte Verbrauchseinträge ohne Archiv-ID können über den Drucknamen zugeordnet
werden, wenn dieser am selben Drucker genau eine Archivdatei bezeichnet.
Mehrdeutige Namen werden nicht automatisch aufgelöst.

Über `PATCH /api/v1/archives/{id}` kann `filament_used_grams` berichtigt werden.
Ohne gleichzeitig übermitteltes `cost` wird der Archivpreis neu berechnet.
Ein Druckverlaufseintrag folgt dieser Änderung nur, wenn seine Menge aus dem
bisherigen Archivwert übernommen war. Gemessene Mengen und Kosten bleiben
erhalten. Aufträge und Kalkulationen verwenden weiterhin ihre bestehenden
PrintOps-Abläufe; eine zusätzliche Budgetverwaltung wird nicht eingeführt.


## Bereits verbrauchte Menge beim Anlegen

Ein beim Anlegen einer Spule eingegebenes positives Verbrauchsgewicht bleibt
für einzelne Spulen, Mehrfacherfassung und CSV-Import gesperrt, bis die
automatische Gewichtsschätzung ausdrücklich wieder freigegeben wird. Eine
explizit gesetzte Sperrwahl hat Vorrang. Negative Erfassungsgewichte werden
abgewiesen. Eine allgemeine Bearbeitung in Spoolman verändert nicht den
Zeitpunkt der letzten Druckverwendung (`last_used`).
