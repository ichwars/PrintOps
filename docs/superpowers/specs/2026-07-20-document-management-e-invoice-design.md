# Dokumentverwaltung und E-Rechnung

Stand: 2026-07-20
Status: fachlich freigegeben

## Zweck und Einordnung

PrintOps erhält unter `Einstellungen > Auftragsverwaltung > Dokumente` eine
vollständige, strukturierte Dokumentkonfiguration. Sie ersetzt die bisherige
einzelne Karte mit Angebotsgültigkeit, Zahlungsziel und freien Standardtexten.
Die Konfiguration bildet Dokumentarten, Sprachen, Zahlungs- und Mahnregeln,
Steuerentscheidungen, Versionierung sowie die fachliche Erzeugung und lokale
Validierung elektronischer Rechnungen ab.

Diese Spezifikation konkretisiert und ersetzt für Dokumentvorlagen,
Dokumentstatus, Steuerermittlung und E-Rechnung die entsprechenden allgemeineren
Abschnitte aus:

- `2026-07-10-order-management-design.md`
- `2026-07-11-business-profile-document-tax-payment-settings.md`

Bestehende Aussagen zu Kunden, Aufträgen, Kalkulationen, Produktion,
Fremdsystemadaptern und sonstigen Auftragsfunktionen bleiben unberührt.

## Ziele

- Fachlich vollständige Dokumentvorgaben statt eines unstrukturierten
  Einstellungsobjekts.
- Deutsche B2B-, B2C- und B2G-Vorgänge sowie EU- und internationale Fälle.
- Unveränderliche, nachvollziehbare Ausgabestände mit sicherer Nummernvergabe.
- Automatische, versionierte Steuerermittlung mit kontrollierter Abweichung.
- Erzeugung, lokale Validierung und Download von XRechnungen.
- Vollständiges semantisches ZUGFeRD-Modell und validiertes CII-XML als Grundlage
  für die spätere PDF/A-3-Einbettung.
- Klare Vererbung vom Unternehmensprofil über den Kunden bis zum Dokument.
- Vollständige Berechtigungs-, Fehler-, Audit- und Bereitschaftslogik.
- Verlustfreie Übernahme vorhandener Dokumenteinstellungen.

## Bewusst ausgeklammerter Umfang

Der spätere Schritt `Format und Vorschau` umfasst ausschließlich:

- visuelles PDF-Layout, Briefpapier, Typografie und Positionierung;
- Dokumentvorschau;
- endgültige PDF/A-3-Erzeugung;
- Einbettung des validierten ZUGFeRD-XML in PDF/A-3.

Ebenfalls nicht Bestandteil dieses Schritts sind:

- Versand über E-Mail, Peppol oder Behördenportale;
- automatische Ausführung oder Zustellung von Erinnerungen und Mahnungen;
- Steuererklärungen, Steuervoranmeldungen oder steuerliche Beratung;
- automatische Online-Aktualisierung rechtlicher Regelwerke.

Die für den späteren Versand benötigten Empfängerkennungen und Profile werden
bereits vollständig erfasst und validiert.

## Fachliche Leitentscheidungen

### Eigenständige Domäne

Dokumente werden als eigener relationaler Fachbereich im bestehenden
FastAPI-/SQLAlchemy-Backend umgesetzt. Ein JSON-Feld in den allgemeinen
Einstellungen ist dafür nicht zulässig. Veränderliche Geschäftsdaten liegen
relational vor; JSON wird nur für kanonische unveränderliche Snapshots,
Validierungsberichte und externe Regelartefakte verwendet.

### Geltungs- und Vererbungshierarchie

Der effektive Wert entsteht strikt in dieser Reihenfolge:

1. System- und Rechtsregeln
2. Unternehmensprofil
3. Kunde
4. Dokumentvorlage für Typ und Sprache
5. zulässige Abweichung im konkreten Dokumententwurf

Jeder effektive Wert liefert neben dem Wert auch seine Quelle. Eine
Überschreibung kann auf die übergeordnete Vorgabe zurückgesetzt werden.
Gesetzliche Pflichtdaten, Rechenergebnisse und systemseitig ermittelte Werte
können nicht als freier Text ersetzt werden. Zulässige manuelle Abweichungen
verlangen eine Begründung und werden auditiert.

### Versionierung

Eine Dokumentkonfiguration ist eindeutig durch Unternehmensprofil,
Dokumenttyp, Sprache und Versionsnummer bestimmt. Sie besitzt einen der Zustände:

- `draft`: bearbeitbarer Entwurf;
- `scheduled`: veröffentlicht, aber erst ab einem zukünftigen Datum wirksam;
- `active`: aktuell wirksame Version;
- `superseded`: durch eine neuere wirksame Version ersetzt.

Pro Unternehmensprofil, Dokumenttyp und Sprache darf zu einem Zeitpunkt genau
eine Version aktiv sein. Gültigkeitszeiträume dürfen sich nicht überschneiden.
Das Bearbeiten einer aktiven Version erzeugt immer einen neuen Entwurf. Eine
Veröffentlichung ist eine bewusste Aktion und speichert Benutzer, Zeitpunkt,
Änderungsgrund, Regelversionen sowie den optionalen Wirksamkeitsbeginn.

## Unterstützte Dokumentarten

Die Konfiguration und das kanonische Dokumentmodell unterstützen:

1. Angebot
2. Auftragsbestätigung
3. Lieferschein
4. Anzahlungsrechnung
5. Abschlagsrechnung
6. Schlussrechnung
7. Rechnung
8. Stornorechnung
9. Rechnungskorrektur
10. kaufmännische Gutschrift
11. Zahlungserinnerung
12. Mahnung
13. Gutschrift im umsatzsteuerlichen Self-Billing-Verfahren

`Kaufmännische Gutschrift` bezeichnet eine vom Lieferanten ausgestellte
Entgeltminderung. `Self-Billing` bezeichnet die vom Leistungsempfänger
ausgestellte Abrechnung. Beide Vorgänge besitzen verschiedene Rollen,
Kennzeichnungen, Prüfungen und Referenzen und werden technisch nicht über
dasselbe Dokumenttypkennzeichen abgebildet.

## Datenmodell

### Konfiguration

| Entität | Verantwortung |
| --- | --- |
| `DocumentConfiguration` | Profil, Dokumenttyp, Sprache, Version, Status, Wirksamkeit und Auditmetadaten |
| `DocumentBasicPolicy` | Dokumentbezogener Geschäftsstatus, Datumsregeln, Währung, Rundung, Referenzen und zulässige Folgedokumente |
| `PaymentPolicy` | Zahlungsziel, Basis, Zahlarten, Skonto, Vorauszahlung, Raten und Bankzuordnung |
| `DunningPolicy` | Verzugszins, Mahnkosten und geordnete Mahnstufen |
| `DunningStage` | Wartezeit, Gebühr, Zinsbehandlung, neue Frist, Text und Eskalationshinweis |
| `DocumentTextBlock` | Zweckgebundener Text, Sprache, Platzhalter und optionale Bedingung |
| `DocumentContentPolicy` | Sichtbarkeit und fachliche Aufnahme strukturierter Inhaltsgruppen |
| `TaxPolicy` | Zulässige Steuerfälle, Ermittlungsregeln und Abweichungsregeln |
| `EInvoicePolicy` | Standard, Syntax, Profil, Version, Kennungen und Empfängeranforderungen |
| `ConfigurationPublication` | Veröffentlichung, Wirksamkeit, Regelstände und Prüfergebnis |

### Geschäftsdokument

`CommercialDocument` besitzt mindestens:

- Dokumenttyp und Richtung;
- Unternehmensprofil, Kunde und verantwortlichen Benutzer;
- interne oder externe Dokumentnummer;
- Lebenszyklus-, Geschäfts- und Zahlungsstatus;
- Sprache, Währung und Rundungsmodus;
- Ausstellungs-, Leistungs-, Liefer-, Fälligkeits- und Bezugsdaten;
- Bestell-, Lieferanten-, Käufer- und Vertragsreferenzen;
- Verkäufer-, Käufer-, Liefer- und Rechnungsempfängerrollen;
- Positionen, Zu- und Abschläge, Steueraufschlüsselung und Summen;
- Zahlungsbedingungen, Zahlwege und Bankdaten;
- Referenzen auf Ursprung, Vorgänger, Korrektur und Folgedokumente;
- verwendete Konfigurations- und Regelversionen.

Positionen enthalten Beschreibung, Menge, UNECE-Einheit, Einzelpreis,
Preisbasismenge, Zu- und Abschläge, Netto, Steuerkategorie, Steuersatz,
Steuerbetrag, Brutto und ihre fachlichen Quellreferenzen. Geldwerte verwenden
SQL `NUMERIC` und Python `Decimal`, niemals binäre Gleitkommazahlen.

### Unveränderlicher Ausgabesnapshot

Beim Ausstellen entsteht ein kanonischer Snapshot mit:

- vollständigen Verkäufer-, Kunden- und Adressständen;
- Positionen, Beträgen, Währung und Rundung;
- Steuerentscheidung und Rechtsgrund;
- Zahlungs- und Bankdaten;
- final aufgelösten Textbausteinen;
- Referenzen und Belegkette;
- Konfigurations-, Sprach- und Regelversionen;
- Aussteller, Zeitpunkt und begründeten Abweichungen.

Der Snapshot wird kanonisch serialisiert und mit SHA-256 gehasht. Er ist nach
der Ausstellung nicht änderbar. Korrekturen erfolgen ausschließlich durch neue,
verknüpfte Dokumente mit eigener Nummer.

### E-Rechnungsartefakte

`EInvoiceArtifact` speichert:

- Dokument und Snapshot;
- Standard, Syntax und Profil;
- Standard-, CIUS- und Regelversion;
- Dateityp, Größe, geschützten Speicherpfad und SHA-256;
- Validierungsstatus und unveränderlichen Validierungsbericht;
- Erzeuger, Erzeugungszeit und Exportereignisse.

Ein fachlich oder syntaktisch ungültiges Artefakt darf nicht als ausgestelltes
E-Rechnungsartefakt freigegeben werden.

## Dokument- und Statuslogik

### Getrennte Statusdimensionen

Der technische Dokumentstatus ist `draft`, `validation_failed`, `ready`,
`issued`, `cancelled`, `corrected` oder `replaced`. Zulässige Übergänge sind:

- `draft -> validation_failed | ready`
- `validation_failed -> draft | ready`
- `ready -> draft | issued`
- `issued -> cancelled | corrected | replaced`

`cancelled`, `corrected` und `replaced` sind terminale Zustände des
Ursprungsdokuments; das verursachende Folge- oder Korrekturdokument besitzt einen
eigenen Lebenszyklus.

Daneben existieren getrennte fachliche Zustände, beispielsweise offen,
angenommen, abgelehnt, abgelaufen, versendet oder erfüllt. Der Zahlungsstatus
ist separat:

`not_applicable | open | partially_paid | paid | overdue | written_off`

Ein Zahlungsereignis verändert nicht den unveränderlichen Ausgabesnapshot.

### Ausstellung

Die Ausstellung erfolgt in einer fachlichen Transaktion:

1. Entwurf und aktuelle Version sperren beziehungsweise prüfen.
2. Stamm-, Pflicht-, Steuer- und Rechendaten abschließend validieren.
3. Dokumentnummer transaktionssicher reservieren.
4. Kanonischen Snapshot und Hash erzeugen.
5. Erforderliches E-Rechnungsartefakt erzeugen und lokal validieren.
6. Snapshot, Artefakt, Nummer und Auditereignis endgültig festschreiben.

Eine nach Reservierung fehlgeschlagene Nummer bleibt als ungültige Reservierung
mit Ursache nachvollziehbar und wird nie wiederverwendet.

### Dokumentartspezifische Anforderungen

#### Angebot

Pflichtdaten sind Ausstellungsdatum, Gültigkeit, Kunde, Leistungsbeschreibung,
Mengen, Preise, Währung, voraussichtliche Steuer, Lieferung und Zahlung. Die
Geschäftszustände sind offen, angenommen, abgelehnt, abgelaufen, zurückgezogen
und ersetzt.

#### Auftragsbestätigung

Sie referenziert ein angenommenes Angebot oder einen dokumentierten Direktauftrag
und enthält Bestellung, bestätigte Positionen, Preise, Termine und Bedingungen.
Abweichungen zum Angebot müssen sichtbar bestätigt werden.

#### Lieferschein

Erforderlich sind Auftrag, Datum, Lieferrollen, Positionen, gelieferte Mengen,
Teil- und Restmengen sowie bei Verwendung Charge, Seriennummer, Versandweg und
Tracking. Preise und interne Kalkulationsdaten erscheinen standardmäßig nicht.

#### Rechnung

Erforderlich sind eindeutige Nummer, Ausstellungs- und Leistungsdaten, Parteien,
Positionen, Netto-, Steuer- und Bruttosummen, Währung, Zahlung, Fälligkeit,
Referenzen und fallbezogene Pflichtangaben.

#### Anzahlungsrechnung

Sie enthält den Gesamtauftrag, angeforderten Anzahlungsbetrag oder Anteil,
Fälligkeit, Steuerbehandlung und Auftragsreferenz.

#### Abschlagsrechnung

Sie enthält Abrechnungszeitraum oder Teilleistung, aktuellen Abschlag sowie
frühere und kumulierte Abrechnungsstände.

#### Schlussrechnung

Sie weist die Gesamtleistung und alle vorherigen Anzahlungs- und
Abschlagsrechnungen sowie erhaltene Teilzahlungen nach Steuergruppen aus und
zieht sie nachvollziehbar ab.

#### Stornorechnung

Sie referenziert das Original, enthält einen Grund und kehrt das Original
vollständig um. Das Original bleibt erhalten und erhält lediglich seinen
abgeleiteten Status.

#### Rechnungskorrektur

Sie enthält Originalreferenz, Grund, geänderte Sachverhalte und steuerliche
Differenzen. Die konfigurierte Korrekturart ist Differenzbeleg oder vollständiger
Ersatzbeleg; sie darf nicht zu einer Mutation des Originals führen.

#### Kaufmännische Gutschrift

Sie wird vom Lieferanten als Minderung oder Rückvergütung ausgestellt und besitzt
eine eigene Nummer und klare Referenz auf den betroffenen Vorgang.

#### Self-Billing

Das Dokument wird vom Leistungsempfänger erstellt. Vereinbarung, Rollen,
Aussteller, Leistung, externe Nummer, interne Referenz sowie Prüf- und
Widerspruchsstatus sind explizit. Die Kennzeichnung `Gutschrift` ist fachlich
pflichtig und nicht mit der kaufmännischen Gutschrift austauschbar.

#### Zahlungserinnerung und Mahnung

Sie verwenden ausgestellte Rechnungen, ursprüngliche Fälligkeit, verbuchte
Zahlungen und offenen Saldo. Sie erzeugen keine neue Umsatzsteuer. Mahnungen
enthalten zusätzlich Stufe, Zinsen, Gebühren, neue Frist und Eskalationshinweis.
Die automatische zeitliche Ausführung bleibt außerhalb dieses Schritts.

### Änderung nach Ausstellung

Nach der Ausstellung dürfen nur noch folgende Informationen ergänzt werden:

- Zahlungsbuchungen und Zahlungsstatus;
- Liefer- und Erfüllungsstatus;
- Archiv- und Transportreferenzen;
- verknüpfte Folge-, Korrektur- und Stornodokumente;
- eigenständige Auditnotizen.

Kopfdaten, Parteien, Positionen, Preise, Steuer, Texte und Fälligkeit des
Ausgabesnapshots bleiben unverändert.

## Zahlungs-, Skonto- und Mahnregeln

Eine `PaymentPolicy` definiert:

- Zahlungsziel in Tagen und seine Berechnungsbasis;
- feste oder ereignisbezogene Fälligkeitsregel;
- erlaubte Zahlarten und Standardzahlart;
- Skontosatz, Skontofrist und Berechnungsbasis;
- Vorauszahlungsanforderungen;
- geordnete Raten mit Betrag oder Prozentanteil;
- Währung, Rundung und Bankverbindung;
- kundenspezifisch überschreibbare Felder.

Eine `DunningPolicy` definiert Verzugszins, Gebühren und beliebig viele geordnete
Stufen. Jede Stufe enthält Wartezeit, Gebühr, Zinsbehandlung, neue Frist,
Textbaustein und Eskalationshinweis. Summen von prozentualen Raten müssen 100
Prozent ergeben. Skontofristen dürfen das Zahlungsziel nicht überschreiten.

## Textbausteine und Sprachen

Textblöcke werden nach Zweck verwaltet:

- Betreff;
- Einleitung;
- Abschluss;
- Zahlung;
- Lieferung;
- Steuer;
- rechtlicher Hinweis;
- Anlagenhinweis;
- Erinnerung und Mahnung je Stufe.

Eine zentrale Platzhalterregistrierung definiert Kennung, Datentyp, zulässige
Dokumentarten, Pflichtquelle und Formatierung. Unbekannte, unzulässige oder nicht
auflösbare Pflichtplatzhalter blockieren die Veröffentlichung.

PrintOps liefert überprüfte deutsche und englische Grundtexte. Weitere Sprachen
werden vom Benutzer vollständig gepflegt und separat veröffentlicht. Es gibt
keine automatische rechtliche Übersetzung und keinen stillen Rückfall auf eine
andere Sprache. Ein Dokument kann nur in einer Sprache ausgestellt werden, für
die eine wirksame und vollständige Vorlage existiert.

## Steuerermittlung

### Eingaben

Die Ermittlung verwendet mindestens:

- Länder und Steuerstatus von Verkäufer und Käufer;
- Liefer- oder Leistungsort;
- Umsatzsteuer- und sonstige Steuerkennungen;
- Ergebnis und Zeitpunkt einer vorhandenen Kennungsprüfung;
- Kundenart B2B, B2C oder öffentliche Stelle;
- Dokument- und Leistungsart;
- Liefer- und Leistungsdatum;
- Währung;
- wirksame Steuerregelversion.

### Unterstützte Fälle

- deutsche Regelbesteuerung;
- Kleinunternehmerregelung;
- innergemeinschaftliche Lieferung;
- EU-B2B und Reverse Charge;
- EU-B2C einschließlich OSS-Konfiguration;
- Drittlandslieferung oder Drittlandsleistung;
- steuerfreie oder besonders begründete Sachverhalte.

### Ergebnis

Die Steuerentscheidung speichert Behandlung, Steuerland, Leistungsort,
Steuerkategorie, Steuersatz, Bemessungsgrundlage, Betrag, Rechtsgrund,
verwendete Kennungen, Regelversion und Prüfergebnis. Das Ergebnis ist Bestandteil
des Ausgabesnapshots.

Eine manuelle Abweichung ist nur mit eigener Berechtigung, fachlichem Grund,
Benutzer und Zeitpunkt zulässig. Fehlende Länder, unplausible Kennungen,
unbestimmter Leistungsort, fehlende Regel oder widersprüchliche Ergebnisse
blockieren die Ausstellung.

## E-Rechnung

### Umfang dieses Schritts

- kanonisches EN-16931-Datenmodell;
- XRechnung als unterstützte deutsche CIUS;
- Erzeugung und lokale Validierung von XRechnungs-XML;
- vollständige ZUGFeRD-Profilkonfiguration;
- Erzeugung und lokale Validierung des für ZUGFeRD benötigten CII-XML;
- Download der validierten XML-Datei und des Validierungsberichts.

Die abschließende hybride ZUGFeRD-Datei entsteht erst mit dem späteren
PDF/A-3-Renderer.

E-Rechnungen sind für Rechnung, Anzahlungsrechnung, Abschlagsrechnung,
Schlussrechnung, Stornorechnung, Rechnungskorrektur, kaufmännische Gutschrift und
Self-Billing fachlich anwendbar. Angebote, Auftragsbestätigungen, Lieferscheine,
Zahlungserinnerungen und Mahnungen werden nicht als E-Rechnung ausgegeben. Pro
anwendbarem Typ ist die Vorgabe `optional` oder `regelabhängig erforderlich`;
`regelabhängig erforderlich` ist der Standard. Ob ein konkretes Dokument eine
E-Rechnung benötigt, ergibt sich aus Transaktion, Empfängertyp und wirksamer
Regelversion.

### Konfiguration

Pro Unternehmensprofil werden festgelegt:

- EN-16931- und CIUS-Version;
- XRechnungs-Syntax `UBL 2.1` oder `UN/CEFACT CII`;
- ZUGFeRD-Profil `EN 16931` oder, für den entsprechenden deutschen
  Anwendungsfall, `XRECHNUNG`;
- Geschäftsprozesskennung;
- Verkäuferkennung und Kennungsschema;
- Standardzahlweg und Bankdaten;
- Steuer- und Kontaktinformationen;
- Regeln für Käuferreferenz, Bestell- und Lieferantenreferenz.

Andere ZUGFeRD-Profile wie `MINIMUM`, `BASIC WL`, `BASIC` oder `EXTENDED` sind
nicht Bestandteil dieser Umsetzung: Die ersten drei unterschreiten den hier
geforderten vollständigen EN-16931-Datenumfang, während `EXTENDED` über den
vereinbarten Rechnungsumfang hinausgeht.

Der Kunde kann Empfängerkennung, Kennungsschema, Leitweg-ID, Buyer Reference,
Bestellreferenz und empfangsspezifische Anforderungen überschreiben.

### Validierungsschichten

Die Prüfung erfolgt in dieser Reihenfolge:

1. PrintOps-Datenmodell und Pflichtfelder;
2. dokumentartspezifische Anforderungen;
3. Steuerentscheidung;
4. mathematische Konsistenz und Rundung;
5. EN-16931-Semantik;
6. XML-Syntax und Schema;
7. XRechnung- beziehungsweise ZUGFeRD-Profilregeln;
8. Anforderungen des konkreten Empfängers.

Für B2B werden elektronische Adresse und erforderliche Käuferreferenzen geprüft.
B2C erzwingt keine E-Rechnung. B2G prüft insbesondere Leitweg-ID,
Zahlungsinformationen, E-Mail-Kontakt sowie Bestell- und Lieferantenreferenzen.
EU- und internationale Fälle prüfen Länder, Währung, Kennungen und Steuerfall.

Die für die Rechnung vorgeschriebenen Umsatzsteuerinformationen müssen im
strukturierten Datenteil enthalten sein; ein ausschließlich visueller PDF-Text
genügt nicht.

### Regelwerk

EN-16931-, XRechnungs-, XSD-, Schematron- und erforderliche Codelisten werden
versioniert mit PrintOps ausgeliefert. Die Validierung läuft ohne Netzwerkzugriff.
Jeder Bericht speichert die verwendeten Regelversionen. Regelwerksupdates
erfolgen kontrolliert mit einer Anwendungsversion und verändern historische
Berichte nicht.

Der fest eingebundene Regelstand dieser Umsetzung besteht aus EN-16931
Validation Artefacts `1.3.16` vom 10. April 2026, der KoSIT-
Validator-Konfiguration für XRechnung `3.0.2` im Bundle vom 31. Januar 2026
sowie ZUGFeRD `2.5` / Factur-X `1.09` vom 10. Juni 2026. Für ZUGFeRD wird das
Profil `EN 16931` auf Basis von CII D22B eingebunden; das ZUGFeRD-Profil
`XRECHNUNG` verwendet zusätzlich die genannten deutschen CIUS-Regeln. Herkunft,
Lizenz, Syntax, Profil und SHA-256 jeder ausgelieferten Regeldatei sind im
E-Rechnungs-Assetmanifest festgehalten.

## Nummern und Referenzen

- Jeder ausstellbare Dokumenttyp besitzt einen zugeordneten Nummernkreis.
- Rechnungsnummern sind mindestens innerhalb des Unternehmensprofils eindeutig.
- Ausgestellte oder fehlgeschlagene reservierte Nummern werden nie
  wiederverwendet.
- Storno, Korrektur und Gutschrift erhalten eine eigene Nummer.
- Dokumentreferenzen sind typisiert und nach Ausstellung unveränderlich.
- Self-Billing speichert externe Ausstellernummer und interne Referenz getrennt.
- Die Bereitschaftsprüfung blockiert fehlende oder unpassende Nummernkreise.

## Benutzeroberfläche

### Navigation und Kopfbereich

Unter `Einstellungen > Auftragsverwaltung` steht `Dokumente` zwischen
`Unternehmensprofil` und `Kalkulation`. Der Kopfbereich zeigt dauerhaft:

- Unternehmensprofil;
- Dokumenttyp;
- Sprache;
- Version und Status;
- Wirksamkeitsbeginn;
- Herkunft der Einstellungen;
- Bereitschaftsstatus.

Abhängig von Zustand und Berechtigung stehen `Entwurf speichern`,
`Vollständigkeit prüfen`, `Veröffentlichen`, `Neue Version anlegen`,
`Terminierte Veröffentlichung zurückziehen` und `Änderungsverlauf` zur Verfügung.

### Seitenaufbau

Desktop verwendet zwei Spalten:

- links: Grundlagen, Zahlungsbedingungen, Textbausteine und Dokumentinhalt;
- rechts: Steuerregeln, E-Rechnung, Vererbungen und Bereitschaftsprüfung.

Auf schmalen Ansichten werden alle Bereiche vollständig untereinander
dargestellt. Typabhängig irrelevante Bereiche werden nicht als leere oder
deaktivierte Karten angezeigt.

### Feldverhalten

Jedes vererbbare Feld zeigt seine Quelle `Unternehmensprofil`, `Kunde`,
`Dokumentvorlage` oder `Dokumentabweichung`. Überschreibungen sind markiert und
können mit `Vorgabe wiederherstellen` entfernt werden. Rechtlich oder rechnerisch
gesperrte Werte erklären, wodurch sie bestimmt werden.

Der Platzhalter-Assistent bietet nur zum Dokumenttyp passende Platzhalter an.
Die Steuerkarte zeigt Ergebnis, Grundlage, Stammdaten und Regelversion. Die
E-Rechnungskarte zeigt Profil, Pflichtkennungen und einen strukturierten
Validierungsbericht.

### Bereitschaftsprüfung

Die Prüfung besitzt zwei klar getrennte Kontexte:

- **Konfigurationsbereitschaft:** prüft vor Veröffentlichung alle profil-, typ-
  und sprachbezogenen Angaben sowie die Regeln, nach denen kundenspezifische
  Daten später verlangt werden.
- **Dokumentbereitschaft:** prüft vor Ausstellung zusätzlich den konkreten
  Kunden, Empfängerkennungen, Referenzen, Positionen, Beträge und Steuerfall.

Der jeweilige Gesamtzustand ist:

- `Bereit`: Veröffentlichung möglich;
- `Warnungen`: Veröffentlichung möglich, Hinweise bleiben sichtbar;
- `Blockiert`: Veröffentlichung nicht möglich.

Einträge sind anklickbar und fokussieren den betroffenen Bereich. Die
Konfigurationsbereitschaft prüft Unternehmensdaten, Adressen, Steuerdaten,
Verkäuferkennungen, Bankdaten, Nummernkreise, Pflichttexte,
Sprachvollständigkeit und E-Rechnungsprofil. Konkrete Empfängerangaben können
eine profilweite Vorlage nicht blockieren; sie werden in der
Dokumentbereitschaft verbindlich geprüft. Fehlt dort eine erforderliche
Empfängerkennung, ist die Ausstellung blockiert.

Entwürfe dürfen unvollständig gespeichert werden. Veröffentlichung ist nur bei
bestandener Bereitschaftsprüfung möglich. Ungespeicherte Änderungen,
Versionskonflikte und zwischenzeitlich veröffentlichte Fremdänderungen werden
explizit behandelt und niemals still überschrieben.

### Fehlerdarstellung

Fehlerantworten enthalten stabilen Fehlercode, Bereich, Feldpfad, fachliche
Ursache, Korrekturhinweis und Korrelations-ID. Regelverletzungen enthalten die
Regelkennung. Pauschale Meldungen wie `Not found` oder `Speichern fehlgeschlagen`
sind in dieser Oberfläche unzulässig.

## Berechtigungen

Die serverseitig durchgesetzten Rechte werden getrennt für:

- Dokumentvorlagen lesen;
- Dokumentvorlagen verwalten;
- Dokumententwürfe erstellen und bearbeiten;
- Dokumente ausstellen;
- Dokumente stornieren oder korrigieren;
- E-Rechnungen erzeugen und exportieren;
- Steuerentscheidungen manuell übersteuern;
- Dokument- und Konfigurationsaudit lesen.

Nicht berechtigte Einstellungen bleiben, sofern Leserechte bestehen, sichtbar
und schreibgeschützt. Das Ausblenden einer Schaltfläche gilt nicht als
Autorisierung. API-Schlüssel erhalten keine neuen Rechte ohne explizite,
geschlossene Zuordnung.

## API-Grenzen

Die API stellt getrennte Ressourcen und Kommandos bereit für:

- Konfigurationen suchen, laden und als Entwurf anlegen;
- Entwürfe versionsgesichert speichern;
- Bereitschaft prüfen, terminieren und veröffentlichen;
- eine neue Version aus einer wirksamen Version erzeugen;
- Vererbung und effektive Werte auflösen;
- unterstützte Dokumenttypen und Platzhalter abrufen;
- Steuerfall ermitteln und begründet abweichend festlegen;
- Geschäftsdokumente validieren und atomar ausstellen;
- Storno-, Korrektur- und Folgedokumente anlegen;
- XRechnung und ZUGFeRD-CII erzeugen und lokal validieren;
- XML und Validierungsbericht herunterladen;
- Versions-, Ausstellungs- und Auditverlauf abrufen.

Mutationen verwenden optimistische Versionsprüfung. Ein Konflikt liefert die
aktuelle Version und einen stabilen Konfliktcode. Binär- und XML-Artefakte werden
nur über berechtigungsgeschützte Downloadendpunkte ausgegeben.

## Technische Komponenten

Die Umsetzung wird in kleine, unabhängig testbare Module getrennt:

| Komponente | Aufgabe |
| --- | --- |
| Konfigurationsservice | Versionen, Vererbung, Veröffentlichung und Wirksamkeit |
| Bereitschaftsservice | Aggregierte Prüfung und navigierbare Befunde |
| Platzhalterservice | Registrierung, Zulässigkeit, Auflösung und Formatierung |
| Zahlungsservice | Fälligkeit, Skonto, Raten und Mahnparameter |
| Steuerentscheidungsservice | Regelwahl, Ergebnis, Begründung und manueller Override |
| Dokumentservice | Entwürfe, Zustände, Relationen, Snapshot und Ausstellung |
| Nummernservice | Transaktionssichere Reservierung und Lückennachweis |
| E-Rechnungsrenderer | Kanonisches Modell nach XRechnung/CII abbilden |
| E-Rechnungsvalidator | Lokale XSD-, Schematron-, CIUS- und Empfängerprüfung |
| Artefaktspeicher | Geschützte Dateien, Prüfsummen und unveränderliche Metadaten |
| Auditservice | Append-only Ereignisse für bindende Aktionen |

Renderer und Validator hängen vom kanonischen Snapshot ab und nicht von
Frontendmodellen. Der Steuerdienst liefert eine dokumentierte Entscheidung und
kennt keine XML-Feldnamen. Dadurch können Regelwerke und Ausgabeprofile
unabhängig weiterentwickelt werden.

## Migration und Standardwerte

### Bestandsübernahme

Vorhandene Werte werden in eine deutsche Entwurfsversion je betroffenem
Unternehmensprofil übernommen:

- Angebotsgültigkeit;
- Zahlungsziel;
- Standardstatus für neue Aufträge, der als Auftragsworkflow-Vorgabe erhalten
  bleibt und nicht fälschlich zur Dokumentvorlage wird;
- Angebots- und Rechnungstexte;
- PDF-Fußzeilentext beziehungsweise zusätzliche Hinweise;
- Übernahme technischer Druck- und Kalkulationsdaten;
- vorhandene Unternehmensprofile und Nummernkreise;
- kundenspezifische Zahlungsziele.

Die Migration veröffentlicht keine Vorlage automatisch. Sie ist wiederholbar
und sowohl für SQLite als auch PostgreSQL ausgelegt. Bestehende Angebote,
Aufträge und sonstige Geschäftsdaten werden nicht rückwirkend verändert.

### Ausgangswerte

- Deutsch und Englisch erhalten gepflegte Grundtexte.
- Angebotsgültigkeit: 14 Tage.
- Zahlungsziel: 14 Tage.
- Skonto: nicht automatisch aktiviert.
- Mahnkosten und Verzugszins: nicht automatisch aktiviert.
- Dokumentartspezifische Pflichtfelder und Steuerfälle sind vorkonfiguriert.
- Technische Druckdaten werden konservativ und typabhängig aufgenommen.
- Mitgelieferte EN-16931- und XRechnungsregeln besitzen eine feste Version.

Unternehmensspezifische Rechts- und Identifikationsdaten werden nicht erfunden.
Steuerstatus, Kennungen, Leitweg-ID, Bankdaten und Empfängerangaben müssen aus
tatsächlichen Stamm- oder Kundendaten stammen.

## Audit, Integrität und Aufbewahrung

Append-only protokolliert werden mindestens:

- Erstellen und Ändern von Entwürfen;
- Veröffentlichung, Terminierung und Zurückziehen einer Terminierung;
- manuelle Steuerabweichungen;
- Ausstellen, Stornieren, Korrigieren und Ersetzen;
- Erzeugung und Validierung elektronischer Rechnungen;
- Exporte und Downloads.

Ein Ereignis enthält Benutzer, Zeitpunkt, Aktion, Objekt, sichere Vorher-/Nachher-
Metadaten, Begründung und Korrelations-ID. Ausgestellte Snapshots,
E-Rechnungsdateien, Validierungsberichte, Regelversionen und Hashwerte bleiben
unverändert. Verwendete oder veröffentlichte Versionen können nicht physisch
gelöscht werden.

Aufbewahrungsfristen werden als eigene Richtlinie verwaltet. Nach § 14b UStG
sind Rechnungen grundsätzlich acht Jahre aufzubewahren; abweichende oder
zusätzliche handels- und steuerrechtliche Pflichten werden nicht durch eine
pauschale automatische Löschung verkürzt.

## Fehler- und Ausfallverhalten

- Unvollständige Entwürfe bleiben speicherbar und zeigen strukturierte Befunde.
- Fachliche Fehler blockieren Veröffentlichung oder Ausstellung ohne Teilstand.
- Versionskonflikte überschreiben keine fremden Änderungen.
- Ein reservierter, aber fehlgeschlagener Nummernwert wird als Lücke auditiert.
- Teilweise erzeugte Artefakte werden verworfen oder als nicht downloadbare
  Fehlerartefakte quarantänisiert.
- Validierungsberichte bleiben auch bei Fehlschlag nachvollziehbar.
- Fehlende lokale Regeldateien blockieren E-Rechnungserzeugung und erzeugen einen
  administrativen Fehler mit Korrelations-ID.
- Wiederholte Erzeugungsanfragen sind über Dokument-ID, Snapshot-Hash und
  Idempotenzschlüssel sicher.
- Protokolle enthalten keine vollständigen Rechnungsinhalte, Bankdaten oder
  sonstigen unnötigen personenbezogenen Daten.

## Verifikation

### Backend-Unit-Tests

- Dezimalrechnung, Steuergruppierung und festgelegte Rundung;
- Zahlungsziel, Skonto, Raten und Mahnstufen;
- alle gültigen und ungültigen Statusübergänge;
- Vererbung, Quellenanzeige und Zurücksetzen einer Überschreibung;
- Wirksamkeitszeiträume und Ausschluss überlappender Versionen;
- Steuerfälle für Deutschland, EU und Drittland;
- Berechtigungen und Begründung manueller Steuerabweichungen;
- Platzhalterzulässigkeit und vollständige Auflösung;
- Snapshotkanonisierung, SHA-256 und Unveränderlichkeit;
- Nummernreservierung, Parallelzugriff, Lücken und Nichtwiederverwendung;
- dokumentartspezifische Pflichtfelder und Relationen.

### Backend-Integrationstests

- Konfigurationsentwurf bis Veröffentlichung und Folgeveröffentlichung;
- kundenspezifische Vererbung bis zum konkreten Dokument;
- Angebot bis Auftrag, Lieferung und Rechnung;
- Anzahlungs-, Abschlags- und Schlussrechnung;
- Storno, Korrektur und kaufmännische Gutschrift;
- Self-Billing mit vertauschten Abrechnungsrollen;
- Erinnerung und mehrere Mahnstufen ohne neue Umsatzsteuer;
- atomare Ausstellung bei konkurrierenden Anfragen auf SQLite und PostgreSQL;
- fehlgeschlagene E-Rechnungsvalidierung ohne ausgestellten Teilstand;
- Berechtigungs- und API-Key-Fail-closed-Verhalten;
- Backup und Restore mit Snapshots, Artefakten und Regelständen.

### Konformitätstests

- gültige XRechnungen gegen die gebündelten XSD- und Schematronregeln;
- bewusst fehlerhafte Referenzrechnungen je Validierungsschicht;
- CII-XML für die konfigurierten ZUGFeRD-Profile;
- Steuerkategorien, mehrere Steuersätze, Zu-/Abschläge und Gutschriften;
- Käuferreferenz, elektronische Adresse, Leitweg-ID und B2G-Pflichtangaben;
- Validierungsbericht und gespeicherte Regelversion;
- deterministische Ausgabe und Prüfsumme für denselben Snapshot.

### Frontend- und Browsertests

- Navigation und responsiver Zweispaltenaufbau;
- Profil-, Typ-, Sprach- und Versionswechsel;
- Entwurf speichern, prüfen, terminieren, veröffentlichen und neue Version;
- Quellenkennzeichnung und Rücksetzen von Überschreibungen;
- Feldnavigation aus Bereitschafts- und Validierungsbefunden;
- Textbausteine und Platzhalter-Assistent;
- Steuerentscheidung und begründeter manueller Override;
- E-Rechnungsprofil, lokale Prüfung und Download;
- Lese-, Schreib-, Ausstellungs- und Exportberechtigungen;
- leere, ladende, blockierte, fehlerhafte und konkurrierend geänderte Zustände;
- Regression vorhandener Unternehmensprofil-, Angebots-, Auftrags- und
  Kalkulationseinstellungen.

## Abnahmekriterien

Die Umsetzung ist vollständig, wenn:

1. alle spezifizierten Dokumentarten fachlich getrennt vorhanden sind;
2. jede Vorlage an Profil, Typ, Sprache und unveränderliche Version gebunden ist;
3. Herkunft und effektiver Wert jeder vererbbaren Vorgabe erkennbar sind;
4. deutsche und englische Grundvorlagen vollständig vorliegen;
5. Zahlung, Skonto, Vorauszahlung, Raten und Mahnstufen abgebildet sind;
6. die vereinbarten deutschen, EU- und Drittlandsteuerfälle regelbasiert
   ermittelt werden;
7. manuelle Steuerabweichungen berechtigt, begründet und auditiert sind;
8. veröffentlichte Vorlagen und ausgestellte Dokumente unveränderlich bleiben;
9. Korrektur, Storno, kaufmännische Gutschrift und Self-Billing getrennt
   funktionieren;
10. Nummernkreise transaktionssicher und ohne Wiederverwendung verwendet werden;
11. XRechnung erzeugt, lokal validiert und heruntergeladen werden kann;
12. ZUGFeRD semantisch vollständig als validiertes CII-XML vorbereitet ist;
13. die Bereitschaftsprüfung alle Blocker feldbezogen und verständlich ausweist;
14. sämtliche Berechtigungen serverseitig durchgesetzt werden;
15. die Migration bestehender Werte nachweislich verlustfrei ist;
16. keine leeren UI-Karten, Platzhalterfunktionen oder pauschalen
    Fehlermeldungen verbleiben;
17. alle spezifizierten automatisierten Tests erfolgreich laufen;
18. der ausgeklammerte Format- und Vorschauumfang nicht verdeckt vorweggenommen
    wird.

## Rechtliche und normative Grundlage

Die Implementierung orientiert sich am zum Spezifikationsdatum verfügbaren
Stand. Regelwerksversionen bleiben technisch explizit, damit spätere Änderungen
kontrolliert übernommen werden können.

- [§ 14 UStG – Ausstellung von Rechnungen](https://www.gesetze-im-internet.de/ustg_1980/__14.html)
- [§ 14b UStG – Aufbewahrung von Rechnungen](https://www.gesetze-im-internet.de/ustg_1980/__14b.html)
- [§ 31 UStDV – Angaben und Berichtigung einer Rechnung](https://www.gesetze-im-internet.de/ustdv_1980/__31.html)
- [§ 286 BGB – Verzug des Schuldners](https://www.gesetze-im-internet.de/bgb/__286.html)
- [BMF – FAQ zur E-Rechnung](https://www.bundesfinanzministerium.de/Content/DE/FAQ/e-rechnung.html)
- [E-Rechnung Bund – Inhaltliche Anforderungen](https://e-rechnung-bund.de/faq/welche-inhaltlichen-anforderungen-mussen-zur-erstellung-einer-e%E2%80%91rechnung-beachtet-werden/)
- [BMF – GoBD, Änderung 2025](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Weitere_Steuerthemen/Abgabenordnung/2025-07-14-GoBD-2-aenderung.pdf?__blob=publicationFile&v=4)

PrintOps unterstützt die fachliche Datenqualität und technische Konformität,
ersetzt aber keine Prüfung des konkreten steuerlichen Einzelfalls.

## Selbstprüfung der Spezifikation

- **Vollständigkeit:** Dokumentarten, Vererbung, Versionen, Zahlung, Mahnung,
  Steuer, E-Rechnung, Nummern, UI, Rechte, Migration und Tests sind verbindlich
  definiert.
- **Begriffsschärfe:** Kaufmännische Gutschrift und Self-Billing sind getrennt;
  fachlicher, technischer und Zahlungsstatus werden nicht vermischt.
- **Integrität:** Entwürfe sind veränderlich, veröffentlichte Konfigurationen und
  ausgestellte Snapshots unveränderlich.
- **E-Rechnungsgrenze:** XRechnung und CII-XML sind Bestandteil; PDF/A-3 und
  ZUGFeRD-Einbettung gehören eindeutig zum Folgeschritt.
- **Fehlerfälle:** Konflikte, Nummernlücken, ungültige Artefakte, fehlende Regeln
  und unvollständige Stammdaten besitzen definiertes Verhalten.
- **Scope:** Die Spezifikation bildet einen zusammenhängenden Dokumentbereich;
  Layout, Vorschau, Transport und automatische Mahnausführung sind klar
  abgegrenzt.
- **Offene Entscheidungen:** Es verbleiben keine fachlichen Produktentscheidungen,
  die einen Umsetzungsplan blockieren.
