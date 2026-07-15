# Kalkulation: ForgeDesk-Parität und Abschluss

## Ziel

PrintOps schließt die noch vorhandenen fachlichen Lücken gegenüber ForgeDesk,
ohne sein stärkeres Modell aus Varianten, Revisionen, zentral verwalteten
Geräten und abgesicherten Freigaben zurückzubauen. Der Arbeitsbereich soll eine
Kalkulation vollständig erfassen, transparent erklären und als belastbaren
Entwurf beziehungsweise unveränderliche Revision speichern können.

## Arbeitsbereich

Der Anfragekopf bündelt Unternehmensprofil, Kunde, optionales Projekt,
Druckart, Gesamtstückzahl, Positionstitel, Positionsbeschreibung, interne
Notizen und gesonderte Absprachen. Varianten bleiben die zentrale Einheit für
alternative Produktions- und Preisentscheidungen.

Fertigungsschritte behalten Drucker, Trockner, Projektplatte, 3MF-Datei,
Gutteile, Teile je Lauf, Ausschussläufe, Materialmenge, Druckzeit und Arbeit.
Ein 3MF-Import übernimmt vorhandene Metadaten. Ein zusätzlicher Slicer-Lauf wird
nur angeboten, wenn bereits eine PrintOps-Slicer-Integration konfiguriert ist.

Material wird bevorzugt aus dem PrintOps-Lager gewählt. Für externe oder noch
nicht angelegte Materialien bleiben eine manuelle Bezeichnung und ein manueller
Kilopreis möglich. Kleinteile und Zusatzmaterialien werden als eigene
kalkulierbare Positionen mit Menge, Einheit und Einstandspreis geführt.

## Kosten und Preis

Zentrale Einstellungen liefern Standardwerte für Arbeit, Ausschuss,
Materialaufschlag, Verbrauch, Verpackung, Versand, Mindestpreis, Mindestgewinn,
Steuer und Rundung. Ein Entwurf darf diese Werte explizit überschreiben; die
Quelle jedes wirksamen Wertes bleibt in der Provenienz nachvollziehbar.

Die Kostenaufschlüsselung zeigt für Maschine, Arbeit, Material, Strom,
Trocknung, Kleinteile, Verbrauch, Ausschuss, Verpackung und Versand jeweils den
Rechenweg und Betrag. Die Preisentscheidung zeigt Herstellkosten, Gewinn,
effektive Marge, Netto-, Brutto- und Stückpreis. Vorschau und Freigabe verwenden
denselben Decimal-Kostenkern.

## Bedienung

Ein Zurücksetzen-Befehl setzt einen noch nicht gespeicherten oder bearbeitbaren
Entwurf nach Bestätigung auf die aktuellen Standardwerte zurück. Validierung,
Warnungsbegründungen, Vorlagen, Archivierung und Folgeversionen bleiben
unverändert erhalten.

Die Optionen `Angebotsentwurf erstellen` und `Als Druckauftrag übernehmen`
werden im Abschlussblock sichtbar, aber deaktiviert dargestellt. Ein Hinweis
erklärt, dass diese Aktionen mit den späteren Angebots- und Auftragsworkflows
aktiviert werden. Sie lösen noch keine Datenänderung aus.

## Datenmodell und Schnittstellen

Neue kalkulationsspezifische Werte werden versioniert in der Kalkulation und in
Freigabesnapshots gespeichert. Lager- und Projektverweise sind optional und
verwenden bestehende PrintOps-Entitäten. Manuelle Fallbackwerte bleiben auch
nach dem Löschen oder Deaktivieren eines referenzierten Stammdatensatzes im
Snapshot erhalten. API-Validierung verhindert negative Mengen und Preise sowie
inkonsistente Stückzahlen.

## Fehlerbehandlung

Fehlende Pflichtdaten bleiben harte Blocker. Fehlende Stammdaten oder manuelle
Fallbackwerte sind fachliche Warnungen und benötigen bei Freigabe eine
Begründung. Ein fehlgeschlagener 3MF-/Slicer-Import verändert den bestehenden
Entwurf nicht.

## Verifikation

- Unit-Tests für Zuschläge, Ausschuss, Kleinteile und Stückpreis.
- API-Tests für neue Felder, Snapshots und Validierung.
- Frontend-Tests für Standardübernahme, Overrides, Zurücksetzen,
  Kostenaufschlüsselung und deaktivierte Folgeaktionen.
- Browser-Smoke-Test für Einstellungen, Neuanlage, Vorschau und Speicherung.
- Ruff, Backend-Regressionssuite, ESLint, TypeScript, Vitest-Coverage und Build.

## Nicht Bestandteil

Die tatsächliche Erzeugung von Angeboten oder Druckaufträgen, neue
Slicer-Infrastruktur sowie Änderungen an Rechnungen und PDF-Dokumenten gehören
nicht zu diesem Abschlussinkrement.
