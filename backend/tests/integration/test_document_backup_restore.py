from __future__ import annotations

import json
import sqlite3
from hashlib import sha256

import pytest

from backend.app.services.github_backup import GitHubBackupService
from backend.app.services.local_backup import (
    restore_document_evidence_files,
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


def test_backup_manifest_covers_layout_pdf_and_validation_evidence(tmp_path):
    data_dir = tmp_path / "data"
    evidence = {
        "document-layout-assets/logo.bin": b"logo",
        "document-render-artifacts/7/document.pdf": b"pdf",
        "document-validation-reports/report.xml": b"report",
    }
    for relative, content in evidence.items():
        target = data_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    staging = tmp_path / "staging"
    staging.mkdir()

    stage_document_evidence(staging, data_dir)

    manifest = json.loads(
        (staging / "document-evidence" / "document-layout-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    entries = {item["path"]: item for item in manifest["files"]}
    assert set(entries) == set(evidence)
    for relative, content in evidence.items():
        assert entries[relative]["sha256"] == sha256(content).hexdigest()
        assert entries[relative]["size"] == len(content)


def test_restore_reports_tampered_manifest_file_for_legacy_database(tmp_path):
    connection = sqlite3.connect(tmp_path / "printops.db")
    connection.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    connection.commit()
    connection.close()
    data_dir = tmp_path / "source"
    pdf = data_dir / "document-render-artifacts" / "9" / "evidence.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"original")
    stage_document_evidence(tmp_path, data_dir)
    (tmp_path / "document-render-artifacts" / "9" / "evidence.pdf").write_bytes(b"tampered")

    issues = verify_restored_document_artifacts(tmp_path, tmp_path / "printops.db")

    assert issues[0]["code"] == "manifest_hash_mismatch"
    assert issues[0]["evidence_type"] == "rendered_pdf"


def test_manifest_restore_is_atomic_and_never_overwrites_different_evidence(tmp_path):
    backup = tmp_path / "backup"
    backup.mkdir()
    connection = sqlite3.connect(backup / "printops.db")
    connection.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    connection.commit()
    connection.close()
    source_data = tmp_path / "source"
    incoming = source_data / "document-render-artifacts" / "9" / "invoice.pdf"
    incoming.parent.mkdir(parents=True)
    incoming.write_bytes(b"incoming-pdf")
    stage_document_evidence(backup, source_data)

    destination = tmp_path / "destination"
    current = destination / "document-render-artifacts" / "9" / "invoice.pdf"
    current.parent.mkdir(parents=True)
    current.write_bytes(b"current-pdf")
    issues = verify_restored_document_artifacts(
        backup,
        backup / "printops.db",
        destination_root=destination,
    )

    report = restore_document_evidence_files(backup, destination, issues)

    assert current.read_bytes() == b"current-pdf"
    assert issues[0]["code"] == "restore_destination_conflict"
    assert report["status"] == "invalid"
    assert report["conflicts"] == 1
    quarantined = list((destination / "document-restore-conflicts").rglob("invoice.pdf"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"incoming-pdf"


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
        "document_layout_configurations",
        "document_layout_assets",
        "document_layout_publications",
        "document_layout_audit_receipts",
        "layout_page_rules",
        "layout_footer_rules",
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
    assert files["documents/evidence-manifest.json"]["artifact_storage"] == "content-addressed/binary"
    assert files[".gitattributes"] == b"documents/binary/** -text\n"
