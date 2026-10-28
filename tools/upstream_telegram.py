"""Persistent numbered upstream selections; no dependency on the PrintOps application."""

from __future__ import annotations

import html
import json
import re
import sqlite3
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPOSITORY = "ichwars/PrintOps"
UPSTREAM = "https://github.com/maziggy/bambuddy/commit/"
TELEGRAM_API = "https://api.telegram.org"
GITHUB_API = "https://api.github.com"
SHA = re.compile(r"[0-9a-f]{40}")
PATCH_LABELS = {
    "identischer_patch": "Identischer Patch vorhanden; Funktionsstand trotzdem prüfen",
    "kein_identischer_patch": "Kein identischer Patch; eigene Umsetzung möglich, fachlich prüfen",
    "merge_nicht_geprueft": "Merge-Commit; Patch nicht geprüft",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward bot or GitHub credentials to a redirect target.


def request_json(url: str, *, data=None, headers=None, timeout=30):
    request = Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(10_000_001)
        if len(raw) > 10_000_000:
            raise ValueError("API-Antwort zu groß")
        return json.loads(raw)
    except HTTPError as error:
        code = error.code
        error.close()
        raise ValueError(f"API-Aufruf fehlgeschlagen (HTTP {code})") from None
    except (URLError, OSError, TimeoutError, UnicodeError, json.JSONDecodeError):
        raise ValueError("API-Aufruf fehlgeschlagen; Verbindung oder Antwort ungültig") from None


def clean(value: str, limit: int = 300) -> str:
    return " ".join(value.split())[:limit]


def markdown(value: str) -> str:
    value = html.escape(clean(value, 2000), quote=False).replace("@", "&#64;")
    return re.sub(r"([\\`*\[\]_])", r"\\\1", value)


def validate_manifest(document: dict) -> None:
    if not isinstance(document, dict) or document.get("schema") != 1 or document.get("repository") != REPOSITORY:
        raise ValueError("Unbekanntes Auswahlformat oder falsches Zielrepository")
    if any(
        not isinstance(document.get(key), str) or not SHA.fullmatch(document[key])
        for key in ("printops", "upstream", "reviewed")
    ):
        raise ValueError("Ungültige Vergleichsstände")
    if not isinstance(document.get("entries"), list):
        raise ValueError("Ungültige Änderungsliste")
    seen = set()
    for entry in document["entries"]:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("sha"), str)
            or not SHA.fullmatch(entry["sha"])
            or entry["sha"] in seen
            or not isinstance(entry.get("subject"), str)
            or entry.get("patch_status") not in PATCH_LABELS
            or not isinstance(entry.get("paths"), list)
            or not all(isinstance(path, str) for path in entry["paths"])
        ):
            raise ValueError("Ungültige oder doppelte Änderung im Bericht")
        seen.add(entry["sha"])


class Catalog:
    def __init__(self, state: Path):
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.connection = sqlite3.connect(state / "selections.sqlite3", timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sha TEXT NOT NULL UNIQUE,
                document TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0,
                issue_url TEXT, pending INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        (state / "selections.sqlite3").chmod(0o600)

    def close(self):
        self.connection.close()

    def get(self, key: str):
        row = self.connection.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value):
        with self.connection:
            self.connection.execute(
                "INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )

    def bind(self, token: str, chat: str, thread: int | None):
        scope = {"bot": token.split(":", 1)[0], "chat": chat, "thread": thread, "repository": REPOSITORY}
        previous = self.get("scope")
        if previous is not None and previous != scope:
            raise ValueError(
                "Statusverzeichnis gehört zu einem anderen Bot, Chat oder Thema; eigenen Zustand verwenden"
            )
        self.put("scope", scope)

    def register(self, document: dict) -> list[dict]:
        validate_manifest(document)
        result = []
        with self.connection:
            for entry in document["entries"]:
                snapshot = {
                    **{key: document[key] for key in ("printops", "upstream", "reviewed")},
                    **{key: entry[key] for key in ("sha", "subject", "paths", "patch_status")},
                }
                self.connection.execute(
                    """
                    INSERT INTO entries(sha,document) VALUES (?,?)
                    ON CONFLICT(sha) DO UPDATE SET document=excluded.document
                """,
                    (entry["sha"], json.dumps(snapshot)),
                )
                row = self.connection.execute("SELECT * FROM entries WHERE sha=?", (entry["sha"],)).fetchone()
                result.append({"number": row["id"], **snapshot})
        return result

    def publish(self, numbers: list[int]):
        with self.connection:
            self.connection.executemany("UPDATE entries SET published=1 WHERE id=?", [(number,) for number in numbers])

    def selected(self, numbers: list[int]) -> list[sqlite3.Row]:
        rows = [
            self.connection.execute("SELECT * FROM entries WHERE id=? AND published=1", (number,)).fetchone()
            for number in numbers
        ]
        if not rows or any(row is None for row in rows):
            raise ValueError(
                "Mindestens eine Nummer wurde in diesem Chat noch nicht veröffentlicht; Auswahl unverändert"
            )
        return rows

    def claim(self, number: int) -> bool:
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE entries SET pending=1 WHERE id=? AND pending=0 AND issue_url IS NULL", (number,)
            )
        return cursor.rowcount == 1

    def link(self, number: int, url: str):
        if not re.fullmatch(r"https://github\.com/ichwars/PrintOps/issues/[1-9][0-9]*", url):
            raise ValueError("Ungültiger GitHub-Issue-Link")
        with self.connection:
            self.connection.execute("UPDATE entries SET issue_url=?,pending=0 WHERE id=?", (url, number))


def numbered_messages(entries: list[dict]) -> list[tuple[str, list[int]]]:
    messages = []
    text, numbers = "", []
    for entry in entries:
        paths = ", ".join(clean(path, 100) for path in entry["paths"][:3]) or "keine Pfade"
        if len(entry["paths"]) > 3:
            paths += f" (+{len(entry['paths']) - 3})"
        block = (
            f"{entry['number']}. {clean(entry['subject'])}\n"
            f"{PATCH_LABELS[entry['patch_status']]}\nDateien: {paths}\n{UPSTREAM}{entry['sha']}\n\n"
        )
        if len((text + block).encode("utf-16-le")) // 2 > 3500:
            messages.append((text.rstrip(), numbers))
            text, numbers = "", []
        text += block
        numbers.append(entry["number"])
    if text:
        messages.append((text.rstrip(), numbers))
    return messages


class Telegram:
    def __init__(self, token: str, chat: str, thread: int | None):
        self.token, self.chat, self.thread = token, chat, thread
        self.last_sent = 0.0

    def call(self, method: str, data=None, *, timeout=30):
        payload = request_json(f"{TELEGRAM_API}/bot{self.token}/{method}", data=data or {}, timeout=timeout)
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise ValueError("Telegram-Aufruf abgelehnt; Zugang, Chat oder gleichzeitigen Bot-Empfang prüfen")
        return payload.get("result")

    def send(self, text: str, *, reply_to: int | None = None):
        time.sleep(max(0, self.last_sent + 1.1 - time.monotonic()))
        data = {"chat_id": self.chat, "text": text, "link_preview_options": {"is_disabled": True}}
        if self.thread is not None:
            data["message_thread_id"] = self.thread
        if reply_to is not None:
            data["reply_parameters"] = {"message_id": reply_to}
        result = self.call("sendMessage", data)
        self.last_sent = time.monotonic()
        if not isinstance(result, dict) or type(result.get("message_id")) is not int:
            raise ValueError("Telegram hat keine Nachrichten-ID bestätigt")
        return result["message_id"]


def deliver_numbered(report: Path, catalog: Catalog, telegram: Telegram) -> None:
    document = json.loads((report / "selection.json").read_text(encoding="utf-8"))
    entries = catalog.register(document)
    (report / "numbered-selection.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    telegram.send(
        f"PrintOps / Bambuddy: {len(entries)} neue Git-Unterschiede seit der Prüfbasis.\n"
        f"PrintOps {document['printops'][:9]} | Bambuddy {document['upstream'][:9]}\n"
        "Die Nummern bleiben über Wochen gleich. Fachliche Funktionsgleichheit muss geprüft werden."
    )
    for text, numbers in numbered_messages(entries):
        telegram.send(text)
        catalog.publish(numbers)
    if entries:
        telegram.send(
            "Antworte auf eine dieser Bot-Nachrichten nur mit den gewünschten Nummern, z. B. 2, 5, 7.\n"
            "Pro Nummer entsteht ein Prüf-/Übernahme-Issue; vorhandene Issues werden wiederverwendet. "
            "Danach erhältst du die Issue-Links. Eine Codeübernahme wird damit nicht gestartet."
        )


def parse_numbers(text: str) -> list[int]:
    if not isinstance(text, str) or len(text) > 1000:
        raise ValueError("Bitte nur Nummern senden, z. B. 2, 5, 7")
    text = text.strip()
    if text.startswith("/issues "):
        text = text[8:].strip()
    if not re.fullmatch(r"[0-9]+(?:[,\s]+[0-9]+)*", text, flags=re.ASCII):
        raise ValueError("Bitte nur Nummern senden, z. B. 2, 5, 7")
    numbers = list(dict.fromkeys(int(value) for value in re.findall(r"[0-9]+", text)))
    if not numbers or len(numbers) > 50 or any(number < 1 or number > 2_147_483_647 for number in numbers):
        raise ValueError("Bitte 1 bis 50 gültige Nummern auswählen")
    return numbers


def parse_allowed_users(value: str) -> set[int]:
    value = value.strip()
    if not re.fullmatch(r"[1-9][0-9]*(?:\s*,\s*[1-9][0-9]*)*", value, flags=re.ASCII):
        raise ValueError("TELEGRAM_ALLOWED_USER_IDS muss erlaubte numerische Benutzer-IDs enthalten (kommagetrennt)")
    return {int(part) for part in value.split(",")}


class GitHub:
    def __init__(self, token: str):
        if not token:
            raise ValueError("GITHUB_TOKEN mit Issues-Schreibrecht für ichwars/PrintOps fehlt")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "PrintOps-Upstream-Selection",
        }

    def existing(self) -> dict[str, str]:
        result = {}
        for page in range(1, 1001):
            items = request_json(
                f"{GITHUB_API}/repos/{REPOSITORY}/issues?state=all&per_page=100&page={page}", headers=self.headers
            )
            if not isinstance(items, list):
                raise ValueError("GitHub-Issue-Liste ungültig; keine neuen Issues erstellt")
            for item in items:
                if "pull_request" in item:
                    continue
                for sha in re.findall(
                    r"https://github\.com/maziggy/bambuddy/commit/([0-9a-f]{40})", item.get("body") or ""
                ):
                    result[sha] = item["html_url"]
            if len(items) < 100:
                return result
        raise ValueError("GitHub-Issue-Liste unvollständig; keine neuen Issues erstellt")

    def create(self, number: int, document: dict) -> str:
        sha = document["sha"]
        paths = "\n".join(f"- {markdown(path)}" for path in document["paths"][:100])
        if len(paths) > 8000 or len(document["paths"]) > 100:
            paths = paths[:8000]
            paths += "\n- Weitere Pfade stehen im verlinkten Upstream-Commit."
        body = (
            f"<!-- printops-bambuddy:{sha} -->\n"
            f"Auswahl **{number}** aus dem Telegram-Bambuddy-Abgleich.\n\n"
            f"Upstream: {UPSTREAM}{sha}\n\n{markdown(document['subject'])}\n\n"
            f"Git-Hinweis: {PATCH_LABELS[document['patch_status']]}.\n"
            "Eine Git-Differenz belegt keine fehlende Funktion.\n\n"
            f"Betroffene Pfade:\n{paths or '- Keine Pfade'}\n\n"
            f"Vergleich: PrintOps `{document['printops']}`, Bambuddy `{document['upstream']}`, "
            f"fachliche Prüfbasis `{document['reviewed']}`.\n\n"
            "- [ ] Prüfen, ob PrintOps die Funktion bereits eigenständig oder angepasst enthält.\n"
            "- [ ] Nutzen, Abhängigkeiten und betroffene Berechtigungen bewerten.\n"
            "- [ ] Umsetzung unter Erhalt eigener Druck-, Auftrags- und Lagerfunktionen festlegen.\n"
            "- [ ] Passende Tests und Dokumentation ergänzen.\n\n"
            "Die Auswahl beauftragt die Prüfung/Planung dieses Punkts; keine automatische Codeübernahme."
        )
        payload = request_json(
            f"{GITHUB_API}/repos/{REPOSITORY}/issues",
            headers=self.headers,
            data={"title": "[Bambuddy prüfen] " + clean(document["subject"], 180).replace("@", "＠"), "body": body},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("html_url"), str):
            raise ValueError("GitHub hat keinen Issue-Link bestätigt")
        return payload["html_url"]


def create_selected(catalog: Catalog, github: GitHub, numbers: list[int]) -> list[str]:
    rows = catalog.selected(numbers)  # Validate the complete selection before any external write.
    existing = github.existing() if any(not row["issue_url"] for row in rows) else {}
    result = []
    for row in rows:
        url = row["issue_url"] or existing.get(row["sha"])
        if url:
            catalog.link(row["id"], url)
            result.append(f"{row['id']}: {url} (vorhanden)")
            continue
        if not catalog.claim(row["id"]):
            result.append(
                f"{row['id']}: früherer Erstellungsversuch unklar; GitHub manuell prüfen, kein Duplikat erstellt"
            )
            continue
        try:
            url = github.create(row["id"], json.loads(row["document"]))
            catalog.link(row["id"], url)
            result.append(f"{row['id']}: {url}")
        except ValueError:
            # Leave the durable claim set: a timeout may have happened AFTER GitHub created the issue.
            result.append(
                f"{row['id']}: Erstellungsstatus unklar; Nummer erneut senden zum Abgleich, kein automatischer Neuversuch"
            )
    return result


def authorized(message: dict, chat: str, thread: int | None, users: set[int]) -> bool:
    sender = message.get("from", {})
    return (
        str(message.get("chat", {}).get("id")) == chat
        and message.get("message_thread_id") == thread
        and type(sender.get("id")) is int
        and sender["id"] in users
        and sender.get("is_bot") is False
        and not any(key in message for key in ("sender_chat", "forward_origin", "forward_date"))
    )


def process_update(update: dict, catalog: Catalog, telegram: Telegram, github: GitHub, users: set[int]) -> None:
    message = update.get("message")
    if (
        not isinstance(message, dict)
        or not authorized(message, telegram.chat, telegram.thread, users)
        or type(message.get("date")) is not int
        or message["date"] < catalog.get("accept_since")
        or type(message.get("message_id")) is not int
    ):
        return
    try:
        numbers = parse_numbers(message.get("text"))
        results = create_selected(catalog, github, numbers)
        text = "GitHub-Auswahl:\n" + "\n".join(results)
    except ValueError as error:
        text = str(error)
    # At most 50 issue URLs fit across these independently bounded messages.
    lines, part = text.splitlines(), ""
    for line in lines:
        if len((part + line).encode("utf-16-le")) // 2 > 3500:
            telegram.send(part.rstrip(), reply_to=message["message_id"])
            part = ""
        part += line + "\n"
    if part:
        telegram.send(part.rstrip(), reply_to=message["message_id"])
