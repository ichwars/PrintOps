# Optionale Upstream-Erweiterungen: Umsetzungsstand 14. Oktober 2026

Dieser Bericht erfasst die 17 ausgewählten Punkte mit ihren dokumentierten
Liefer- und Prüfständen. Die 16 früheren Punkte sind mit tatsächlichem Review-
und Merge-Commit verzeichnet; O18 wird durch [PR #233](https://github.com/ichwars/PrintOps/pull/233)
geliefert. Abschließende Reviews, Checks und Merge sind in den verlinkten PRs
nachvollziehbar. Die datierten lokalen und historischen Nachweise unten ersetzen
keinen späteren Prüfstand und keine Hardware- oder Produktionsfreigabe.

Die App-Anhänge aller 17 Punkte wurden nachgereicht. Ältere Einschränkungen zur
Anhangsverfügbarkeit in den einzelnen Liefernachweisen beschreiben den damaligen
Stand.

Die Begleitrepositories waren nicht verfügbar (404), das GitHub-Wiki war
deaktiviert. Deshalb liegt die Bedienungsdokumentation in diesem Repository.
Fremde lokale Änderungen und vorhandene Stashes wurden nicht verändert.

## Lieferungen und tatsächliche Prüfgrenzen

Für jeden abgeschlossenen Punkt nennt das Register den tatsächlich geprüften
Commit und Merge. Erfolgreiche CI-Jobs werden nur für diesen Stand behauptet;
Wiederholungen, ausgelassene oder unvollständige lokale Prüfungen bleiben sichtbar.

### O02 — [PR #201](https://github.com/ichwars/PrintOps/pull/201)

Status: gemergt.
Geprüfter Stand: `6dbb81a5b5a75fb8c1e0688fe1f6f8aa6d954a6a`.
Merge: `f1a6c9902f8e45c131a52842c64f4ca37c50a2e1` (2026-10-13T09:43:38Z).

No live physical printer or Orca Cloud account; unknown PEEK profile without verified material/ID is rejected.

### O05 — [PR #203](https://github.com/ichwars/PrintOps/pull/203)

Status: gemergt.
Geprüfter Stand: `b371f5de1bd8765d721400565fba0194dbb4b0e8`.
Merge: `829beff12e1b90614a75bd7d88345c7a056d5f2b` (2026-10-13T15:04:43Z).

No physical client/third-party IdP exercise; earlier local broad backend run was aborted after pre-fix stall, final exact-head GitHub CI all 31 green including live PostgreSQL race.

### O06 — [PR #205](https://github.com/ichwars/PrintOps/pull/205)

Status: gemergt.
Geprüfter Stand: `a6fe363b17ad1442fe49e13706326b922384cb30`.
Merge: `a4a360f21e391cc3439d16b20c8ce888b2adb314` (2026-10-13T17:35:15Z).

All 31 exact-head GitHub checks passed and all four review threads resolved. No physical printer/camera or live local PostgreSQL concurrency; production browser QA used software fixtures. Pre-fix broad local backend run was interrupted after 8089 passed/187 skipped, one preheat timeout and five missing-native-Pango errors; named cases later passed isolated. MJPEG recovery has 3/6/12-second bounded error retries and a conservative 60-second connection lease that also renews healthy streams.

### O07 — [PR #207](https://github.com/ichwars/PrintOps/pull/207)

Status: gemergt.
Geprüfter Stand: `58e787f3088006153e7dd77fac647f3b43a97fa9`.
Merge: `ba7691f034cc5b6160b8130f0f67601fcfb755a6` (2026-10-13T20:43:47Z).

All31 exact-head GitHub checks completed SUCCESS after one justified failed-job rerun on unchanged reviewed head; Docker Build actually ran and passed, all four threads resolved/CLEAN. User selected manual-cycle protection, accepting lost new-cycle auto-stop/PAUSE preemption and conditional IDLE launch without prior stop. Final local RED12+4controls, GREEN202 focused/1173 covering backend; original full frontend3497, final copy locale9250/build/Safari272/rendered EN/DE desktop/mobile4. The complete local backend suite was not rerun after final fix; no physical printer/live drying command, and unobserved between-poll transitions/pending-window physical acceptance remain unverified. First CI attempt had one unchanged 50ms concurrency timing assertion (peak3/4); target rerun passed and dependent Docker Build passed.

### O09 — [PR #209](https://github.com/ichwars/PrintOps/pull/209)

Status: gemergt.
Geprüfter Stand: `70f989a83f7e86bb67f0890733ae79e699e01b99`.
Merge: `a275f941d9968dca3dfb75bfd7a74fe19e11621b` (2026-10-13T22:17:09Z).

All31 exact-head GitHub checks completed SUCCESS after one justified shard1-only identical-head rerun: first Docker shard1 attempt hit25min timeout at97% without assertion, second passed; Docker Build passed in first attempt. Both external P2 first-old-update/older-branch findings independently fixed/reviewed and two threads resolved, CLEAN/normal merge. Local RED10/GREEN43 local+real no-network Docker/94 expanded local; complete local backend run interrupted at9% without result. No live macOS signing/TCC/launchd/printer validation; historical updaters predating existing PDF staging hook not tested.

### O10 — [PR #211](https://github.com/ichwars/PrintOps/pull/211)

Status: gemergt.
Geprüfter Stand: `0fad48b7302247c542c030e4cfb1375fce969ea6`.
Merge: `3993e163ffd08954a817cd05beb01b0b97bb9de7` (2026-10-13T23:52:44Z).

MERGED after first Docker Backend shard1 cancelled at configured 25-minute limit after 97%/no assertion, then one same-head targeted rerun succeeded; all 31 final checks COMPLETED/SUCCESS and zero review threads/CLEAN. Local full frontend 3497 tests, effective app/node TS checks, Vite build, desktop/mobile browser; actual backend-test Docker runner RED8/GREEN8; Windows full-checkout 4 pass. No measured 2 GB/RSS, no actual Windows executable or multiarchitecture release image built locally. Native install/update is Vite-only by recorded ruling; CI/Docker/Windows release explicitly typecheck. Prior fontless browser failure was environment-only and passed with font config.

### O11 — [PR #213](https://github.com/ichwars/PrintOps/pull/213)

Status: gemergt.
Geprüfter Stand: `e1c4eddc595215401a3ec75dbdffbb8555b01e2a`.
Merge: `9ad27263b6ab3f8a6512171326bd09f7d7151951` (2026-10-14T00:54:20Z).

MERGED after initial Important retained-global-token bypass was closed by narrow MakerWorld-only fix: actual HTTP RED6/GREEN9, affected181 pass, both independent scoped re-reviews approved exact e1c4 with no remaining findings. All31 exact-head GitHub checks COMPLETED/SUCCESS on first run, zero paginated threads, CLEAN and normal merge. No live MakerWorld/Bambu traffic, second provider operation, or 3MF rendering/extraction fidelity exercise; full repository backend suite verified by remote CI rather than rerun locally.

### O12 — [PR #215](https://github.com/ichwars/PrintOps/pull/215)

Status: gemergt.
Geprüfter Stand: `30b4669d35c34c188dace4a50474db17b4d8f052`.
Merge: `6d2d0d61483216b99772984190a55379f88f6da2` (2026-10-14T02:17:14Z).

First exact-head CI Docker shard1 job115628517193 hit 25min CANCELLED at 99% (retained /tmp/printops-o12-shard1-timeout.log); single targeted retry attempt2 job115639218452 SUCCESS with 2663 passed/9 skipped/4 preexisting duplicate-OpenAPI-ID warnings, log /tmp/printops-o12-shard1-retry-success.log. All 31 final checks COMPLETED/SUCCESS, zero threads and CLEAN; actual Docker Build integration SUCCESS. Local rendered RED4/GREEN16, backend scope RED12/order RED3/final five-suite697, frontend full3505, desktop/mobile software browser body[200] passed. No full local backend repository suite or physical printer/firmware test. Optional authorized JWT/key drying-reservation coverage suggestion remains Minor.

### O13a — [PR #217](https://github.com/ichwars/PrintOps/pull/217)

Status: gemergt.
Geprüfter Stand: `efc77c288b5805a651cf3c3dfd0537ed39b212bc`.
Merge: `242d1f513eb7032b0f5619f075c7b4a16018d6f5` (2026-10-14T03:52:18Z).

MERGED at independently task+whole reviewed exact efc77c after fixing two Important preference isolation findings (failed auth-status shared appliance scope; stale A /me after B login). Real-provider RED4/focused108 and final frontend331 files/3530 pass; auth backend328 pass/1 optional PostgreSQL skip; software browser12 size/grid/scale combinations and four 100% default card-crop pixel comparisons; all12 locales/build/guards. Initial wave2 full run had26 missing-export test mocks/387 failures, corrected by fixed-session exports only; affected398 pass. Final exact-head GitHub31 COMPLETED/SUCCESS, zero paginated review threads, CLEAN and normal merge. No physical printer/model check or full local backend repository suite. Detached integration WT has known one static/index.html EOL-only checkout artifact, root main/foreign WIP/stashes untouched.

### O13b — [PR #219](https://github.com/ichwars/PrintOps/pull/219)

Status: gemergt.
Geprüfter Stand: `59189c5b3533eea939a593b2c89ec7069072ba72`.
Merge: `c6af36053137671c63bbd77f618203b8eea26e63` (2026-10-14T05:17:43Z).

Both independent task+whole reviews APPROVED exact59189c, no findings. RED rendered missing-eye3; focused109, full frontend334files/3548 pass, all12 locales/build/guards; software Chromium browser10 cases/26 screenshots, in-place cached-AMS loss in rendered Vitest, no physical printer/hardware. No backend change/full local backend suite. Original exact-head CI workflow38509856645 Docker Backend shard1 job115675621036 CANCELLED at25min/94%, no F/E/Assertion marker in retained /tmp/printops-o13b-shard1-timeout.log SHA256 48f72066b3f441dd2f914c1438224355521fdf786392dc55715ed89b2b003a04. Sole unchanged-head targeted rerun attempt2 job115689481316 SUCCESS, all other30 checks incl Docker Build SUCCESS. Final saved gate all31 COMPLETED/SUCCESS, 0 fully paginated threads, CLEAN. Normally matched-head merged and remote normal two-parent ancestry verified.

### O13c — [PR #221](https://github.com/ichwars/PrintOps/pull/221)

Status: gemergt.
Geprüfter Stand: `1034f05cccca6cc4e3ebd8301d23f1c5496297e7`.
Merge: `a7456037cb3b4e831c5b1872fa5c5187fde57129` (2026-10-14T07:13:23Z).

MERGED normally at independently reviewed exact1034; task review initial500 Needs fixes/R1+R2 scoped approved bdf, whole initial bdf NOT READY/Important Camwall, scoped whole approved1034 zero new Critical/Important/Minor. First exact-head CI normal Backend shard4 failed unchanged 1s preheat event wait (2672 pass/1 fail; `/tmp/printops-o13c-backend-shard4-failure.log`); ten local repetitions of both cases 20/20 pass supports but does not prove timing cause. Exactly one targeted same-head retry job115718856813 passed2673 `/tmp/printops-o13c-backend-shard4-retry-success.log`; dependent Docker Build job115719944517 SUCCESS. Final gate all31 COMPLETED/SUCCESS/CLEAN/paginated2 resolved. Local final frontend337/3586, all12 locales9256, TS/lint/build/Safari16/source/dependency/domain green. Corrected readable synthetic browser8/16 is layout-only, not live Camwall/camera/physical printer/signed-out auth-enabled public playback/screen-reader/semantic minified/reproducible build proof. Public token tests prove transient preference isolation only; unchanged session stream-token transport. No local full backend rerun after final frontend-only fix.

### O13d — [PR #223](https://github.com/ichwars/PrintOps/pull/223)

Status: gemergt.
Geprüfter Stand: `e1ca25c169cfb0c149595768b9afec5f16408c7b`.
Merge: `9c414e96835afed9a4e097002c30a680481e881d` (2026-10-14T08:28:51Z).

MERGED normally at exact independently reviewed e1ca; task+whole Approved, zero Critical/Important, same nonblocking Minor: rendered A→B test does not await B settled 403 before recovery. Actual strict gate31 COMPLETED/SUCCESS/CLEAN/zero paginated threads; workflow38529725196 Docker Build job115743738449 SUCCESS after integration. Real ASGI auth/ordering and rendered same-ID A→B RED→GREEN; affected backend394, final frontend338 files/3601, guard22, 12 locales, TS/lint/Ruff/build/Safari272/source/dependency/domain green; browser32/32 synthetic fixtures. Local full backend stopped being observable at ~30% without summary/retained exit status; incomplete and cause unknown, not green. No live scheduler/hardware or global dispatch claim. Candidate is authorized snapshot, not dispatch guarantee. Detached integration worktree holds exact HEAD raw static/index.html blob but Git CRLF normalization falsely shows a line-ending modification; only that path was marked assume-unchanged in detached WT after exact raw-blob hash equality, no product change.

### O14 — [PR #225](https://github.com/ichwars/PrintOps/pull/225)

Status: gemergt.
Geprüfter Stand: `6b53eff47b16951150ec01e2ea3d520af14e57f7`.
Merge: `0a2485855052370a2c787928f72b55b090f8543a` (2026-10-14T09:46:46Z).

MERGED normally at exact task+whole independently reviewed6b53 (sole docs timeout Minor closed, zero residual C/I/M). Strict saved gate all27 actually registered current-head checks COMPLETED/SUCCESS, zero paginated threads, CLEAN. Four absent duplicate push Security Audit contexts are explained by docs-only final commit and security.yml push path filters; all four unique pull_request Security Audit contexts exact-head SUCCESS (workflow38537710233). Initial CI Docker Backend shard1 job115765014661 CANCELLED at25min despite2673pass/9skip summary and all steps success; full log `/tmp/printops-o14-docker-shard1-cancelled.log` SHA256 3d00972bb71dfd91ad4f555f09c81453dd92017355053b71fd5dac990f52965a. Exactly one targeted same-head retry job115779695051 SUCCESS, retained `/tmp/printops-o14-docker-shard1-retry-success.log` SHA256 207ebce2f8d3574d9fae7ad07d24619c6b84fd4bf50e7a85a24807671a85121c, 2673pass/9skip; DockerBuild successful. Local full backend10550 passed/187 skipped/9374 warnings in392.96s, final focused72pass, Ruff/guards green. No live PostgreSQL server; fake async connection/startup boundary. Nominal5s cancellation can await cleanup, documented. No deployment-wide capacity certification.

### O15 — [PR #227](https://github.com/ichwars/PrintOps/pull/227)

Status: gemergt.
Geprüfter Stand: `acf8e05d5bc4db8c151fb1ccdc79f7670670b0ab`.
Merge: `cfddab94bfab6c20dfcb38eb7c0c20d65b58db21` (2026-10-14T10:50:35Z).

COMPLETE: independent task+whole scoped R1 addenda APPROVED exact acf8, prior renewal Important/stale-WindowProxy Minor closed; exact31 registered checks all COMPLETED/SUCCESS, same31 contexts as O13d, zero fully paginated threads, CLEAN, normal matched-head merge cfddab parents0a248+acf8. Local frontend339files/3653pass, focused73pass, backend unchanged18pass, TS/lint/build/i18n/mocker/source/dependency/domain guards, timed Chromium renewal and4 origin/viewport cases; synthetic loopback only, no third-party/non-Chromium/device proof. Same-subject silent renewal retains iframe while bridge pauses for current-session registration; explicit re-login/account/URL/error removes/replaces. Native PR artifact attachment attempt by root response unconfirmed, direct URL delivered.

### O16 — [PR #229](https://github.com/ichwars/PrintOps/pull/229)

Status: gemergt.
Geprüfter Stand: `682983277e6b8193ba7227d12c0bf8d55a8271fb`.
Merge: `b2f68c00c585c49c97db6a57ef14b559419331fd` (2026-10-14T12:59:47Z).

Actual final exact682983 CI: 31/31 registered checks COMPLETED/SUCCESS, including PostgreSQL Migration Compatibility job115847582088 dedicated app-message step 5 passed/0 skipped (raw `/tmp/o16-682983-postgres-job115847582088.log`,382077bytes/SHA256 2632cff576f28d71ff461e73da6cbc4097f9ed163bece522221d3554dd550937), four host and four Docker backend shards, Frontend Tests/Build, Docker Build integration, security/CodeQL. Final paginated four external review threads all resolved, CLEAN, normal merge with exact reviewed head. Both scoped R2 task+whole reviews APPROVED after R1 product approval. R2 targeted backend cwd RED1fail→GREEN1pass and root cwd GREEN1pass, preserving two real OS worker quota20/10; full storage backend cwd3pass/2 PG-env skips. Original db62 workflow was FAILED host shard1 and CANCELLED Docker shard1/Build SKIPPED; raw logs retained, GH F identity inferential from same-cwd local reproduction, not directly named in GH output. Initial supplemental local full backend stopped44% without summary, not full-green. No live notification providers, physical printers or hardware. App-containing digest partial failure retains all entries; retry may duplicate delivered chunks; one logical PrintOps quota slot can incur multiple provider calls. Native task attachment response unavailable, direct PR URL supplied.

### O17 — [PR #231](https://github.com/ichwars/PrintOps/pull/231)

Status: gemergt.
Geprüfter Stand: `2667acff70e99532275dd69a977c922b40ed3092`.
Merge: `76802b5c368f6aa7725d27f257a3ed2ead2187ba` (2026-10-14T15:49:44Z).

MERGED normally exact independently Task+Whole reviewed head2667, normal parents b2f68c+2667, merge76802b. Saved strict gate31/31 actual COMPLETED/SUCCESS with same27 unique/multiplicity contexts as O16, final paginated GH reviewThreads3/3 resolved/hasNextPage=false, CLEAN. Exact PG job115910772432/run38580720155 dedicated owner/index+independent disable/enabled actor-removal step12passed/0skip and portable compatibility7passed, raw /tmp/o17-pr231-final2667-postgres-job.log SHA256 f1af63b6cbca418ed47351495e0b04f16a610995f90d59ea3b455cde0e3e6b7c. First Docker Build job115917945700 CANCELLED at35m26s/98% without pytest summary, raw /tmp/o17-pr231-final2667-docker-build-cancelled.log SHA256 d20e426bb5802785e45216088b802e612961c5c2da9cb903bc271cb13641286e; one targeted unchanged-head retry job115936690965 SUCCESS, integration4078passed/17skipped/4warnings in1442.58s and cleanup SUCCESS, raw /tmp/o17-pr231-final2667-docker-build-retry-success.log SHA256 3a07cc494b42aac4d8dd36e078cbfe606d0d2470c983f4630fdae5e3e8762d8f. Local R3 browser-route SQLite RED1fail/1pass→DELETE/WAL GREEN4pass, affected117pass/0skip, R2 frontend81pass/build/browser unchanged. No live Bot, chat-admin, physical printer or comprehensive live PG poller stress. Telegram own-only legacy archives without nonreused owner provenance deny; explicit dirty form edits persist across remote refetch. Original R1/R2 NOT READY and initial PG/Frontend failures retained; final R3 approvals supersede code findings only.

### O18 — [PR #233](https://github.com/ichwars/PrintOps/pull/233): native Orca-HTTP-Variante

Status: geliefert durch diesen [PR #233](https://github.com/ichwars/PrintOps/pull/233).
Die abschließenden Reviews, Checks und der Merge-Status stehen im verlinkten PR;
für diese zum Prüfzeitpunkt laufende Lieferung wird kein zukünftiger Merge-SHA
vorweggenommen. Issue: [#232](https://github.com/ichwars/PrintOps/issues/232).

Offizieller OrcaSlicer 2.4.2 und der bestehende Wrapper-Commit
`4c05506e40a0057db33234837db164143cbf3ad3` werden mit SHA256 geprüft.
Die optionale Compose-Datei baut lokal; Standard-AMD64 und optionaler Bambu-
Service bleiben verfügbar. Unbekannte Plattformen, falsche Hashes und
abweichende ELF-Architekturen werden abgewiesen. Die Quellen und Installations-
und Rückfallwege stehen in der [Sidecar-Anleitung](../slicer-api/README.md).

Lokaler Nachweis: 11 Integritäts-/Architekturtests nach RED mit 11 Fehlern;
32 vorhandene Backend-Slicer-Clienttests bestanden. Ein echter AMD64-Docker-
Build und zehn echte HTTP-Prüfungen bestehen: Version, Profilvererbung,
G-Code, 3MF, umbenannter Drucker, fehlerhaftes JSON, fehlendes Modell, die bestehende
4-MiB-Profilgrenze, höchstens 16 Filamentteile und abgewiesenes STEP-Format.
Die drei erfolgreichen Slices lieferten positive Metadaten (839 Sekunden,
1,08 g, 360,96 mm) für den 10-mm-Testwürfel. Die native ARM64-CI prüft denselben
Vertrag auf `ubuntu-24.04-arm`, ohne QEMU. Die vorhandene 512-MiB-Modellgrenze wurde nicht mit einem übergroßen
Modell ausgelastet; die 4-MiB-Profilgrenze wurde real geprüft. Kein physischer Drucker oder Live-Bot
wurde betrieben; 2-GB-Speicherbedarf wurde nicht gemessen. Vollständiger lokaler
Backend-Testlauf: 10666 bestanden, 195 übersprungen, fünf Warnungen in 418,56
Sekunden (Exit 0).

Der erste echte Build scheiterte an einer falschen Pfadannahme (`usr/bin`);
der verifizierte offizielle Download enthält die Engine unter `bin/orca-slicer`.
Der erste HTTP-Versuch startete zu früh. Im nächsten Versuch deckte der echte
Slicer zwei Fixture-Annahmen auf: Der PLA-Preset heißt `Generic PLA`, und die
STL-Datei benötigt passende Normalen, damit diese Engine sie korrekt erkennt.
Alle fehlgeschlagenen Versuche bleiben in der lokalen Prüfhistorie erhalten.

Die geprüfte Quelle hatte sieben betroffene Produktionspakete mit mehreren
GHSA-Meldungen. Nach ausdrücklicher Controller-Entscheidung ersetzt ein
geprüftes Lockfile die ursprüngliche Abhängigkeitssperre. Quellcode und
`package.json` bleiben unverändert. Der finale lokale Docker-Build mit dieser
Sperre berichtet `found 0 vulnerabilities` für `npm audit --omit=dev` und
besteht dieselben zehn realen HTTP-Prüfungen wie das ursprüngliche Image.
Entwicklungsabhängigkeiten werden nach dem Build entfernt; dieser Auditbeleg
bezieht sich ausdrücklich auf Produktionsabhängigkeiten. Die Build-Umgebung
meldet weiterhin Entwicklungsabhängigkeitswarnungen.

### Nachprüfung des Container-Benutzers am 14. Oktober 2026

Der frühere Stand `f356b8ac50ce1544632abf170298d20788ac1b20` bestand echte
[ARM64](https://github.com/ichwars/PrintOps/actions/runs/38596344800/job/115964063193)-
und [AMD64](https://github.com/ichwars/PrintOps/actions/runs/38596344800/job/115964063392)-
CI mit Engine 2.4.2 und je zehn HTTP-Tests. Trivy meldete an diesem Stand jedoch
HIGH DS-0002 (Check 115965244925): Das eigene Dockerfile hatte keinen
unprivilegierten Standardbenutzer. Diese frühere native CI belegt nicht die
nachfolgende Benutzer-/Volume-Änderung; deren abschließende native Prüfungen sind
im PR einsehbar.

Das korrigierte Image startet Wrapper und Engine als UID/GID `10001:10001`.
Programmdateien bleiben für diesen Benutzer schreibgeschützt. Ein realer
Zwischentest deckte zusätzlich Orcas Schreibzugriff auf `00000.log` im
Arbeitsverzeichnis auf; `/home/orca` dient jetzt als beschreibbares
Arbeitsverzeichnis mit privatem XDG-Verzeichnis.

Die native Compose-Variante verwendet ein eigenes persistentes Volume statt des
bisherigen Host-Bind-Mounts. Vorhandene Host-Daten bleiben unverändert erhalten;
sie werden nicht automatisch übernommen. Die [Migrationsanleitung](../slicer-api/README.md#data-persistence-and-switching-an-existing-installation)
stoppt den bisherigen Schreiber und kopiert dessen Profile/Bundles aus einem
schreibgeschützten Quell-Mount in ein leeres Ziel. Ein nicht leeres Ziel wird
abgewiesen. Nur diese einmalige Kopieroperation läuft als root; der Dienst bleibt
unprivilegiert. Rollback verwendet das ursprüngliche Host-Verzeichnis, während
neue native Daten im separaten Volume verbleiben.

Der lokale Test verwendet die tatsächlichen Compose-Dateien in einem eigenen
Testprojekt: Image-Standardbenutzer, tatsächliche UID/GID, schreibgeschützten
Programmcode, Migration, Ablehnung eines nicht leeren Ziels, unveränderte Quelle,
Erhalt nach Container-Neuerstellung, HTTP-Lesen des migrierten Profils und die
zehn echten Slice-/Upload-Fälle. Trivy 0.74.0 prüfte das finale Dockerfile mit den
Repository-Schweregraden/Ignore-Regeln: keine HIGH/CRITICAL/MEDIUM-Konfigurations-
Befunde. Dieser lokale Befund ersetzt nicht die abschließenden PR-Prüfungen.

Die Produktions-Audit-Aussage gilt für die tatsächlich ausgeführte Dependency-
Build-Schicht. Docker kann deren früheres Audit-Ergebnis aus dem Cache verwenden;
`--pull` allein erzwingt keine erneute Abfrage. Die Anleitung nennt dafür
`build --no-cache --pull`. 17 Build-Toolchain-Audit-Einträge bleiben außerhalb des
akzeptierten Produktions-Lock-Umfangs. Die fünf Warnungen des vollständigen
Backend-Laufs waren vier doppelte OpenAPI-Operations-IDs und eine ignorierte
Scheduler-Coroutine (`PytestUnraisableExceptionWarning`, `KeyError: '__import__'`);
der Lauf war erfolgreich, jedoch nicht warnungsfrei.

## Chronologische Entscheidungen und Kosten

Die folgenden 86 Einträge übernehmen die quellengeprüfte Reihenfolge des
Controller-Protokolls einschließlich der ursprünglichen O18-Entscheidungen.
Die nachfolgenden Korrekturen ergänzen diese Historie einmalig. Eine spätere
Korrektur ersetzt die jeweilige frühere Entscheidung ausdrücklich. Interne
Quellverweise nennen lokale, nicht mitgelieferte Ausführungsprotokolle.

| Nr. | Punkt | Entscheidung | Kosten bei Fehlentscheidung / akzeptierte Kosten |
|---|---|---|---|
| 1 | Ausführung | Selbstständige Umsetzung und normale PR-Merges gemäß deiner Freigabe. | Eine unerwünschte Änderung müsste durch einen weiteren PR zurückgenommen werden. |
| 2 | Ausführung | Mangels App-Werkzeug isolierte Git-Worktrees verwenden. | Deren Lebenszyklus muss manuell verwaltet werden. |
| 3 | Auswahl | Deine aktuelle Auswahl ersetzt die frühere Ablehnung der Kartenskalierung. | Eine unerwünschte Darstellung lässt sich wieder ausschalten. |
| 4 | Dokumentation | Ignorierte Ausführungspläne lokal belassen, Nutzerdokumentation einchecken. | Die interne Planung bleibt außerhalb des Repositories. |
| 5 | CONTRIBUTING | Zwölf Sprachen, zugewiesene Issues und zunächst begleitenden Dokumentations-PR vorsehen. | Zusätzlicher Dokumentationsaufwand; die geplante Wiki-Veröffentlichung wurde anschließend ersetzt. |
| 6 | Dokumentation | Wegen fehlender Begleitrepositories und deaktiviertem Wiki die Dokumentation in PrintOps/docs veröffentlichen. | Bei später verfügbarem Wiki muss sie dorthin übertragen werden. |
| 7 | Arbeitsbereich | Fremde lokale Änderungen und Stashes erhalten; bei Überschneidungen einen separaten Integrations-Worktree nutzen. | Der belegte lokale main kann hinter dem GitHub-main bleiben. |
| 8 | O02 | Die zunächst als nicht blockierend betrachtete Generic-Zuordnung nach Review korrigieren und vorhandene Live-IDs auch in Hintergrundaufrufen erhalten. | Ohne Korrektur wären Wiederverwendung und Kalibrierung beeinträchtigt; die frühere Einschätzung ist ersetzt. |
| 9 | O02 | Die spekulative zusätzliche Generic-Warnung nach Quellprüfung nicht ändern. | Bei falscher Einschätzung könnte eine veraltete Warnung sichtbar bleiben. |
| 10 | O02 | Unbekannte Orca-Materialien ohne verifizierbare Material-ID auch bei angegebener K-ID ablehnen. | Der Anwender muss ein identifiziertes kompatibles Profil wählen. |
| 11 | O02 | Nicht separat protokollierte lokale Prüfungen der letzten Korrektur durch die tatsächliche erfolgreiche Backend-Lint-CI belegen. | Die lokale Herkunft dieser einzelnen Prüfergebnisse bleibt eingeschränkt. |
| 12 | O06 | Eigenen StreamOverlayBuilder neben dem vorhandenen Kameraquellen-Builder einführen. | Zwei spezialisierte Komponenten müssen gepflegt werden. |
| 13 | O06 | Nach Löschung des letzten erlaubten Druckers ausdrücklich jeglichen Druckerzugriff verweigern. | Ein Ersatzdrucker benötigt eine neue Freigabe. |
| 14 | O07 | Den vorhandenen separaten Trocknungsdienst als Integrationsstelle verwenden. | Die Struktur unterscheidet sich weiter vom Upstream-Monolithen. |
| 15 | O07 | Den Zeilenenden-Artefakt prüfen und fremde Dateien nicht zurücksetzen. | Eine scheinbar geänderte Datei benötigt gegebenenfalls besondere Behandlung. |
| 16 | O07, zunächst | Eine flüchtige Eigentümerliste für bestätigte automatische AMS-Starts vorsehen. | Nach Neustart wäre ein älterer Lauf nicht mehr automatisch stoppbar; diese Annahme wurde später verworfen. |
| 17 | O07 | Anhaltende Feuchtigkeit und Temperaturgrenze auch beim Druck beobachten; reine Druck- und geplante Deadline-Läufe ausnehmen. | Umgebungsabhängige Trocknung kann sich verzögern; Wartezeit null bleibt der Standard. |
| 18 | O07, Korrektur | ACK und positive Trocknungszeit reichen nicht als Herkunftsnachweis; uneindeutige Starts zunächst als ausstehend/unzugeordnet behandeln. | Auch automatisch gestartete Läufe könnten bis zum Firmware-Ende weiterlaufen und Aufträge verzögern. |
| 19 | O07, Prüfung | Die Umsetzung dieser Eigentümerpolitik bis zur Entscheidung über den nachgewiesenen Konflikt mit der bisherigen Warteschlange zurückhalten. | Der Punkt wartete auf deine Prioritätsentscheidung. |
| 20 | O07, deine Entscheidung | Manuelle Trocknung schützen und die konservative Zuordnung umsetzen. | Automatischer Stopp und sofortige Unterbrechung bei PAUSE entfallen; bei IDLE kann ein Druck ohne vorherigen Trocknungsstopp ausgewählt werden. |
| 21 | O07 | Ungültige Messwerte als fehlende Beobachtung behandeln und eine gültige Feuchtigkeitsserie erhalten; vollständige Rohhistorie vor dem Filtern prüfen. | Aktualität muss durch gültige Messungen, Zeitlücken und Historienabdeckung festgestellt werden. |
| 22 | O10 | Native Installation und Aktualisierung nur mit Vite bündeln; wirksame TypeScript-Prüfung in CI, Docker, Releases und Entwicklerprüfung erhalten. | Ein ungeprüfter nativer Branch kann bis zu diesen Prüfungen fehlerhaftes TypeScript bündeln. |
| 23 | O11 | MakerWorld-Adapter vom bewährten vorhandenen Dienst ableiten. | Weitere Anbieter können später eine kleine Umstellung auf Komposition erfordern. |
| 24 | O11 | Bisher akzeptierte MakerWorld-Subdomains und URL-Formen beibehalten. | Eine strengere URL-Zulassung braucht einen eigenen Auftrag. |
| 25 | O11 | Anbieterstatus anhand der gespeicherten Zugangsdaten-Anforderung beantworten. | Künftige Live-Erreichbarkeitsprüfungen benötigen eine eigene Statusoperation. |
| 26 | O11 | Lokal betroffene Tests ausführen, anschließend vollständige CI auf dem endgültigen Commit verlangen. | Weitere Wechselwirkungen müssen durch Review und GitHub-CI erkannt werden. |
| 27 | O12 | Die entdeckten fehlenden Druckerberechtigungen an den beiden Objekt-Routen im selben Punkt korrigieren. | Bisher unbeabsichtigt erlaubte Zugriffe können jetzt 403 liefern und eine ausdrückliche Freigabe benötigen. |
| 28 | O13a | Die vorhandene nicht wiederverwendete connected_identity als optionales öffentliches sub für sichere Anzeigeeinstellungen ausgeben. | Clients erhalten ein zusätzliches Feld; bei fehlendem Identitätsnachweis wird die Einstellung nicht dauerhaft gespeichert. |
| 29 | O13a, erste Korrektur | Die bestätigte Authentifizierungsart und neueste Prüfung für Anzeigeeinstellungen verlangen. | Bei fehlgeschlagener Prüfung kann die Einstellung vorübergehend gesperrt sein. |
| 30 | O13a, zweite Korrektur | Den Anzeigenutzer separat an die aktuelle Sitzung binden, ohne die gesamte bestehende Authentifizierung umzubauen. | Vorsichtige Ablehnung deaktiviert die Einstellung bis zur erneuten Bestätigung; sonst könnten fremde Einstellungen übernommen werden. |
| 31 | O13b | Die gesamte externe Spulenanzeige optional ausblenden und mit einer sichtbaren Schaltfläche wiederherstellen. | Die vorhandenen Bedienelemente sind erst nach einem Klick auf Anzeigen erreichbar. |
| 32 | O13b, Korrektur | Nur tatsächlich vorhandene Kartenaktionen wiederherstellen; Ausblendbarkeit am aktuellen AMS-Status statt an gecachten Daten festmachen. | Falsche Cache-Nutzung könnte die einzige aktuelle Spulenanzeige verbergen; erfundene Aktionen würden Bedienung und Berechtigungen ändern. |
| 33 | O13b | Die Einstellung mit bestätigter Sitzung und stabiler Benutzer-/Druckeridentität speichern. | Bei fehlendem Nachweis wird die Spule vorsichtshalber sichtbar; ohne diese Grenze könnten Nachfolgebenutzer fremde Einstellungen übernehmen. |
| 34 | O13c | Die Wahl Fenster/Eingebettet lokal speichern, ohne globale Einstellungen zu verändern. | Administratoren ändern den globalen Standard weiterhin in Einstellungen. |
| 35 | O13c | Alte Kameraeinstellungen mit wiederverwendbaren numerischen IDs nicht migrieren. | Stream/Snapshot muss einmal erneut gewählt werden. |
| 36 | O13c | Den globalen Kameramodus als Startstandard verwenden und bestehende lokale Overlays nicht automatisch schließen. | Zum Schließen bereits geöffneter Overlays sind die vorhandenen Schließen-Schaltflächen nötig. |
| 37 | O13c | Geöffnete Overlays sicher über Benutzer und Hardware-Seriennummer wiederherstellen; alte ungebundene ID-Listen ignorieren. | Früher geöffnete Viewer müssen einmal erneut geöffnet werden. |
| 38 | O13c, erste Korrektur | Kamerastarts auf der Karte erst nach bestätigtem Authentifizierungsmodus und Nutzer zulassen. | Nach fehlgeschlagener Prüfung muss diese wiederholt werden. |
| 39 | O13c, erste Korrektur | Bei bestätigter Berechtigung, aber fehlender Seriennummer synchron auf das vorhandene Kamerafenster ausweichen. | Eingebettet öffnet dann bis zum Vorliegen stabiler Hardwaredaten ein separates Fenster. |
| 40 | O13c, zweite Korrektur | Die Inhaltsauswahl bis zum Abschluss des ersten Metadatenversuchs warten lassen. | Stream/Snapshot lässt sich während dieses ersten Versuchs noch nicht umschalten. |
| 41 | O13c, öffentliche Links | Öffentliche Link-Einstellungen nur flüchtig an die jeweilige Link-Generation binden. | Ein neuer Link übernimmt die vorherige Inhaltswahl nicht. |
| 42 | O13c, Beleggrenze | Nur die Isolation öffentlicher Link-Einstellungen bestätigen; die weitergehende Behauptung zur abgemeldeten Wiedergabe entfernen. | Eine bestehende Einschränkung des öffentlichen Kameratransports bleibt für einen separaten Auftrag offen. |
| 43 | O13c, Gesamtprüfung | Camwall-Starts auf der Druckerseite ebenfalls an bestätigte Identität und camera:view binden. | Der bisherige Fensterpfad wartet nun ebenfalls auf diesen Nachweis. |
| 44 | O13c, Gesamtprüfung | Bei berechtigtem Camwall-Start ohne Seriennummer den bestehenden Fensterpfad verwenden. | Unvollständige Hardwaredaten führen vorerst zu einem separaten Fenster. |
| 45 | O13d | Einen Kandidaten aus dem gelesenen Warteschlangenstand anzeigen und ausstehende Prüfungen deutlich machen. | Er ist keine Zusage, welcher Auftrag tatsächlich als Nächstes startet. |
| 46 | O13d | Gespeicherte Scheduler-Dauer, Übernahmezustand und Sortiermodus auf bereits berechtigten Zeilen ergänzen. | Falsche Fakten würden die Kandidatenreihenfolge verfälschen. |
| 47 | O13d | Einen ausdrücklich unzugänglichen Drucker vor dem Modell-Fallback ablehnen. | Andernfalls könnten Kandidaten für einen nicht freigegebenen Drucker abgeleitet werden. |
| 48 | O13d | Zähler und Vorschau über einen eng sitzungsgebundenen gemeinsamen Query-Hook laden. | Ohne korrekte Sitzungstrennung könnten Namen und Zähler eines vorherigen Benutzers kurz erscheinen. |
| 49 | O13d | Bekannte Sperren nur bei der Vorschau überspringen und die Entscheidung des Schedulers erhalten. | Der angezeigte Kandidat kann vom nächsten tatsächlichen Scheduler-Durchlauf abweichen. |
| 50 | O13d | Bisherige Offline-/Leeranzeige und angrenzende Druckerzustände erhalten. | Verborgene Zustände könnten die Vorschau sonst irreführend machen. |
| 51 | O13d | Zusätzlich zur Datenaktualisierung eine 30-Sekunden-Anzeigeuhr verwenden. | Ohne sie könnte ein abgelaufener Termin bei unveränderten Daten weiterhin als zukünftig erscheinen. |
| 52 | O15 | Bei verifiziertem gleichen Konto die eingebettete App während stiller Anmeldungserneuerung erhalten; ihre Nachrichtenrechte sofort sperren und die Registrierung mit neuen Zugangsdaten prüfen. | Eine falsche Zuordnung könnte alte Rechte weitergelten lassen oder App-Zustand verlieren; echte Konto-, Login-, URL- und Rechteänderungen ersetzen oder entfernen den Frame. |
| 53 | O15 | Bis zur ersten bestätigten Anmeldung den Zugriff gesperrt halten; bei verifizierter stiller Erneuerung das Dokument erhalten und Nachrichten bis zur frischen Registrierung pausieren. | Ein zusätzlicher Registrierungsabruf und kurzzeitig pausierte App-Nachrichten; unbestätigte Sitzungen erhalten keine Brückenrechte. |
| 54 | O16 | App-Berechtigung an die ursprüngliche Benutzeridentität binden; ältere ungebundene API-Schlüssel müssen neu erstellt werden. | Neu ausgestellte Schlüssel sind nötig, um App-Nachrichten freizugeben; andernfalls könnte eine wiederverwendete numerische Benutzer-ID alte Berechtigungen übernehmen. |
| 55 | O16 | Die vorhandene Zuordnung von Benachrichtigungslesen zu can_read_status neben der neuen Sendeberechtigung beibehalten. | Statuszugriff bleibt separat möglich; er darf keine App-Sendeberechtigung oder Provider-Verwaltung eröffnen. Entfernen würde bestehende Clients verändern. |
| 56 | O16 | Die Antwort zählt bearbeitete Kanäle; vorhandenen Sofortversand und zusätzliche Sammelbenachrichtigungen beibehalten. | Eine erfolgreiche API-Antwort bestätigt keinen Empfang beim Versanddienst. Clients müssen bei Bedarf die Versandprotokolle prüfen. |
| 57 | O16 | App-Inhalt nur mit einem vom jeweiligen unterstützten Versanddienst verstandenen sicheren Format ausgeben; die erste gemeinsame Slack-/Mattermost-Variante vor dem Merge korrigieren. | Die ursprüngliche Variante konnte Erwähnungen auslösen oder gültige Nachrichten wegen Dienstgrenzen verlieren; die nachfolgende R1-Korrektur wurde geprüft und mit O16 gemergt. |
| 58 | O16 | Den Mattermost-Text separat maskieren und @-Erwähnungen durch ein unsichtbares Trennzeichen unterbrechen. | Maskierungszeichen können sichtbar sein; kopierte Erwähnungen enthalten ein Trennzeichen. Normalisiert ein Empfänger es vor der Erkennung weg, könnte die Erwähnung wieder wirksam werden; kein Versand an einen realen Mattermost-Server geprüft. |
| 59 | O16 | Nach der jeweiligen Kodierung an vollständigen Unicode-Codepunkten in dienstgerechte Nachrichtenteile aufteilen. | Mehrere Push-Meldungen; zusammengesetzte Zeichen und lange Links können über Teile verteilt und Links nicht mehr anklickbar sein. Geänderte Providergrenzen erfordern Anpassungen. |
| 60 | O16 | Zu lange maskierte Discord-Titel vollständig an den Anfang des Nachrichtentexts verschieben. | Die Titelgestaltung ändert sich bei stark expandierenden Eingaben; der Text bleibt vollständig erhalten. |
| 61 | O16 | Eine logische Anfrage als einen PrintOps-Kontingentplatz und einen bearbeiteten Kanal zählen, auch bei mehreren Versandteilen. | Jeder Teil kann Providerkontingent verbrauchen und eine eigene Meldung oder Pushover-Notfallbenachrichtigung auslösen; lange Inhalte kosten mehr und dauern länger. |
| 62 | O16 | Beim ersten fehlgeschlagenen Teil stoppen und die gesamte Sammelbenachrichtigung mit App-Inhalten zur späteren Wiederholung erhalten. | Bereits zugestellte Teile können beim nächsten Termin erneut erscheinen, auch zusammen mit neuen Einträgen; eine dauerhafte Fortschrittsverwaltung je Teil wurde hier nicht eingeführt. |
| 63 | O16 | Nicht druckbare Titel vor Speicherung und Versand mit422 ablehnen; mehrzeiligen Nachrichtentext zulassen. | Clients mit Tabulatoren, Zeilenumbrüchen oder Formatierungszeichen im Titel müssen auf eine druckbare einzelne Zeile umstellen. |
| 64 | O16 | Kontingentdaten beim Löschen eines Benutzers explizit für dessen Schlüssel entfernen, auch wenn SQLite keine Fremdschlüssel erzwingt. | Eine falsche Zuordnung könnte Daten anderer Besitzer entfernen; der Regressionstest prüft deren Erhalt. |
| 65 | O16 | Das Arbeitsverzeichnis der Kontingent-Testprozesse aus der Testdatei bestimmen; Fehlerausgaben der Unterprozesse sichtbar machen. | Bei einer späteren Verlagerung der Testdatei muss die Pfadberechnung angepasst werden. Die zwei echten Prozesse und ihre bisherigen Prüfungen bleiben verpflichtend. |
| 66 | O17 | Telegram-Reaktionen über ausgehendes Polling und einen ausdrücklich exklusiv verwendeten Bot empfangen; bestehende Webhooks erhalten. | Ein eigener Bot, Chat-Administratorrechte und die Abstimmung anderer Bot-Verbraucher sind nötig; konkurrierende Poller sind vorab nicht immer erkennbar. |
| 67 | O17 | Für Reaktionen die vorhandenen Bestätigungstoken und die erste gültige Antwort verwenden; historische Aufforderungen bleiben beim Browserdialog. | Reaktionen gelten nur für den aktuellen geeigneten Lauf innerhalb der vorhandenen 48 Stunden. |
| 68 | O17 | Beim Senden die Konfigurationsversion merken und danach die Nachrichtenbindung gegen dieselbe Version absichern. | Eine kurze Datenbankschreibphase nach dem Versand ist nötig; eine inzwischen widerrufene, bereits versandte Aufforderung funktioniert nur noch im Browser. |
| 69 | O17 | Archivbesitz mit der unverwechselbaren Kontoidentität speichern; mehrdeutige Altdaten nicht anhand wiederverwendbarer IDs nachtragen. | Eine additive Migration und ein weiteres Archivfeld sind nötig. Nutzer mit Rechten nur für eigene Archive müssen alte Archive ohne Herkunftsnachweis im Browser bestätigen; berechtigte Operatoren mit Zugriff auf alle Archive können reagieren. |
| 70 | O17 | Mangels Browser-Plugin mit Playwright/Chromium prüfen und wegen fehlender Emoji-Schrift die Bedeutung von Daumen hoch/runter zusätzlich ausschreiben. | Die Belege gelten für die verwendeten Browser-Fixtures; echte Telegram-Chats, Geräte, andere Browser und vollständige Barrierefreiheit sind damit nicht nachgewiesen. |
| 71 | O17 | HTTPX/httpcore auch bei eingeschaltetem App-Debug dauerhaft auf WARNING begrenzen, statt den globalen Logger während einzelner Anfragen umzuschalten. | HTTP-Request-Diagnostik auf INFO/DEBUG entfällt auch im App-Debug; andere Debug-Ausgaben bleiben verfügbar. |
| 72 | O17 | Das Laufmodell PrintLogEntry im zentralen Modelleinstieg registrieren; den bestehenden Fremdschlüssel und die Restore-Prüfung erhalten. | Der Modelleinstieg lädt zusätzlich dieses Modell. Eine unvollständige Registrierung würde die nachgewiesene Datenbankinitialisierung erneut verhindern. |
| 73 | O17 | Vor dem Austausch der Datenbank beim Restore das vollständige Beenden des Telegram-Hintergrundprozesses abwarten. | Die Wiederherstellung wartet auf die Bereinigung des Prozesses; ein Fehler dabei könnte den Restore verzögern. Das vorhandene Neustartverfahren bleibt bestehen. |
| 74 | O17 | Die echte Unterprozess-Isolation beibehalten und das Arbeitsverzeichnis aus der Testdatei bestimmen; die Tests aus Repositorywurzel und backend prüfen. | Die Tests benötigen ein ausdrücklich festgelegtes Arbeitsverzeichnis; bei geändertem Dateiaufbau muss es angepasst werden. Ohne die Korrektur scheitern drei echte CI-Testfälle beim Paketimport. |
| 75 | O17 | Die Konfiguration beim Anwenden einer Telegram-Antwort gegen ihre Version sperren und Widerrufe in derselben Reihenfolge abwickeln. | Konfigurationsänderungen und Antworten desselben Providers warten kurz aufeinander. Die erste Platzierung vor der lokalen Sperre führte bei SQLite zu einer belegten Blockierung; diese Version wird durch R3 korrigiert und nicht gemergt. |
| 76 | O17 | Verbrauchte Nachrichtenbindungen atomar löschen; abgelaufene Bindungen regelmäßig bereinigen und Such- sowie Ablaufindex ergänzen. | Zwei zusätzliche Indizes und regelmäßige Löscharbeit sind nötig. Während Stillstand oder langer Polling-Durchläufe kann die Bereinigung später erfolgen; abgelaufene Bindungen gewähren dennoch sofort keine Berechtigung mehr. |
| 77 | O17 | Unberührte Telegram-Formulare aus aktuellen Serverdaten anzeigen; ausdrücklich bearbeitete Entwürfe erhalten und vorhandene UI-Komponenten verwenden. | Ein bewusst gespeicherter eigener Entwurf kann Änderungen eines anderen Administrators überschreiben; es gibt keine allgemeine Versionskonfliktprüfung für solche Entwürfe. |
| 78 | O17 | Dem bestehenden DDL-Test eine echte isolierte SQLite-Verbindung für die Index-Introspektion geben und seine PostgreSQL-DDL-Prüfungen erhalten. | Der Test benötigt nun eine kurzlebige Datenbankverbindung. Er prüft weiterhin generierte PostgreSQL-Anweisungen; tatsächliche PostgreSQL-Migrationen werden separat geprüft. |
| 79 | O17 | Die Sperrreihenfolge nach Datenbank wählen: bei SQLite erst die vollständigen vorhandenen Archiv- und Batch-Sperren, bei PostgreSQL weiter zuerst die Konfigurationszeile. | Ein ausdrücklicher Dialektzweig und ein kleiner Helfer sind nötig. Die Serialisierung bleibt erhalten; eine falsche Reihenfolge würde Browser-Bestätigungen erneut blockieren. |
| 80 | O18 | Den gepinnten HTTP-Wrapper mit seiner Profilauflösung und bestehenden Upload-Grenzen wiederverwenden. | Ein Upstream-Fehler benötigt weiterhin Analyse und eine gezielte Korrektur. |
| 81 | O18 | Die native Orca-Variante als ausdrücklich gewählte lokale Compose-Ergänzung anbieten. | Betreiber tragen den lokalen Build-Aufwand; die vorhandene GHCR- und Bambu-Nutzung bleibt erhalten. |
| 82 | O18 | Offizielle Assets sowie AppImage und extrahierte Engine vor ihrer Nutzung auf Hash und ELF-Architektur prüfen. | Geänderte Download-Bytes blockieren den Build bis zur erneuten Quellenprüfung. |
| 83 | O18 | Echte ARM64- und AMD64-CI-Slices auf nativen Hosts als Lieferbedingung verlangen. | Runner- oder Download-Ausfälle blockieren die Abnahme; reine Architekturprüfung genügt nicht. |
| 84 | O18 | Bei gepinnten Basis-Images die signierten aktuellen OS-Paketquellen verwenden. | Sicherheitsupdates bleiben möglich, wiederholte Builds sind aber nicht byte-identisch. |
| 85 | O18 | Die durch echte Build- und Slicer-Fehler widerlegten Pfad-, Profilnamen- und STL-Fixture-Annahmen korrigieren. | Frühere fehlgeschlagene Versuche bleiben als zusätzlicher Dokumentationsaufwand erhalten. |
| 86 | O18 | Auf die exakt geprüfte Wrapperquelle ein getracktes Abhängigkeits-Lock anwenden; Anwendung, package.json und Orca-Version erhalten. | Das zusätzliche Lock muss bei einem Quellwechsel gepflegt werden; transitive Aktualisierungen können Laufzeitverhalten ändern. Deshalb reproduzierbare Installation, Produktionsaudit und echte Upload-/Limit-/Profil-/G-Code-/3MF-Prüfungen auf beiden Architekturen. |
| 87 | O18, Container-Korrektur | Wrapper und Engine standardmäßig als UID/GID 10001 starten; eigenes beschreibbares Arbeits-/XDG-Verzeichnis verwenden, Programmcode schreibgeschützt halten. | Weitere bisher unbekannte Engine-Schreibzugriffe können gezielte Verzeichnisfreigaben benötigen; der reale Slice-Test muss solche Fehler erkennen. |
| 88 | O18, Datenmigration | Native Daten in eigenem Volume mit passender Eigentümerschaft halten; bestehende Host-Daten nur explizit, schreibgeschützt und in ein leeres Ziel kopieren. | Bestehende Betreiber benötigen einen Migrationsschritt; beim Rollback müssen neue native Änderungen separat gesichert/übernommen werden. |

### Quellen der Entscheidungshistorie

- 1: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:6`
- 2: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:7`
- 3: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:8`
- 4: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:33`
- 5: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:34`
- 6: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:36`
- 7: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:47`
- 8: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:50`
- 9: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:55`
- 10: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:58`
- 11: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:58`
- 12: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:79`; `.worktrees/optional-o06-streaming-overlay/.superpowers/sdd/2026-10-13-o06-streaming-overlay/progress.md:18`
- 13: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:87`
- 14: `.worktrees/optional-o07-sustained-humidity/.superpowers/sdd/2026-10-13-o07-sustained-ambient-humidity/progress.md:15`
- 15: `.worktrees/optional-o07-sustained-humidity/.superpowers/sdd/2026-10-13-o07-sustained-ambient-humidity/progress.md:16`
- 16: `.worktrees/optional-o07-sustained-humidity/.superpowers/sdd/2026-10-13-o07-sustained-ambient-humidity/progress.md:20`; `.worktrees/optional-o07-sustained-humidity/.superpowers/sdd/2026-10-13-o07-sustained-ambient-humidity/progress.md:24`
- 17: `.worktrees/optional-o07-sustained-humidity/.superpowers/sdd/2026-10-13-o07-sustained-ambient-humidity/progress.md:25`
- 18: `.worktrees/optional-o07-sustained-humidity/.superpowers/sdd/2026-10-13-o07-sustained-ambient-humidity/progress.md:35`
- 19: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:147`; `.worktrees/optional-o07-sustained-humidity/.superpowers/sdd/2026-10-13-o07-sustained-ambient-humidity/progress.md:37`
- 20: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:151`; `.worktrees/optional-o07-sustained-humidity/.superpowers/sdd/2026-10-13-o07-sustained-ambient-humidity/progress.md:39`
- 21: `.worktrees/optional-o07-sustained-humidity/.superpowers/sdd/2026-10-13-o07-sustained-ambient-humidity/task-1-implementation.md:233`
- 22: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:211`
- 23: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:231`; `.worktrees/optional-o11-model-provider-abstraction/.superpowers/sdd/2026-10-13-o11-model-provider-abstraction/progress.md:9`; `.worktrees/optional-o11-model-provider-abstraction/.superpowers/sdd/2026-10-13-o11-model-provider-abstraction/task-1-implementation.md:91`
- 24: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:233`; `.worktrees/optional-o11-model-provider-abstraction/.superpowers/sdd/2026-10-13-o11-model-provider-abstraction/progress.md:10`; `.worktrees/optional-o11-model-provider-abstraction/.superpowers/sdd/2026-10-13-o11-model-provider-abstraction/task-1-implementation.md:92`
- 25: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:235`; `.worktrees/optional-o11-model-provider-abstraction/.superpowers/sdd/2026-10-13-o11-model-provider-abstraction/progress.md:11`; `.worktrees/optional-o11-model-provider-abstraction/.superpowers/sdd/2026-10-13-o11-model-provider-abstraction/task-1-implementation.md:93`
- 26: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:237`; `.worktrees/optional-o11-model-provider-abstraction/.superpowers/sdd/2026-10-13-o11-model-provider-abstraction/progress.md:12`; `.worktrees/optional-o11-model-provider-abstraction/.superpowers/sdd/2026-10-13-o11-model-provider-abstraction/task-1-implementation.md:94`
- 27: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:253`; `.worktrees/optional-o12-plate-object-selection/.superpowers/sdd/2026-10-13-o12-plate-object-selection/progress.md:17`; `.worktrees/optional-o12-plate-object-selection/.superpowers/sdd/2026-10-13-o12-plate-object-selection/task-1-implementation.md:18`
- 28: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:277`; `.worktrees/optional-o13a-card-text-scale/.superpowers/sdd/2026-10-13-o13a-card-text-scale/progress.md:15`
- 29: `.worktrees/optional-o13a-card-text-scale/.superpowers/sdd/2026-10-13-o13a-card-text-scale/task-1-implementation.md:103`
- 30: `.worktrees/optional-o13a-card-text-scale/.superpowers/sdd/2026-10-13-o13a-card-text-scale/progress.md:25`; `.worktrees/optional-o13a-card-text-scale/.superpowers/sdd/2026-10-13-o13a-card-text-scale/task-1-implementation.md:143`
- 31: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:301`
- 32: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:303`
- 33: `.worktrees/optional-o13b-hide-external-spool/.superpowers/sdd/2026-10-13-o13b-hide-external-spool/progress.md:15`
- 34: `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:12`
- 35: `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:14`
- 36: `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:19`
- 37: `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:21`
- 38: `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:29`
- 39: `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:31`
- 40: `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:38`
- 41: `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:40`
- 42: `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:46`; `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:53`
- 43: `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:49`
- 44: `.worktrees/optional-o13c-camera-split-button/.superpowers/sdd/2026-10-13-o13c-camera-split-button/progress.md:51`
- 45: `.worktrees/optional-o13d-next-queue-job/.superpowers/sdd/2026-10-13-o13d-next-queue-job/task-1-implementation.md:14`
- 46: `.worktrees/optional-o13d-next-queue-job/.superpowers/sdd/2026-10-13-o13d-next-queue-job/task-1-implementation.md:16`
- 47: `.worktrees/optional-o13d-next-queue-job/.superpowers/sdd/2026-10-13-o13d-next-queue-job/task-1-implementation.md:18`
- 48: `.worktrees/optional-o13d-next-queue-job/.superpowers/sdd/2026-10-13-o13d-next-queue-job/task-1-implementation.md:20`
- 49: `.worktrees/optional-o13d-next-queue-job/.superpowers/sdd/2026-10-13-o13d-next-queue-job/task-1-implementation.md:22`
- 50: `.worktrees/optional-o13d-next-queue-job/.superpowers/sdd/2026-10-13-o13d-next-queue-job/task-1-implementation.md:24`
- 51: `.worktrees/optional-o13d-next-queue-job/.superpowers/sdd/2026-10-13-o13d-next-queue-job/task-1-implementation.md:26`
- 52: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:375`
- 53: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:379`
- 54: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:391`
- 55: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:392`
- 56: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:393`
- 57: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:394`
- 58: `.worktrees/optional-o16-app-notifications/.superpowers/sdd/2026-10-13-o16-app-notifications/implementation-report.md:128`
- 59: `.worktrees/optional-o16-app-notifications/.superpowers/sdd/2026-10-13-o16-app-notifications/implementation-report.md:129`
- 60: `.worktrees/optional-o16-app-notifications/.superpowers/sdd/2026-10-13-o16-app-notifications/implementation-report.md:130`
- 61: `.worktrees/optional-o16-app-notifications/.superpowers/sdd/2026-10-13-o16-app-notifications/implementation-report.md:131`
- 62: `.worktrees/optional-o16-app-notifications/.superpowers/sdd/2026-10-13-o16-app-notifications/implementation-report.md:132`
- 63: `.worktrees/optional-o16-app-notifications/.superpowers/sdd/2026-10-13-o16-app-notifications/implementation-report.md:133`
- 64: `.worktrees/optional-o16-app-notifications/.superpowers/sdd/2026-10-13-o16-app-notifications/implementation-report.md:134`
- 65: `.worktrees/optional-o16-app-notifications/.superpowers/sdd/2026-10-13-o16-app-notifications/implementation-report.md:170`
- 66: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:19`
- 67: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:20`
- 68: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:22`
- 69: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:21`
- 70: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:23`
- 71: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:166`
- 72: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:167`
- 73: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:168`
- 74: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:420`; `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:206`
- 75: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:203`
- 76: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:204`
- 77: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:205`
- 78: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:206`
- 79: `.worktrees/optional-o17-telegram-quality/.superpowers/sdd/2026-10-13-o17-telegram-quality/task-1-report.md:273`
- 80: `.worktrees/optional-o18-native-arm64-slicer/.superpowers/sdd/2026-10-13-o18-native-arm64-slicer/progress.md:3`
- 81: `.worktrees/optional-o18-native-arm64-slicer/.superpowers/sdd/2026-10-13-o18-native-arm64-slicer/progress.md:4`
- 82: `.worktrees/optional-o18-native-arm64-slicer/.superpowers/sdd/2026-10-13-o18-native-arm64-slicer/progress.md:5`
- 83: `.worktrees/optional-o18-native-arm64-slicer/.superpowers/sdd/2026-10-13-o18-native-arm64-slicer/progress.md:6`
- 84: `.worktrees/optional-o18-native-arm64-slicer/.superpowers/sdd/2026-10-13-o18-native-arm64-slicer/progress.md:7`
- 85: `.worktrees/optional-o18-native-arm64-slicer/.superpowers/sdd/2026-10-13-o18-native-arm64-slicer/progress.md:8`
- 86: `.superpowers/sdd/2026-10-13-optional-upstream/progress.md:438`
- 87–88: O18-Feature-Protokoll und `task-1-report.md`, Abschnitt „Non-root correction after Trivy DS-0002“; reale Docker-/Compose-/Trivy-Logs.
