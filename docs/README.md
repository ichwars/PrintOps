# PrintOps-Dokumentation

Dieser Ordner enthält dauerhaft gepflegte Projekt- und Betriebsdokumentation.
Kurzlebige Session-Übergaben, Agentenpläne, Testprotokolle und nicht referenzierte
Screenshots gehören nicht in das Repository.

## Dokumentationsübersicht

| Thema | Dokument | Inhalt |
| --- | --- | --- |
| Authentifizierung | [Azure Entra ID](authentication/entra-id.md) | Einrichtung der OIDC-Anmeldung mit Microsoft Entra ID |
| Bambu Lab | [Preset Sync API](bambu_lab_preset_sync_api.md) | Referenz der beobachteten Cloud-Endpunkte für Preset-Synchronisation |
| Betrieb | [Docker-Laufzeitsicherheit](docker-runtime-security.md) | Root-Init, PUID/PGID, Capabilities und Volume-Rechte |
| Migration | [Virtual-Printer-FTP-Port](migration-vp-ftp-port.md) | Umstellung des FTP-Ports und erforderliche Migrationsschritte |
| Aufträge | [Auftragsverwaltung](order-management.md) | Unternehmensprofile, Kundenstammdaten, Berechtigungen und Nummernkreise |
| Lager | [Lagerorte](storage-locations.md) | Datenmodell und Verhalten strukturierter Lagerorte |
| NFC und Filament | [Mobiler NFC-Ablauf für Fremdspulen](mobile-nfc-spool-workflow.md) | Produktvorschlag für Scan-Link, Smartphone-Tag und AMS-Zuweisung |
| Netzwerk | [Proxy-Modus](images/proxy-mode-diagram.png) | Architekturdiagramm des Proxy-Modus |
| Sicherheit | [Alert-Triage 2026-07-23](security-alert-triage-2026-07-23.md) | Befund und Disposition der bereinigten GitHub-Sicherheitswarnungen |
| Upstream | [Queue- und Projektfunktionen 2026-08-27](upstream-queue-project-evaluation-2026-08-27.md) | Bewertung, Abgrenzung und Folgeissues für optionale Bambuddy-Funktionen |
| Entwicklung | [README Editorial Guide](readme-editorial-guide.md) | Zielgruppen, Positionierung und Regeln für die zentrale Projekt-README |

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
