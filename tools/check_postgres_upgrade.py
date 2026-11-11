"""Compare PostgreSQL upgrades from tagged PrintOps releases with a fresh install."""

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.tests.postgres.suite_databases import _manage_databases, local_postgres_url

REPO = Path(__file__).resolve().parents[1]
BASELINES = ("v1.2.8.1", "v1.2.8.2")
OBJECT_KINDS = ("column", "constraint", "index", "trigger", "sequence")
_STARTUP = """
import asyncio
from backend.app.core.database import engine, init_db

async def run():
    try:
        await init_db()
    finally:
        await engine.dispose()

asyncio.run(run())
"""

QUERIES = (
    """
    SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
           a.attnotnull, pg_get_expr(d.adbin, d.adrelid), a.attidentity, a.attgenerated
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid
    LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
    WHERE n.nspname = current_schema() AND c.relkind IN ('r','p') AND a.attnum > 0 AND NOT a.attisdropped
    """,
    """
    SELECT c.relname, k.contype, pg_get_constraintdef(k.oid, true), k.convalidated
    FROM pg_constraint k
    JOIN pg_class c ON c.oid = k.conrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = current_schema()
    """,
    """
    SELECT c.relname, i.indisunique, am.amname, i.indnkeyatts, i.indisvalid,
           ARRAY(SELECT pg_get_indexdef(i.indexrelid, col, true) FROM generate_series(1, i.indnatts) col),
           pg_get_expr(i.indpred, i.indrelid)
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indrelid
    JOIN pg_class ix ON ix.oid = i.indexrelid
    JOIN pg_am am ON am.oid = ix.relam
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = current_schema()
    """,
    """
    SELECT c.relname, t.tgname, pg_get_triggerdef(t.oid, true), t.tgenabled
    FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = current_schema() AND NOT t.tgisinternal
    """,
    """
    SELECT sequencename, data_type::text, start_value, min_value, max_value, increment_by, cycle, cache_size
    FROM pg_sequences
    WHERE schemaname = current_schema()
    """,
)


def _extract_release(ref: str, directory: Path) -> Path:
    commit = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    checkout = directory / "checkout"
    checkout.mkdir()
    archive = directory / "backend.tar"
    with archive.open("wb") as handle:
        subprocess.run(["git", "archive", commit, "backend"], cwd=REPO, check=True, stdout=handle)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(checkout)], check=True)
    archive.unlink()
    return checkout


def _initialize(checkout: Path, url, data: Path) -> None:
    dsn = url.render_as_string(hide_password=False)
    env = dict(
        os.environ,
        PYTHONPATH=str(checkout),
        DATABASE_URL=dsn,
        DATA_DIR=str(data),
        LOG_DIR=str(data / "logs"),
        LOG_TO_FILE="false",
        DEBUG="false",
    )
    result = subprocess.run(
        [sys.executable, "-c", _STARTUP],
        cwd=checkout,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode:
        message = result.stdout.replace(dsn, "[DATABASE_URL]")
        if url.password:
            message = message.replace(url.password, "[REDACTED]")
        detail = "\n".join(message.splitlines()[-20:])
        raise RuntimeError(f"PrintOps database initialization failed ({result.returncode})\n{detail}")


async def _schema(url) -> Counter[tuple[str, str]]:
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.connect() as connection:
            entries: Counter[tuple[str, str]] = Counter()
            for kind, query in zip(OBJECT_KINDS, QUERIES, strict=True):
                rows = await connection.execute(text(query))
                entries.update((kind, repr(tuple(row))) for row in rows)
            return entries
    finally:
        await engine.dispose()


def _compare(label, expected, actual) -> bool:
    if expected == actual:
        print(f"{label}: {expected.total()} schema objects match")
        return True
    for direction, difference in (("missing", expected - actual), ("additional", actual - expected)):
        for (kind, definition), count in sorted(difference.items()):
            print(f"{label}: {direction} {count} {kind} {definition}")
    return False


async def _check(server, baselines: list[str], directory: Path) -> bool:
    prefix = "printops_schema_" + uuid4().hex
    names = [f"{prefix}_{index}" for index in range(len(baselines) + 1)]
    await _manage_databases(server, names, create=True)
    try:
        fresh_url = server.set(database=names[0])
        fresh_data = directory / "fresh"
        _initialize(REPO, fresh_url, fresh_data)
        fresh = await _schema(fresh_url)
        _initialize(REPO, fresh_url, fresh_data)
        checks = [_compare("Fresh installation restart", fresh, await _schema(fresh_url))]
        for index, ref in enumerate(baselines, start=1):
            baseline = directory / f"baseline-{index}"
            baseline.mkdir()
            source = _extract_release(ref, baseline)
            url = server.set(database=names[index])
            data = baseline / "data"
            _initialize(source, url, data)
            _initialize(REPO, url, data)
            upgraded = await _schema(url)
            checks.append(_compare(f"{ref} upgrade", fresh, upgraded))
            _initialize(REPO, url, data)
            checks.append(_compare(f"{ref} restart", upgraded, await _schema(url)))
        return all(checks)
    finally:
        await _manage_databases(server, names, create=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="append", help="tag or commit to upgrade, repeatable")
    arguments = parser.parse_args()
    raw_url = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
    if not raw_url:
        parser.error("set PRINTOPS_POSTGRES_TEST_URL to a local PostgreSQL test server")
    try:
        server = local_postgres_url(raw_url)
        with tempfile.TemporaryDirectory(prefix="printops_schema_check_") as directory:
            passed = asyncio.run(_check(server, arguments.baseline or list(BASELINES), Path(directory)))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
