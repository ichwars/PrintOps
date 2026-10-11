# PDF-Runtime bei nativen Updates

Die veraPDF-Version gehört zum geprüften Release und muss mit dessen
Runtime-Manifest übereinstimmen. Linux-/macOS-Updates und der interne Updater
führen deshalb den gemeinsamen Vendor-Schritt aus. Dieser prüft Download-Hashes,
Signatur, CLI-Payload und Version vor dem Austausch des gesamten Verzeichnisses.
Alte JARs dürfen nicht neben der neuen Version auf dem Klassenpfad verbleiben.
Bei einem fehlgeschlagenen Dienststart stellen die Shell-Updater die vorherige
Runtime zusammen mit dem vorherigen Code wieder her.

Updates, die noch mit einem älteren Updater gestartet wurden, müssen diesen
Schritt nach dem Codeupdate einmal manuell ausführen, bevor die Anwendung neu
gestartet wird. Im Installationsverzeichnis:

```bash
venv/bin/python scripts/vendor_pdf_runtime.py \
  --destination runtime/verapdf --cache-dir .cache/pdf-runtime
```

Den Befehl als Installationsbenutzer ausführen. Java und GnuPG aus der nativen
Installation müssen verfügbar sein; ein Verifikationsfehler darf nicht umgangen
werden. Explizit konfigurierte externe Validatoren müssen ebenfalls der im
Manifest geforderten Version entsprechen.

Docker-Updates ersetzen das Image mit der bereits geprüften Runtime.
Windows-Upgrades entfernen das alte verwaltete veraPDF-Verzeichnis nach dem
Dienststopp und installieren die neue Runtime aus dem Installer.
Bestehende Dokumentbelege behalten ihre historische Validator-Version.
