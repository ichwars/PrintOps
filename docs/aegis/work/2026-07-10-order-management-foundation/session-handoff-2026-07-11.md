# Session-Uebergabe: Auftragsverwaltung

Stand: 2026-07-11

## Repository und Git-Stand

- Workspace: `C:\Users\droth\Documents\GitHub\PrintOps`
- Aktiver Branch: `main`
- Fork/Push-Remote: `origin = https://github.com/ichwars/PrintOps.git`
- Upstream: `maziggy/bambuddy`, Push-URL weiterhin `DISABLED`
- Pull Request: `ichwars/PrintOps#6`, Status `MERGED`
- Merge-Commit auf lokalem und Fork-`main`: `935fad0c9f15d96ad9ecf0880178223bfdf05e9a`
- Feature-Commit der letzten Korrekturwelle: `339fc511`
- Der Remote-Feature-Branch `codex/order-management` wurde nach dem Merge geloescht.

## Erledigter Funktionsumfang

Die freigegebene erste Ausbaustufe der Auftragsverwaltung ist in den Fork-`main`
integriert. Sie umfasst:

- relationale Unternehmensprofile mit Adressen, Steuerkennungen, Bankkonten,
  Sprache, Zeitzone, Waehrung und internem/externem/hybridem Abrechnungsmodus;
- Kundenstammdaten mit Profilkonten, Kontakten, Adressen, Steuerkennungen,
  Schlagwoertern, Zahlungsbedingungen und profilbezogenen Kundennummern;
- transaktionale, pro Unternehmensprofil gefuehrte Nummernsequenzen;
- neue Berechtigungen, sichere Standardrollen und weiterhin fail-closed
  behandelte API-Keys;
- Backend-APIs sowie die Oberflaechen fuer Unternehmensprofile und Kunden;
- Navigation und Einstellungen unter der neuen Auftragsverwaltung;
- internationale Stammdaten mit 249 Laendern und 178 Waehrungen;
- eine fuer Backend und Frontend gepinnte Unicode-15.1-Normalisierung;
- lokalisierte Konflikt-, Validierungs- und `not_found`-Meldungen in allen elf
  vorhandenen Sprachdateien;
- robuste Dialog-Fokussteuerung, aktive Profilauswahl und vollstaendige
  verschachtelte Profil-Payloads.

Die vorherigen Hauptmenues wurden bereits fachlich umbenannt und mit passenden
Untermenues versehen:

- `Drucker & Produktion` -> `Geraeteverwaltung`
- `Projekte & Dateien` -> `Projektverwaltung`
- `Lager & Material` -> `Lagerverwaltung`
- `Auftraege & Kalkulation` -> `Auftragsverwaltung`

## Wichtige Architekturentscheidungen

- Unter SQLite serialisieren Kundenwrites und Profil-Lebenszyklusaenderungen
  ueber die Kundennummern-Sequenzzeile. Der Schreib-Lock wird vor dem ersten
  Lesen erworben, um `SQLITE_BUSY_SNAPSHOT` unter WAL zu vermeiden.
- Ein globales SQLite-Fremdschluessel-PRAGMA wurde verworfen, da es bestehende
  Migrationen und Initialisierungspfade ausserhalb dieses Inkrements veraendert.
- Python 3.13 verwendet seine Unicode-15.1-Standardbibliothek. Python 3.10 bis
  3.12 verwenden `unicodedata2==15.1.0`.
- Unbekannte Datenbank-Integritaetsfehler werden nicht als vermeintliche
  Duplikate maskiert, sondern nach Rollback erneut ausgeliefert.
- Die automatische Kundennummernsuche normalisiert vorhandene sichtbare Werte
  einmal in ein Set und bleibt damit im Kollisionsfall linear.

## Verifikation

- Backend: 117 fokussierte Tests bestanden.
- Frontend: 85 fokussierte Tests bestanden.
- Ruff, ESLint, i18n-Paritaet, TypeScript und Produktionsbuild bestanden.
- Alle elf Locale-Dateien enthalten 5.829 Blaetter.
- Generator-Check: 249 Laender, 178 Waehrungen, 1.530 Casefold-Mappings.
- Unicode-Paritaet: 1.114.112 Codepunkte verglichen, 0 Abweichungen.
- Unabhaengige Backend- und Frontend-Re-Reviews: `APPROVED`, keine verbleibenden
  Critical- oder Important-Befunde.
- GitHub-Pruefungen fuer PR #6: CodeQL, Trivy, Bandit und Security-Audits gruen.
- `git diff --check` und der Arbeitsbaum waren vor dem Merge sauber.

## Offene Grenzen und naechste Ausbaustufen

Die integrierte Arbeit ist bewusst nur das Foundation-Inkrement. Noch nicht
implementiert sind:

1. Kalkulationen mit Revisionen, Varianten, Slicer-Eingaben und geplanten
   Kosten;
2. Angebote, Auftraege, Lieferungen, Rechnungen und Zahlungen;
3. systemabhaengige interne/externe Dokumentausgabe im operativen Ablauf;
4. PDF-Layout-Einstellungen nach Unternehmensprofil, Dokumentart und Sprache;
5. standardisierte Exporte nach EN 16931 sowie UBL/CII;
6. CSV- und Lexware-Office-Exporte beziehungsweise Integrationen.

Die PDF-Layouts bleiben an das spaetere kanonische Dokument-Inkrement gekoppelt,
damit keine temporaeren Dokumentvertraege entstehen. Die freigegebene fachliche
Reihenfolge steht in:

- `docs/superpowers/specs/2026-07-10-order-management-design.md`
- `docs/superpowers/plans/2026-07-10-order-management-foundation.md`
- `docs/order-management.md`

## Bekannte Rest-Risiken

- Der lokale Docker-Client war vorhanden, aber die Docker-Engine lief nicht.
  Deshalb wurde lokal kein Python-3.13-Image gebaut. Provider-Tests,
  Requirements-Marker, GitHub-Sicherheitspruefungen und der gemeinsame
  Generator-/Backend-Owner decken die Entscheidung begrenzt ab.
- Vitest meldet bestehende React-`act(...)`-Warnungen; die betroffenen Tests
  bestehen. Diese Warnungen waren kein Blocker dieses Inkrements.
- Vite meldet weiterhin den bestehenden Hinweis auf grosse Bundles.

## Lokaler Server

- Der zuvor laufende Server war der Vite-Frontend-Server auf
  `http://127.0.0.1:5173`.
- Alte Listener-PID: `13752`.
- Neustartkommando:

  ```powershell
  npm.cmd run dev -- --host 127.0.0.1 --port 5173
  ```

- Neue Listener-PID nach dem Neustart: `36940`.
- HTTP-Pruefung nach dem Neustart: `200 OK`.
- Auf Port `8000` lief kein Backend-Prozess; dort wurde daher nichts beendet
  oder neu gestartet.

## Wiederaufnahme

1. Mit `git status --short --branch` bestaetigen, dass `main` sauber und mit
   `origin/main` synchron ist.
2. Die naechste Ausbaustufe aus dem freigegebenen Design abgrenzen. Fachlich
   folgt die Kalkulation vor kanonischen Dokumenten und Exporten.
3. Vor weiteren Remote-Schreibvorgaengen erneut pruefen, dass ausschliesslich
   `origin` auf `ichwars/PrintOps` zeigt und Upstream-Push deaktiviert bleibt.
4. Kein automatischer Standby: Der Benutzer hat den Standby am Ende dieser
   Session ausdruecklich ausgesetzt.
