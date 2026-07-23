# Dokumentformat und PDF-Vorschau

**Datum:** 23. Juli 2026

**Status:** fachlich und technisch freigegeben

**Voraussetzung:** `2026-07-20-document-management-e-invoice-design.md`

## Ziel

PrintOps erhält einen vollständigen, strukturierten Layoutbereich für alle
kaufmännischen Dokumente. Benutzer gestalten professionelle, mehrseitige
Dokumente über kontrollierte Optionen statt über frei positionierbare Elemente.
Eine echte PDF-Vorschau und die endgültige Ausgabe verwenden ausnahmslos
dieselbe serverseitige Renderpipeline.

Die Ausbaustufe umfasst:

- visuelles PDF-Layout, Briefpapier, Typografie, Farben und Positionierung;
- automatische, versionierte Speicherung von Layoutentwürfen;
- Vorschau mit reproduzierbaren Beispieldaten oder einem realen Dokumententwurf;
- endgültige PDF/A-3u-Erzeugung für sämtliche kaufmännischen Dokumente;
- normgerechte Einbettung des validierten ZUGFeRD-XML;
- unveränderliche Ablage von PDF, Prüfbericht, Regeln und verwendeten Assets;
- eine abgesicherte Render- und Exportschnittstelle für externe Programme.

## Nicht enthalten

Diese Ausbaustufe enthält ausdrücklich nicht:

- einen frei positionierbaren DTP- oder Canvas-Editor;
- benutzerdefiniertes HTML, CSS, JavaScript oder ausführbare Vorlagenskripte;
- E-Mail-, Peppol-, Behördenportal- oder Buchhaltungstransport;
- automatische Mahnausführung oder Zustellung;
- digitale Signaturen oder qualifizierte elektronische Signaturen;
- OCR oder nachträgliche inhaltliche Bearbeitung ausgestellter PDFs.

## Leitentscheidungen

### Strukturierter semantischer Editor

Layoutoptionen steuern fachlich definierte Bereiche: Absender, Empfänger,
Dokumentkopf, Metadaten, Positionen, Summen, Steuern, Zahlungsdaten, technische
Druckdaten, Hinweise und Fußzeile. Reihenfolge und Sichtbarkeit sind nur dort
änderbar, wo keine Pflichtangaben, Seitenregeln oder Dokumentsemantik verletzt
werden.

Der Editor bietet drei professionelle Ausgangsvorlagen:

- `classic` – klassisch, klar gerahmte Tabellen und zurückhaltende Gestaltung;
- `modern` – offenere Flächen, stärkere Typografie und dezente Akzentflächen;
- `compact` – geringere Abstände und hohe Informationsdichte.

Die Vorlagen unterscheiden sich nur visuell. Datenquellen, Pflichtinhalte,
Rundung und Dokumentsemantik bleiben identisch.

### Eigener Einstellungsbereich

Der Menüpunkt heißt `Format & Vorschau` und liegt unter
`Einstellungen → Auftragsverwaltung` direkt nach `Dokumente`. Fachliche
Dokumentregeln und visuelle Ausgabe bleiben damit getrennte, aber verknüpfte
Bereiche.

### Eine Renderpipeline

Vorschau, Download, externe API und endgültige Ausstellung rufen denselben
Renderer auf. Eine separate HTML-Näherung im Browser ist nicht zulässig. Die
Oberfläche stellt das tatsächlich erzeugte PDF mit PDF.js dar.

### PDF/A-3u für alle kaufmännischen Dokumente

Angebote, Aufträge, Lieferscheine, Rechnungen, Korrekturen, Gutschriften,
Zahlungserinnerungen und Mahnungen werden als PDF/A-3u erzeugt. Nur fachlich
dafür vorgesehene ZUGFeRD-Rechnungen enthalten das validierte CII-XML als
zugeordnete Datei.

Bei XRechnung bleibt das validierte XML das maßgebliche Rechnungsoriginal. Ein
zusätzliches PDF ist eine lesbare Darstellung und wird weder als ZUGFeRD
bezeichnet noch mit einem fachlich falschen Hybrid-XML versehen.

## Geltung und Vererbung

Ein effektives Layout entsteht in dieser Reihenfolge:

1. unveränderliche Systemvorlage;
2. Standardlayout des Unternehmensprofils;
3. Abweichung für eine Dokumentart;
4. Abweichung für eine Sprache innerhalb der Dokumentart.

Eine spezifischere Ebene speichert nur ihre Abweichungen. Das Zurücksetzen eines
Feldes entfernt die Abweichung und macht die darunterliegende Quelle wieder
wirksam. Jede sichtbare Einstellung zeigt ihre Herkunft analog zur bestehenden
Dokumentkonfiguration.

Das Unternehmensprofil benötigt genau ein wirksames Standardlayout. Fehlt eine
dokument- oder sprachspezifische Version, ist der Fallback deterministisch.
Systemwerte werden niemals still in eine spezifische Ebene kopiert.

## Relationales Datenmodell

### `DocumentLayoutConfiguration`

Identifiziert ein Layout über Unternehmensprofil, optionale Dokumentart,
optionale Sprache und Version. Verbindliche Felder sind:

- `id`, `business_profile_id`, `document_type`, `language`;
- `version`, `status`, `effective_from`, `lock_version`;
- `template_key`, `page_format`, `orientation`;
- `change_reason`, `created_by_id`, `published_by_id`;
- `created_at`, `updated_at`, `published_at`;
- `renderer_version`, `validation_status`, `validation_report`.

`document_type = null` und `language = null` kennzeichnet den Profilstandard.
Eine Sprache ohne Dokumentart ist unzulässig. Unterstützte Zustände entsprechen
dem Dokumentbereich: `draft`, `scheduled`, `active`, `superseded`, `withdrawn`.

### Layoutbereiche

Die fachlichen Bereiche werden relational oder in klar getrennten
Ein-zu-eins-Tabellen gespeichert:

- Seiten- und Randregeln;
- Typografie und Farbregeln;
- Kopf-, Absender- und Empfängerregeln;
- Dokumenttitel und Metadaten;
- Positionstabellenregeln;
- Summen-, Steuer- und Zahlungsregeln;
- Regeln für technische Druckdaten;
- Hinweis- und Textbausteinplatzierung;
- Fußzeilen- und Seitennummernregeln.

Beliebige CSS-Fragmente oder nicht typisierte Eigenschaftssammlungen sind nicht
zulässig. JSON ist nur für unveränderliche effektive Snapshots, Prüfberichte und
Rendererbelege erlaubt.

### `DocumentLayoutAsset`

Assets gehören zu einem Unternehmensprofil und besitzen:

- Typ `logo`, `letterhead_first`, `letterhead_following` oder `font`;
- Originalname, MIME-Typ, Dateigröße und SHA-256;
- unveränderlichen Speicherpfad oder eingebetteten Inhalt;
- technischen Prüfstatus und strukturierten Prüfbericht;
- Schrifteigenschaften beziehungsweise PDF-Seiteneigenschaften;
- Ersteller und Zeitstempel.

Ein Layout referenziert konkrete Assetversionen. Das Ersetzen eines Assets
ändert niemals eine aktive oder bereits verwendete Layoutversion.

### Ausstellungsbeleg

Jedes endgültige PDF-Artefakt speichert:

- Layoutkonfigurations-ID und -Version;
- alle Asset-IDs und Prüfsummen;
- Renderer- und Validatorversion;
- kanonischen Dokument-Snapshot und dessen SHA-256;
- PDF-Datei, PDF-SHA-256 und PDF/A-Prüfbericht;
- bei ZUGFeRD XML-SHA-256, Profil und zugeordnete Dateimetadaten.

Damit ist eine spätere bitgenaue Integritätsprüfung möglich, ohne historische
Layouts oder Assets erneut aufzulösen.

## Entwurf, Autosave und Freigabe

Layoutänderungen werden über die vorhandene zentrale Autosave-Infrastruktur
gespeichert. Deren zentrale Verzögerung, Abbruchlogik und Statusanzeige bleiben
maßgeblich; es entsteht keine zweite Autosave-Implementierung.

Der Ablauf lautet:

1. Benutzer ändert einen typisierten Layoutwert.
2. Der lokale Zustand wird sofort aktualisiert.
3. Autosave sendet Patch, `lock_version` und eine stabile Bearbeitungssitzung an
   den Entwurf; das Audit erfasst automatisch die geänderten Feldpfade.
4. Der Server bestätigt die neue Version des Entwurfs.
5. Erst danach wird eine Vorschau für genau diese bestätigte Version erzeugt.
6. Ältere Speicher- und Vorschauantworten dürfen neuere Zustände nicht ersetzen.

Autosave erzeugt keine Freigabe. Die manuelle Freigabe bleibt gesperrt, solange
eine Speicherung aussteht, ein Versionskonflikt besteht, Assets ungültig sind
oder die Bereitschaftsprüfung einen Blocker enthält.

Ein eigener Änderungsgrund ist beim Anlegen einer neuen Layoutversion, bei der
Freigabe und bei der Rücknahme erforderlich. Einzelne Autosaves verlangen keine
wiederholte Texteingabe; sie bleiben über Bearbeitungssitzung, Feldänderungen,
Akteur und Zeitstempel vollständig nachvollziehbar.

Aktive Layouts sind unveränderlich. `Neue Version anlegen` kopiert die aktive
Version samt Assetreferenzen in einen neuen Entwurf. Eine terminierte Freigabe
kann begründet zurückgezogen werden.

## Oberfläche

### Desktop

Die Hauptfläche verwendet zwei Spalten im Verhältnis ungefähr 2:1:

- links die große, echte A4-/Letter-Vorschau als vertikaler Seitenstapel;
- rechts die kompakte, sticky Layoutsteuerung.

Die Vorschau besitzt eine kompakte Werkzeugleiste mit:

- Unternehmensprofil, Dokumentart und Sprache;
- Datenquelle `Beispieldokument` oder `Dokumententwurf`;
- Auswahl des realen Entwurfs, sofern dieser Modus aktiv ist;
- Seitenanzahl, Zoom, Einpassen und aktuellem Renderstatus;
- `PDF öffnen` und – bei ausreichender Berechtigung – `Herunterladen`.

PDF.js rendert ausschließlich die vom Server erhaltenen PDF-Bytes. Der
Seitenstapel zeigt alle Seiten, nicht nur ein Vorschaubild der ersten Seite.

### Layoutsteuerung

Die rechte Spalte enthält aufklappbare, fachlich geordnete Abschnitte:

1. Basislayout und Papierformat;
2. Briefpapier für erste Seite und Folgeseiten;
3. Typografie und Farben;
4. Logo, Absender und Empfängerbereich;
5. Dokumenttitel und Metadaten;
6. Positionstabelle und technische Druckdaten;
7. Summen, Steuern und Zahlungsinformationen;
8. Hinweise und Textbausteine;
9. Fußzeile und Seitennummerierung;
10. PDF/A- und ZUGFeRD-Status.

Abhängige Felder werden nur angezeigt, wenn sie fachlich relevant sind. Ein
deaktivierter Pflichtbereich erklärt, warum er nicht ausgeblendet werden kann.
Leere Karten und funktionslose Platzhalter sind nicht zulässig.

### Mobile und Touch

Bei 390 × 844 Pixeln wird die Ansicht einspaltig: vollständige Vorschau zuerst,
Layoutsteuerung danach. Seiten bleiben als erkennbare Papierflächen sichtbar
und werden auf die verfügbare Breite skaliert. Alle Bedienelemente erfüllen die
bestehenden Touch- und Design-System-Vorgaben; horizontaler Seitenüberlauf ist
unzulässig.

## Konfigurierbare Layoutwerte

### Seite

- Papierformat `A4` oder `Letter`;
- ausschließlich Hochformat;
- oberer, rechter, unterer und linker Rand in Millimetern;
- eigener Inhaltsbeginn auf erster Seite und Folgeseiten;
- Vorlage `classic`, `modern` oder `compact`;
- Akzentfarbe im validierten Hex-Format.

Ränder werden gegen druckbare Mindestwerte und reservierte Kopf-/Fußbereiche
validiert. Eine Konfiguration, deren nutzbarer Inhaltsbereich zu klein ist,
kann nicht freigegeben werden.

### Typografie

- Grundschrift, Tabellen- und Metadatengröße;
- Überschriftenhierarchie;
- Zeilenhöhe und Absatzabstand;
- integrierte oder hochgeladene Schriftfamilie;
- getrennte Regular-, Bold-, Italic- und Bold-Italic-Schnitte.

Alle verwendeten Glyphen müssen Unicode-zuordenbar und vollständig eingebettet
sein. Fehlt ein benötigter Schnitt, wird ein definierter integrierter Fallback
verwendet und als Warnung ausgewiesen; ein fehlender Zeichensatz ist ein
Blocker.

### Kopf und Empfänger

- Logo sichtbar, Größe und zulässige Ausrichtung;
- Firmendatenblock sichtbar;
- kurze Absenderzeile über der Empfängeranschrift;
- Empfängerfensterposition innerhalb des strukturierten Rasters;
- Dokumenttitel, Nummer, Datum, Fälligkeit und weitere typabhängige Metadaten.

### Positionen und Summen

- Tabellenstil `compact`, `standard` oder `spacious`;
- zulässige Spalten je Dokumentart;
- technische Druckdaten sichtbar oder ausgeblendet;
- Beschreibungsumfang und Sekundärzeilen;
- Summen-, Steuer-, Skonto-, Zahlungs- und Anzahlungsblöcke.

Pflichtspalten und gesetzlich beziehungsweise semantisch notwendige Summen
können nicht ausgeblendet werden.

### Fußzeile

- Fußzeile aktiv;
- Layout mit einer, zwei oder drei Spalten;
- Firmendaten;
- Steuerangaben oder §-19-UStG-Hinweis;
- Bankverbindung und alternative Zahlungsdaten;
- zusätzliche freigegebene Hinweise;
- Seitennummerierung im Format `Seite x/y`.

Nicht vorhandene optionale Daten erzeugen keine leeren Spalten. Die verbleibenden
Bereiche werden deterministisch neu verteilt.

## Briefpapier und eigene Schriften

### Briefpapier

Ein Unternehmensprofil kann getrennte einseitige PDFs für erste Seite und
Folgeseiten hochladen. Fehlt die Folgeseite, wird die erste Seite verwendet,
sofern die Konfiguration dies ausdrücklich erlaubt; andernfalls bleibt die
Folgeseite ohne Briefpapier.

Der Upload wird abgelehnt bei:

- Verschlüsselung oder Passwortschutz;
- JavaScript, Aktionen, Formularen, eingebetteten Dateien oder externen
  Abhängigkeiten;
- mehr als einer Seite pro Asset;
- nicht unterstützter oder nicht zur Konfiguration passender Seitengröße;
- fehlenden eingebetteten Schriften oder ungültiger PDF-Struktur;
- Überschreitung der zentralen Assetgrößenbegrenzung.

Das Briefpapier wird als Seitenhintergrund übernommen. Nach dem Zusammenführen
muss das Gesamtdokument erneut PDF/A-3u-konform sein; andernfalls bleibt die
Layoutfreigabe blockiert.

### Schriften

Unterstützt werden TTF und OTF. Vor Speicherung werden Dateisignatur,
Schrifttabellen, Familienname, Schnitte, Glyphenabdeckung und Einbettungsrechte
geprüft. Variable oder farbige Schriften werden nur akzeptiert, wenn die
gepinnten Renderer- und PDF/A-Tests sie nachweislich unterstützen.

Die Oberfläche weist darauf hin, dass der hochladende Benutzer für ausreichende
Nutzungs- und Einbettungsrechte verantwortlich ist. Technisch nicht einbettbare
Schriften werden nicht gespeichert.

## Vorschau- und Beispieldaten

Für jede Dokumentart und Sprache existiert ein versioniertes, deterministisches
Beispieldokument. Die Fixtures enthalten mindestens:

- lange Absender- und Empfängeranschrift;
- mehrere kurze und lange Positionen;
- technische Druckdaten;
- Rabatt, Skonto und mindestens zwei Steuersätze, soweit fachlich zulässig;
- Zahlungs- und Bankinformationen;
- relevante Hinweise und Textbausteine;
- genügend Positionen für mindestens zwei Seiten.

Beispieldaten reservieren keine Nummer, verändern keinen Bestand und erzeugen
kein kaufmännisches Dokument. Sie tragen ein deutliches, aber abschaltbares
Vorschauwasserzeichen.

Im Modus `Dokumententwurf` wird ein vorhandener, lesbarer Entwurf über seine ID
verwendet. Der Server prüft Unternehmensprofil und Berechtigung; beliebige
Snapshotdaten aus dem Browser werden nicht akzeptiert.

## Seiten- und Umbruchregeln

Der Renderer erzwingt:

- wiederholte Tabellenköpfe auf jeder Folgeseite;
- ungetrennte Positionen, solange eine Position auf eine leere Seite passt;
- kontrollierte Teilung einer einzelnen überlangen Position;
- zusammenhängende Summen-, Steuer- und Zahlungsblöcke;
- reservierten Fußzeilenraum ohne Inhaltsüberlagerung;
- typografische Mindestabstände vor und nach Überschriften;
- kontrollierte Umbrüche langer Wörter, Artikelnummern, URLs und Adressen;
- keine leeren fachlichen Bereiche bei fehlenden optionalen Daten;
- korrekte Gesamtseitenzahl für `Seite x/y`.

Ein Layout, das Pflichtinhalte nicht ohne Überlagerung oder Abschneiden rendern
kann, erhält einen feldbezogenen Blocker. Der Renderer verkleinert Texte nicht
stillschweigend unter die konfigurierte Mindestgröße.

## Renderpipeline

### Komponenten

1. **Snapshot-Resolver** lädt einen unveränderlichen Dokument-Snapshot oder ein
   versioniertes Beispieldokument.
2. **Layout-Resolver** bestimmt die effektive veröffentlichte beziehungsweise
   angeforderte Entwurfsversion samt Assetversionen.
3. **Semantischer View-Model-Builder** erzeugt typisierte Renderblöcke ohne
   HTML aus Benutzereingaben.
4. **Interner Template-Renderer** erzeugt kontrolliertes HTML/CSS für
   WeasyPrint.
5. **WeasyPrint** erzeugt das paginierte PDF/A-3u-Grunddokument.
6. **pikepdf** übernimmt geprüftes Briefpapier und stellt die erforderlichen
   Dateibeziehungen beziehungsweise Metadaten sicher.
7. **ZUGFeRD-Schritt** bettet ausschließlich das bereits validierte CII-XML mit
   normgerechtem Namen, MIME-Typ und `AFRelationship` ein.
8. **veraPDF** prüft das vollständige Ergebnis gegen PDF/A-3u.
9. **Integritätsdienst** berechnet Prüfsummen und speichert Datei, Bericht,
   Versionen und Belege unveränderlich.

WeasyPrint, pikepdf, PDF.js und veraPDF werden exakt gepinnt. Die verwendeten
Versionen sind Bestandteil jedes Prüfberichts. Alle Komponenten werden für die
unterstützten PrintOps-Plattformen gebündelt und benötigen zur Laufzeit keinen
Internetzugriff.

### Ausfallverhalten

Ist der PDF/A-Validator nicht verfügbar, darf eine nicht archivfähige
Arbeitsvorschau erzeugt werden. Sie wird sichtbar als ungeprüft markiert.
Freigabe, Ausstellung und externer Export bleiben blockiert. Ein Renderer- oder
Validatorfehler fällt niemals still auf ein ungeprüftes PDF zurück.

### Determinismus

Bei identischem Snapshot, Layout, Assets und Rendererstand sind Seiteninhalt
und fachliche PDF-Struktur identisch. Laufzeitabhängige Erstellungszeitpunkte
und Dokumentkennungen werden aus dem Ausstellungskontext übernommen und nicht
willkürlich beim Rendern erzeugt.

## ZUGFeRD und XRechnung

### ZUGFeRD

- Grundlage ist das bereits validierte CII-D22B-XML des gewählten Profils.
- PDF- und XML-Inhalte stammen aus demselben kanonischen Snapshot.
- Das XML wird mit normgerechtem Dateinamen und Zuordnungsbeziehung eingebettet.
- XMP-Metadaten enthalten Profil und Dokumentart.
- Nach Einbettung werden PDF/A und XML erneut geprüft.
- XML-SHA-256 muss dem gespeicherten validierten Artefakt entsprechen.

### XRechnung

- UBL- oder CII-XRechnung bleibt als eigenständiges Originalartefakt erhalten.
- Ein PDF kann parallel erzeugt und gemeinsam exportiert werden.
- Das PDF behauptet keine ZUGFeRD-Konformität und enthält kein umdeklariertes
  XRechnung-XML.
- UI und Export benennen eindeutig, welches Artefakt das Rechnungsoriginal ist.

## API

Der Bereich erhält typisierte Endpunkte für:

- Layoutkatalog und zulässige Optionen;
- effektives Layout für Profil, Dokumentart und Sprache;
- Entwurf anlegen, lesen und per Patch automatisch speichern;
- Bereitschaft prüfen, freigeben, terminieren, zurückziehen und klonen;
- Versionsverlauf und Auditprotokoll;
- Asset hochladen, prüfen, lesen und nur bei Nichtverwendung löschen;
- verfügbare Beispieldokumente und lesbare reale Entwürfe;
- Vorschau erzeugen, Status lesen und PDF abrufen;
- Prüfbericht abrufen;
- endgültiges PDF aus einem unveränderlichen Snapshot erzeugen;
- PDF und gegebenenfalls XML exportieren.

Die Vorschauanfrage enthält nur IDs, Versionen und den Modus. Der Server
akzeptiert weder beliebige Dateipfade noch HTML, CSS, URLs oder vollständige
Snapshotobjekte vom Client.

Für externe Programme steht dieselbe authentifizierte Render-/Export-API zur
Verfügung. Endgültige Ausgaben akzeptieren nur veröffentlichte Layouts und
unveränderliche Dokument-Snapshots. Vorschauen dürfen einen berechtigten
Layoutentwurf verwenden.

## Berechtigungen

- `document_layouts:read` – Layouts, Vorschauen, Verlauf und Prüfberichte lesen;
- `document_layouts:manage` – Entwürfe und Assets verwalten, prüfen und
  freigeben;
- `commercial_documents:read` – reale Dokumententwürfe als Datenquelle lesen;
- `commercial_documents:export` – endgültige PDFs und E-Rechnungsartefakte
  herunterladen;
- `order_audit:read` – vollständiges Auditprotokoll lesen.

API-Key- und Benutzerrechte werden serverseitig für jeden Endpunkt geprüft.
Ein verstecktes oder deaktiviertes UI-Element ersetzt keine Berechtigungsprüfung.
Nicht berechtigte Benutzer erhalten einen erklärten Nur-Lese-Zustand.

## Sicherheit

- Uploads werden anhand des Inhalts und nicht nur der Dateiendung erkannt.
- Dateinamen bestimmen niemals Speicherpfade.
- Assets werden inhaltsadressiert außerhalb frei erreichbarer statischer Pfade
  gespeichert.
- Renderer darf keine Netzwerkressourcen, lokalen beliebigen Dateien oder
  `data:`-Inhalte außerhalb explizit bereitgestellter Assets laden.
- Interne Templates escapen sämtliche Dokumentwerte.
- Rendering besitzt Zeit-, Speicher-, Seiten- und Dateigrößenlimits.
- PDF-Uploads werden auf aktive Inhalte, Aktionen, Formulare, Anhänge,
  Verschlüsselung und externe Referenzen geprüft.
- Schriftparser und PDF-Verarbeitung laufen mit minimalen Rechten.
- Vorschauartefakte sind kurzlebig und nicht ohne Berechtigung adressierbar.

## Fehler- und Bereitschaftsmodell

Fehlerklassen bleiben getrennt:

- Autosave- oder Versionskonflikt;
- unvollständige oder widersprüchliche Layoutwerte;
- ungültiges, fehlendes oder nicht mehr verfügbares Asset;
- unvollständige Dokument- oder Stammdaten;
- Seitenüberlauf oder nicht erfüllbare Umbruchregel;
- Renderer- oder Ressourcenfehler;
- PDF/A-Regelverletzung;
- ZUGFeRD-Metadaten-, Einbettungs- oder Hashabweichung;
- fehlende Berechtigung.

Jeder Befund enthält Schweregrad, stabilen Code, Feldpfad, verständlichen Text,
Korrekturhinweis und – soweit vorhanden – externe Regel-ID. Blocker verhindern
Freigabe und endgültige Ausgabe. Warnungen bleiben sichtbar und werden im
Freigabebeleg gespeichert.

Die Oberfläche zeigt unabhängig voneinander:

- `Speichert` / `Gespeichert` / `Speicherfehler`;
- `Vorschau wird erzeugt` / `Vorschau bereit` / `Vorschaufehler`;
- `Ungeprüft` / `Bereit` / `Blockiert`;
- PDF/A- und E-Rechnungsstatus.

## Audit und Unveränderlichkeit

Erfasst werden mindestens:

- Entwurfserstellung und Autosave-Änderungen;
- Assetupload, Prüfung, Zuordnung und Löschversuch;
- Bereitschaftsprüfung und deren Regelstände;
- Freigabe, Terminierung, Rücknahme und Klonen;
- Vorschauerzeugung mit realem Dokumententwurf;
- endgültige Rendererzeugung und Export;
- fehlgeschlagene Integritäts- oder PDF/A-Prüfung.

Freigegebene Layouts, verwendete Assets, endgültige PDFs und Prüfberichte sind
append-only. Löschung ist ausgeschlossen, solange ein historischer Beleg darauf
verweist.

## Backup und Wiederherstellung

Lokale und private Git-Backups werden erweitert um:

- Layoutkonfigurationen und Veröffentlichungen;
- Layoutaudit;
- Logos, Briefpapier und Schriften;
- endgültige PDFs und PDF/A-Prüfberichte;
- Renderer- und Validatorbelege;
- Verknüpfungen zu XML-Artefakten.

Beim Restore werden sämtliche Assets und PDFs gegen ihre Prüfsummen geprüft.
Fehlende oder veränderte Dateien werden als ungültig markiert und niemals
stillschweigend neu gerendert. Historische Dokumente behalten ihren Beleg auch
dann, wenn der aktuelle Rendererstand abweicht.

## Migration

Die Migration erzeugt je Unternehmensprofil einen Entwurf auf Basis von
`classic`, A4, Hochformat und den vorhandenen Profilwerten:

- Logo und Akzentfarbe;
- vorhandene Firmendaten;
- gespeicherte Dokumenthinweise und Fußzeilentexte;
- Bank- und Steuerinformationen;
- bestehende Sichtbarkeit technischer Druckdaten.

Sie veröffentlicht nichts automatisch. Der erzeugte Entwurf muss geprüft und
manuell freigegeben werden. Migrationsbericht und Quellwerte bleiben erhalten.

## Tests

### Backend

- Schema-, Constraint- und Migrationstests;
- Vererbungs- und Fallbacktests für alle Ebenen;
- Entwurf, Autosave, Sperrkonflikt, Freigabe und Unveränderlichkeit;
- Assettyp-, Größen-, Pfad-, Hash- und Manipulationstests;
- Schriftprüfung und Glyphenabdeckung;
- Briefpapierprüfung und Zusammenführung;
- jede Dokumentart auf Deutsch und Englisch;
- A4 und Letter;
- erste Seite, Folgeseiten und mindestens zehnseitige Dokumente;
- lange Adressen, Wörter, URLs, Positionen und Textblöcke;
- wiederholte Tabellenköpfe und ungetrennte Summenblöcke;
- deterministische Referenz-PDFs;
- veraPDF-Prüfung aller Referenzdateien gegen PDF/A-3u;
- ZUGFeRD-Dateiname, MIME-Typ, `AFRelationship`, XMP und Hashgleichheit;
- eindeutige XRechnung-/ZUGFeRD-Trennung;
- Berechtigungen für Benutzer und API-Keys;
- Backup, Restore und beschädigte Artefakte;
- Ressourcenlimits und Ausfall des Validators.

### Frontend

- Kontext, Herkunft und Layoutvererbung;
- Autosavezustände und Versionskonflikte;
- Abbruch und Reihenfolge paralleler Vorschauanfragen;
- sämtliche Steuerabschnitte und Abhängigkeiten;
- Assetupload und konkrete Validierungsfehler;
- Beispiel- und Echtdatenumschaltung;
- mehrseitige PDF.js-Vorschau;
- Nur-Lese- und fehlende Berechtigungszustände;
- Freigabesperren und feldbezogene Bereitschaft;
- Desktop-Zweispaltenlayout;
- mobile Ansicht bei 390 × 844 ohne horizontalen Überlauf;
- Tastaturbedienung, Fokusführung und zugängliche Bezeichnungen.

### Browser-Abnahme

Die reale Anwendung wird mindestens mit `classic`, einem mehrseitigen
Beispieldokument und einem realen Rechnungsentwurf geprüft. Abgenommen werden:

- echte A4-Vorschau links und kompakte Steuerung rechts;
- Vorschau zuerst auf Mobilgeräten;
- automatische Speicherung ohne Datenverlust;
- Aktualisierung ausschließlich auf bestätigten Layoutständen;
- sichtbare Fehlermeldungen an den verursachenden Feldern;
- Downloadidentität zwischen Vorschau und endgültig erzeugtem Testartefakt;
- vollständige Seiten ohne Überlagerung oder abgeschnittene Fußzeile.

## Qualitätsziele

- Normale Layoutänderungen erreichen nach abgeschlossenem Autosave innerhalb
  von höchstens zwei Sekunden eine neue Vorschau auf der Referenzumgebung.
- Identische Renderanforderungen werden anhand eines Inhalts-Hashes
  wiederverwendet.
- Veraltete Vorschauen ersetzen niemals einen neueren Stand.
- Rendererfehler führen nicht zu einem Prozessabsturz oder Teilartefakt.
- Der Bereich entspricht dem bestehenden Dark-UI-Designsystem.
- Sämtliche sichtbaren Texte sind vollständig internationalisiert.
- Vorschau und endgültiges PDF sind technisch dieselbe Ausgabeart.

## Abnahmekriterien

Der Schritt ist abgeschlossen, wenn:

1. `Format & Vorschau` als eigener Menüpunkt vollständig erreichbar ist;
2. Profil-, Dokumentart- und Sprachvererbung nachvollziehbar funktionieren;
3. Entwürfe automatisch speichern und Freigaben versioniert bleiben;
4. Briefpapier für erste und folgende Seiten geprüft verwendet werden kann;
5. eigene einbettbare TTF-/OTF-Schriften unterstützt werden;
6. links eine echte mehrseitige PDF-Vorschau und rechts die kompakte Steuerung
   erscheinen;
7. Beispiel- und reale Dokumentdaten wählbar sind;
8. sämtliche Dokumentarten mehrseitig und ohne Überlagerung rendern;
9. alle endgültigen PDFs PDF/A-3u-konform sind;
10. ZUGFeRD-XML normgerecht eingebettet und XRechnung korrekt getrennt bleibt;
11. endgültige Artefakte, Layouts, Assets und Prüfberichte unveränderlich und
    vollständig auditiert sind;
12. externe Programme nur veröffentlichte Layouts und unveränderliche Snapshots
    rendern oder exportieren können;
13. Backup und Restore sämtliche neuen Belege integer erhalten;
14. Berechtigungs-, Sicherheits-, Backend-, Frontend- und Browserprüfungen
    erfolgreich sind;
15. keine offenen fachlichen oder technischen Platzhalter verbleiben.

## Technische Referenzen

- [WeasyPrint – PDF-Varianten, Attachments und Output-Intent](https://doc.courtbouillon.org/weasyprint/stable/manpage.html)
- [WeasyPrint – PDF/A-3 und Dateianhänge](https://doc.courtbouillon.org/weasyprint/latest/common_use_cases.html)
- [pikepdf – eingebettete Dateien](https://pikepdf.readthedocs.io/en/stable/topics/attachments.html)
- [veraPDF – PDF/A-Validierung](https://docs.verapdf.org/validation/)
- [veraPDF – CLI und PDF/A-3u-Profil](https://docs.verapdf.org/cli/validation/)

## Selbstprüfung der Spezifikation

- **Vollständigkeit:** Datenmodell, Vererbung, UI, Assets, Renderer, PDF/A,
  E-Rechnung, API, Rechte, Audit, Backup, Migration und Tests sind definiert.
- **Begriffsschärfe:** Vorschau und endgültige Ausgabe verwenden denselben
  Renderer; XRechnung und ZUGFeRD werden nicht vermischt.
- **Integrität:** Entwürfe sind veränderlich, veröffentlichte Layouts und
  ausgestellte Artefakte unveränderlich.
- **Sicherheit:** Beliebiges HTML/CSS, aktive PDF-Inhalte, freie Pfade und
  Netzwerkressourcen sind ausgeschlossen.
- **Scope:** Transport, DTP-Freiheit, Signaturen und automatische Zustellung
  bleiben ausdrücklich außerhalb dieses Schritts.
- **Offene Entscheidungen:** Es verbleiben keine fachlichen Produktentscheidungen,
  die einen Umsetzungsplan blockieren.
