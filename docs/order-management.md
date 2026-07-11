# Auftragsverwaltung: Unternehmensprofile und Kunden

Diese Anleitung beschreibt den ersten ausgelieferten Baustein der
Auftragsverwaltung: Unternehmensprofile, Kundenstammdaten, Berechtigungen und
Kundennummern. Kalkulationen, Angebote, Auftraege und kaufmaennische Dokumente
werden in den folgenden Ausbaustufen ergaenzt.

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

Als naechstes folgt die Kalkulation mit Revisionen, Varianten, Slicer-Eingaben
und geplanten Kosten. Die vollstaendige Reihenfolge steht im Abschnitt
[`Delivery Shape`](superpowers/specs/2026-07-10-order-management-design.md#delivery-shape)
des freigegebenen Designs.

PDF-Layouts werden als strukturierte Einstellungen nach Unternehmensprofil,
Dokumentart und Sprache umgesetzt, sobald die kanonischen Dokumente in
Ausbaustufe 4 eingefuehrt werden. EN 16931, UBL/CII, CSV und Lexware Office
folgen in den dort beschriebenen Dokument- und Integrationsinkrementen.
