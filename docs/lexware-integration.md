# Lexware Office und Warenlager

PrintOps kann Lexware Office lesend anbinden. Lexware Office XL unterstützt die
eigene Public API. Der tatsächliche Zugriff hängt zusätzlich von den Rechten des
erstellten API-Schlüssels ab.

## Einrichtung

1. In Lexware Office einen API-Schlüssel mit Leserechten für Kontakte, Artikel,
   Belege und belegbezogene Zahlungen erstellen. Für Originaldateien werden die
   entsprechenden Dateirechte benötigt. Schreibrechte sind nicht erforderlich.
2. In PrintOps **Einstellungen → Auftragsverwaltung → Lexware Office** öffnen.
3. **Verbindung einrichten** öffnet ein Popup. Dort das passende aktive
   PrintOps-Unternehmensprofil auswählen und den Schlüssel eingeben.
4. Den Schlüssel testen, die angezeigte Lexware-Organisation prüfen und verbinden.
5. **Jetzt aktualisieren** lädt den ersten vollständigen Datenstand.

Pro Unternehmensprofil und Lexware-Organisation ist eine Verbindung möglich.
Eine bestehende Verbindung kann einen neuen Schlüssel derselben Organisation
erhalten, aber nicht einer anderen Organisation zugeordnet werden.
**Schlüssel verwalten** im Drei-Punkte-Menü der Verbindung öffnet dafür ein eigenes
Popup. Auch Pausieren und Trennen befinden sich in diesem Menü.

Schlüssel nur in das dafür vorgesehene Feld eingeben, nicht in Tickets, Chat oder
Konfigurationsdateien im Repository. Das Backend speichert sie mit der vorhandenen
Fernet-Verschlüsselung. Die HTTP-Antworten enthalten weder den Schlüssel noch dessen
verschlüsselte Fassung. Wenn sichere Speicherung nicht verfügbar ist, wird das
Verbinden abgewiesen.

## Abrufe und lokale Übernahme

Bei laufendem PrintOps-Backend werden aktive Verbindungen ungefähr alle 15 Minuten
abgerufen. Manuelles Aktualisieren verwendet denselben Ablauf. Listen werden
vollständig paginiert; Kunden, Artikel, Belege und Zahlungsinformationen werden erst
nach einem erfolgreichen Gesamtabruf gemeinsam veröffentlicht. Bei Fehlern bleibt
der letzte vollständige Datenstand erhalten. Status, letzter erfolgreicher Abruf und
Verbindungsprofil sind an der Verbindung sichtbar.

Automatisch aktualisiert wird die externe Ansicht. Lokale Kunden und Artikel ändern
sich nur über **Vorschau** und eine anschließende bewusste Auswahl. Die Vorschau
öffnet sich als Popup über der Tabelle; Suche, Filter und Auswahl bleiben beim
Schließen erhalten. Komplexe Werte zeigen eine Kurzfassung und lassen sich über
**Alle Felder anzeigen** vollständig aufklappen. Während der Übernahme ist das
Schließen gesperrt. Namen
führen nicht automatisch zur Zusammenführung. Bereits zugeordnete Datensätze können
nicht beiläufig umverknüpft werden. Änderungen seit der Vorschau erfordern eine neue
Prüfung.

Bei Kunden lassen sich Identität, Kundennummer, Adressen, Kontaktdaten und Steuerkennungen
getrennt übernehmen. Bei neuen Kunden ist die Lexware-Kundennummer vorausgewählt.
Ohne übernommene Nummer verwendet PrintOps seinen lokalen Nummernkreis. Bei bereits
verknüpften Kunden lässt sich die Nummer nachträglich über **Vorschau** und
Auswahl von **Kundennummer** übernehmen. Sie ändert sich nur im Unternehmensprofil
der Verbindung; doppelte Nummern werden abgewiesen. Kontozuordnungen und bestehende
Belegschnappschüsse bleiben erhalten. Interne Notizen, Tags und nicht ausgewählte
Daten bleiben ebenfalls erhalten. Bei einem
Kunden, den mehrere Unternehmensprofile gemeinsam verwenden, warnt die Vorschau
vor den Auswirkungen auf diese Profile. Neue Kunden können nach Prüfung ihrer
Vorschauen gemeinsam übernommen werden.
Neue Kunden erhalten die Währungs- und Sprachvorgaben des verbundenen
Unternehmensprofils. Bei bestehenden Kunden bleiben diese Einstellungen erhalten.

Neue Artikel benötigen eine lokale Artikelnummer, eine bestätigte Art und Einheit
sowie eine Bestandsquelle. Lexware-Verkaufspreise werden nicht als Einstandskosten
verwendet. Lagerbestände werden nicht von Lexware geliefert oder aus Rechnungen
automatisch gebucht.

Bei bestehenden Artikeln werden externe und lokale Einheit zur Bestätigung
gegenübergestellt. Die Übernahme setzt dieselbe Mengenbasis voraus; eine automatische
Umrechnung, etwa von Kilogramm auf Stück, findet nicht statt.

**Abruf pausieren** behält den Schlüssel. **Verbindung trennen** entfernt ihn und
stoppt weitere Abrufe; lokale Daten, externe Schnappschüsse und bereits geladene
Originale bleiben erhalten. Eine nachträglich eintreffende Antwort eines getrennten
Abrufs darf keine neuen Daten veröffentlichen. Profile mit gespeicherter Verbindung
und verknüpfte Kunden werden deaktiviert beziehungsweise archiviert statt gelöscht.

## Warenlager

**Lager → Warenlager** verwaltet Fertigprodukte, Handelswaren und Dienstleistungen.
Wie im Filamentbestand und unter **Material** steht die Suche über den Filtern.
Mit **Aktiv**, **Archiviert** und **Alle** wechselst du den Artikelstatus.
Artikelart, Bestandsquelle und **Unter Mindestbestand** grenzen die Liste weiter ein.
Material und Warenlager bieten dieselbe Anordnung für Suche, Spaltenauswahl,
Gruppierung, Sortierung nach Restmenge sowie Tabelle und Karten. Material gruppiert
nach Kategorie, das Warenlager nach Artikelart innerhalb der geladenen Seite.
Die Filter für Verwendung und Mindestbestand lassen sich mit Kategorie,
bevorzugtem Lieferanten, Lagerort und Einheit im Materiallager kombinieren.
Im Warenlager stehen dafür Artikelart, Bestandsquelle, Lagerort und Einheit zur
Verfügung. Lagerorte für eigene Waren folgen dem aktuellen physischen Bestand.
Bei verknüpften Artikeln gilt der Lagerort des Materials. Die Trefferzahl und
das Rücksetzen stehen am Ende der Filterleiste.
Die Spaltenköpfe sortieren die gesamte gefilterte Liste. Wiederholtes Anklicken
wechselt zwischen aufsteigend, absteigend und der Standardreihenfolge.
Material und Warenlager zeigen die interne Nummer, das Erfassungsdatum, die
letzte gebuchte Entnahme und die bisher verbrauchte Menge. Die Spalte **Verbleibend**
zeigt den physischen Bestand im Verhältnis zu physischem Bestand plus gebuchtem
Verbrauch. Jede Menge trägt die Einheit des Artikels. Gegenbuchungen heben
die ursprüngliche Entnahme für die Verbrauchsanzeige auf.
Ein Klick auf die Zeile öffnet bei Bearbeitungsrechten den Editor. Mit den
Auswahlkästchen und **Inventur bestätigen** protokollierst du einen gezählten oder
gewogenen Bestand. Der dabei gespeicherte Zeitpunkt erscheint unter **Geprüft**.
Bei verknüpften Handelsartikeln gehört die Prüfung zum zugrunde liegenden
Material. Der Filamentbestand unterstützt dieselbe Bestätigung für lokale Spulen.
In den drei Lagertabellen bleibt das Drei-Punkte-Menü der Zeile rechts sichtbar.
Das Warenlager bietet mit den jeweiligen Berechtigungen Artikeldetails, Bearbeitung,
Archivieren und Reaktivieren. **Wareneingang** und **Freier Warenausgang** öffnen
bei aktiven, buchbaren Beständen direkt den passenden Dialog. Für Dienstleistungen
ohne Bestand gibt es keine Buchungsaktion. Unter **Material** sind auch
Einzel-Etikettendruck und Statuswechsel direkt über das Zeilenmenü erreichbar.
**Duplizieren** öffnet in beiden Lagern einen neuen Stammdatensatz zum Prüfen und
Speichern. Die Artikelnummer ist leer, Bestand und Historie beginnen bei null.
Lieferantenangebote, verknüpfte Materialbestände und Projektbezüge werden bei der
jeweiligen Kopie nicht übernommen.

Die Artikelverwaltung ist auch ohne Lexware nutzbar. Es gibt drei Bestandsquellen:

| Quelle | Verhalten |
| --- | --- |
| Eigener Warenbestand | Eigenes Journal und Bestände je PrintOps-Lagerort |
| Bestehendes Material | Anzeige des bestehenden Materialbestands; Buchungen erfolgen weiterhin in der Materialverwaltung |
| Kein Bestand | Dienstleistungen ohne Lagerbuchungen |

Ein Materialdatensatz kann nur einem Verkaufsartikel als Bestandsquelle dienen.
Für eigene Waren sind Anfangsbestand, Wareneingang, Warenausgang, Umbuchung,
Inventurkorrektur, Reservierung und Freigabe möglich. Ein Ausgang gegen eine
Reservierung vermindert physische und reservierte Menge gemeinsam. Gründe sind
verpflichtend; ein Auftragsbezug ist optional.

Verfügbar ist der physische Bestand abzüglich Reservierungen. Negative Bestände,
Überreservierungen und das Umbuchen bereits reservierter Ware werden abgewiesen.
Mengen werden mit bis zu sechs Nachkommastellen exakt gespeichert; die jeweilige
Einheit kann weniger Nachkommastellen erlauben. Wiederholungen derselben Buchung
mit demselben Request-Schlüssel erzeugen keine weiteren Bewegungen.
Bei einer unklaren Netzwerkantwort bleibt der Buchungsauftrag beim erneuten Öffnen
im selben Browser-Tab erhalten. Die unveränderte Wiederholung prüft das Ergebnis
mit demselben Schlüssel; die gesperrten Felder verhindern eine versehentliche
zweite Buchung mit geänderten Angaben.

Das Journal ist unveränderlich. Fehler werden durch Gegenbuchungen berichtigt.
Einheiten und Bestandsquellen sind nach Beginn der Historie geschützt. Artikel mit
Restbestand oder Reservierungen können nicht archiviert werden.

### Bestand planen und nachproduzieren

Die **Bestandsprognose** im Warenlager berechnet aus den wirksamen Entnahmen
der letzten 30 Tage den voraussichtlichen Bestand und die Tage bis zum
Mindestbestand. Wenn keine Entnahmen vorliegen, zeigt sie das entsprechend an.

Unter **Lager → Nachbestellbedarf** stehen fertige Waren und Materialfehlmengen
in getrennten Tabellen. Ein Zeilenklick springt zum Eintrag im jeweiligen Lager.
Über das Drei-Punkte-Menü kannst du Material auf die gespeicherte **Einkaufsliste**
setzen. Bei Fertigprodukten öffnet **Nachproduzieren** einen neuen Projektentwurf
mit dem ausgewählten Artikel und der vorgeschlagenen Fehlmenge als Teileziel.
Vor dem Speichern wählst du den Ziellagerort.

Für Projekte mit einem solchen Lagerziel bestätigst du zuerst die Gutteile der
fertigen Druckläufe. Beim Projektabschluss bucht PrintOps diese Stückzahl am
gewählten Lagerort. Ein Drucklauf wird dabei einmal berücksichtigt. Ohne
Lagerziel bleibt der übliche Projektabschluss ohne automatische Lagerbuchung.
Zum Festlegen des Ziels und zur automatischen Buchung beim Abschluss ist
`inventory:update` zusätzlich zu den Projektrechten erforderlich.

### API für Bestand und Beschaffung

- `GET /api/v1/warehouse-articles` akzeptiert `sort_by`, `sort_dir`, `limit`
  und `offset`. `GET /api/v1/warehouse-articles/forecast` liefert die
  paginierte Warenprognose. Beide verwenden `inventory:read`.
- `POST /api/v1/inventory/spools/stock-check`,
  `POST /api/v1/small-parts/stock-check` und
  `POST /api/v1/warehouse-articles/stock-check` speichern den Inventurzeitpunkt
  für die übergebenen Artikel-IDs. Sie verwenden `inventory:update`.
- `GET /api/v1/warehouse-shopping-list` liest die Material-Einkaufsliste.
  Ein Material lässt sich mit `PUT /api/v1/warehouse-shopping-list/material/{resource_id}`
  hinzufügen und mit `DELETE /api/v1/warehouse-shopping-list/{item_id}`
  entfernen. Änderungen verwenden `inventory:update`.

## Belege und Finanzen

**Aufträge → Lexware-Belege** zeigt externe Belege getrennt von in PrintOps
ausgestellten Dokumenten. Unterstützt sind Rechnungen, Rechnungskorrekturen,
Angebote, Auftragsbestätigungen sowie Einkaufs- und Verkaufsbelege der Buchhaltung.
Andere Arten, insbesondere Abschlagsrechnungen und Lieferscheine, bleiben sichtbar
als nicht unterstützt und fließen nicht in die Finanzsummen ein.

Die separate Finanzübersicht zeigt offene Forderungen und Verbindlichkeiten,
Überfälligkeit und Zahlungspositionen je Währung. Unvollständige, widersprüchliche
oder nicht zugängliche Zahlungsinformationen gelten als unbekannt. Entwürfe,
stornierte und nicht unterstützte Belege werden nicht als offene Forderungen
gezählt. Verrechnung, Skonto und Ausbuchung sind keine Bankzahlungen.

Eine manuelle Zuordnung zu einem bereits ausgestellten lokalen Beleg setzt dasselbe
Unternehmensprofil, passende Belegart, Währung und Bruttobetrag voraus. Ein Beleg
kann nur einmal zugeordnet werden. Der zugeordnete externe Betrag wird aus der
separaten Lexware-Summe ausgeschlossen. Die Zuordnung ändert weder lokale
Zahlungen noch Nummernkreise oder ausgestellte Dokumente.

Originale werden bei Bedarf heruntergeladen, nach Dateityp und Größe geprüft
(maximal 10 MiB je Original) und mit SHA-256-Prüfsumme unveränderlich in der
Datenbank zwischengespeichert. Unterstützte Formate sind PDF, XML, PNG und JPEG.
Bei Verkaufsbelegen wird die Lexware-Version vor und nach dem Dateidownload geprüft.
Hat sich der Beleg geändert oder fehlt eine prüfbare Version, ist zuerst ein neuer
Abruf erforderlich; die Datei wird nicht unter einer veralteten Version gespeichert.
Bereits geladene Versionen bleiben nach späteren Abrufen und nach dem Trennen
verfügbar. Es werden keine Ersatz-PDFs aus lokalen Daten erzeugt.

Vollständige Bankumsätze, Kontostände, Zahlungen ausführen, Belegversand und
Schreibzugriffe nach Lexware sind nicht enthalten. Die öffentliche API dokumentiert
keine Lagerbestände und keine vollständige Bankkontenabfrage.

## Rechte und Betrieb

| Aktion | PrintOps-Berechtigungen |
| --- | --- |
| Verbindung verwalten und Abruf starten | `accounting_integrations:manage` |
| Externe Kunden lesen | `customers:read` |
| Kundenvorschau und Übernahme | zusätzlich Integrationsverwaltung; Übernahme zusätzlich `customers:manage` |
| Artikel lesen und übernehmen | `inventory:read`; Übernahme zusätzlich Integrationsverwaltung und `inventory:create` beziehungsweise `inventory:update` |
| Externe Belege lesen | `commercial_documents:read` |
| Finanzdaten und Originaldateien lesen | zusätzlich `payments:read` |
| Lokalen Beleg zuordnen | zusätzlich `commercial_documents:draft` |

Die Prüfungen erfolgen im Backend. Finanzfelder und Originaldateien werden ohne
Zahlungsleserecht nicht in Belegantworten ausgeliefert. Bestehende Rechte für lokale
Lagerbuchungen gelten auch im Warenlager.
Integrationsverwalter ohne allgemeines Einstellungsleserecht erreichen unter
**Einstellungen** ausschließlich die Lexware-Verwaltung. Andere Einstellungsbereiche
und deren Daten bleiben gesperrt.

Der Transport verwendet ausschließlich GET gegen `https://api.lexware.io` und eine
feste Pfadliste. Weiterleitungen werden nicht verfolgt. Abrufe werden unterhalb des
dokumentierten Limits von zwei Requests pro Sekunde gedrosselt und bei temporären
Fehlern begrenzt wiederholt. Diese Koordination gilt für einen Backend-Prozess;
mehrere parallel betriebene Backend-Instanzen benötigen eine gemeinsame
Abrufkoordination und sind für diese Integration nicht vorgesehen.

Schnappschüsse, Zuordnungen, Lagerjournal und gecachte Originale liegen in der
Datenbank und sind Teil der bestehenden vollständigen Sicherung. Der verwendete
Verschlüsselungsschlüssel muss ebenfalls erhalten bleiben; vollständige PrintOps-
Backups berücksichtigen die lokale Schlüsseldatei. Bei extern vorgegebenem
Verschlüsselungsschlüssel muss dieser separat sicher wiederhergestellt werden.
Nach Wiederherstellung den Verbindungsstatus prüfen und gegebenenfalls erneut
verbinden. Backups enthalten vertrauliche Geschäfts- und Zugangsdaten und sind
entsprechend zu schützen.

Referenzen: [Lexware Public API](https://developers.lexware.io/docs/) und
[Lexware-Hilfe zur Public API](https://help.lexware.de/de-form/articles/548863-alles-rund-um-public-api).
