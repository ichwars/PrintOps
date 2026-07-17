# Sitzungsübergabe – 16. Juli 2026

## Kurzfassung

Die Arbeiten am Unternehmensprofil und an der Kalkulation wurden bis zu einem veröffentlichungsfähigen Stand geführt. PR #18 wurde nach vollständiger Prüfung gemergt und PrintOps `0.2.5 RC2` als Prerelease einschließlich Windows-Installer und Multi-Arch-Container veröffentlicht.

Der lokale Repository-Stand liegt auf `main`, entspricht `origin/main` und war vor Erstellung dieses Dokuments sauber.

## Repository- und Release-Stand

- Repository: `ichwars/PrintOps`
- Aktueller Branch: `main`
- Aktueller Commit: `a69d6997570a3d06189d50b77cbc31f942e38485`
- Merge-Commit: `a69d6997 Merge pull request #18`
- PR #18: `feat: complete ForgeDesk-parity calculation workflow`
- PR-Status: gemergt am 15. Juli 2026
- Anwendungsversion: `0.2.5rc2`
- Release: [PrintOps 0.2.5 RC2](https://github.com/ichwars/PrintOps/releases/tag/v0.2.5rc2)
- Release-Typ: veröffentlichtes Prerelease, kein Entwurf

### Release-Artefakte

- `printops-0.2.5rc2-windows-x64-setup.exe`
- `printops-windows-x64-setup.exe`
- SHA-256 beider Installer:
  `fab8870410870e3f400f249e94341eb2dfdf5357367b0b485fb3248e3b1bda50`
- GHCR-Tags:
  - `ghcr.io/ichwars/printops:0.2.5rc2`
  - `ghcr.io/ichwars/printops:rc`
- Container-Architekturen: `linux/amd64` und `linux/arm64`

## Unternehmensprofil

Die in der Sitzung besprochenen Schwächen wurden bearbeitet:

- Erklärung und optionaler Charakter des Handelsnamens
- einheitliche Höhen von Textfeldern und Auswahlfeldern
- vertikale Ausrichtung von Checkboxen und Statusanzeige
- verständlichere Steuer-ID-Erfassung und Hinweise
- Sprach- und Regionsauswahl
- bessere Ausnutzung der verfügbaren Tabellenbreite
- Rechnungs- und Lieferanschriften bei Kunden
- Designangleichung der Unternehmensprofilseite an die übrigen Einstellungen
- Logo-Upload als verwaltete Datei
- Logo-Vorschau nach erfolgreichem Upload
- Logo-Miniatur in der Profiltabelle
- vorbereitete QR-Code-Option für Online-Angebote auf PDFs
- internationales Steuermodell statt einer rein deutschen Sonderlösung
- Mehrwertsteuer-/Umsatzsteuerkonfiguration
- Kleinunternehmerregelung
- Vorsteuerabzug
- PayPal-Link bei den Zahlungsdaten

Die binären Logodaten werden nicht als Base64 in Profilantworten gespeichert. Verwendet wird die freigegebene Variante mit verwalteter Datei im PrintOps-Datenverzeichnis und relational gespeicherten Metadaten.

## Kalkulation und Geräteverwaltung

Die Kalkulation wurde funktional und gestalterisch an ForgeDesk angeglichen, ohne die PrintOps-Struktur aufzugeben.

### Einstellungen

- übersichtlicher zweispaltiger Aufbau
- passende Icons und sinnvoll gruppierte Bereiche
- Währung als Auswahlfeld
- Rundungsregeln für die Preisbildung
- Energieanzeige beziehungsweise Energieverfolgungsmodus
- gemeinsame kommerzielle Standardwerte für Vorschau und Freigabe
- robustes Verhalten bei ungültigem `calculation_defaults`-JSON

### Geräte

- Drucker und Trockner werden zentral in der Geräteverwaltung gepflegt
- keine doppelte Geräteerfassung in der Kalkulation
- mehrere Drucker und mehrere Trockner werden unterstützt
- Geräte können in Einstellungen und konkreten Auftragskalkulationen ausgewählt werden
- explizite Auswahl „kein Gerät“ bleibt erhalten und wird nicht durch Standardgeräte überschrieben
- Restwert wird berechnet und nicht manuell eingegeben
- Maschinenstundensatz wird aus Anschaffungswert, Nutzungsdauer, Jahresstunden und Wartungsrate berechnet
- Drucker-API liefert Restwert und berechneten Stundensatz
- Trockner werden als eigenständige Geräte mit eigenen Kosten und Leistungsdaten behandelt

### Kalkulationsablauf

- strukturierte Anfrage- und Variantenbearbeitung
- Materialien und zusätzliche Kosten
- Arbeitszeitpositionen
- Gerätezuweisung pro Vorgang
- Kostenaufschlüsselung und Preisentscheidung
- Vorschau und Freigabe verwenden dieselben kaufmännischen Standardwerte
- Standarddrucker- und Trocknerkosten fließen in die Freigabe ein
- unvollständige Entwürfe können gespeichert werden
- Blocker verhindern erst die Freigabe, nicht das Speichern
- fehlerhafte numerische Provenienz erzeugt einen Validierungsblocker statt eines Serverfehlers
- hochgeladene Quelldateidetails werden beim Erstellen von Vorlagen bereinigt
- Arbeitszeitpositionen werden in Vorlagen übernommen
- Vorlagen übernehmen keine kundenspezifischen oder sensiblen Quelldateidaten
- vorbereitete, noch nicht verfügbare Folgefunktionen werden deaktiviert angezeigt

## Review- und Qualitätskorrekturen

Vor dem Merge wurden zehn offene Reviewpunkte geprüft und behoben:

1. Kosten des Standardgeräts werden bei der Freigabe berücksichtigt.
2. Vorschau und Freigabe nutzen dieselben kommerziellen Standardwerte.
3. Arbeitszeitpositionen werden in Kalkulationsvorlagen kopiert.
4. Druckerantworten enthalten berechnete Gerätekosten.
5. Eine explizite Auswahl ohne Gerät wird nicht überschrieben.
6. Unvollständige Entwürfe können gespeichert werden.
7. Der Energieverfolgungsmodus ist wieder konfigurierbar.
8. Quelldateidetails gelangen nicht unbereinigt in Vorlagen.
9. Ungültiges Standardwerte-JSON bringt den Workspace nicht zum Absturz.
10. Ungültige Dezimalwerte in der Provenienz führen nicht mehr zu HTTP 500.

Zusätzlich wurde ein bestehender Fehler beim Erstellen einer Kalkulationsrevision korrigiert (`labor.kind` statt des nicht vorhandenen `labor.role`).

## Verifikation

Vor dem Merge wurden unter anderem erfolgreich ausgeführt:

- Ruff-Lint
- Ruff-Formatprüfung
- 193 fokussierte Backend-Tests
- 2.477 vollständige Frontend-Tests
- ESLint
- TypeScript-/Produktions-Build
- vier native Backend-Test-Shards auf GitHub
- vier Docker-Backend-Test-Shards
- Frontend-Tests und Frontend-Build
- Docker-Build
- CodeQL für Actions, Python und JavaScript/TypeScript
- Bandit
- Trivy
- Backend- und Frontend-Sicherheitsaudits

Ein zwischenzeitlicher CI-Fehler stammte nicht aus der Kalkulation. `pip-audit` beanstandete `setuptools 79.0.1` wegen `PYSEC-2026-3447`. Beide Audit-Workflows aktualisieren nun vor der Prüfung auf `setuptools>=83.0.0`. Der anschließende vollständige Lauf war grün.

## Lokaler Betriebszustand

Zum Ende dieser Sitzung wurden die üblichen lokalen Entwicklungsports geprüft:

- `5173` – kein Listener
- `5174` – kein Listener
- `8000` – kein Listener
- `8080` – kein Listener

Zusätzlich wurden keine laufenden Vite-, Uvicorn-, PrintOps- oder ForgeDesk-Serverprozesse gefunden. Es musste daher kein Anwendungsserver mehr beendet werden.

## Git-for-Windows-Installer

Der Git-for-Windows-Installer wurde durch zahlreiche verwaiste, nur lesende Git-Prozesse blockiert. Die Prozesse stammten aus Codex-Repository-Abfragen wie:

- `git status --porcelain`
- `git rev-parse HEAD`
- `git remote -v`
- `git config --get core.fsmonitor`

Zwölf bestätigte Codex-Git-Prozesse wurden beendet. Danach lief kein `git.exe` mehr. Falls das Problem während eines zukünftigen Git-Updates erneut auftritt, Codex vor dem Klick auf „Wiederholen“ vollständig schließen.

## Empfohlene nächste Schritte

1. RC2 mit dem veröffentlichten Windows-Installer in einer frischen Installation testen.
2. Kernablauf manuell abnehmen:
   Unternehmensprofil → Geräte → Kunde → Kalkulation → Freigabe.
3. Datenmigration und bestehende Installationen mit realen Unternehmens- und Gerätedaten prüfen.
4. PDF-Ausgabe mit Logo, Steuerangaben, Zahlungsdaten und vorbereitetem QR-Code kontrollieren.
5. Nach erfolgreicher RC-Abnahme das nächste Fachthema festlegen; Angebote, Rechnungen und weitere Auftragsfolgeprozesse bleiben eigenständige Ausbaugebiete.
