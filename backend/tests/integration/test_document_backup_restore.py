from __future__ import annotations

import json
import sqlite3
from hashlib import sha256

import pytest

from backend.app.services.github_backup import GitHubBackupService
from backend.app.services.local_backup import (
    stage_document_evidence,
    verify_restored_document_artifacts,
)


def _evidence_database(path, artifacts: list[tuple[int, str, bytes]]) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """CREATE TABLE document_artifacts (
        id INTEGER PRIMARY KEY,
        storage_path TEXT,
        content BLOB,
        sha256 TEXT NOT NULL,
        validation_status TEXT NOT NULL,
        validation_report JSON NOT NULL
        )"""
    )
    for artifact_id, storage_path, expected in artifacts:
        connection.execute(
            "INSERT INTO document_artifacts VALUES (?, ?, NULL, ?, 'valid', ?)",
            (artifact_id, storage_path, sha256(expected).hexdigest(), json.dumps({"valid": True})),
        )
    connection.commit()
    connection.close()


def test_backup_stages_artifacts_and_pinned_ruleset_manifest(tmp_path):
    data_dir = tmp_path / "data"
    artifact = data_dir / "document-artifacts" / "42" / "invoice.xml"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"<Invoice/>")
    staging = tmp_path / "staging"
    staging.mkdir()

    stage_document_evidence(staging, data_dir)

    assert (staging / "document-artifacts" / "42" / "invoice.xml").read_bytes() == b"<Invoice/>"
    manifest = json.loads(
        (staging / "document-evidence" / "ruleset-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["en16931"]["version"] == "1.3.16"
    assert manifest["xrechnung"] == {"version": "3.0.2", "bundle_date": "2026-01-31"}
    assert manifest["zugferd"]["version"] == "2.5"


def test_restore_verifies_hashes_and_never_leaves_broken_artifacts_valid(tmp_path):
    good = b"<Invoice id='good'/>"
    missing = b"<Invoice id='missing'/>"
    corrupt = b"<Invoice id='original'/>"
    _evidence_database(
        tmp_path / "printops.db",
        [
            (1, "document-artifacts/1/good.xml", good),
            (2, "document-artifacts/2/missing.xml", missing),
            (3, "document-artifacts/3/corrupt.xml", corrupt),
        ],
    )
    good_path = tmp_path / "document-artifacts" / "1" / "good.xml"
    corrupt_path = tmp_path / "document-artifacts" / "3" / "corrupt.xml"
    good_path.parent.mkdir(parents=True)
    corrupt_path.parent.mkdir(parents=True)
    good_path.write_bytes(good)
    corrupt_path.write_bytes(b"tampered")

    issues = verify_restored_document_artifacts(tmp_path, tmp_path / "printops.db")

    assert [(item["artifact_id"], item["code"]) for item in issues] == [
        (2, "artifact_file_missing"),
        (3, "artifact_hash_mismatch"),
    ]
    connection = sqlite3.connect(tmp_path / "printops.db")
    rows = connection.execute(
        "SELECT id, validation_status, validation_report FROM document_artifacts ORDER BY id"
    ).fetchall()
    connection.close()
    assert rows[0][1] == "valid"
    assert rows[1][1] == rows[2][1] == "invalid"
    assert json.loads(rows[1][2])["restore_integrity"]["code"] == "artifact_file_missing"
    assert json.loads(rows[2][2])["valid"] is False


def test_restore_accepts_legacy_backup_without_document_tables(tmp_path):
    connection = sqlite3.connect(tmp_path / "printops.db")
    connection.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    connection.commit()
    connection.close()

    assert verify_restored_document_artifacts(tmp_path, tmp_path / "printops.db") == []


@pytest.mark.asyncio
async def test_private_git_backup_exports_every_commercial_evidence_table(db_session):
    files: dict = {}

    await GitHubBackupService()._collect_commercial_evidence(db_session, files)

    expected_tables = {
        "number_sequences",
        "document_configurations",
        "document_snapshots",
        "document_artifacts",
        "document_number_reservations",
        "document_audit_events",
    }
    assert expected_tables <= {
        value["table"]
        for name, value in files.items()
        if name.startswith("documents/tables/")
    }
    assert files["documents/ruleset-manifest.json"]["xrechnung"]["bundle_date"] == "2026-01-31"
    assert files["documents/evidence-manifest.json"]["artifact_storage"] == "content-addressed/base64"
