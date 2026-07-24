# Docker-Laufzeit und minimale Root-Initialisierung

**Datum:** 24. Juli 2026

**Status:** Design freigegeben; schriftliche Spezifikation zur Abnahme

## Ziel

PrintOps behält die bestehende `PUID`/`PGID`-Kompatibilität für Docker-Named-
Volumes, NAS-Systeme und Bind-Mounts. Der Container darf ausschließlich während
einer kurzen, eng begrenzten Initialisierungsphase mit UID 0 laufen. Vor dem
Start der Anwendung werden die Rechte dauerhaft abgegeben; der eigentliche
PrintOps-Prozess läuft immer als Nicht-root-Benutzer.

DS-0002 wird damit nicht durch eine feste Container-UID ersetzt, sondern als
begründete und technisch begrenzte Init-Ausnahme geschlossen. Gerätezugriff und
FFmpeg rechtfertigen keinen Root-Anwendungsprozess.

## Ausgangslage

Der aktuelle Container startet ohne Docker-`USER` als root. Das Entrypoint-Skript
normalisiert Eigentümer von `/app/data` und `/app/logs`, aktualisiert bei Bedarf
den System-Zertifikatsspeicher und wechselt anschließend über `gosu` zu
`PUID:PGID`. Die Anwendung läuft damit bereits grundsätzlich als Nicht-root.

Verbleibende Lücken sind:

- `PUID=0` oder `PGID=0` kann den Schutz aushebeln;
- der Root-Init-Prozess erhält die üblichen, breiten Docker-Standard-Capabilities;
- fehlgeschlagene Eigentümerkorrekturen werden ignoriert;
- der tatsächliche Benutzer und Capability-Satz von PID 1 werden nicht
  automatisiert geprüft;
- die Ausnahme und ihre Grenzen sind nicht als dauerhafte Betriebsentscheidung
  dokumentiert.

## Nicht enthalten

- feste, nicht konfigurierbare UID oder GID;
- ein separater Init-Container;
- privilegierter Containerbetrieb;
- pauschale `--device`-Mounts;
- Mitgliedschaft in `video`, `dialout` oder anderen Host-Gerätegruppen;
- Änderungen an Drucker-, Kamera- oder FFmpeg-Funktionen;
- automatische Rechteänderungen an externen, schreibgeschützten Bibliotheken.

PrintOps kommuniziert mit Druckern und Kameras über Netzwerkprotokolle. FFmpeg
verarbeitet Netzwerkstreams und Dateien im Userspace. Deshalb besteht kein
technischer Bedarf für Host-Gerätezugriff.

## Gewählte Architektur

### Phase 1: begrenzte Initialisierung

Der Container startet für die Dauer des Entrypoints mit UID 0. In dieser Phase
sind ausschließlich folgende Aktionen zulässig:

1. `PUID` und `PGID` lesen und validieren;
2. Eigentümer der konstanten Pfade `/app/data` und `/app/logs` bei Bedarf auf
   `PUID:PGID` setzen;
3. bei ausdrücklich gesetztem `USE_SYSTEM_TRUST_STORE` die bereits gemounteten
   `.crt`-Dateien in den System-Zertifikatsspeicher übernehmen;
4. die Privilegien irreversibel über `gosu` abgeben.

Die IDs müssen reine Dezimalzahlen zwischen 1 und 2147483647 sein. UID oder GID
0, Vorzeichen, Leerzeichen und sonstige Zeichen führen vor jeder
Dateisystemänderung zu einem erklärten Startfehler.

Eigentümerkorrekturen folgen keinen symbolischen Links und verwenden niemals
konfigurierbare Zielpfade. Scheitert eine erforderliche Korrektur, bricht der
Container mit einer verständlichen Fehlermeldung ab. Ein unsicherer oder nicht
schreibbarer Zustand wird nicht an die Anwendung weitergereicht.

Wird der Container vom Betreiber bereits mit `docker run --user` oder Compose
`user:` als Nicht-root gestartet, führt der Entrypoint keine privilegierte
Aktion aus. Der Betreiber bleibt in diesem Modus für passende Volume-Rechte und
einen gegebenenfalls vorab bereitgestellten Zertifikatsspeicher verantwortlich.

### Phase 2: Anwendung

Nach erfolgreicher Initialisierung ersetzt `gosu` den Root-Prozess. Der
Startbefehl verwendet `exec`, sodass Python/Uvicorn PID 1 wird. Für die gesamte
Lebensdauer der Anwendung gelten die validierten `PUID` und `PGID`; es verbleibt
kein Root-Wächter- oder Helper-Prozess.

Die Anwendung kann die privilegierten Ports 322 und 990 weiterhin binden. Dafür
besitzt ausschließlich der Python-Interpreter die File-Capability
`CAP_NET_BIND_SERVICE`. Die Anwendung erhält keine Berechtigung für Geräte,
Netzwerkadministration, Mounts, Prozessüberwachung oder beliebige
Dateisystemumgehung.

## Capability-Modell

Compose entfernt zunächst alle Laufzeit-Capabilities mit `cap_drop: [ALL]` und
fügt für die Init-Phase ausschließlich hinzu:

- `CHOWN` für die Eigentümerkorrektur;
- `DAC_OVERRIDE` zum Bearbeiten restriktiv angelegter Bind-Mounts;
- `SETGID` und `SETUID` für den irreversiblen Benutzerwechsel;
- `NET_BIND_SERVICE` als Bounding-Set für die am Python-Interpreter gesetzte
  File-Capability.

Nach `gosu` und dem `exec` von Python darf der Anwendungsprozess effektiv nur
`NET_BIND_SERVICE` besitzen. Alle übrigen Init-Capabilities müssen abgegeben
sein. `privileged`, `SYS_ADMIN`, `NET_ADMIN`, `NET_RAW`, Geräte-Mounts und der
Docker-Socket bleiben ausgeschlossen.

`no-new-privileges` wird nicht gesetzt, weil es die bewusst benötigte
File-Capability des Python-Interpreters unterbinden würde. Diese Abweichung wird
zusammen mit dem auf eine einzelne Capability begrenzten Ersatz dokumentiert.

## Volume- und Zertifikatsverhalten

- Named Volumes funktionieren ohne manuelle Vorbereitung mit Standardwert
  `1000:1000`.
- Bind-Mounts können durch passende `PUID`/`PGID` auf den Host-Benutzer
  abgestimmt werden.
- Ein Wechsel von `PUID` oder `PGID` löst die erforderliche
  Eigentümernormalisierung erneut aus.
- Externe Bibliotheksmounts außerhalb von `/app/data` und `/app/logs` werden
  niemals verändert.
- Schreibgeschützte Mounts bleiben schreibgeschützt und werden nicht als
  Init-Ziel verwendet.
- `USE_SYSTEM_TRUST_STORE` bleibt opt-in. Im expliziten Nicht-root-Modus wird
  der Start mit einer Handlungsanweisung abgebrochen, statt die Option still zu
  ignorieren.

## Fehlerverhalten und Protokollierung

Das Entrypoint protokolliert knapp:

- validierte Ziel-UID und -GID;
- tatsächlich notwendige Eigentümerkorrekturen;
- Aktivierung oder Deaktivierung des System-Zertifikatsspeichers;
- den Wechsel zum Nicht-root-Anwendungsprozess.

Es protokolliert keine Zertifikatsinhalte, Secrets oder vollständigen
Umgebungsvariablen. Validierungs-, Dateisystem- und Zertifikatsfehler enden mit
einem Exit-Code ungleich null und einer konkreten Korrekturanweisung.

## Dokumentation und Migration

Die Docker-Dokumentation erklärt:

- warum der Container kurz mit UID 0 startet;
- dass die Anwendung selbst nicht als root läuft;
- wie `PUID` und `PGID` gewählt werden;
- welche fünf Capabilities die Init-Phase benötigt;
- warum keine `video`-/`dialout`-Gruppen oder Geräte-Mounts erforderlich sind;
- welche Verantwortung beim expliziten `user:`-Modus beim Betreiber liegt.

Bestehende Standardinstallationen benötigen keine Konfigurationsänderung. Eine
Installation mit `PUID=0` oder `PGID=0` startet nach der Änderung bewusst nicht
mehr und muss auf eine Nicht-root-ID migriert werden.

## Tests

### Entrypoint-Tests

- gültige Standard- und benutzerdefinierte IDs werden akzeptiert;
- UID 0, GID 0, negative, leere und nichtnumerische Werte werden abgelehnt;
- ungültige Werte verursachen keine vorherige Dateisystemänderung;
- Eigentümerkorrekturen bleiben auf die beiden erlaubten Pfade begrenzt und
  folgen keinen Symlinks;
- Fehler bei `chown` werden nicht verschluckt;
- expliziter Nicht-root-Start führt keine Root-Aktion aus;
- `USE_SYSTEM_TRUST_STORE` verhält sich in Root- und Nicht-root-Modus eindeutig.

### Container-Integration

- Docker Compose lässt sich mit dem reduzierten Capability-Satz starten;
- PID 1 besitzt die konfigurierte Nicht-root-UID und -GID;
- PID 1 besitzt effektiv ausschließlich `NET_BIND_SERVICE`;
- Datenbank-, Log- und Upload-Schreibzugriffe funktionieren auf Named Volumes;
- vorbereitete Bind-Mounts funktionieren mit abweichenden `PUID`/`PGID`;
- Healthcheck und normale HTTP-Funktionen bleiben grün;
- die virtuellen Listener können weiterhin die Ports 322 und 990 binden;
- im Prozessbaum verbleibt kein Prozess mit UID 0.

Die bestehenden Backend-, Frontend-, Compose- und Docker-Integrationstests
bleiben unverändert grün.

## Abnahmekriterien

Der Punkt DS-0002 ist abgeschlossen, wenn:

1. `PUID=0`, `PGID=0` und syntaktisch ungültige IDs vor Init-Aktionen scheitern;
2. Compose nur die fünf dokumentierten Init-Capabilities bereitstellt;
3. Python/Uvicorn als Nicht-root-PID 1 läuft;
4. der Anwendungsprozess effektiv nur `NET_BIND_SERVICE` besitzt;
5. Volume- und Zertifikatsfehler sicher und verständlich abbrechen;
6. Named Volumes, Bind-Mounts und benutzerdefinierte Nicht-root-IDs weiterhin
   funktionieren;
7. keine Geräte-, Docker-Socket- oder privilegierten Mounts ergänzt wurden;
8. Port-, Healthcheck- und Docker-Integrationstests erfolgreich sind;
9. die dauerhafte Docker-Dokumentation das Betriebs- und Capability-Modell
   vollständig beschreibt.

## Selbstprüfung der Spezifikation

- **Vollständigkeit:** Init-Phase, Privilege-Drop, Capabilities, Volumes,
  Zertifikate, Migration, Fehlerverhalten und Tests sind definiert.
- **Begriffsschärfe:** Root bezeichnet ausschließlich den kurzlebigen
  Entrypoint; Anwendung bezeichnet den nach `gosu` ausgeführten Python-Prozess.
- **Sicherheit:** Root-IDs, breite Capabilities, stille Rechtefehler und
  unbegründeter Gerätezugriff sind ausgeschlossen.
- **Kompatibilität:** Flexible `PUID`/`PGID`-Werte und bestehende Volume-Arten
  bleiben erhalten.
- **Scope:** Drucker-, Kamera- und FFmpeg-Funktionen werden nicht verändert.
- **Offene Entscheidungen:** Es verbleibt keine Produkt- oder
  Architekturentscheidung, die den Implementierungsplan blockiert.
