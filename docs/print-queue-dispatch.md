# Filamentzuordnung und Freigabe der Druckwarteschlange

Die Warteschlange prüft einen Auftrag am Drucker, der ihn tatsächlich ausführen
soll. Gespeicherte AMS-Tray-IDs gehören zu diesem einen Drucker. Wird ein Auftrag
auf einen anderen Drucker oder auf „beliebiger Drucker dieses Modells“ umgestellt,
werden die bisherigen druckerspezifischen Zuordnungen neu ermittelt. Eigene
Auftrags-, Platten-, Qualitäts- und Lagerbezüge bleiben bestehen.

## Material, Farbe und verfügbare Menge

Eine gespeicherte Zuordnung wird gegen die aktuell gemeldeten Materialien des
Druckers geprüft. Bereits passende manuelle Zuordnungen bleiben erhalten;
fehlende Slots werden ergänzt, sobald passende Spulen geladen sind. Der Matcher
berücksichtigt die tatsächlich gedruckte Platte und bei mehreren Düsen deren
Filamentzuführung. Zwei erforderliche Slots erhalten verschiedene Spulen.

„Farbe zwingend zuordnen“ verlangt die genaue Farbe und, soweit beide Seiten sie
melden, dieselbe Filamentvariante. Ein gleiches Grundmaterial in einer anderen
Farbe genügt dann nicht. Ohne diese Vorgabe gelten weiterhin die vorhandenen
Farbpräferenzen und Materialäquivalenzen.

Für einen Modellauftrag werden passende Drucker vor der Zuweisung geprüft.
Ein Drucker mit genügend erfasstem Filament wird einem passenden Drucker mit zu
wenig Filament vorgezogen. Kann kein passender Drucker genügend Material bieten,
bleibt der Auftrag zur Bestätigung zurückgehalten. Ein wegen geringer Restmenge
zurückgehaltener Modellauftrag kann auf einen anderen freien Drucker wechseln,
wenn dort die benötigten Mengen vollständig bekannt und ausreichend sind.
Unbekannte Restmengen genügen für diesen automatischen Wechsel nicht. Der bisherige
Drucker wird dabei nicht automatisch freigegeben, während jemand eine Spule lädt.

Bei eingeschalteter Authentifizierung verwendet ein automatischer Wechsel die
aktuellen Druckerfreigaben des aktiven Erstellers. Ein unbekannter, gelöschter oder
inaktiver Ersteller und eine leere Druckerfreigabe erlauben keinen solchen Wechsel.
Aufträge mit mehreren Modellvarianten bleiben bei einer Mengenbestätigung stehen,
damit keine andere Quelldatei unbemerkt an ihre Stelle tritt.

## Fehlendes Filament bestätigen

Kann ein benötigter Slot auf dem gewählten Drucker nicht zugeordnet werden,
wird der Auftrag bereitgestellt und nennt das fehlende Filament. **Druck starten**
prüft erneut. Fehlt es weiterhin, bietet der Dialog zwei Möglichkeiten:

- **Abbrechen** erhält den bereitgestellten Auftrag und seine Prüfung.
- **Trotzdem drucken** bestätigt die Filamentabweichung für diesen Auftrag und
  diesen Drucker. Die Warteschlange prüft sie dann nicht erneut vor dem Versand.

Eine bewusst neu gewählte Zuordnung zu einem anderen Material gilt ebenfalls als
Bestätigung. Ein unverändert gespeicherter alter Mapping-Eintrag gilt nicht als
neue bewusste Auswahl. Beim Wechsel des Druckers entfällt eine frühere Bestätigung,
wenn für den neuen Drucker keine neue Bestätigung mitgesendet wird. Andere Sperren,
etwa Druckerzustand, Plattenfreigabe, Trocknungsreservierung und Berechtigungen,
gelten weiterhin.

## Externe Spule und Virtual Printer

Für einen Druck von der externen Spule zählt ausschließlich der Materialbedarf der
gewählten Platte. AMS-Trays, die nur andere Platten derselben Datei verwenden,
schalten den AMS für diese Platte nicht wieder ein. Fehlen die nötigen Quelldaten
oder ist eine Zuordnung ungelöst, wird daraus keine externe Zuführung geraten.
Bei Druckern mit mehreren Düsen bleibt die vorhandene Düsen-Routing-Semantik
maßgeblich.

Ein Virtual Printer für beliebige Drucker eines Modells übernimmt die
AMS-Abwahl des Slicers nicht: Der Slicer sieht den Virtual Printer, dessen spätere
physische Zuordnung noch offen ist. Ein an einen konkreten Drucker gebundener
Virtual Printer erhält dessen Auswahl, auch wenn die Slicer-Meldung verspätet
ankommt. Beim Einrichten von Spulen wird eine vorhandene Materialoberfläche, etwa
Matte oder Silk, bei der Wiederverwendung eines Slot-Presets berücksichtigt.
Explizit gewählte Preset-Identitäten und PrintOps-Kalibrierungsprofile bleiben
maßgeblich.

## Trocknung und Vorläuferfehler

„Trocknung blockiert die Warteschlange“ gilt für feste Drucker und Modellaufträge.
Ein Modellauftrag kann einen anderen freien Drucker wählen. Zeitlich geplante
Modellaufträge zählen beim automatischen Vortrocknen für alle aktiven passenden
Drucker ihres Standorts innerhalb der Erstellerfreigaben; manuell bereitgestellte
Aufträge lösen dadurch kein geplantes Vortrocknen aus.

Vor dem Druck wird ausschließlich die von PrintOps kontrollierte automatische
Trocknung beendet. Die aktivierte und vom Gerät unterstützte Funktion zum
Trocknen während des Drucks darf weiterlaufen. Eine Veröffentlichung eines Befehls
oder ein sichtbarer Timer begründet keine Stop-Berechtigung für fremde Läufe.
Ein geparkter Timer wird nur nach mindestens 150 Sekunden unverändertem positivem
Zähler und wiederholten frischen Inaktivmeldungen erkannt. Fortschritt, eine
aktive Phase, ein neuer Verbindungsnachweis oder ein Geräteeingriff entwerten
diesen Nachweis. Die dauerhaften Reservierungen der
[täglichen AMS-Trocknung](scheduled-ams-drying.md) bleiben unabhängig davon bestehen.

„Nur wenn der vorherige Druck erfolgreich war“ bezieht sich auf den tatsächlich
gewählten Drucker. Ein Modellauftrag wartet, wenn alle freien passenden Drucker
an dieser Sperre stehen. Die Modellfreigabe bestätigt nur Fehler des angezeigten
Modells im zulässigen Druckerbereich. Drucker- und Modellfreigaben ändern weder
das Ergebnis des früheren Drucks noch die Qualitätsbewertung.

## Stapel und Startfehler

Eine reine Gruppierung, deren Läufe alle fehlgeschlagen sind, erscheint als
**Fehlgeschlagen** im Stapelfilter. Ein Produktionsauftrag mit noch offenen
Sollmengen bleibt aktiv. Neue zugehörige Läufe können eine fehlgeschlagene
Gruppierung wieder aktivieren. Abbruch, Löschen, fehlende Quellen und endgültige
Startfehler aktualisieren die Stapelübersicht.

Ein verweigerter Dateiupload wartet auf einen späteren Versuch, statt die
Warteschlange auf einem nicht verfügbaren Drucker abzuarbeiten. Ein ausdrücklich
abgelehnter Start wird in beiden Wartephasen erkannt. Eine MQTT-Neuverbindung
sendet keine Befehle der vorherigen Verbindung erneut. Diese Abläufe ersetzen
keine Bestätigung des tatsächlichen Druckstarts durch den Drucker.

## API-Hinweise

- `GET /api/v1/queue/?status=pending,printing` akzeptiert mehrere durch Komma
  getrennte Statuswerte.
- `POST /api/v1/queue/7/start` kann bei fehlendem Filament `409` mit
  `detail.code = unmatched_filament` und einer Liste `detail.missing` liefern.
  Ein bestätigter Wiederholungsaufruf verwendet `?skip_filament_check=true`.
- `POST /api/v1/queue/model/X1C/resume` bestätigt Vorläuferfehler für das Modell.
  Erforderlich ist `queue:update_all`. Benutzerfreigaben, der Druckerbereich des
  API-Schlüssels und die Druckerfreigaben seines Besitzers begrenzen den Umfang.

Die Beispiele zeigen konkrete Ressourcenkennungen. Bei aktivierter
Authentifizierung gelten die vorhandenen Authentifizierungs- und
Besitzprüfungen auch für den manuellen Start.

## Reprinting a recorded plate

Reprinting from an archive, adding a replacement after production inspection,
and re-queueing a history entry initially select the plate that run printed.
If the source file no longer contains that plate, the dialog selects its first
available plate. Existing queue edits keep their recorded plate when available.
The selected card scrolls into view once; a summary beside the action buttons
shows the plate number and name. Further selections and per-plate quantities
remain editable before submission.

A reprint starts with a clear current failure reason and completion time. Earlier
run records and production inspections remain in the print history. If an expected
archive was deleted after dispatch was registered, an enabled auto-archive creates
a new entry; disabling auto-archive keeps that choice. The deleted source is not
reactivated. Existing queue deletion and active-print protection still apply.

A still-running print with the same printer job ID resumes its archive after a
restart. A different job ID starts a new run unless the current dispatch or the
same printer's running queue entry proves that the source is being reprinted.
Finished and cancelled rows remain historical. A superseded unfinished archive
is marked with the translated reason “No completion status received”. That reason
can be reviewed and saved without changing its stored cancellation status.

When a touchscreen-started print reports its complete 3MF filename as the job
name, PrintOps tries that file first and can match its existing live archive.
A model title that merely ends in “.3mf” still receives the appropriate sliced
file suffix; the two cases are distinguished by the reported file itself.
