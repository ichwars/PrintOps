# PrintOps-Dokumentation

Dieser Ordner enthält dauerhaft gepflegte Projekt- und Betriebsdokumentation.
Kurzlebige Session-Übergaben, Agentenpläne, Testprotokolle und nicht referenzierte
Screenshots gehören nicht in das Repository.

## Dokumentationsübersicht

| Thema | Dokument | Inhalt |
| --- | --- | --- |
| Authentifizierung | [Azure Entra ID](authentication/entra-id.md) | Einrichtung der OIDC-Anmeldung mit Microsoft Entra ID |
| Bambu Lab | [Preset Sync API](bambu_lab_preset_sync_api.md) | Referenz der beobachteten Cloud-Endpunkte für Preset-Synchronisation |
| Migration | [Virtual-Printer-FTP-Port](migration-vp-ftp-port.md) | Umstellung des FTP-Ports und erforderliche Migrationsschritte |
| Aufträge | [Auftragsverwaltung](order-management.md) | Unternehmensprofile, Kundenstammdaten, Berechtigungen und Nummernkreise |
| Lager | [Lagerorte](storage-locations.md) | Datenmodell und Verhalten strukturierter Lagerorte |
| Netzwerk | [Proxy-Modus](images/proxy-mode-diagram.png) | Architekturdiagramm des Proxy-Modus |

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
