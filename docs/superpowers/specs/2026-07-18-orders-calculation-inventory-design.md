# Aufträge/Kalkulation: Projektdateien, Lager und Reservierungen

**Status:** fachlich freigegeben

**Datum:** 2026-07-18

**Geltungsbereich:** Kalkulationsarbeitsplatz, 3MF-Auswertung, Filamentverfügbarkeit, vollständiges Kleinteilelager sowie Übergang von angenommenen Angeboten zu Auftrag/Projekt und Reservierungen

## 1. Einordnung

Diese Spezifikation baut auf den bestehenden Entwürfen zur Auftragsverwaltung und Kalkulation auf. Bei Widersprüchen ersetzt sie die UI- und Ablaufvorgaben aus:

- `2026-07-12-calculation-workspace-design.md`
- `2026-07-13-calculation-forgedesk-completion-design.md`

Bestehende Regeln zu Kalkulationsrevisionen, Freigaben, Preisentscheidung, Kostenaufschlüsselung und optionalen Folgeaktionen bleiben bestehen, soweit sie hier nicht ausdrücklich geändert werden.

## 2. Ziele und Abgrenzung

### Ziele

- Eine 3MF-Projektdatei ist die fachliche Quelle für Druckplatten und daraus abgeleitete Angebotspositionen.
- Mehrere Platten und Varianten mit unterschiedlichen Stückzahlen oder Materialien sind ohne doppelte Dateneingabe kalkulierbar.
- Die produktiven PrintOps-Slicer-Sidecars werden genutzt; ForgeDesk dient als Referenz für Plattenauswahl, Vorschau und Fallback-Schätzung.
- Alle tatsächlich verwendeten Kalkulationswerte sind sichtbar, editierbar und hinsichtlich ihrer Herkunft nachvollziehbar.
- Filament und Kleinteile werden bereits während der Kalkulation auf Verfügbarkeit geprüft, aber erst bei Angebotsannahme reserviert.
- Das Kleinteilelager wird in diesem Arbeitsschritt vollständig umgesetzt, einschließlich Einstellungen, Bestandsjournal, Suche, Verfügbarkeitsprüfung und Reservierungen.
- Die Annahme eines Angebots erzeugt transaktional Auftrag/Projekt und alle benötigten Reservierungen.

### Nicht-Ziele

- Es wird keine neue Slicing-Engine implementiert.
- Der bestehende Lagerbereich bleibt in die drei Bereiche **Filament**, **Kleinteile** und **Ware** gegliedert.
- Das Warenlager erhält in diesem Schritt keine automatische Einlagerung gedruckter Teile. Das folgt in einem späteren, separat geplanten Ausbau.
- Kalkulationen reservieren keinen Bestand.
- Teilreservierungen und negative Bestände sind nicht zulässig.

## 3. Kalkulationsarbeitsplatz

Der Arbeitsplatz verwendet auf größeren Ansichten ein Zweispaltenlayout:

- **Links:** durchgängiges Formular mit den Abschnitten Varianten, Projektdatei, Kleinteile, Arbeitszeit & Nachbereitung und Kosten & Preise.
- **Rechts:** fixierte Live-Zusammenfassung mit Verfügbarkeit, Kosten, Verkaufspreis, Marge und Validierungsstatus.

Auf schmalen Ansichten wird die Zusammenfassung unter dem Formular angeordnet. Die Bearbeitungsreihenfolge und Tastaturnavigation bleiben dabei logisch erhalten.

### 3.1 Varianten

Die bisherige Darstellung als einzelne große Auswahlfläche wird durch eine kompakte Variantenleiste ersetzt.

Jede Variante zeigt mindestens:

- Name
- wesentliche Stückzahl-/Materialabweichung
- ausgewählte Platten
- Nettoverkaufspreis
- Verfügbarkeitsstatus

Es gibt zwei getrennte Zustände:

- **Aktive Variante:** wird gerade bearbeitet.
- **Bevorzugte Angebotsvariante:** wird dem Kunden als bevorzugte Option markiert; exakt eine Variante kann bevorzugt sein.

Varianten können neu angelegt, umbenannt, dupliziert und entfernt werden. Beim Duplizieren werden Plattenauswahl und Overrides kopiert, nicht aber eine neue Projektdatei erzeugt. Eine Variante darf mehrere Platten auswählen. Mehrfachauswahl ist der Standardfall.

### 3.2 Projektdatei

Der bisherige manuelle Abschnitt **Positionen** entfällt an dieser Stelle. Angebots- und Auftragspositionen werden aus der Projektdatei, den ausgewählten Platten und der aktiven Variante abgeleitet.

Der Abschnitt enthält:

- Druckerauswahl
- Trocknerauswahl
- Trocknungsdauer in Stunden
- Upload-Zone für 3MF per Drag-and-drop und Dateidialog
- Kartenansicht der Projektplatten mit Name, Vorschau, Auswahlstatus und Kurzzusammenfassung
- Detailauswertung für die aktuell fokussierte Platte

Die Zahl gleichzeitig sichtbarer Plattenkarten und die Darstellungsgröße werden über Einstellungen steuerbar. Mehrfachauswahl erfolgt unabhängig von der fokussierten Detailplatte.

Für jede Platte werden angezeigt:

- Plattenname
- erkannte Druckteilanzahl, editierbar
- erkanntes Material und zugeordneter Filamentbestand
- benötigtes Material und frei verfügbare Menge
- **Druckteile je Druck** als Ersatz für „Teile/Lauf“
- Ausschussdrucke
- Material in `g/Druck`
- Dauer in `h/Druck`

Erkannte Werte dürfen überschrieben werden. Jeder überschriebene Wert erhält eine Herkunftsanzeige und eine Aktion **Auf erkannten Wert zurücksetzen**.

### 3.3 Kleinteile

Kleinteile werden zeilenweise erfasst. Jede Zeile enthält:

- durch Tastatureingabe filterbare Artikelauswahl aus dem Kleinteilelager
- benötigte Anzahl
- Bestandseinheit
- frei verfügbare Anzahl
- resultierenden Verfügbarkeitsstatus
- Einstandspreis und kalkulierte Kosten
- Entfernen-Aktion

Über **Kleinteil hinzufügen** können beliebig viele Zeilen ergänzt werden. Die Suche berücksichtigt mindestens Artikelnummer, Bezeichnung, Kategorie und optionale Suchbegriffe.

### 3.4 Arbeitszeit & Nachbereitung

Der Abschnitt zeigt die effektiven Werte direkt als Eingabewerte und nicht nur als Platzhalter:

- Rüstzeit in Stunden
- Nachbereitung in Stunden je Stück
- CAD/Konstruktion in Stunden
- Qualitätskontrolle in Stunden
- Filamentpreis in EUR/kg
- Materialaufschlag in Prozent
- Ausschuss in Prozent
- Stundensatz in EUR/h
- Verbrauchsmaterial in EUR
- Verpackung in EUR
- Versand in EUR
- Rabatt in Prozent

Für jeden Wert ist sichtbar, ob er aus den globalen Einstellungen, einer Drucker-/Materialvorgabe, einer 3MF-Auswertung, einem Slicer-Ergebnis oder einer manuellen Änderung stammt. Geänderte Standardwerte können einzeln zurückgesetzt werden.

### 3.5 Kosten & Preise

Der bestehende Abschnitt bleibt inhaltlich erhalten. Kostenaufschlüsselung, Preisentscheidung und optionale Folgeaktion bleiben ebenfalls erhalten. Sie rechnen künftig mit den strukturierten Platten-, Filament- und Kleinteildaten.

Die rechte Live-Zusammenfassung zeigt zusätzlich:

- Status je benötigtem Filament und Kleinteil
- deutlichen Hinweis „Prüfung ohne Reservierung“ während der Kalkulation
- Blocker, Warnungen und manuelle Schätzungen
- Zeitpunkt der letzten Verfügbarkeitsprüfung

## 4. Projektdatei- und Slicer-Pipeline

### 4.1 Persistenzmodell

Eine hochgeladene 3MF wird als eigenständige Kalkulations-Projektdatei gespeichert. Sie besitzt mindestens:

- stabile ID und Bezug zur Kalkulation
- Originaldateiname, Dateigröße und Prüfsumme
- Speicherreferenz
- erkannte Drucker-/Profilmetadaten
- Analyse- und Slicerstatus
- strukturierte Platten mit stabiler Plattenkennung, Name, Vorschau und Objektzahl
- Analyseergebnisse und deren Herkunft

Varianten referenzieren dieselbe Projektdatei. Pro Variante werden nur Plattenauswahl und fachliche Overrides gespeichert. Ein erneuter Upload ersetzt die Datei nicht stillschweigend: Er erzeugt eine neue Dateirevision, ordnet Platten anhand stabiler Merkmale neu zu und meldet nicht mehr auflösbare Zuordnungen zur manuellen Prüfung.

### 4.2 Vorschauen und Plattenauswahl

Vorschauen werden in dieser Reihenfolge ermittelt:

1. eingebettete 3MF-Vorschaubilder
2. vorhandener PrintOps-3MF-Renderer
3. neutrale Platzhalterkarte mit vollständigen Textdaten

Eine fehlende Vorschau verhindert die Kalkulation nicht. Platte, Name und Auswahl bleiben bedienbar.

### 4.3 Slicing

Das eigentliche Slicing erfolgt im Hintergrund über die bereits produktiven Orca-/Bambu-Sidecars bzw. deren bestehende CLI-Anbindung. Es wird keine Slicing-Logik aus ForgeDesk kopiert, wenn PrintOps bereits eine produktive Entsprechung besitzt.

Slicer-Ergebnisse werden anhand folgender Eingaben gecacht:

- Datei-Prüfsumme
- Plattenkennung
- Drucker
- Prozessprofil
- Materialprofil
- relevante Profilrevisionen

Ein Job liefert Status und Ergebnis je Platte. Der Benutzer kann währenddessen weiterarbeiten. Nach Abschluss aktualisieren sich Detailwerte und Kosten automatisch, sofern die betroffenen Felder nicht manuell überschrieben wurden.

Schlägt das produktive Slicing fehl oder ist kein Sidecar erreichbar, darf die vorhandene ForgeDesk-Geometrieschätzung als Fallback verwendet werden. Sie ist deutlich als **Schätzung** zu kennzeichnen und muss den Grund für den Fallback zeigen. Ein Slicer-Fehler darf nie als erfolgreiches Slicer-Ergebnis dargestellt werden.

### 4.4 Herkunft und Priorität

Für berechnete Felder gilt folgende Priorität:

1. manueller Override
2. erfolgreiches Slicer-Ergebnis
3. 3MF-Metadaten
4. ForgeDesk-Geometrieschätzung
5. Einstellungen/Standardwert

Die UI verwendet verständliche Herkunftskennzeichen: **Manuell**, **Slicer**, **3MF**, **Schätzung** und **Einstellung**.

## 5. Werte, Einheiten und Positionen

Intern bleibt die für Kalkulation und Bestandsführung erforderliche Genauigkeit erhalten. In der UI gelten:

- Stückzahlen und Läufe: ganze Zahlen
- Grammwerte: höchstens eine Nachkommastelle
- Stunden und Prozentwerte: höchstens zwei Nachkommastellen
- Geldbeträge: genau zwei Nachkommastellen
- Eingabe und Ausgabe nach deutschem Zahlenformat; API und Persistenz bleiben locale-unabhängig

Der Kalkulationskern arbeitet mit normalisierten Basiseinheiten und rundet Geld erst an den definierten Summengrenzen. Reine Anzeigeformatierung verändert keine gespeicherten Werte.

Aus jeder in einer Variante ausgewählten Platte entsteht eine nachvollziehbare Angebotsposition. Bei Bedarf können fachlich identische Platten zu einer Position zusammengefasst werden, solange die Rückverfolgung auf Quelldatei und Platten erhalten bleibt. Kleinteile werden Bestandteil der Kosten der betreffenden Variante und nicht automatisch als separate Kundenposition ausgewiesen.

## 6. Kleinteilelager

### 6.1 Lagerstruktur

Die bestehende Navigation bleibt:

1. Filament
2. Kleinteile
3. Ware

Das Kleinteilelager erhält ein gemeinsames Artikelmodell. Ein Artikel enthält mindestens:

- Artikelnummer und Bezeichnung
- Beschreibung und Suchbegriffe
- Kategorie
- Bestandseinheit
- Lagerort
- Mindestbestand
- Einstandspreis und optionale Lieferantenreferenz
- Aktivstatus

Bestände werden nicht als frei editierbare Zahl geführt, sondern aus einem unveränderlichen Bestandsjournal ermittelt. Journalvorgänge umfassen mindestens Zugang, Korrektur, Reservierung, Reservierungsfreigabe und bestätigte Entnahme. Korrekturen erfordern einen Grund.

### 6.2 Einstellungen

Der Einstellungsbereich ermöglicht:

- Kategorien verwalten
- zugelassene Bestandseinheiten verwalten
- Lagerorte verwalten
- Standard-Mindestbestand und Warnschwellen festlegen
- Verhalten für inaktive Artikel und Suchergebnisse festlegen

Einheiten eines bereits verwendeten Artikels dürfen nicht ohne explizite Bestandsumrechnung geändert werden.

### 6.3 Verfügbarkeit

Für Filament und Kleinteile gilt:

`frei verfügbar = physischer Bestand - aktive Reservierungen`

Bereits abgelaufene oder freigegebene Reservierungen zählen nicht. Die Verfügbarkeitsprüfung liefert sowohl Gesamtstatus als auch konkrete Fehlmengen. Die Kalkulation zeigt eine Momentaufnahme; vor der Annahme wird immer erneut innerhalb derselben Transaktion geprüft.

## 7. Angebot, Auftrag/Projekt und Reservierung

### 7.1 Statusübergang

Der fachliche Ablauf lautet:

`Kalkulation → Angebotsentwurf → versendet → angenommen → Auftrag/Projekt mit Reservierungen`

Erst beim Übergang zu **angenommen** werden Auftrag und Projekt erzeugt und Bestände reserviert. Die Aktion ist serverseitig atomar:

1. Angebotsrevision und bevorzugte Variante validieren.
2. Aktuelle Bedarfe reproduzierbar aus der Revision ermitteln.
3. Filament und Kleinteile gegen den aktuellen freien Bestand prüfen.
4. Konkrete Spulen und Kleinteilbestände zuordnen.
5. Auftrag, Projekt, Reservierungen und Journalvorgänge anlegen.
6. Angebot als angenommen markieren und Beziehungen speichern.

Schlägt ein Schritt fehl, wird nichts teilweise angelegt oder reserviert.

### 7.2 Filamentzuordnung

Filament bleibt ein spezialisiertes Spulenmodell. Die automatische Zuordnung berücksichtigt Material, Farbe bzw. definierte Austauschbarkeit, benötigte Masse und frei verfügbare Restmenge. Mehrere Spulen dürfen einen Bedarf erfüllen. Die Zuordnung ist in der Reservierung sichtbar und später nachvollziehbar änderbar, solange keine Entnahme erfolgt ist.

### 7.3 Parallelität und Wiederholungen

Die Annahmeaktion benötigt einen Idempotenzschlüssel. Ein wiederholter identischer Aufruf liefert dasselbe Ergebnis und erzeugt keine doppelten Aufträge, Projekte, Journalvorgänge oder Reservierungen.

Bestandsprüfung und Reservierung müssen mit Datenbankschutz gegen konkurrierende Annahmen erfolgen. Ist Bestand zwischen Kalkulation und Annahme nicht mehr verfügbar, erhält das Angebot einen blockierten Annahmestatus mit konkreten Fehlmengen. Es findet keine Teilreservierung statt.

### 7.4 Freigabe und Verbrauch

- Bei Stornierung des Auftrags/Projekts werden noch offene Reservierungen freigegeben.
- Bei Ablehnung eines noch nicht angenommenen Angebots existieren keine Reservierungen.
- Filamentreservierungen werden nach dem Druck mit dem tatsächlichen Verbrauch abgeglichen; Differenzen werden nachvollziehbar gebucht.
- Kleinteile werden im Projekt durch eine explizit bestätigte Entnahme verbraucht.
- Eine Entnahme über den verfügbaren bzw. reservierten Bestand hinaus ist blockiert.

## 8. Schnittstellen und Verantwortlichkeiten

Die bestehenden Routen werden kompatibel weitergeführt oder versioniert. Benötigt werden fachlich getrennte Schnittstellen für:

- Projektdatei-Upload, Dateirevisionen und Plattenanalyse
- Slicerjobs und Status je Platte
- Varianten, Plattenauswahl und Overrides
- Kleinteilartikel, Einstellungen, Bestandsjournal und Suche
- aggregierte Verfügbarkeitsprüfung ohne Reservierung
- atomare Angebotsannahme
- Reservierungsübersicht, Freigabe und bestätigte Entnahme

Berechnungen, Verfügbarkeitsentscheidungen und Statusübergänge sind Backend-Verantwortung. Das Frontend darf Ergebnisse unmittelbar voranzeigen, aber keine verbindliche Reservierungs- oder Preislogik allein ausführen.

## 9. Fehlerfälle und Bedienbarkeit

- Upload-, Analyse- und Slicerfehler werden pro Datei bzw. Platte angezeigt und sind wiederholbar.
- Ein Fallback wird nie still verwendet.
- Fehlende Lagerzuordnungen zeigen eine direkte Aktion zur Auswahl eines passenden Artikels oder einer Spule.
- Alle Auswahlfelder und Plattenkarten sind vollständig per Tastatur bedienbar und besitzen sichtbare Fokuszustände.
- Status wird nicht ausschließlich über Farbe vermittelt.
- Destruktive Aktionen wie Dateirevision ersetzen, Variante löschen oder Reservierung freigeben benötigen eine eindeutige Bestätigung, wenn dadurch Datenbezüge verloren gehen können.
- Veraltete Verfügbarkeitsdaten werden sichtbar gekennzeichnet und vor verbindlichen Aktionen serverseitig erneuert.

## 10. Migration und Kompatibilität

- Bestehende Kalkulationen bleiben lesbar und bearbeitbar.
- Vorhandene Source-Files und Fertigungsoperationen werden, soweit eindeutig möglich, in Projektdatei/Platten überführt.
- Nicht eindeutig zuordenbare Altwerte bleiben als manuelle Werte mit Herkunft **Migration** erhalten und werden zur Prüfung markiert.
- Bestehende Kalkulationsrevisionen werden nicht rückwirkend verändert.
- Das neue Kleinteilejournal startet mit einer dokumentierten Eröffnungsbuchung je bestehendem Bestand.
- Der Funktionsausbau kann per Feature-Schalter aktiviert werden, bis Migration und End-to-End-Tests abgeschlossen sind.

## 11. Teststrategie

### Backend

- Migrationen vorwärts und, soweit unterstützt, rückwärts
- Kalkulationskern mit mehreren Platten, Varianten, Ausschuss und Rundungsgrenzen
- 3MF-Fixtures mit einer und mehreren Platten sowie fehlenden Vorschaubildern
- Slicer-Sidecar-Erfolg, Timeout, Fehler und expliziter Schätzungsfallback
- Cachetrennung bei Profil- und Dateirevisionen
- Kleinteil-CRUD, Suche, Einheitenregeln und Bestandsjournal
- konkurrierende Angebotsannahmen auf denselben Bestand
- Idempotenz wiederholter Annahmen
- vollständiger Rollback bei Fehlbestand
- Freigabe, Entnahme und Filamentverbrauchsabgleich

### Frontend

- aktive und bevorzugte Variante unabhängig bedienen
- Plattenmehrfachauswahl und Detailfokus
- Upload per Drag-and-drop und Dateidialog
- Herkunftsanzeige und Zurücksetzen manueller Werte
- deutsches Zahlenformat ohne Verlust interner Genauigkeit
- filterbare Kleinteilauswahl und Fehlmengenanzeige
- responsive Zweispalten-/Einspaltenansicht
- Tastaturbedienung und zugängliche Statusmeldungen

### End-to-End

Mindestens ein vollständiger Pfad wird automatisiert geprüft:

1. 3MF mit mehreren Platten hochladen.
2. Platten auswählen und Variante duplizieren.
3. Material und Stückzahl in einer Variante ändern.
4. Kleinteile ergänzen und Verfügbarkeit prüfen.
5. Angebot mit bevorzugter Variante erzeugen und versenden.
6. Angebot annehmen und genau einen Auftrag, ein Projekt und vollständige Reservierungen erzeugen.
7. Kleinteile entnehmen, Filamentverbrauch abgleichen und verbleibende Reservierungen bei Abschluss freigeben.

## 12. Abnahmekriterien

Der Ausbau gilt als abgeschlossen, wenn:

- die freigegebene UI-Struktur umgesetzt ist,
- Platten aus realen 3MF-Dateien auswählbar und mit Vorschau dargestellt werden,
- produktive Sidecars verwendet werden und der Schätzungsfallback eindeutig erkennbar ist,
- alle Kalkulationswerte sichtbar vorbelegt und in korrekter Genauigkeit angezeigt werden,
- Positionen nachvollziehbar aus Projektplatten entstehen,
- das Kleinteilelager einschließlich Einstellungen und Journal vollständig nutzbar ist,
- Filament- und Kleinteilverfügbarkeit korrekt in Kalkulation und Live-Zusammenfassung erscheint,
- vor Angebotsannahme keine Reservierung existiert,
- Angebotsannahme Auftrag/Projekt und vollständige Reservierungen atomar und idempotent erzeugt,
- Konkurrenz- und Fehlbestandsszenarien ohne Überbuchung oder Teilreservierung enden,
- bestehende Kalkulationen ohne Datenverlust migriert oder eindeutig zur Prüfung markiert werden,
- die aufgeführten automatisierten Tests erfolgreich sind.
