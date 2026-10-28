#!/usr/bin/env python3
"""Receive authorized Telegram number selections and create/reuse GitHub issues."""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import sys
import time
from pathlib import Path

from run_upstream_comparison import telegram_settings
from upstream_telegram import Catalog, GitHub, Telegram, parse_allowed_users, process_update

ROOT = Path(__file__).resolve().parents[1]


def allowed_users() -> set[int]:
    return parse_allowed_users(os.environ.get("TELEGRAM_ALLOWED_USER_IDS", ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".cache/upstream-comparison")
    parser.add_argument("--once", action="store_true", help="Poll and process at most one batch")
    parser.add_argument("--check-config", action="store_true", help="Validate environment without network or writes")
    args = parser.parse_args(argv)
    previous_umask = os.umask(0o077)
    catalog = None
    try:
        token, chat, thread = telegram_settings()
        if not re.fullmatch(r"-?[1-9][0-9]*", chat, flags=re.ASCII):
            raise ValueError("Der Auswahlempfang benötigt eine numerische TELEGRAM_CHAT_ID, keinen Kanalnamen")
        users = allowed_users()
        github = GitHub(os.environ.get("GITHUB_TOKEN", "").strip())
        if args.check_config:
            print("Konfiguration formal vollständig; keine Netzwerkaufrufe oder Schreibaktionen")
            return 0
        state = args.state_dir.expanduser().resolve()
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (state / "listener.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Ein Auswahlempfänger läuft für dieses Statusverzeichnis bereits") from None
            telegram = Telegram(token, chat, thread)
            webhook = telegram.call("getWebhookInfo")
            if not isinstance(webhook, dict) or "url" not in webhook or webhook["url"]:
                raise ValueError(
                    "Bot verwendet einen Webhook oder Status unbekannt; keine Übernahme, eigenen Bot verwenden"
                )
            catalog = Catalog(state)
            catalog.bind(token, chat, thread)
            if catalog.get("accept_since") is None:
                catalog.put("accept_since", int(time.time()))
            while True:
                offset = catalog.get("offset") or 0
                updates = telegram.call(
                    "getUpdates", {"offset": offset, "timeout": 20, "allowed_updates": ["message"]}, timeout=30
                )
                if not isinstance(updates, list):
                    raise ValueError("Telegram hat keine gültige Update-Liste geliefert")
                for update in updates:
                    if not isinstance(update, dict) or type(update.get("update_id")) is not int:
                        raise ValueError("Telegram-Update ohne gültige ID")
                    if update["update_id"] < offset:
                        continue
                    process_update(update, catalog, telegram, github, users)
                    offset = update["update_id"] + 1
                    catalog.put("offset", offset)
                if args.once:
                    return 0
    except (ValueError, OSError) as error:
        message = str(error)
        for key in ("TELEGRAM_BOT_TOKEN", "GITHUB_TOKEN"):
            secret = os.environ.get(key, "").strip()
            if secret:
                message = message.replace(secret, "[Token ausgeblendet]")
        print(f"Auswahlempfang fehlgeschlagen: {message}", file=sys.stderr)
        return 1
    finally:
        if catalog is not None:
            catalog.close()
        os.umask(previous_umask)


if __name__ == "__main__":
    raise SystemExit(main())
