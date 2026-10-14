# Datenbank-Verbindungspool

PrintOps verwendet ohne Umgebungsüberschreibungen für PostgreSQL `pool_size=20`
und `max_overflow=20`, für SQLite `20 + 200`. Der maximale Bedarf eines
Worker-Prozesses ist die Summe beider Werte. Verbindungen werden nach Bedarf
geöffnet; der Grenzwert ist keine Vorreservierung auf dem Server.

| Umgebungsvariable | Bedeutung | Zulässiger Wert |
| --- | --- | --- |
| `DB_POOL_SIZE` | Dauerhafte Poolgröße | Ganze Zahl größer als 0 |
| `DB_MAX_OVERFLOW` | Zusätzliche Verbindungen bei Last | Ganze Zahl ab 0 |
| `DB_POOL_TIMEOUT` | Wartezeit auf eine Poolverbindung in Sekunden | Ganze Zahl größer als 0 |
| `DB_POOL_RECYCLE` | PostgreSQL-Verbindungsalter vor Erneuerung in Sekunden | Ganze Zahl größer als 0 |

Ohne Überschreibung beträgt der Pool-Timeout 30 Sekunden. PostgreSQL verwendet
`pool_pre_ping` und erneuert Verbindungen nach 1800 Sekunden; SQLite hat
standardmäßig keinen Alterswechsel. Änderungen an Umgebungsvariablen werden
beim nächsten Prozessstart wirksam. Ungültige Werte werden weiterhin von der
Konfigurationsvalidierung abgelehnt.

Beim Anwendungsstart prüft PrintOps nach erfolgreicher Datenbankinitialisierung
den PostgreSQL-Grenzwert mit einer festen, ausschließlich lesenden Abfrage.
`max_connections` wird um `superuser_reserved_connections` und, sofern vorhanden,
`reserved_connections` reduziert. Reserven bleiben auch bei privilegierten
Anwendungskonten ausgespart. Auf älteren Servern ist ein fehlender Parameter
`reserved_connections` kein Fehler. Die PostgreSQL-Dokumentation beschreibt
[diese Reserven](https://www.postgresql.org/docs/17/runtime-config-connection.html)
und die [Abfrage fehlender Parameter](https://www.postgresql.org/docs/17/functions-admin.html).

Übersteigt `pool_size + max_overflow` die verbleibenden Plätze, erscheint eine
Warnung mit den konfigurierten Werten. Zum Beispiel überschreiten `20 + 78`
auf einem Server mit 100 Verbindungen und drei reservierten Plätzen die
verfügbaren 97 Plätze. `20 + 20` passt dort für einen einzelnen Worker.
Reduziere `DB_POOL_SIZE` beziehungsweise `DB_MAX_OVERFLOW` oder prüfe die
Serverkapazität vor einer Änderung von `max_connections`.

Alle Worker, weitere PrintOps-Instanzen und andere Datenbankclients teilen
sich die Serverkapazität. Eine ausbleibende Warnung bestätigt deshalb keine
ausreichende Kapazität der gesamten Installation. Die Diagnose zählt keine
aktiven Clients und prüft keine zusätzlichen Rollen-, Datenbank- oder
Proxy-Limits. Sie verändert weder den Pool noch Servereinstellungen.

Nicht erreichbare, eingeschränkte oder ungültige Antworten führen zu einer
kurzen Warnung ohne Verbindungsdaten, Antwortinhalte oder Ausnahme-Traceback.
Nach fünf Sekunden wird der Abbruch der Diagnose angefordert. Das Aufräumen
der Datenbankverbindung kann den anschließenden Start verzögern; Fehler der
eigentlichen Initialisierung oder Migration bleiben Fehler.
SQLite führt diese Abfrage überhaupt nicht aus. Eine Wiederherstellung, die
`init_db()` aufruft, löst keine zusätzliche Kapazitätsdiagnose aus.
