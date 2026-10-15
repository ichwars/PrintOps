# PrintOps-Dokumentation

Dieser Ordner enthält dauerhaft gepflegte Projekt- und Betriebsdokumentation.
Kurzlebige Session-Übergaben, Agentenpläne, Testprotokolle und nicht referenzierte
Screenshots gehören nicht in das Repository.

## Dokumentationsübersicht

| Thema | Dokument | Inhalt |
| --- | --- | --- |
| Integration | [App-Nachrichten](app-notifications.md) | Eigene API-Schlüssel, freigegebene Kanäle, Druckerbereiche und Zustellgrenzen |
| Authentifizierung | [Azure Entra ID](authentication/entra-id.md) | Einrichtung der OIDC-Anmeldung mit Microsoft Entra ID |
| Bambu Lab | [Preset Sync API](bambu_lab_preset_sync_api.md) | Referenz der beobachteten Cloud-Endpunkte für Preset-Synchronisation |
| Betrieb | [Docker-Laufzeitsicherheit](docker-runtime-security.md) | Root-Init, PUID/PGID, Capabilities und Volume-Rechte |
| Betrieb | [Virtual Printer mit Docker / NAT](virtual-printer-docker-networking.md) | Gemeinsame IPv4-Zieladresse für Discovery und FTPS, Port-Mappings und Beispiele |
| Migration | [Virtual-Printer-FTP-Port](migration-vp-ftp-port.md) | Umstellung des FTP-Ports und erforderliche Migrationsschritte |
| Aufträge | [Auftragsverwaltung](order-management.md) | Unternehmensprofile, Kundenstammdaten, Berechtigungen und Nummernkreise |
| Aufträge und Lager | [Lexware Office und Warenlager](lexware-integration.md) | Lesende Anbindung, geprüfte Stammdatenübernahme, Belege, Finanzen und Warenbestände |
| Lager | [Lagerorte](storage-locations.md) | Datenmodell und Verhalten strukturierter Lagerorte |
| NFC und Filament | [Mobiler NFC-Ablauf für Fremdspulen](mobile-nfc-spool-workflow.md) | Produktvorschlag für Scan-Link, Smartphone-Tag und AMS-Zuweisung |
| Netzwerk | [Proxy-Modus](images/proxy-mode-diagram.png) | Architekturdiagramm des Proxy-Modus |
| Sicherheit | [Alert-Triage 2026-07-23](security-alert-triage-2026-07-23.md) | Befund und Disposition der bereinigten GitHub-Sicherheitswarnungen |
| Upstream | [Gesamtabgleich 2026-10-11](upstream-comparison-2026-10-11.md) | Historische Funktions- und Korrekturmatrix mit fünf Kategorien, Prioritäten und vollständiger Commit-Liste |
| Upstream | [Umsetzung 2026-10-11](upstream-implementation-2026-10-11.md) | Umsetzung der 36 wichtigen und fehlenden Punkte auf eigenem main, erhaltene PrintOps-Funktionen und Prüfergebnisse |
| Bedienung | [Neue Druck-, Lager- und Dateifunktionen](upstream-features-guide.md) | Qualitätsbestätigung, Materialnummern, Warnungen, Etiketten, Dateivorschauen und Druckeralarme bedienen |
| Upstream | [Queue- und Projektfunktionen 2026-08-27](upstream-queue-project-evaluation-2026-08-27.md) | Bewertung, Abgrenzung und Folgeissues für optionale Bambuddy-Funktionen |
| Upstream | [Slicer-Funktionen 2026-08-27](upstream-slicer-evaluation-2026-08-27.md) | Nutzen-, Plattform- und Wartungsbewertung optionaler Bambuddy-Slicer-Funktionen |
| Upstream | [H2C- und Home-Assistant-Funktionen 2026-08-27](upstream-h2c-home-assistant-evaluation-2026-08-27.md) | Gerätebestand, Sensorzustände, Interlock-Fallbacks und Folgeissues |
| Betrieb | [H2C-Nozzle-Mapping-Audit](h2c-nozzle-mapping-dispatch-audit.md) | Software-Sicherheitsgrenze und Hardware-Freigabenachweis für physische H2C-Düsen-IDs |
| Drucker | [Geräteabnahme und Telemetrie-Nachweise](hardware-acceptance.md) | Issue-Kriterien, Firmware-Vergleiche, lesende Erhebung und anonymisierte Hardware-Nachweise |
| Entwicklung | [Eingebettete Sidebar-Apps](sidebar-apps.md) | Theme-Nachrichten, Navigation, Origins und Sitzungsgrenzen |
| Entwicklung | [Modellanbieter](model-providers.md) | MakerWorld-Import, Anbieter-Vertrag, Berechtigungen und HTTP-Lebenszyklus |
| Entwicklung | [README Editorial Guide](readme-editorial-guide.md) | Zielgruppen, Positionierung und Regeln für die zentrale Projekt-README |
| Entwicklung | [Dateien und Auslieferungsbuild](repository-layout.md) | Repository-Hygiene, lokale Artefakte und das benötigte native Frontend-Bundle |
| Release | [Version 1.2.8.0](releases/1.2.8.0.md) | Neuerungen seit 1.2.7.9, Upgrade-Hinweise, Grenzen und Veröffentlichungsschritte |
| Browser | [Browser-Kompatibilität](browser-compatibility.md) | Safari-16-Syntaxbaseline, README-Markdown und Grenzen der PDF-Vorschau |
| Bedienung | [Touch und Tastatur](touch-and-keyboard-controls.md) | Sichtbare Karten-/Zeilenaktionen, Ordnermenüs und Fokusnavigation |
| Drucker | [Tägliche AMS-Trocknung](scheduled-ams-drying.md) | Fähigkeiten, Zeitzonen, Reservierungen und unbestätigte Starts |

Die allgemeine Projektübersicht, Installation und erste Schritte stehen in der
[README im Projektstamm](../README.md).

## Regeln für neue Dokumentation

- Nur Inhalte aufnehmen, die nach Abschluss einer Arbeit weiterhin als Referenz
  dienen.
- Dateinamen in `kebab-case` wählen und neue Dokumente in dieser Übersicht
  verlinken.
- Repository-relative Links verwenden; absolute lokale Dateipfade sind nicht
  zulässig.
- Dauerhafte Abbildungen unter `docs/images/` ablegen und aus mindestens einem
  Dokument referenzieren.
- Session-Übergaben, Agentenpläne, Design-QA-Belege, temporäre Testpläne und
  Werkzeugprotokolle lokal halten.
- Bei Änderungen prüfen, ob Aussagen, Versionsstände und Screenshots weiterhin
  zum aktuellen Verhalten passen.

## Geplanter Ausbau

Diese Übersicht ist der bereinigte Ausgangspunkt. Weitere Bereiche wie
Installation, Konfiguration, Rollen und Berechtigungen, Lager- und
Beschaffungsabläufe, Fehlerbehebung sowie Entwicklerhinweise werden schrittweise
ergänzt und hier zentral erschlossen.
