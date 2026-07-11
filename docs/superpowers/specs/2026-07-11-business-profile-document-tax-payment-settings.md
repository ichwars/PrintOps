# Unternehmensprofil: Dokument-, Steuer- und Zahlungsangaben

Stand: 2026-07-11

## Ziel

Unternehmensprofile erhalten persistente Einstellungen für Dokumentdarstellung,
internationale Umsatzsteuerbehandlung und PayPal-Zahlungen. Die Einstellungen
bereiten Angebote, Rechnungen und PDFs vor, ohne die noch nicht vorhandene
Dokumentpipeline vorwegzunehmen.

## Funktionsumfang

### Logo

- Jedes Unternehmensprofil kann genau ein Logo besitzen.
- Unterstützt werden serverseitig validierte PNG- und JPEG-Bilder bis 2 MB.
- Die Datei liegt in einem verwalteten Unterverzeichnis des PrintOps-Datenverzeichnisses.
- Die Datenbank speichert Dateiname, Medientyp und Versionskennung, nicht die Bilddaten.
- Separate berechtigungsgeschützte Endpunkte übernehmen Upload, Abruf und Löschung.
- Ein erfolgreicher Upload aktualisiert die Vorschau sofort.
- Das Logo kann ersetzt und entfernt werden.
- Die Profilübersicht zeigt vor dem Profilnamen eine kleine Logo-Miniatur. Ohne Logo
  erscheint ein neutraler Platzhalter, damit die Zeilen ausgerichtet bleiben.
- Dateinamen werden nicht vertraut; der Server erzeugt den Speicherpfad selbst.
- Beim Löschen eines Profils wird die verwaltete Logodatei entfernt. Fehlende Dateien
  führen beim Abruf zu einer kontrollierten 404-Antwort.

### Online-Angebots-QR-Code

- `show_offer_qr` wird als boolesche Profileinstellung gespeichert, Standard `false`.
- Die Oberfläche erklärt, dass eine von außen erreichbare PrintOps-URL erforderlich ist.
- Der Schalter wird bereits vollständig verwaltet; die tatsächliche QR-Ausgabe erfolgt
  erst in der späteren Angebots- und PDF-Pipeline.

### Internationales Steuermodell

- `tax_mode`: `standard`, `exempt` oder `none`.
- `default_tax_rate`: Dezimalwert von 0 bis 100 mit höchstens zwei Nachkommastellen.
- `cash_accounting`: boolesche Information zur Ist-Versteuerung.
- `input_tax_deductible`: boolescher Status zum Vorsteuerabzug.
- Bei `exempt` oder `none` gilt zwingend: Steuersatz 0 und kein Vorsteuerabzug.
- Bei deutschem Profil wird `exempt` als „Kleinunternehmerregelung §19 UStG“ bezeichnet.
  In anderen Ländern wird eine neutrale lokalisierte Bezeichnung verwendet.
- Bei `standard` darf der Steuersatz 0 bis 100 betragen; 0 bleibt für fachliche
  Sonderfälle zulässig.
- Steuer-ID und Steuernummer bleiben in der vorhandenen Liste der Steuerkennungen.
- Die Oberfläche weist darauf hin, dass die Konfiguration keine steuerliche Prüfung ersetzt.

### PayPal

- `paypal_me_url` ist eine optionale Profileinstellung.
- Zulässig sind ausschließlich HTTPS-URLs mit Host `paypal.me` oder `www.paypal.me`.
- Pfad, Groß-/Kleinschreibung und optionale PayPal-Betragssegmente bleiben erhalten.
- Leere Eingaben werden als `null` gespeichert.
- Das Feld steht im Bereich Bank und Zahlungsdaten, bleibt aber unabhängig von einzelnen
  Bankkonten, weil es für das ausstellende Unternehmensprofil gilt.

## API und Persistenz

- Das Profilmodell, Create-/Update-/Response-Schemas und der Frontendvertrag werden um
  die strukturierten Felder sowie Logo-Metadaten erweitert.
- Listen- und Detailantworten enthalten nur Logo-Verfügbarkeit und Versionskennung; keine
  Base64- oder Binärdaten.
- Logoabrufe verwenden eine versionierte URL, damit Browsercaches nach Austausch sicher
  invalidiert werden.
- Profilupdates bleiben versionsgesichert. Logo-Upload und -Löschung erhöhen ebenfalls
  die Profilversion und prüfen die erwartete Version, damit parallele Änderungen nicht
  überschrieben werden.
- Die bestehende Berechtigung `order_settings:manage` schützt Mutation und Upload;
  `order_settings:read` schützt Profil- und Logoabrufe.

## Migration und Standardwerte

- Bestehende deutsche Profile: `tax_mode=standard`, `default_tax_rate=19.00`,
  `input_tax_deductible=true`.
- Bestehende andere Profile: `tax_mode=standard`, `default_tax_rate=0.00`,
  `input_tax_deductible=true`.
- Für alle Profile: `cash_accounting=false`, `show_offer_qr=false`,
  `paypal_me_url=null` und keine Logo-Metadaten.
- Die Migration muss auf SQLite und PostgreSQL wiederholbar und upgrade-sicher sein.

## Oberfläche

- Der Profil-Editor erhält klar getrennte Abschnitte „Dokumentdarstellung“,
  „Steuerangaben“ und „Bank und Zahlungsdaten“.
- Abhängige Steuerfelder werden sofort konsistent geschaltet und erklärt.
- Backendvalidierungsfehler erscheinen am zugehörigen Feld; Uploadfehler bleiben im
  Dokumentabschnitt sichtbar und verlieren den ausgewählten Entwurf nicht.
- Alle neuen Texte werden in allen elf vorhandenen Locale-Dateien ergänzt.

## Verifikation

- Backendtests decken Migration, Schema- und Servicevalidierung, Berechtigungen,
  Versionskonflikte, Uploadtyp, Dateisignatur, Größenlimit, Austausch, Abruf und Löschung ab.
- Frontendtests decken Steuerabhängigkeiten, PayPal-Validierung, QR-Schalter,
  Logo-Upload/Vorschau/Löschung und Tabellenminiatur ab.
- Ruff, Backendtests, TypeScript, ESLint, i18n-Parität, Frontendtests und Produktionsbuild
  müssen bestehen.

## Nicht Bestandteil

- Erzeugung von Angeboten, Rechnungen oder PDFs.
- Tatsächliche Einbettung von Logo, QR-Code oder PayPal-Link in Dokumente.
- Steuerberatung, automatische Ländersteuersätze oder steuerliche Prüfung.
- PayPal-API, Zahlungsabgleich oder Zahlungsanforderungen.
