# Kalkulationsentwürfe abbrechen und löschen

## Ziel

Automatisch für einen 3MF-Upload angelegte Kalkulationsentwürfe dürfen nicht als scheinbar bewusst gespeicherte Kalkulationen zurückbleiben. Gleichzeitig benötigen bestehende Entwürfe eine ausdrückliche Löschfunktion. Freigegebene, ersetzte und archivierte Kalkulationen bleiben aus Gründen der Nachvollziehbarkeit erhalten.

## Verhaltensregeln

- Löschen ist ausschließlich für Kalkulationen mit Status `draft` zulässig.
- Wird eine neue Kalkulation erst durch den 3MF-Upload automatisch gespeichert, löschen `Abbrechen` und das Schließen über `X` diesen Entwurf sofort und ohne Rückfrage.
- Das automatische Verwerfen gilt nur für den Entwurf, der innerhalb des aktuell geöffneten Neuanlage-Dialogs erzeugt wurde.
- Eine Kalkulation, die bereits vor dem Öffnen des Dialogs existierte, wird durch `Abbrechen` oder `X` nur geschlossen.
- Bestehende Entwürfe erhalten eine ausdrückliche Aktion `Löschen` mit Sicherheitsabfrage.
- Freigegebene und ersetzte Kalkulationen behalten die Aktion `Archivieren`. Archivierte Kalkulationen haben keine Löschaktion.

## Backend

Die Kalkulations-API erhält folgenden Endpunkt:

```text
DELETE /api/v1/calculations/{calculation_id}?expected_version={version}
```

Der Endpunkt:

1. benötigt die Berechtigung `CALCULATIONS_UPDATE`,
2. lädt und sperrt die Kalkulation,
3. prüft die erwartete Version,
4. lehnt jeden Status außer `draft` als fachlichen Konflikt ab,
5. löscht die Kalkulation samt kaskadierenden Kinddatensätzen,
6. bestätigt die Datenbanktransaktion,
7. entfernt danach den kalkulationsbezogenen Dateibaum unter `calculations/{id}`.

Die Datenbank bleibt die führende Quelle. Schlägt die Dateisystembereinigung nach erfolgreichem Datenbank-Commit fehl, wird der Fehler protokolliert; der fachlich bereits gelöschte Entwurf darf nicht wieder als vorhanden gemeldet werden. Die Pfadbereinigung arbeitet ausschließlich mit einem aus der numerischen Kalkulations-ID gebildeten, gegen das konfigurierte Basisverzeichnis geprüften Pfad.

Antwort bei Erfolg: HTTP `204 No Content`.

Fehlerfälle:

- unbekannte Kalkulation: `404`,
- Versionskonflikt: `409`,
- Status ist nicht `draft`: `409`,
- fehlende Berechtigung: bestehendes Authentifizierungs-/Autorisierungsverhalten.

## Frontend und Zustandsfluss

`CalculationWorkspace` führt einen sitzungsbezogenen Zustand, der ausschließlich nach erfolgreichem Aufruf von `ensureCalculationForUpload` gesetzt wird. Er enthält ID und Version des automatisch erzeugten Entwurfs. Das Öffnen einer vorhandenen Kalkulation setzt diesen Zustand nicht.

### Automatisch erzeugten Entwurf verwerfen

Bei `Abbrechen` oder `X`:

1. Existiert kein sitzungsbezogener Autosave-Entwurf, wird der Dialog normal geschlossen.
2. Existiert ein Autosave-Entwurf, ruft der Dialog den DELETE-Endpunkt ohne Rückfrage auf.
3. Während des Löschens sind Schließen und Footer-Aktionen deaktiviert, um doppelte Anfragen zu verhindern.
4. Nach Erfolg wird der Dialog geschlossen und die Kalkulationsliste neu geladen.
5. Bei einem Fehler bleibt der Dialog geöffnet und zeigt die lokalisierte Fehlermeldung. Der Autosave-Zustand bleibt erhalten, damit der Löschversuch wiederholt werden kann.

Ein ausdrücklich betätigtes `Speichern` beendet den temporären Charakter des Entwurfs. Danach schließt `Abbrechen` nur noch den Dialog.

### Bestehenden Entwurf löschen

Bei einer vorhandenen Kalkulation mit Status `draft` zeigt der linke Footer-Bereich einen roten `Löschen`-Button. Nach Betätigung erscheint der bestehende `ConfirmModal` mit einer eindeutigen Warnung, dass Kalkulation und hochgeladene Projektdateien endgültig entfernt werden. Die Bestätigung ruft denselben DELETE-Endpunkt auf. Erfolg schließt den Dialog und lädt die Liste neu; Fehler bleiben im Dialog sichtbar und können erneut versucht werden.

## API-Client

`calculationsApi` erhält eine Methode:

```ts
remove(id: number, expectedVersion: number): Promise<void>
```

Sie verwendet den zentralen Request-Client und sendet `DELETE` mit `expected_version`.

## Tests

### Backend

- Ein Entwurf wird bei passender Version gelöscht und ist anschließend nicht mehr abrufbar.
- Varianten, Plattenverknüpfungen, Projektdateidatensätze und der kalkulationsbezogene Dateibaum werden entfernt.
- Freigegebene, ersetzte und archivierte Kalkulationen können nicht gelöscht werden.
- Eine veraltete Version erzeugt einen Versionskonflikt.
- Eine unbekannte ID liefert `404`.

### Frontend

- Nach einem uploadbedingten Autosave löscht `Abbrechen` den erzeugten Entwurf ohne Bestätigungsdialog.
- Das Schließen über `X` verwendet denselben Ablauf.
- Schlägt das Löschen fehl, bleibt der Dialog geöffnet und zeigt den Fehler.
- Nach ausdrücklichem Speichern wird bei `Abbrechen` nicht gelöscht.
- Das Abbrechen einer bereits vorhandenen Kalkulation löscht nicht.
- Bestehende Entwürfe zeigen `Löschen`; andere Status zeigen diese Aktion nicht.
- Die manuelle Löschaktion verlangt eine Bestätigung und aktualisiert nach Erfolg die Liste.

## Nicht Bestandteil

- Wiederherstellung oder Papierkorb für Kalkulationen.
- Löschen freigegebener, ersetzter oder archivierter Kalkulationen.
- Automatische zeitgesteuerte Bereinigung verwaister Entwürfe.
- Änderungen an Reservierungen; Entwürfe besitzen noch keine verbindlichen Lagerreservierungen.
