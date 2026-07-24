# Dokumentverwaltung und E-Rechnung

PrintOps verwaltet kaufmännische Dokumentregeln versioniert je
Unternehmensprofil, Dokumentart und Sprache. Die Einstellungen befinden sich
unter `Einstellungen > Auftragsverwaltung > Dokumente`.

## Voraussetzungen

Vor der ersten Freigabe müssen im gewählten Unternehmensprofil ein rechtlicher
Name, eine vollständige Geschäftsanschrift und – bei steuerpflichtigen
Dokumenten – eine Steuer- oder Umsatzsteuerkennung gepflegt sein. Dokumente mit
Zahlungsbedingungen benötigen ein Bankkonto mit IBAN und genau eine
Standardzuordnung. Außerdem muss der passende Nummernkreis eingerichtet sein:
Angebote verwenden `offer`, Auftragsbestätigungen und Lieferscheine `order`, alle
Rechnungs-, Korrektur- und Mahndokumente `invoice`.

## Kontext und Vererbung

Die Kopfzeile legt Unternehmensprofil, Dokumentart und Sprache fest. Jeder
Feldwert zeigt seine Herkunft. Die wirksame Rangfolge lautet Systemvorgabe,
Unternehmensprofil, veröffentlichte Dokumentkonfiguration, Kundenkonto und
dokumentbezogene Abweichung. Eine spezifischere Ebene überschreibt nur das
betroffene Feld; „Vorgabe wiederherstellen“ entfernt die Abweichung und macht
die darunterliegende Quelle wieder wirksam.

Ein Kontextwechsel mit ungespeicherten Änderungen verlangt eine ausdrückliche
Bestätigung. Dadurch gehen Änderungen nicht unbemerkt verloren.

## Entwurf, Prüfung und Freigabe

1. `Entwurf anlegen` erzeugt eine vollständige sprach- und dokumentartspezifische
   Ausgangskonfiguration.
2. Regeln und Textbausteine werden bearbeitet. Für jede Speicherung ist ein
   Änderungsgrund mit mindestens drei Zeichen erforderlich.
3. `Bereitschaft prüfen` bündelt alle fachlichen und technischen Prüfungen.
   Blocker nennen Feld, Korrekturhinweis und – soweit vorhanden – Regel-ID.
4. `Freigeben` macht die geprüfte Version sofort oder zum gewählten Datum
   wirksam. Eine freigegebene Version ist unveränderlich.
5. `Neue Version anlegen` kopiert eine aktive oder abgelöste Version in einen
   neuen Entwurf. Die bisherige Fassung und ihr Prüfprotokoll bleiben erhalten.

Gleichzeitige Bearbeitung wird über eine Versionsnummer erkannt. Bei einem
Konflikt muss der aktuelle Stand neu geladen und verglichen werden. Geplante
Freigaben lassen sich mit Begründung zurückziehen. Versionsverlauf und
append-only Auditprotokoll zeigen Akteur, Zeitpunkt, Änderungsgrund,
Korrelations-ID und verwendete Regelstände.

## Unterstützte Dokumentarten

- Angebot
- Auftragsbestätigung
- Lieferschein
- Abschlagsrechnung
- Teilrechnung
- Schlussrechnung
- Rechnung
- Stornorechnung
- Rechnungskorrektur
- kaufmännische Gutschrift
- Zahlungserinnerung
- Mahnung
- Gutschrift im Selbstabrechnungsverfahren (Self-Billing)

Die möglichen Folgedokumente sind fachlich begrenzt. Ein Angebot kann
beispielsweise in eine Auftragsbestätigung oder Rechnung überführt werden;
ausgestellte Rechnungen können storniert, korrigiert, gutgeschrieben oder
gemahnt werden. Storno und Korrektur erzeugen neue Belege und verändern den
ursprünglich ausgestellten Beleg nicht.

## Dokumentregeln und Textbausteine

Je Dokumentart werden Betreff, maßgebliches Datum, Rundungsverfahren,
Pflichtreferenzen, erlaubte Folgedokumente und sichtbare technische Inhalte
festgelegt. Textbausteine besitzen einen geschlossenen Verwendungszweck, zum
Beispiel Einleitung, Schluss, Zahlungs- oder Lieferbedingungen, Steuerhinweis,
Fußzeile und Mahntext. Platzhalter werden gegen die gewählte Dokumentart
geprüft; unbekannte oder dort nicht verfügbare Platzhalter blockieren die
Freigabe.

## Zahlung, Skonto, Raten und Mahnwesen

Zahlungsziel, Bezugsdatum, Währung, Zahlungsarten und Bankkonto werden zentral
vorgegeben. Skontofrist und -satz dürfen die reguläre Fälligkeit nicht
überschreiten. Ein aktivierter Ratenplan muss positive Raten enthalten, deren
Anteile exakt 100 Prozent ergeben.

Das Mahnwesen verwaltet Verzugszins, Grundgebühr und geordnete Mahnstufen. Jede
Stufe enthält Wartezeit, optionale Gebühr, neue Zahlungsfrist, Text und eine
optionale Eskalation. Doppelte oder lückenhafte Stufennummern sowie negative
Beträge oder Fristen blockieren die Freigabe.

## Steuerermittlung und begründete Abweichung

Die gepinnte Steuerregelversion `2026.1` entscheidet deterministisch anhand von
Verkäuferland, Käuferland, Leistungsort, B2B/B2C, Leistungsart und vorhandenen
USt-Id-Prüfnachweisen. Abgedeckt sind insbesondere Inland, Kleinunternehmer,
innergemeinschaftliche Lieferung, EU Reverse Charge, EU B2C/OSS, Drittland und
explizite Steuerbefreiung. Fehlende oder widersprüchliche Nachweise erzeugen
einen Blocker statt einer stillen Annahme.

Eine manuelle Abweichung benötigt die Berechtigung
`commercial_documents:tax_override` und eine nicht leere fachliche Begründung.
Behandlung, Steuerland, Kategorie, Satz, Rechtsgrund, Akteur und Zeitpunkt
werden im Dokument und Auditprotokoll festgehalten. Die automatische
Entscheidung und ihre Regelversion bleiben nachvollziehbar.

## E-Rechnung

Rechnungsfähige Dokumentarten können XRechnung oder ZUGFeRD-XML erzeugen. Vor
der Ausstellung wird zuerst das kanonische Rechnungsmodell mathematisch
geprüft, danach XML-Schema und Geschäftsregeln vollständig offline validiert.
PrintOps bündelt und protokolliert folgende Regelstände:

- EN 16931 Validation Artefacts `1.3.16`
- XRechnung `3.0.2`, Validator-Bundle `2026-01-31`
- ZUGFeRD `2.5` / Factur-X `1.09`

Unterstützt werden XRechnung als UBL 2.1 und UN/CEFACT CII D16B sowie ZUGFeRD
als CII D22B im Profil EN16931 oder XRECHNUNG. Für B2G-Empfänger sind unter
anderem elektronische Adresse, Schema und Buyer Reference beziehungsweise
Leitweg-ID erforderlich. Ein Validierungsfehler verhindert die Ausgabe; eine
bereits reservierte Nummer wird nachvollziehbar als verworfen markiert.

Bei erfolgreicher Ausstellung werden unveränderlicher kanonischer Snapshot,
SHA-256-Prüfsumme, XML-Artefakt, Validierungsbericht und Regelversionen
gespeichert. Metadaten und Bericht benötigen Leserechte; der XML-Download
benötigt `commercial_documents:export`. Beim Download wird die gespeicherte
Datei erneut gegen ihre Prüfsumme geprüft.

## Berechtigungen

- `document_templates:read`: Konfigurationen, Verlauf und Prüfungen lesen
- `document_templates:manage`: Entwürfe bearbeiten, prüfen, freigeben und neue
  Versionen anlegen
- `commercial_documents:read`: Dokumente und E-Rechnungsmetadaten lesen
- `commercial_documents:draft`: Dokumententwürfe anlegen und bearbeiten
- `commercial_documents:approve`: einen Entwurf fachlich bereitstellen
- `commercial_documents:issue`: Nummer reservieren und unveränderlich ausstellen
- `commercial_documents:correct`: Storno, Korrektur und Gutschrift anlegen
- `commercial_documents:export`: validierte E-Rechnungsdatei herunterladen
- `commercial_documents:tax_override`: begründete Steuerabweichung erfassen
- `order_audit:read`: vollständiges Auditprotokoll lesen

Die API prüft jedes Recht unabhängig von der Sichtbarkeit eines UI-Elements.

## Sicherung und Wiederherstellung

Vollständige lokale ZIP-Sicherungen enthalten Datenbank und damit
Konfigurationen, Dokumente, Snapshots, Auditereignisse, Nummernreservierungen
und Validierungsberichte. Zusätzlich werden `document-artifacts` und ein
Regelwerksmanifest gesichert. Beim Wiederherstellen wird jede ausgelagerte
Datei per SHA-256 geprüft. Fehlende, unsichere oder veränderte Artefakte werden
gemeldet und im wiederhergestellten Datensatz ausdrücklich auf `invalid`
gesetzt; sie erscheinen niemals stillschweigend als gültig.

Private Git-Backups nehmen bei aktivierter Einstellungssicherung dieselben
kommerziellen Tabellen, das Regelwerksmanifest und Artefakte in
inhaltsadressierter Base64-Form auf. PrintOps verweigert diese Sicherung, wenn
das Ziel-Repository nicht als privat bestätigt werden kann. Supportpakete
nehmen diese fachlichen Belege und unnötige personenbezogene Inhalte nicht auf.

## Bewusste Abgrenzung

PDF-Layout, visuelle Formatgestaltung und Dokumentvorschau sind nicht Teil
dieser Ausbaustufe. Ebenfalls nicht enthalten ist der automatische Transport
über Peppol, E-Mail oder ein Buchhaltungssystem. PrintOps erzeugt, prüft,
speichert und exportiert die strukturierte E-Rechnung; Versand und visuelle
Ausgabe werden separat umgesetzt.
