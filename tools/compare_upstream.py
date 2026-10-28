#!/usr/bin/env python3
"""Generate a read-only Bambuddy commit comparison using Git and the standard library."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_REPOSITORY = "maziggy/bambuddy"
PATCH_LABELS = {
    "identischer_patch": "Identischer Patch vorhanden",
    "kein_identischer_patch": "Kein identischer Patch; fachlich prüfen",
    "merge_nicht_geprueft": "Merge; Patch nicht geprüft",
}


@dataclass
class Commit:
    sha: str
    parents: list[str]
    date: str
    subject: str
    paths: list[str]
    patch_status: str
    subject_matches: list[str]
    new_since_review: bool


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, check=False, timeout=300)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip() or f"git {args[0]} fehlgeschlagen")
    return result.stdout.decode("utf-8", errors="replace")


def resolve_commit(ref: str) -> str:
    return git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").strip()


def log_records(ref: str, format_string: str, width: int) -> list[list[str]]:
    fields = git("log", "-z", f"--format={format_string}", ref, "--").split("\0")[:-1]
    if len(fields) % width:
        raise ValueError("Git-Commit-Metadaten konnten nicht gelesen werden")
    return [fields[index : index + width] for index in range(0, len(fields), width)]


def compare(printops: str, upstream: str, reviewed: str) -> tuple[list[Commit], int, int, str]:
    if git("rev-parse", "--is-shallow-repository").strip() == "true":
        raise ValueError("Der Abgleich benötigt die vollständige Git-Historie (fetch-depth: 0)")
    git("merge-base", "--is-ancestor", reviewed, upstream)
    common = git("merge-base", printops, upstream).strip()
    own_count = int(git("rev-list", "--count", f"{upstream}..{printops}"))
    new_shas = set(git("rev-list", f"{reviewed}..{upstream}").splitlines())
    patches = {}
    for line in git("cherry", printops, upstream).splitlines():
        marker, sha = line.split()
        patches[sha] = "identischer_patch" if marker == "-" else "kein_identischer_patch"
    subjects: dict[str, list[str]] = {}
    for sha, subject in log_records(printops, "%H%x00%s", 2):
        subjects.setdefault(subject, []).append(sha)
    commits = []
    for sha, parent_string, date, subject in log_records(f"{printops}..{upstream}", "%H%x00%P%x00%cI%x00%s", 4):
        parents = parent_string.split()
        revisions = [parents[0], sha] if parents else ["--root", sha]
        paths = git("diff-tree", "-r", "--no-commit-id", "--no-renames", "--name-only", "-z", *revisions, "--")
        commits.append(
            Commit(
                sha=sha,
                parents=parents,
                date=date,
                subject=subject,
                paths=paths.split("\0")[:-1],
                patch_status="merge_nicht_geprueft" if len(parents) > 1 else patches[sha],
                subject_matches=subjects.get(subject, []),
                new_since_review=sha in new_shas,
            )
        )
    return commits, own_count, len(new_shas), common


def cell(value: str, limit: int | None = None) -> str:
    value = value.replace("\r", " ").replace("\n", " ")
    if limit and len(value) > limit:
        value = value[: limit - 1] + "…"
    value = html.escape(value, quote=False)
    for character, entity in (
        ("\\", "&#92;"),
        ("|", "&#124;"),
        ("`", "&#96;"),
        ("[", "&#91;"),
        ("]", "&#93;"),
        ("*", "&#42;"),
        ("_", "&#95;"),
    ):
        value = value.replace(character, entity)
    return value


def commit_table(commits: list[Commit], *, compact: bool) -> list[str]:
    lines = [
        "| Commit | Datum | Änderung | Dateien | Patch-Abgleich | Gleicher Betreff (nur Indiz) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for commit in commits:
        paths = ", ".join(commit.paths[:3] if compact else commit.paths)
        if compact and len(commit.paths) > 3:
            paths += f" (+{len(commit.paths) - 3})"
        subject = cell(commit.subject, 180 if compact else None)
        if len(commit.parents) > 1:
            subject = "**Merge:** " + subject
        link = f"[`{commit.sha[:9]}`](https://github.com/{UPSTREAM_REPOSITORY}/commit/{commit.sha})"
        lines.append(
            f"| {link} | {cell(commit.date[:10])} | {subject} | {cell(paths, 150 if compact else None)} "
            f"| {PATCH_LABELS[commit.patch_status]} | {'ja' if commit.subject_matches else 'nein'} |"
        )
    return lines


def write_reports(
    output: Path,
    commits: list[Commit],
    *,
    printops: str,
    upstream: str,
    reviewed: str,
    common: str,
    own_count: int,
    new_count: int,
    repository: str,
    review_document: str,
    summary_limit: int,
) -> None:
    new = [commit for commit in commits if commit.new_since_review]
    historical = [commit for commit in commits if not commit.new_since_review]
    # Keep individual changes visible before duplicate merge envelopes and identical patches.
    new.sort(key=lambda commit: (len(commit.parents) > 1, commit.patch_status == "identischer_patch"))
    new_without_patch = sum(commit.patch_status == "kein_identischer_patch" for commit in new)
    equivalent = sum(commit.patch_status == "identischer_patch" for commit in commits)
    merges = sum(len(commit.parents) > 1 for commit in commits)
    review_url = f"https://github.com/{repository}/blob/{printops}/{quote(review_document, safe='/')}"
    introduction = [
        "# PrintOps / Bambuddy: automatischer Commit-Abgleich",
        "",
        f"Erstellt: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Git-Unterschiede sind keine fehlenden Funktionen. Eigene Implementierungen und angepasste Ports "
        "können andere Commit-IDs und Patches haben. Ein gleicher Betreff ist nur ein Indiz; "
        "ein identischer Patch bestätigt weder spätere Änderungen noch vollständige Funktionsgleichheit.",
        "",
        "| Vergleichsstand | Commit |",
        "| --- | --- |",
        f"| PrintOps | [`{printops[:9]}`](https://github.com/{repository}/commit/{printops}) |",
        f"| Bambuddy | [`{upstream[:9]}`](https://github.com/{UPSTREAM_REPOSITORY}/commit/{upstream}) |",
        f"| Letzter fachlich geprüfter Bambuddy-Stand | `{reviewed}` |",
        f"| Gemeinsamer Git-Vorfahr | `{common}` |",
        "",
        f"Der [dokumentierte fachliche Umsetzungsstand]({review_url}) erklärt die bereits bewerteten Änderungen. "
        "Die Prüfbasis wird erst nach einem fachlichen Abgleich aktualisiert, nicht durch einen Wochenlauf.",
        "",
        "| Kennzahl | Anzahl |",
        "| --- | ---: |",
        f"| Neue Bambuddy-Commits seit der Prüfbasis (einschließlich Merges) | {new_count} |",
        f"| Davon mit abweichender Git-Ancestry zu PrintOps | {len(new)} |",
        f"| Davon Nicht-Merges ohne identischen Patch (fachlich prüfen) | {new_without_patch} |",
        f"| Gesamte Bambuddy-Divergenz | {len(commits)} |",
        f"| Davon Merge-Commits (kein Patch-Abgleich) | {merges} |",
        f"| Davon mit identischem Patch in PrintOps | {equivalent} |",
        f"| Historische Divergenz bis einschließlich Prüfbasis | {len(historical)} |",
        f"| Eigene divergierende PrintOps-Commits | {own_count} |",
        "",
        "## Neue divergierende Bambuddy-Commits seit der Prüfbasis",
        "",
    ]
    if new:
        full = introduction + commit_table(new, compact=False)
        summary = introduction + commit_table(new[:summary_limit], compact=True)
        if len(new) > summary_limit:
            summary += ["", f"{len(new) - summary_limit} weitere neue Commits stehen vollständig im Download."]
    else:
        full = introduction + ["Keine neuen divergierenden Bambuddy-Commits seit der Prüfbasis."]
        summary = full.copy()
    full += ["", "## Historische Git-Unterschiede bis zur Prüfbasis", ""]
    if historical:
        full += [
            "Bereits vom historischen Abgleich erfasst; die Ancestry-Divergenz belegt keine offene Funktionslücke.",
            "",
        ]
        full += commit_table(historical, compact=False)
    else:
        full += ["Keine historischen divergierenden Commits."]
    summary += [
        "",
        "Das Berichtspaket enthält `report.md` mit allen Commit-Details "
        "und `commits.csv` mit sämtlichen divergierenden Commits und betroffenen Pfaden.",
    ]
    notification = [
        "PrintOps / Bambuddy: Wochenabgleich",
        f"Neue divergierende Commits: {len(new)}",
        f"Ohne identischen Patch: {new_without_patch} (fachlich prüfen)",
        f"Historische Git-Unterschiede: {len(historical)}",
        f"PrintOps: {printops[:9]} | Bambuddy: {upstream[:9]}",
        "Git-Unterschiede bedeuten nicht automatisch fehlende Funktionen.",
        "Vollständiger Markdown-/CSV-Bericht im ZIP.",
    ]
    if new:
        notification += ["", "Neueste individuelle Änderungen:"]
        for commit in [commit for commit in new if len(commit.parents) <= 1][:3]:
            subject = commit.subject.replace("\r", " ").replace("\n", " ")[:100]
            notification.append(f"• {commit.sha[:9]}: {subject}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.md").write_text("\n".join(full) + "\n", encoding="utf-8")
    (output / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    (output / "notification.txt").write_text("\n".join(notification) + "\n", encoding="utf-8")
    manifest = {
        "schema": 1,
        "repository": repository,
        "printops": printops,
        "upstream": upstream,
        "reviewed": reviewed,
        "entries": [
            {
                "sha": commit.sha,
                "subject": commit.subject,
                "paths": commit.paths,
                "patch_status": commit.patch_status,
                "subject_matches": commit.subject_matches,
            }
            for commit in new
        ],
    }
    (output / "selection.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "commits.csv").open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(
            [
                "sha",
                "typ",
                "committer_datum",
                "betreff",
                "geaenderte_pfade",
                "seit_letztem_fachlichen_abgleich",
                "patch_abgleich",
                "identischer_betreff_in_printops_nur_indiz",
                "printops_commits_mit_identischem_betreff",
                "upstream_link",
            ]
        )
        for commit in commits:
            writer.writerow(
                [
                    commit.sha,
                    "Merge" if len(commit.parents) > 1 else "Nicht-Merge",
                    commit.date,
                    commit.subject,
                    "\n".join(commit.paths),
                    "ja" if commit.new_since_review else "nein",
                    commit.patch_status,
                    "ja" if commit.subject_matches else "nein",
                    "\n".join(commit.subject_matches),
                    f"https://github.com/{UPSTREAM_REPOSITORY}/commit/{commit.sha}",
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "tools" / "upstream-comparison.json")
    parser.add_argument("--printops-ref", default="HEAD")
    parser.add_argument("--upstream-ref", default="upstream/main")
    parser.add_argument("--printops-repository", default="ichwars/PrintOps")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--summary-limit", type=int, default=40)
    args = parser.parse_args()
    try:
        if not 1 <= args.summary_limit <= 200:
            raise ValueError("summary-limit muss zwischen 1 und 200 liegen")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.printops_repository):
            raise ValueError("Ungültiges PrintOps-GitHub-Repository")
        config = json.loads(args.config.read_text(encoding="utf-8"))
        reviewed_ref = config["reviewed_upstream_commit"]
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", reviewed_ref):
            raise ValueError("Die Prüfbasis muss eine vollständige Commit-ID sein")
        review_document = config["review_document"]
        path = PurePosixPath(review_document)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Das Abgleichdokument muss ein relativer Repository-Pfad sein")
        printops = resolve_commit(args.printops_ref)
        upstream = resolve_commit(args.upstream_ref)
        reviewed = resolve_commit(reviewed_ref)
        commits, own_count, new_count, common = compare(printops, upstream, reviewed)
        write_reports(
            args.output_dir,
            commits,
            printops=printops,
            upstream=upstream,
            reviewed=reviewed,
            common=common,
            own_count=own_count,
            new_count=new_count,
            repository=args.printops_repository,
            review_document=review_document,
            summary_limit=args.summary_limit,
        )
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Abgleich fehlgeschlagen: {error}", file=sys.stderr)
        return 1
    print(f"{len(commits)} divergierende Bambuddy-Commits; Bericht: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
