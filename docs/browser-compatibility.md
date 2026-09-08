# Browser-Kompatibilität

Aktuelle Browser bleiben für den vollständigen Funktionsumfang empfohlen.
Der JavaScript-Produktionsbuild hat eine explizite **Safari-/iOS-16.0-Syntaxbaseline**
(neben Chrome/Edge 111 und Firefox 114). Insbesondere darf der Dateimanager
unter Safari/iOS 16.0–16.3 nicht wegen des README-Markdown-Imports leer bleiben.
Das ist keine Zusage, dass sämtliche Browser-APIs, CSS-Effekte, Offline-Funktionen
oder gerätespezifischen Abläufe auf diesen alten Versionen unterstützt werden.

## Markdown im Dateimanager

Tabellen, Aufgabenlisten, Durchstreichung, Fußnoten und normales Markdown bleiben
erhalten. Unmarkierte URLs und E-Mail-Adressen erscheinen als Text. Für klickbare
Links `[Beschreibung](https://example.com)`, `<https://example.com>` oder
`<name@example.com>` verwenden. Raw-HTML wird nicht ausgeführt; die URL-Filterung
von ReactMarkdown und `noopener noreferrer` für Links bleiben erhalten.

Der Parser kombiniert die vier benötigten GFM-Erweiterungen direkt. Der
Autolink-Literal-Import aus `remark-gfm` entfällt: Er enthielt einen bereits beim
Laden ungültigen Lookbehind-Ausdruck. In PrintOps war davon der lazy geladene
Dateimanager betroffen, nicht der bereits funktionierende Login-Einstieg.

## PDF-Vorschau ist eine separate Laufzeitgrenze

Auch der PDF-Worker wird durch Vite übersetzt und auf Syntax geprüft, statt als
unveränderte `.mjs`-Datei kopiert zu werden. Das ergänzt **keine** fehlenden
Browser-APIs für PDF.js. Die Dokumentlayout-PDF-Vorschau benötigt weiterhin einen
aktuellen, von PDF.js unterstützten Browser; Safari 16 wird dafür nicht zugesagt.
Der bestehende Fehlerbereich der Vorschau schützt den übrigen Layouteditor.
Keine Änderungen an Belegberechnung, Berechtigungen oder PDF-Erzeugung im Backend.

## Reproduzierbare Prüfungen

Im Verzeichnis `frontend`:

```sh
npm ci
npm run build -- --outDir ./dist/browser-baseline
npm run preview -- --outDir ./dist/browser-baseline --host 127.0.0.1 --port 4184 --strictPort
```

Jeder Vite-Produktionsbuild prüft automatisch alle tatsächlich geschriebenen
`.js`- und `.mjs`-Dateien im gewählten Ausgabeverzeichnis, einschließlich Worker
und öffentlicher Assets. Die AST-Prüfung erkennt Lookbehind-Literale, statische
Klassenblöcke und RegExp-Unicode-Sets; Text/Kommentare werden nicht als Code
fehlinterpretiert. Fehlendes/leeres Ausgabe-JavaScript führt zum Fehler.
Dies ist ein gezielter Regressionswächter, kein vollständiger Safari-Parser oder
eine Prüfung dynamisch erzeugter regulärer Ausdrücke.

In einem zweiten Terminal, während die Vorschau läuft:

```sh
npx playwright install chromium
npm run check:browser-runtime
```

Der Check lädt den **gebauten** Dateimanager mit deterministischen lokalen
API-Testdaten bei 1440×1000 und 390×844, prüft Markdown und Link-/HTML-Schutz und
klappt die README zu und wieder auf. Relevante Konsolen-/HTTP-Fehler schlagen
fehl. Service Worker sind für die API-Fixtures ausgeschaltet; die erwarteten
WebSocket-Verbindungsfehler ohne Backend sind explizit ausgenommen. Der Check
läuft auch im CI-Job „Frontend Build“.

Für einen historischen Engine-Gegencheck kann eine **separat installierte**
Playwright-Version verwendet werden, ohne App-Abhängigkeiten zu downgraden:

```sh
BASELINE_ENGINE=webkit BASELINE_PLAYWRIGHT=/absolute/path/to/playwright-core npm run check:browser-runtime
```

Unter PowerShell die beiden Variablen mit `$env:BASELINE_ENGINE='webkit'` und
`$env:BASELINE_PLAYWRIGHT='C:/.../playwright-core'` setzen und danach denselben
npm-Befehl ausführen. `BASELINE_URL` überschreibt die lokale Vorschauadresse;
`BASELINE_SCREENSHOTS` speichert Bilder in einem vorhandenen Verzeichnis.

Validiert am 08.09.2026: WebKit 16.0 (Playwright 1.27.1, Build 1724, Windows) und
Chromium 149.0.7827.55. Derselbe alte Produktions-Dateimanager schlug in WebKit
mit `Invalid regular expression: invalid group specifier name` fehl; der
korrigierte Build besteht den README-Ablauf in beiden Engines und Viewports.
Das ersetzt keinen Test auf einem physischen iOS-Gerät. Bestehende mobile
Toolbar-Überbreite und Schrift-Rasterung der historischen Windows-Engine sind
nicht Teil dieser Parsefehler-Korrektur.

Referenzen: [Safari 16.4 / neue JavaScript-Syntax](https://webkit.org/blog/13966/webkit-features-in-safari-16-4/),
[Vite Build-Ziel](https://vite.dev/config/build-options.html#build-target),
[PDF.js Browser-Anforderungen](https://github.com/mozilla/pdf.js/wiki/Frequently-Asked-Questions).
