# PrintOps Windows Installer

Builds a self-contained Windows installer (`.exe`) for PrintOps: embedded
Python 3.13 distribution + pre-built frontend + NSSM-supervised Windows
service. No Python or Node installation required on the target machine.

## Architecture

- **Install target:** `C:\Program Files\PrintOps\`
- **Data target:** `C:\ProgramData\PrintOps\data\` (preserved on uninstall by default)
- **Logs target:** `C:\ProgramData\PrintOps\logs\`
- **Service:** registered via NSSM, runs as `LocalSystem`, autostart on boot
- **Service command:** `python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --loop asyncio` (`--loop asyncio` avoids a uvloop TLS bug that can truncate VP FTP uploads, #1896)
- **Bundled binaries:** Python 3.13 embeddable, NSSM, ffmpeg, WeasyPrint
  69.0 with its Pango/GTK runtime, Temurin JRE 21.0.10+7 and veraPDF 1.30.2

Browser is the UI. Start Menu shortcut opens `http://localhost:8000`.

## Why these choices

See `memory/windows-installer-decision.md` for the full reasoning. Short
version: PowerShell install scripts can't survive environmental drift
across the Windows host fleet, so we ship a self-contained bundle that
depends on nothing on the host. Inno Setup + embedded Python is the
lowest-maintenance path that delivers native-app UX. No Tauri/Electron
launcher in v1 — browser-as-UI matches every other PrintOps platform.

## Build prerequisites

The build runs on Windows (or in a Windows GitHub Actions runner). Cross-
building from Linux is possible via Wine but not officially supported.

- Windows 10/11 x64 (or `windows-latest` GitHub Actions runner)
- Python 3.11+ (for running `build.py`; the embedded Python that ships
  in the installer is downloaded fresh by the build script)
- Node.js 22 LTS + npm (for building the frontend bundle)
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (for compiling
  `printops.iss` → `.exe`)
- Git for Windows including GnuPG (used to verify veraPDF's detached
  signature; the build aborts if it is missing or has the wrong fingerprint)

The build script downloads everything else automatically (embedded Python,
NSSM, ffmpeg).

## PDF runtime provenance and licenses

Commercial documents are rendered and validated without runtime downloads.
The installer build stages only pinned artifacts and verifies them before they
enter `build/staging/runtime/`:

- WeasyPrint `69.0` standalone Windows archive from the official Kozea GitHub
  release, SHA-256
  `330101ff3ea50ebde4abf805283b6d703d5f3d71c77c983db94357ec4524a3ef`.
  It contains the native Pango/GTK libraries required on Windows. WeasyPrint is
  BSD-3-Clause; the archive carries its `LICENSE` file and the licenses of its
  bundled dependencies.
- Eclipse Temurin JRE `21.0.10+7` from the official Adoptium release,
  SHA-256
  `a6ac6789e51a2c245f41430c42e72b39ec706a449812fc5e4cbfc55ceed1e5ae`.
  Temurin is distributed under GPLv2 with the Classpath Exception and retains
  the upstream legal files inside the staged JRE.
- veraPDF Greenfield `1.30.2` from `software.verapdf.org`. The archive and
  detached signature hashes are recorded in
  `backend/app/resources/pdf/runtime-manifest.json`; the build additionally
  verifies signing fingerprint
  `13DD102B4DD69354D12DE5A83184863278B17FE7`. Only the CLI payload is retained.
  veraPDF is distributed under GPL-3.0 and MPL-2.0.

To upgrade a runtime, change its version, immutable URL and expected hash in
`build.py` or the shared veraPDF manifest in the same commit. Download from the
official publisher, verify the publisher's signature where available, run the
offline smoke below, and review the packaged license files. Never replace a
hash without documenting the corresponding upstream release.

## Build steps

```cmd
:: From the repo root on a Windows machine
cd installers\windows
python build.py
:: Then open printops.iss in Inno Setup Compiler and click Build → Compile
:: (or invoke ISCC.exe directly:)
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" printops.iss
```

The lightweight CI receipt check does not assemble the installer:

```cmd
python build.py --verify-runtime-only
```

After a full build, disconnect the machine from the network and run:

```cmd
build\staging\runtime\weasyprint\dist\weasyprint.exe --version
build\staging\runtime\java\bin\java.exe -version
build\staging\runtime\verapdf\verapdf.bat --version
```

The expected versions are respectively `69.0`, `21.0.10` and `1.30.2`; no
command may attempt a network connection.

Output: `installers\windows\build\output\printops-windows-setup.exe`

## Testing without signing

The installer can be built and run unsigned. Windows SmartScreen will
show "Windows protected your PC" on first run. Click **More info** →
**Run anyway** to proceed. This is expected and harmless for testing.
Production builds will be signed via SignPath OSS (application in
flight as of 2026-06-10) and won't show this warning after reputation
accrues.

## CI build

See `.github/workflows/windows-installer.yml` for the automated build.
The workflow runs on every tag matching `v*` and uploads the installer
as a release asset.

## Known limitations / open questions

- **VP feature on Windows:** the Virtual Printer needs to bind 322/990/8883
  (privileged ports). Service runs as LocalSystem which can bind these
  ports, but the user's Windows Firewall will prompt on first VP enable.
  Documenting this is TBD.
- **Spoolman:** explicitly NOT bundled in v1. Users who want Spoolman
  install it separately. PrintOps internal-inventory mode is the default
  on Windows.
- **Bundle size:** estimated 250–350MB installed (mostly opencv +
  ffmpeg + matplotlib). Acceptable for a v1; can investigate slimming
  later if users complain.
- **Updates:** v1 ships as a fresh install / uninstall + install cycle.
  In-place upgrade via the same installer is supported by Inno Setup but
  needs end-to-end testing before we promise it.
