#!/usr/bin/env python3
"""Fetch current PrintOps/Bambuddy refs locally and deliver a ZIP report through Telegram."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from upstream_telegram import Catalog, GitHub, NoRedirect, Telegram, deliver_numbered, parse_allowed_users

ROOT = Path(__file__).resolve().parents[1]
TELEGRAM_API_ROOT = "https://api.telegram.org"
REPORT_FILES = (
    "report.md",
    "commits.csv",
    "summary.md",
    "notification.txt",
    "selection.json",
    "numbered-selection.json",
)
LEGACY_REPORT_FILES = REPORT_FILES[:4]


def telegram_settings() -> tuple[str, str, int | None]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID fehlen; ohne Versand mit --dry-run testen")
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
        raise ValueError("TELEGRAM_BOT_TOKEN hat kein gültiges Bot-Token-Format")
    if not re.fullmatch(r"-?[0-9]+|@[A-Za-z0-9_]+", chat_id):
        raise ValueError("TELEGRAM_CHAT_ID muss eine numerische Chat-ID oder ein @Kanalname sein")
    thread = os.environ.get("TELEGRAM_THREAD_ID", "").strip()
    if thread and (not thread.isascii() or not thread.isdecimal() or int(thread) <= 0):
        raise ValueError("TELEGRAM_THREAD_ID muss eine positive Themen-ID sein")
    return token, chat_id, int(thread) if thread else None


def send_telegram(token: str, chat_id: str, archive: Path, caption: str, thread_id: int | None = None) -> None:
    if archive.stat().st_size > 50_000_000:
        raise ValueError("Das Berichtspaket überschreitet das Telegram-Limit von 50 MB; Dateien lokal behalten")
    # Plain text avoids interpreting commit subjects as Telegram formatting.
    caption = caption.encode("utf-16-le")[:2048].decode("utf-16-le", errors="ignore")
    boundary = uuid.uuid4().hex
    fields = {"chat_id": chat_id, "caption": caption}
    if thread_id is not None:
        fields["message_thread_id"] = str(thread_id)
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts += [
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="document"; '
            'filename="bambuddy-comparison.zip"\r\nContent-Type: application/zip\r\n\r\n'
        ).encode(),
        archive.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    request = Request(
        f"{TELEGRAM_API_ROOT}/bot{token}/sendDocument",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=60) as response:
            payload = json.loads(response.read(65_536))
    except HTTPError as error:
        code = error.code
        error.close()
        raise ValueError(f"Telegram-Versand fehlgeschlagen (HTTP {code}); Bot-Zugang und Chat-Rechte prüfen") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError(
            "Telegram ist nicht erreichbar; das Berichtspaket bleibt lokal für einen späteren Versand"
        ) from None
    except (ValueError, UnicodeError):
        raise ValueError("Telegram hat keine gültige JSON-Antwort geliefert") from None
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        code = payload.get("error_code") if isinstance(payload, dict) else None
        code = code if isinstance(code, int) else "unbekannt"
        raise ValueError(f"Telegram hat den Versand abgelehnt (Fehler {code}); Bot-Zugang und Chat-Rechte prüfen")


def command(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        capture_output=True,
        timeout=600,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"{Path(args[0]).name} fehlgeschlagen: {detail}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def generate_report(state: Path, config: Path, printops_url: str, upstream_url: str) -> Path:
    repository = state / "repository.git"
    if not repository.exists():
        command("git", "init", "--bare", str(repository))
    if command("git", "rev-parse", "--is-bare-repository", cwd=repository) != "true":
        raise ValueError("Der lokale Git-Cache muss ein separates Bare-Repository sein")
    for url, target in ((printops_url, "printops"), (upstream_url, "bambuddy")):
        command("git", "fetch", "--no-tags", url, f"+refs/heads/main:refs/heads/{target}", cwd=repository)
    reports = state / "reports"
    reports.mkdir(exist_ok=True)
    prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S_")
    output = Path(tempfile.mkdtemp(prefix=prefix, dir=reports))
    command(
        sys.executable,
        str(ROOT / "tools" / "compare_upstream.py"),
        "--config",
        str(config),
        "--printops-ref",
        "refs/heads/printops",
        "--upstream-ref",
        "refs/heads/bambuddy",
        "--output-dir",
        str(output),
        cwd=repository,
    )
    return output


def package_report(report: Path, *, numbered: bool = False) -> Path:
    files = REPORT_FILES if numbered or (report / "selection.json").exists() else LEGACY_REPORT_FILES
    for filename in files:
        if not (report / filename).is_file():
            raise ValueError(f"Bericht ist unvollständig: {filename} fehlt")
    archive = report / "bambuddy-comparison.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for filename in files:
            target.write(report / filename, arcname=filename)
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "tools" / "upstream-comparison.json")
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".cache" / "upstream-comparison")
    parser.add_argument("--printops-url", default="https://github.com/ichwars/PrintOps.git")
    parser.add_argument("--upstream-url", default="https://github.com/maziggy/bambuddy.git")
    parser.add_argument(
        "--dry-run", action="store_true", help="Fetch and generate reports without Telegram credentials or sending"
    )
    parser.add_argument(
        "--send-existing", type=Path, help="Send a previously generated report directory without fetching again"
    )
    parser.add_argument("--numbered", action="store_true", help="Enable numbered Telegram entries and issue selection")
    args = parser.parse_args(argv)
    previous_umask = os.umask(0o077)
    try:
        settings = None if args.dry_run else telegram_settings()
        if settings and args.numbered:
            parse_allowed_users(os.environ.get("TELEGRAM_ALLOWED_USER_IDS", ""))
            GitHub(os.environ.get("GITHUB_TOKEN", "").strip())
            if not re.fullmatch(r"-?[1-9][0-9]*", settings[1], flags=re.ASCII):
                raise ValueError("Die nummerierte Auswahl benötigt eine numerische TELEGRAM_CHAT_ID")
        state = args.state_dir.expanduser().resolve()
        state.mkdir(parents=True, exist_ok=True)
        with (state / "run.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Ein lokaler Bambuddy-Abgleich läuft bereits") from None
            report = (
                args.send_existing.expanduser().resolve()
                if args.send_existing
                else generate_report(state, args.config.expanduser().resolve(), args.printops_url, args.upstream_url)
            )
            if (report / "selection.json").exists():
                catalog = Catalog(state)
                try:
                    if settings:
                        catalog.bind(*settings)
                    entries = catalog.register(json.loads((report / "selection.json").read_text(encoding="utf-8")))
                    (report / "numbered-selection.json").write_text(
                        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )
                finally:
                    catalog.close()
            archive = package_report(report, numbered=args.numbered)
            print(f"Berichtspaket: {archive}")
            if settings:
                token, chat_id, thread_id = settings
                caption = (report / "notification.txt").read_text(encoding="utf-8")
                send_telegram(token, chat_id, archive, caption, thread_id)
                if args.numbered:
                    catalog = Catalog(state)
                    try:
                        deliver_numbered(report, catalog, Telegram(token, chat_id, thread_id))
                    finally:
                        catalog.close()
                print("Telegram-Versand erfolgreich")
            else:
                print("Testlauf abgeschlossen; Telegram-Versand ausgelassen")
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        message = str(error)
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if token:
            message = message.replace(token, "[Bot-Token ausgeblendet]")
        print(f"Abgleich fehlgeschlagen: {message}", file=sys.stderr)
        return 1
    finally:
        os.umask(previous_umask)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
