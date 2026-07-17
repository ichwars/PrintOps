# Geräteverwaltung: zweispaltige Oberfläche

## Ziel

Die Geräte-Seite unter `Einstellungen → Geräteverwaltung → Geräte` soll den verfügbaren Platz besser nutzen und Drucker sowie Trockner als klar unterscheidbare, konsistente Gerätebereiche darstellen. Der bestehende Bereich „Virtuelle Drucker“ bleibt unverändert und weiterhin über die volle Inhaltsbreite.

## Umfang

Die Überarbeitung betrifft ausschließlich den Bereich oberhalb von „Virtuelle Drucker“:

- FTP-Wiederholung
- Standarddrucker
- Drucker
- Trockner
- Kamera

Der Aufbau, die Komponenten und die Breite des Bereichs „Virtuelle Drucker“ werden nicht verändert.

## Seitenlayout

### Große Desktop-Ansicht

Oberhalb von „Virtuelle Drucker“ werden zwei unabhängige Spalten verwendet:

- Linke Spalte:
  1. FTP-Wiederholung
  2. Drucker
- Rechte Spalte:
  1. Standarddrucker
  2. Trockner
  3. Kamera

Die Spalten stapeln ihre Karten unabhängig voneinander. Karten müssen deshalb nicht dieselbe Zeilenhöhe einnehmen; unnötiger Leerraum durch unterschiedlich hohe Inhalte wird vermieden.

### Kleine Desktop-, Tablet- und Mobilansicht

Unterhalb der großen Desktop-Breite werden alle Bereiche einspaltig gestapelt. Die Reihenfolge lautet:

1. FTP-Wiederholung
2. Standarddrucker
3. Drucker
4. Trockner
5. Kamera
6. Virtuelle Drucker

Eingabefelder und Aktionsleisten dürfen nicht horizontal überlaufen. Aktionsschaltflächen dürfen auf schmalen Ansichten umbrechen oder die verfügbare Breite einnehmen.

## Drucker und Trockner

Die bisher gemeinsame, verschachtelte Gerätekarte wird in zwei eigenständige Hauptkarten aufgeteilt:

- „Drucker“
- „Trockner“

Beide Bereiche verwenden dieselbe strukturelle Sprache:

- Kopfzeile mit Icon, Titel, Kurzbeschreibung und Hinzufügen-Aktion
- optionales Formular zum Anlegen oder Bearbeiten
- Geräteübersicht mit klarer Kopfzeile
- hervorgehobene kaufmännische Kennzahlen
- einheitliche Feldhöhen, Abstände, Beschriftungen und Fokuszustände

### Drucker

Der Druckerbereich verwendet PrintOps-Grün für Icon, primäre Aktionen, Fokus und aktive Zustände. Vorhandene Drucker werden als kompakte Gerätepanels dargestellt. Name und Modell stehen links, Restwert und Stundensatz rechts beziehungsweise auf schmalen Ansichten darunter.

Die sechs Kostenfelder bleiben funktional unverändert:

- Anschaffungsdatum
- Anschaffungswert
- Nutzungsdauer
- Betriebsstunden pro Jahr
- Wartungsrate
- Leistung

### Trockner

Der Trocknerbereich verwendet ein zurückhaltendes Blau/Cyan als Bereichsakzent. Der Akzent unterscheidet die Geräteart, ohne neue globale Markenfarben einzuführen. Primäre Speichern- und Hinzufügen-Aktionen bleiben PrintOps-Grün; Blau/Cyan wird für Icon, leichte Flächen- oder Rahmenbetonung und ausgewählte Trocknerdetails eingesetzt.

Trocknerkarten zeigen:

- Name
- Aktivstatus
- Restwert
- Stundensatz
- Leistung
- Anschaffungswert
- Bearbeiten
- Aktivieren oder Deaktivieren
- Löschen

Das Trocknerformular bleibt funktional unverändert, wird aber an dieselbe Feld- und Aktionsgestaltung wie der Druckerbereich angeglichen.

## Farb- und Zustandsregeln

- Primäre Aktionen: PrintOps-Grün
- Drucker-Akzent: PrintOps-Grün
- Trockner-Akzent: dezentes Blau/Cyan
- Neutrale beziehungsweise inaktive Zustände: Grau
- Löschen und destruktive Aktionen: Rot
- Warnungen und notwendige Einrichtung: Gelb
- Orange wird in Drucker- und Trockneraktionen nicht mehr verwendet.

Die dunklen bestehenden Hintergründe, Rahmenfarben, Rundungen und Typografie bleiben Teil des vorhandenen PrintOps-Designsystems. Es wird kein neuer visueller Stil eingeführt.

## Interaktionen

Vorhandene Funktionen bleiben erhalten:

- Drucker hinzufügen und speichern
- Druckerkosten bearbeiten und speichern
- Trockner hinzufügen
- Trockner bearbeiten
- Trockner aktivieren oder deaktivieren
- Trockner löschen
- Standarddrucker auswählen
- FTP-Wiederholung konfigurieren
- Kameraeinstellungen konfigurieren

Formulare öffnen weiterhin innerhalb ihres jeweiligen Bereichs. Es werden keine neuen Dialoge oder Abläufe eingeführt.

## Komponenten und Verantwortlichkeiten

- `SettingsPage` verantwortet das neue zweispaltige Seitenraster und ordnet die bestehenden Karten den beiden Spalten zu.
- `DeviceManagement` verantwortet weiterhin Datenabfragen und Mutationen für Drucker und Trockner, rendert diese aber als zwei eigenständige Karten.
- Wiederkehrende Feld-, Button-, Kopfzeilen- und Gerätepanel-Stile werden innerhalb der Geräteverwaltung gemeinsam definiert, statt für Drucker und Trockner getrennt kopiert zu werden.
- `VirtualPrinterList` bleibt unverändert.

## Fehler- und Ladeverhalten

Die vorhandenen React-Query-Zustände und Mutationen bleiben bestehen. Buttons bleiben während laufender Mutationen deaktiviert. Die Überarbeitung führt keine neue Fehlerbehandlung und keine Änderung an API-Verträgen ein.

## Verifikation

Die Umsetzung wird mindestens wie folgt geprüft:

- Frontend-TypeScript-Build
- relevante Komponenten- und Settings-Tests
- Browserprüfung der Geräte-Seite in großer Desktop-Ansicht
- Browserprüfung in einer mobilen Ansicht
- kein horizontaler Überlauf
- keine Überlagerungen oder abgeschnittenen Inhalte
- Drucker- und Trocknerformulare öffnen und schließen korrekt
- sichere, nicht-destruktive Interaktion mit mindestens einem sichtbaren Steuerelement
- „Virtuelle Drucker“ bleibt in Aufbau und voller Breite unverändert
- Browserkonsole ohne neue relevante Fehler

## Nicht-Ziele

- Keine Änderung an APIs, Datenmodellen oder Kostenberechnungen
- Keine funktionale Überarbeitung der Kamera- oder FTP-Einstellungen
- Keine Änderung an „Virtuelle Drucker“
- Keine neue globale Farbpalette
- Keine Neugestaltung der Seitenleiste oder der übrigen Einstellungsseiten
