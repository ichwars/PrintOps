# Auftragsverwaltung: Unternehmensprofile und Kunden

Diese Anleitung beschreibt den ersten ausgelieferten Baustein der
Auftragsverwaltung: Unternehmensprofile, Kundenstammdaten, Berechtigungen und
Kundennummern. Die inzwischen verfügbare, versionierte Dokumentverwaltung mit
E-Rechnung ist in der separaten Anleitung
[`Dokumentverwaltung und E-Rechnung`](document-management.md) beschrieben.

## Tabellen sortieren

In Auftragsübersicht, Kalkulation, Angeboten, Kunden, Rechnungen und
Lexware-Belegen sortieren Sie über die Spaltenüberschrift. Ein weiterer
Klick auf dieselbe Überschrift kehrt die Richtung um. Der Pfeil zeigt
die aktive Sortierung. Bei Angeboten und Rechnungen sortiert **Kunde**
alphabetisch nach dem angezeigten Namen. Einträge ohne Kundennamen stehen am Ende.

Bei Kunden, Angeboten und Lexware-Belegen werden alle Treffer der gewählten
Filter sortiert. Bei einem Wechsel der Sortierung öffnet sich die erste Seite.
In Angeboten sucht das Suchfeld nach Angebotsnummer, Kalkulation oder
Kundennamen. Unter der Tabelle lässt sich die Seitengröße wählen.
In der Rechnungsliste sortiert die Spalte **Fälligkeit** nach Datum.
Die voreingestellten Sortierungen nach Priorität, Fälligkeit, offenem
Betrag und Erstellungsdatum sind oberhalb der Tabelle verfügbar.
In Lexware-Belegen erfordert die Sortierung nach offenem Betrag das
Recht **Zahlungen lesen**.

## Zeilenaktionen

Ein Klick auf eine Datenzeile öffnet direkt die zugehörigen Details. Mit
der Tastatur können Sie die Zeile fokussieren und mit Enter oder der
Leertaste öffnen. Links in der Zeile führen zu ihrem jeweiligen Ziel.

Das Drei-Punkte-Menü steht rechts in der Tabelle. Es enthält die Aktionen,
die für den jeweiligen Datensatz und Ihre Rechte verfügbar sind. Mit den
Pfeiltasten wechseln Sie zwischen Aktionen. Escape schließt das Menü.

- **Aufträge** öffnen den Auftrag, das Projekt oder das zugrunde liegende Angebot.
  Die Auftragsdetails zeigen den Kundennamen, Positionen mit Menge, Einheit
  und Nettopreisen sowie Netto, Steuer und Brutto aus der Auftragsbestätigung.
  Bei älteren Aufträgen ohne Bestätigung ist der in der Kalkulationsrevision
  gespeicherte Nettopreis verfügbar. Aktive Aufträge lassen sich nach
  Bestätigung stornieren.
- **Angebote** öffnen Details, die Kalkulation, den Beleg und den verknüpften
  Auftrag, soweit vorhanden. Der Dialog zeigt den Kundennamen, die gespeicherten
  Belegpositionen mit Menge und Nettopreisen sowie Netto, Steuer und Brutto.
  Bei älteren Angeboten ohne Beleg steht der gespeicherte Nettopreis im Dialog.
  Der Status bestimmt die nächsten Schritte.
- **Kalkulationen** öffnen den Revisionsverlauf und zeigen die zugehörigen Angebote.
- **Kunden** öffnen gefilterte Angebote und Rechnungen für das gewählte
  Unternehmensprofil. Der Filter lässt sich über das X entfernen.
- **Rechnungen** zeigen den Kundennamen, die Rechnungspositionen mit Menge,
  Einheit und Nettopreisen sowie die Summen für Netto, Steuer und Brutto.
  Verfügbare Dateien und der Zahlungsverlauf stehen darunter.
- **Lexware-Belege** öffnen Details und den verknüpften PrintOps-Beleg. Ein
  einzelnes verfügbares Original lässt sich direkt herunterladen. Bei mehreren
  Originalen wählen Sie die Datei in den Details.

## Erstes Unternehmensprofil einrichten

Oeffnen Sie `Einstellungen > Auftragsverwaltung > Unternehmensprofil` und
waehlen Sie `Unternehmensprofil hinzufuegen`.

Fuer ein nutzbares erstes Profil werden mindestens folgende Angaben benoetigt:

- Profilname und rechtlicher Name;
- Land des Unternehmensprofils;
- Standardwaehrung, Sprache und Zeitzone;
- Abrechnungsmodus;
- eine registrierte Adresse mit Strasse, Postleitzahl, Ort und Land.

Steuerkennungen, Bankkonten, Handelsname und weitere Adressen koennen bei Bedarf
ergaenzt werden. Unternehmensprofile enthalten die ausstellende Organisation
und deren Richtlinien. Sie sind keine getrennten Mandanten und schraenken die
Sichtbarkeit von Kunden nicht automatisch ein.

## Standardprofil

Das erste aktive Unternehmensprofil wird zum Standardprofil. Zu jedem Zeitpunkt
gibt es hoechstens ein Standardprofil. Wird ein anderes Profil als Standard
gesetzt, verliert das bisherige Profil diese Eigenschaft atomar.

Das aktuelle Standardprofil kann nicht deaktiviert oder geloescht werden. Setzen
Sie zuerst ein anderes aktives Profil ausdruecklich als Standard. Eine Loeschung
kann weiterhin blockiert sein, wenn Kundenkonten auf das Profil verweisen. Die
Kundenverwaltung waehlt beim Oeffnen standardmaessig das aktive Standardprofil
aus.

## Abrechnungsmodi

Der Abrechnungsmodus legt die spaetere fachliche Verantwortung fuer
kaufmaennische Dokumente fest:

- `internal`: PrintOps soll Dokumentnummer, Freigabe und Ausgabe besitzen.
- `external`: Ein angebundenes Buchhaltungssystem soll die finale Ausgabe und
  Nummer besitzen; PrintOps bereitet die Daten vor.
- `hybrid`: Die Verantwortung kann spaeter je Dokumentart auf PrintOps oder ein
  externes System verteilt werden.

Der Modus ist bereits konfigurierbar, fuehrt in diesem Foundation-Inkrement aber
noch keine Rechnungsstellung, Dokumentausgabe oder Buchhaltungssynchronisation
aus.

## Kunden pro Unternehmensprofil

Oeffnen Sie `Auftraege > Kunden`. Ein Kunde besitzt eine gemeinsame Identitaet
mit Kontakten, Adressen, Steuerkennungen, Schlagwoertern und Notizen. Zusaetzlich
hat er mindestens ein Profilkonto. Dadurch kann derselbe Kunde mehreren
Unternehmensprofilen mit jeweils eigenen Konditionen zugeordnet werden.

Ein Profilkonto enthaelt insbesondere:

- Unternehmensprofil und Kundennummer;
- bevorzugte Waehrung;
- Zahlungsziel und Lieferbedingungen;
- Rabatt und Aktivstatus.

Kontakte koennen als Hauptkontakt und fuer spaetere Dokumente markiert werden.
Rechnungs-, Liefer- und sonstige Adressen werden getrennt gepflegt. Suchfeld,
Statusfilter und Kundenart beziehen sich auf das aktuell ausgewaehlte Profil.

## Kundennummern

Bleibt die Kundennummer eines Profilkontos beim Anlegen leer, reserviert PrintOps
transaktional die naechste Nummer der Sequenz des zugehoerigen
Unternehmensprofils, zum Beispiel `CUST-00001`. Bei mehreren Profilkonten wird
jede leere Nummer unabhaengig aus der Sequenz des jeweiligen Profils vergeben.
Nach einem Neustart wird jede Sequenz an der naechsten freien Nummer
fortgesetzt.

Eine manuelle Kundennummer ist zulaessig. Sie muss innerhalb desselben
Unternehmensprofils eindeutig sein. Dieselbe Nummer darf in einem anderen Profil
verwendet werden. Manuelle Nummern blockieren die automatische Sequenz nicht;
automatische Reservierungen ueberspringen bereits belegte Werte.

## Technische Integritaetsgrenzen

Kundennummern und andere case-insensitive Geschaeftsschluessel verwenden eine
fest gepinnte Unicode-15.1-Normalisierung. Python 3.13 nutzt dafuer seine
mitgelieferten Unicode-15.1-Tabellen; Python 3.10 bis 3.12 verwenden den
gleichversionierten `unicodedata2`-Backport. Dadurch bleiben persistierte
Schluessel und Frontend-Pruefungen unabhaengig von der Laufzeitversion gleich.

Unter SQLite serialisieren Kundenwrites und Lebenszyklusaenderungen eines
Unternehmensprofils ueber die zugehoerige Kundennummern-Sequenzzeile. Der
Schreib-Lock wird vor dem ersten Lesen der Transaktion erworben, damit ein
WAL-Read-Snapshot nicht spaeter in einen fehlgeschlagenen Schreib-Lock
hochgestuft werden muss. Ein globales Einschalten von SQLite-Fremdschluesseln
ist bewusst nicht Teil dieses Inkrements, weil es bestehende Migrations- und
Initialisierungspfade ausserhalb der Auftragsverwaltung veraendern wuerde.
PostgreSQL verwendet weiterhin Zeilen-Locks und Datenbank-Fremdschluessel.

## Rollen und Gruppen

Die Standardgruppen erhalten folgende Rechte:

- Administratoren verwalten Unternehmensprofile, Kunden und Gruppen und
  besitzen alle neuen Berechtigungen.
- Operatoren lesen und verwalten Kunden sowie die spaeteren operativen
  Auftragsbereiche. Sie duerfen standardmaessig keine Rechnungen ausgeben oder
  Buchhaltungsintegrationen konfigurieren.
- Viewer erhalten einen schreibgeschuetzten Zugriff auf Kunden und weitere
  freigegebene kaufmaennische Daten.
- API-Keys erhalten keine Auftragsverwaltungsrechte, bis dafuer ausdrueckliche,
  eng begrenzte Scopes implementiert sind.

Administratoren koennen die Zuordnung unter
`Einstellungen > Benutzer & Sicherheit > Gruppen` anpassen. Die API prueft die
Berechtigungen unabhaengig davon, ob eine Aktion in der Oberflaeche sichtbar ist.

## Naechste Ausbaustufen

Die Kalkulation ist unter `Auftraege > Kalkulation` erreichbar. Eine neue
Kalkulation beginnt mit einer konkreten Kundenanfrage; die Kundenzuordnung kann
zunaechst leer bleiben. Positionen, Drucklaeufe, Materialverbrauch, Druckzeit,
Ausschusslaeufe und Varianten werden in einem gemeinsamen Arbeitsbereich
gepflegt. Freigegebene Kalkulationen erzeugen unveraenderliche Revisionen und
koennen als wiederverwendbare Vorlage gespeichert werden.

Die Kostenbasis unter `Einstellungen > Auftragsverwaltung > Kalkulation`
enthaelt Ersatzwerte fuer Maschine, Arbeit, Energie, Risiko, Mindestpreis,
Nebenkosten und Preisverfahren. Konkrete Drucker- und Materialdaten haben
Vorrang. Die Beispielrechnung zeigt die Auswirkung der aktuellen Vorgaben.

Drucker und Trockner werden zentral unter `Einstellungen > Drucker & Produktion
> Geräteverwaltung` gepflegt. Dort hinterlegte Anschaffungs-, Restwert-,
Nutzungs-, Wartungs-, Leistungs- und Betriebsdaten ergeben den berechneten
Maschinenstundensatz. In Kalkulationen werden diese Geräte lediglich zugeordnet;
eine doppelte Gerätepflege ist nicht erforderlich. Ein 3MF-Upload übernimmt
Plattenzahl, Druckzeit und Materialverbrauch, soweit diese Angaben im Archiv
enthalten sind.

Die Freigabe unterscheidet harte Blocker von fachlichen Warnungen. Warnungen
benötigen eine dokumentierte Begründung und werden mit der unveränderlichen
Revision gespeichert. Freigegebene Kalkulationen können nicht überschrieben,
sondern nur als neuer Entwurf fortgeschrieben werden. Vorlagen erzeugen ebenfalls
einen neuen bereinigten Entwurf ohne Kunden- und Quelldateikontext.

Der Kalkulationsarbeitsbereich umfasst außerdem Druckart, Gesamtstückzahl,
optionalen Projektbezug, Positionstitel, Beschreibung und gesonderte
Absprachen. Zusatzmaterialien und Kleinteile können aus dem lokalen
Spulenbestand übernommen oder mit manueller Bezeichnung, Menge und
Einstandspreis kalkuliert werden. Kalkulationsspezifische Abweichungen von den
zentralen Vorgaben werden versioniert gespeichert und lassen sich kontrolliert
zurücksetzen.

Die Live-Vorschau weist Maschine, Arbeit, Material, Strom und Trocknung,
Zusatzmaterial, Verbrauch, Ausschuss, Risiko, Verpackung und Versand mit
Rechenbasis einzeln aus. Eine separate Preisentscheidung zeigt Herstellkosten,
Gewinn, effektive Marge, Stückpreis, Netto und Brutto. Die vorbereiteten
Optionen zum Erzeugen eines Angebotsentwurfs oder Druckauftrags bleiben bis zum
jeweiligen Folgeinkrement sichtbar deaktiviert und lösen keine Datenänderung
aus.

Angebote werden im folgenden Ausbau aus einer freigegebenen Kalkulationsrevision
erzeugt.

Kanonische Dokumente, EN 16931, XRechnung als UBL/CII und ZUGFeRD-XML sind in
der [Dokumentverwaltung](document-management.md) beschrieben. PDF-Layout und
-Vorschau sowie Transport- und Buchhaltungsintegrationen bleiben davon bewusst
getrennte Ausbaustufen.

## Material, Lieferanten und Beschaffung

Unter `Lager > Lieferanten` werden Bezugsquellen zentral gepflegt. Neben Firma,
Kontakt- und Adressdaten koennen Kundennummer, Zahlungsbedingungen,
Standardlieferzeit und interne Notizen hinterlegt werden. Nicht verwendete
Lieferanten koennen geloescht werden. Lieferanten mit Beschaffungsangeboten sind
vor dem Loeschen geschuetzt und koennen stattdessen deaktiviert werden. Die Liste lässt sich
nach Namen suchen, nach Status filtern und seitenweise durchsuchen. Suche,
Status und Seite bleiben beim Teilen der Adresse erhalten.

Material und Filament verwenden dieselben Beschaffungsangebote. Je Artikel ist
eine bevorzugte Bezugsquelle moeglich; weitere Angebote dienen als Alternativen.
Ein Angebot umfasst Lieferanten-Artikelnummer, Bezugslink, Verpackungsmenge,
Mindestbestellmenge, Lieferzeit sowie Netto- und Bruttopreis. Beim Anlegen eines
Angebots wird die Standardlieferzeit des Lieferanten vorbelegt und kann je
Angebot angepasst werden. Hersteller und Lieferant bleiben bei Filament bewusst
getrennte Angaben.

`Lager > Material` ersetzt in der sichtbaren Oberflaeche die bisherige
Bezeichnung Kleinteile. Beim Anlegen kann ein einmaliger Anfangsbestand erfasst
werden. Spaetere Mengenbewegungen erfolgen ausschliesslich ueber die
Bestandsaktionen und bleiben dadurch nachvollziehbar. Mindestbestand, Einheit,
Lagerort, Suchbegriffe, Verbrauchsgrund und interne Notiz werden am Material
gepflegt. Die bisherige freie Lieferantenreferenz bleibt fuer Altdaten lesbar;
neue Beschaffungsdaten werden ueber die zentrale Lieferantenverwaltung erfasst.

In der Filament-Bestandsprognose werden bevorzugtes Angebot und Alternativen
direkt am betroffenen Bestand angezeigt. So koennen Material- und
Filamentbeschaffung dieselbe Lieferantenbasis nutzen, ohne Bestands- und
Stammdaten zu vermischen.
