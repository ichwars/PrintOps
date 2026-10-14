# App-Nachrichten

Externe Anwendungen können über einen eigenen API-Schlüssel Nachrichten an ausdrücklich freigegebene PrintOps-Benachrichtigungskanäle senden. Die Anmeldung über „Verbundene Anwendungen“ erteilt diese Berechtigung nicht.

## Einrichtung

1. Anmeldung aktivieren und als Administrator unter **Einstellungen → Integrationen → API** einen eigenen API-Schlüssel anlegen. **App-Nachrichten** aktivieren. Andere Berechtigungen nur aktivieren, wenn die Anwendung sie tatsächlich benötigt; insbesondere erlaubt „Status lesen“ bereits den Zugriff auf vorhandene Status- und Benachrichtigungseinstellungen.
2. Bei jedem gewünschten Benachrichtigungsanbieter **App-Nachrichten** aktivieren. Neue und bestehende Anbieter sowie bestehende Schlüssel erhalten diese Freigabe nicht automatisch.
3. Den vollständigen Schlüssel sicher in der Anwendung hinterlegen. PrintOps zeigt ihn nur beim Anlegen an. Den API-Schlüssel niemals in URLs oder Browser-Frontend-Code veröffentlichen.

Die Freigabe kann in der Liste vorhandener Schlüssel über **App-Nachrichten** wieder entzogen oder bei Schlüsseln mit gültiger Eigentümerbindung aktiviert werden.

Der Schlüssel bleibt an seinen ursprünglichen aktiven Benutzer gebunden. Abgelaufene, deaktivierte oder gelöschte Schlüssel werden abgewiesen. Ein späterer Benutzer mit derselben numerischen ID erbt keine Freigabe. Schlüssel aus Versionen ohne diese Eigentümerbindung müssen für App-Nachrichten neu angelegt werden. Ein gültiger gebundener Schlüssel funktioniert auch bei später deaktivierter Anmeldung; anonyme Nachrichten und reine Anmeldetokens bleiben gesperrt. Neue Schlüssel mit dieser Freigabe benötigen eine angemeldete Identität.

## API-Beispiel

Die folgenden Befehle senden eine echte Nachricht, wenn sie mit einem echten Schlüssel und einer erreichbaren Installation ausgeführt werden. `PRINTOPS_API_KEY` enthält den eigenen API-Schlüssel, `PRINTOPS_URL` die Basis-URL der Installation.

```sh
curl --fail-with-body "$PRINTOPS_URL/api/v1/notifications/app-message/channels" \
  -H "X-API-Key: $PRINTOPS_API_KEY"

curl --fail-with-body "$PRINTOPS_URL/api/v1/notifications/app-message" \
  -H "X-API-Key: $PRINTOPS_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Auftrag bereit","message":"Die neue Druckdatei ist verfügbar.","channel_ids":[12]}'
```

Alternativ wird `Authorization: Bearer <API-Schlüssel>` unterstützt. Die Kanalliste enthält ausschließlich `id`, `name` und `provider_type`, keine Zugangsdaten oder Provider-Konfiguration. `channel_ids` ist eine optionale Liste von 1 bis 50 IDs. Ohne Auswahl werden alle für den Kontext geeigneten Kanäle verwendet, höchstens 50. Unbekannte, deaktivierte, nicht freigegebene oder außerhalb des Druckerbereichs liegende IDs führen zur Ablehnung der gesamten Anfrage.

| Feld | Bedeutung |
| --- | --- |
| `title` | Pflicht, 1–120 druckbare Zeichen auf einer Zeile; keine Zeilenumbrüche, Tabulatoren oder Steuerzeichen; nach Bereinigung nicht leer |
| `message` | Pflicht, 1–2000 Zeichen, nach Bereinigung nicht leer |
| `url` | Optional, höchstens 500 Zeichen, HTTP(S)-Adresse ohne Zugangsdaten oder Leerzeichen; wird als Text angefügt |
| `channel_ids` | Optional, 1–50 Kanal-IDs |
| `printer_id` | Optional für uneingeschränkte Schlüssel, erforderlich bei Druckerbeschränkung |

Die erlaubten Drucker ergeben sich aus der Schnittmenge der aktuellen Benutzer- und Schlüsselbeschränkung. Mit `printer_id` kommen globale Kanäle und Kanäle dieses Druckers infrage. Ohne Druckerkontext verwendet ein uneingeschränkter Aufruf nur globale Kanäle. Ein eingeschränkter Listenaufruf ohne Druckerkontext zeigt nur Kanäle seiner erlaubten Drucker; für die tatsächliche Zustellung ist `printer_id` erforderlich. Die Kanalliste akzeptiert denselben Parameter, beispielsweise `?printer_id=4`.

## Grenzen und Zustellung

Pro API-Schlüssel sind höchstens **20 Nachrichten in einem gleitenden 60-Sekunden-Fenster** möglich, gemeinsam über alle Kanäle, Prozesse und Neustarts. Ein Versandversuch verbraucht eine Nachricht, auch wenn ein Anbieter fehlschlägt oder Ruhezeiten die Zustellung unterdrücken. Ungültige Anfragen lösen keinen Versand aus. HTTP `429` enthält `Retry-After: 60`; `401` bedeutet fehlender/ungültiger Schlüssel, `403` fehlende Freigabe oder unzulässiger Bereich, `422` ungültige Eingabefelder und `400` fehlende geeignete Kanäle oder eine zu große implizite Auswahl.

HTTP `200` mit `{"channels":1}` bestätigt die Verarbeitung für einen Kanal, nicht dessen erfolgreiche externe Zustellung. Der bestehende Versand protokolliert Versuche und aktualisiert den Anbieterstatus. Ruhezeiten gelten weiterhin. Bei aktiviertem Tagesbericht werden Titel, vollständiger Nachrichtentext und optionale URL zusätzlich in die Zusammenfassung aufgenommen; der Tagesbericht ersetzt den unmittelbaren Versandversuch nicht. Die globale Zeiteinstellung für Ruhezeiten und Tagesberichte bleibt unverändert.

App-Inhalte werden als Text behandelt: Telegram erhält keinen Markdown-Parse-Modus, Discord und Home Assistant erhalten maskierte Auszeichnung, Slack erhält Klartextblöcke ohne Erwähnungsauflösung. Der gemeinsame Slack/Mattermost-Fallback maskiert zusätzlich Markdown/HTML und unterbricht `@`-Erwähnungen mit einem unsichtbaren Trennzeichen, da Mattermost die Slack-Parsing-Schalter ignoriert. In Vorschauen können deshalb Maskierungszeichen sichtbar sein. Andere Provider erhalten ihren bisherigen Texttransport. Tagesberichte mit App-Inhalten verwenden ebenfalls die sichere Darstellung. Benutzerdefinierte nachgelagerte Webhook-Empfänger müssen ihre eigene Darstellung entsprechend absichern.

Lange App-Nachrichten und Tagesberichte mit App-Inhalten werden ohne Abschneiden auf mehrere Provider-Nachrichten verteilt. Die Grenzen gelten nach der jeweiligen Textkodierung:

| Provider | Darstellung und Grenze je Teil |
| --- | --- |
| Slack / Mattermost | Ein Slack-Klartextblock mit höchstens 3000 UTF-16-Einheiten; maskierter Mattermost-Fallback höchstens 15000 Zeichen |
| Discord | Höchstens 256 UTF-16-Einheiten im maskierten Titel und 4096 im Text; ein Embed je Nachricht, somit unter 6000 insgesamt. Zu lange maskierte Titel stehen vollständig am Anfang des Texts. |
| Pushover | Höchstens 1024 Unicode-Zeichen im Nachrichtentext einschließlich angefügter URL; HTML bleibt deaktiviert. |
| Telegram | Höchstens 4096 UTF-16-Einheiten je Klartextnachricht. |

Die Providergrenzen sind dokumentiert bei [Slack](https://docs.slack.dev/reference/block-kit/blocks/section-block/), [Mattermost](https://docs.mattermost.com/developers/integrate/webhooks/incoming), [Discord](https://docs.discord.com/developers/resources/message#embed-object-embed-limits), [Pushover](https://pushover.net/api) und [Telegram](https://core.telegram.org/bots/api#sendmessage). UTF-16 wird vorsichtig gezählt; zusammengehörige Maskierungssequenzen und Unicode-Codepunkte werden nicht geteilt. Lange Links können über mehrere Nachrichten verteilt werden und sind dann eventuell nicht mehr direkt anklickbar.

Jeder Teil kann ein eigenes Providerkontingent verbrauchen und eine eigene Push-Meldung auslösen; bei Pushover gilt auch eine eingestellte Notfallpriorität für jeden Teil. PrintOps zählt weiterhin eine API-Anfrage für sein 20/60-Sekunden-Kontingent und gibt die Anzahl bearbeiteter Kanäle zurück, nicht die Zahl der Teilnachrichten. Bei einem Fehler stoppt der Versand der weiteren Teile dieses Kanals und protokolliert einen Fehlschlag. Unmittelbare Versandversuche werden nicht automatisch wiederholt. Ein fehlgeschlagener Tagesbericht mit App-Inhalten behält sämtliche Einträge für den nächsten geplanten Versuch; bereits zugestellte Teile können dabei nochmals erscheinen. Erst ein erfolgreicher Tagesbericht leert diese Warteschlange. Die bisherige Behandlung reiner Druckereignis-Berichte und der Ruhezeiten bleibt bestehen.

## Betrieb und Entwicklung

Die Migration ergänzt `api_keys.can_send_notifications` und `notification_providers.on_app_message` mit `FALSE` sowie die unveränderliche Eigentümerbindung. `app_message_quotas` speichert höchstens 20 Zeitstempel je Schlüssel. SQLite serialisiert die kurze Schreibtransaktion, PostgreSQL die jeweilige Schlüsselzeile. Ein atomarer Upsert sperrt vor dem Lesen der Zeitstempel; der Commit erfolgt vor Provider-Netzwerkaufrufen. Abgelaufene Zeitstempel werden bei der nächsten Anfrage entfernt, beim Widerruf und beim Löschen des Eigentümers wird die Kontingentzeile auch ohne SQLite-Fremdschlüsselprüfung gelöscht. Aufträge, Lager und andere bestehende Schlüsselberechtigungen bleiben eigenständig.

Die automatisierten Tests verwenden ausschließlich nachgebildete Providertransporte. SQLite-Dateitests prüfen Parallelität, echte getrennte Prozesse, Neustart und Benutzer-ID-Wiederverwendung. PostgreSQL-Tests benötigen `F01_TEST_POSTGRES_DSN` auf einer isolierten Testdatenbank und erzeugen/löschen dafür eigene Testschemas.
