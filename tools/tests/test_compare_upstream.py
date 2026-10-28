"""Exercise the report CLI against real, isolated Git histories."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPORT_SCRIPT = Path(__file__).resolve().parents[1] / "compare_upstream.py"


class UpstreamComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_DATE": "2026-10-01T10:00:00+00:00",
            "GIT_COMMITTER_DATE": "2026-10-01T10:00:00+00:00",
        }
        self.git("init", "-b", "printops")
        self.git("config", "user.name", "Report Test")
        self.git("config", "user.email", "test@example.invalid")
        self.base = self.commit("README.md", "shared\n", "Shared base")
        self.git("branch", "bambuddy")
        self.config = self.root / "config.json"
        self.write_config(self.base)
        self.output = self.root / "report"

    def git(self, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=self.repo, env=self.env, text=True, capture_output=True, check=True)
        return result.stdout.strip()

    def commit(self, filename: str, content: str, subject: str) -> str:
        path = self.repo / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.git("add", "--", filename)
        self.git("commit", "-m", subject)
        return self.git("rev-parse", "HEAD")

    def write_config(self, reviewed: str) -> None:
        self.config.write_text(
            json.dumps(
                {
                    "reviewed_upstream_commit": reviewed,
                    "review_document": "docs/upstream-implementation-2026-10-11.md",
                }
            ),
            encoding="utf-8",
        )

    def run_report(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(REPORT_SCRIPT),
                "--config",
                str(self.config),
                "--printops-ref",
                "printops",
                "--upstream-ref",
                "bambuddy",
                "--printops-repository",
                "example/PrintOps",
                "--output-dir",
                str(self.output),
                *extra,
            ],
            cwd=self.repo,
            env=self.env,
            text=True,
            capture_output=True,
        )

    def rows(self) -> list[dict[str, str]]:
        with (self.output / "commits.csv").open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source))

    def test_reports_new_changes_and_preserves_the_reviewed_backlog(self) -> None:
        self.commit("commerce.py", "own\n", "PrintOps commerce")
        self.git("checkout", "bambuddy")
        reviewed = self.commit("old.py", "old\n", "Previously reviewed fix")
        self.write_config(reviewed)
        newer = self.commit("backend/queue.py", "new\n", "Fix queue | dispatch <details>")

        result = self.run_report()

        self.assertEqual(result.returncode, 0, result.stderr)
        rows = {row["sha"]: row for row in self.rows()}
        self.assertEqual(set(rows), {reviewed, newer})
        self.assertEqual(rows[reviewed]["seit_letztem_fachlichen_abgleich"], "nein")
        self.assertEqual(rows[newer]["seit_letztem_fachlichen_abgleich"], "ja")
        self.assertEqual(rows[newer]["patch_abgleich"], "kein_identischer_patch")
        self.assertEqual(rows[newer]["geaenderte_pfade"], "backend/queue.py")
        summary = (self.output / "summary.md").read_text(encoding="utf-8")
        self.assertIn(newer, summary)
        self.assertNotIn("Previously reviewed fix", summary)
        self.assertIn("Fix queue &#124; dispatch &lt;details&gt;", summary)
        report = (self.output / "report.md").read_text(encoding="utf-8")
        self.assertIn("Previously reviewed fix", report)
        self.assertIn("https://github.com/example/PrintOps/commit/", report)
        self.assertIn("https://github.com/maziggy/bambuddy/commit/" + newer, report)
        self.assertIn("keine fehlenden Funktionen", report)
        notification = (self.output / "notification.txt").read_text(encoding="utf-8")
        self.assertIn("Neue divergierende Commits: 1", notification)
        self.assertIn("Ohne identischen Patch: 1", notification)
        self.assertIn("Historische Git-Unterschiede: 1", notification)

    def test_detects_identical_patches_with_different_subjects_and_shas(self) -> None:
        self.git("checkout", "bambuddy")
        upstream = self.commit("fix.py", "fixed\n", "Upstream fix")
        self.git("checkout", "printops")
        self.git("cherry-pick", upstream)
        self.git("commit", "--amend", "-m", "Port upstream fix")
        port = self.git("rev-parse", "HEAD")
        self.assertNotEqual(upstream, port)

        result = self.run_report()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows()[0]["patch_abgleich"], "identischer_patch")
        self.assertEqual(self.rows()[0]["identischer_betreff_in_printops_nur_indiz"], "nein")

    def test_subject_match_does_not_claim_patch_equivalence(self) -> None:
        own = self.commit("own.py", "own implementation\n", "Fix printer")
        self.git("checkout", "bambuddy")
        self.commit("upstream.py", "different implementation\n", "Fix printer")

        result = self.run_report()

        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.rows()[0]
        self.assertEqual(row["patch_abgleich"], "kein_identischer_patch")
        self.assertEqual(row["identischer_betreff_in_printops_nur_indiz"], "ja")
        self.assertEqual(row["printops_commits_mit_identischem_betreff"], own)

    def test_merge_commits_keep_the_first_parent_paths_and_are_not_patch_checked(self) -> None:
        self.git("checkout", "bambuddy")
        self.commit("main.py", "main\n", "Main change")
        self.git("checkout", "-b", "topic")
        self.commit("feature.py", "feature\n", "Topic feature")
        self.git("checkout", "bambuddy")
        self.git("merge", "--no-ff", "topic", "-m", "Merge topic")
        merged = self.git("rev-parse", "HEAD")

        result = self.run_report()

        self.assertEqual(result.returncode, 0, result.stderr)
        row = next(row for row in self.rows() if row["sha"] == merged)
        self.assertEqual(row["typ"], "Merge")
        self.assertEqual(row["patch_abgleich"], "merge_nicht_geprueft")
        self.assertEqual(row["geaenderte_pfade"], "feature.py")

    def test_ancestry_integrated_commits_are_not_listed_as_differences(self) -> None:
        self.git("checkout", "bambuddy")
        self.commit("integrated.py", "integrated\n", "Integrated change")
        self.git("checkout", "printops")
        self.git("merge", "--ff-only", "bambuddy")

        result = self.run_report()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows(), [])
        self.assertIn("Keine neuen divergierenden", (self.output / "summary.md").read_text(encoding="utf-8"))

    def test_reports_root_commits_from_an_unrelated_history_merged_into_upstream(self) -> None:
        self.git("checkout", "--orphan", "imported")
        self.git("read-tree", "--empty")
        root = self.commit("imported.py", "imported\n", "Imported history root")
        self.git("checkout", "--force", "bambuddy")
        self.git("merge", "--allow-unrelated-histories", "imported", "-m", "Import unrelated history")

        result = self.run_report()

        self.assertEqual(result.returncode, 0, result.stderr)
        row = next(row for row in self.rows() if row["sha"] == root)
        self.assertEqual(row["typ"], "Nicht-Merge")
        self.assertEqual(row["geaenderte_pfade"], "imported.py")
        self.assertEqual(row["patch_abgleich"], "kein_identischer_patch")
        self.assertEqual(row["seit_letztem_fachlichen_abgleich"], "ja")

    def test_summary_limit_does_not_truncate_downloads(self) -> None:
        self.git("checkout", "bambuddy")
        for index in range(5):
            self.commit(f"change-{index}.py", "change\n", f"Change {index}")

        result = self.run_report("--summary-limit", "2")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.rows()), 5)
        summary = (self.output / "summary.md").read_text(encoding="utf-8")
        full = (self.output / "report.md").read_text(encoding="utf-8")
        self.assertEqual(summary.count("https://github.com/maziggy/bambuddy/commit/"), 3)  # tip and two rows
        self.assertIn("Change 4", summary)
        self.assertIn("Change 3", summary)
        self.assertNotIn("Change 0", summary)
        self.assertIn("Change 0", full)
        self.assertIn("3 weitere", summary)

    def test_handles_unicode_and_newlines_in_filenames_without_losing_csv_data(self) -> None:
        self.git("checkout", "bambuddy")
        self.commit("frontend/ä,|\nname.py", "change\n", "Unicode ü and `markup` [link]")

        result = self.run_report()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows()[0]["geaenderte_pfade"], "frontend/ä,|\nname.py")
        summary = (self.output / "summary.md").read_text(encoding="utf-8")
        self.assertIn("Unicode ü and &#96;markup&#96; &#91;link&#93;", summary)
        self.assertIn("frontend/ä,&#124; name.py", summary)

    def test_rejects_missing_or_rewritten_review_baseline_without_a_success_report(self) -> None:
        own = self.commit("own.py", "own\n", "Only on PrintOps")
        for reviewed in ("0" * 40, own):
            with self.subTest(reviewed=reviewed):
                self.write_config(reviewed)
                result = self.run_report()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Abgleich fehlgeschlagen", result.stderr)
                self.assertFalse((self.output / "summary.md").exists())

    def test_rejects_shallow_history(self) -> None:
        shallow = self.git("rev-parse", "--git-path", "shallow")
        (self.repo / shallow).write_text(self.base + "\n", encoding="utf-8")

        result = self.run_report()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("vollständige Git-Historie", result.stderr)
        self.assertFalse((self.output / "summary.md").exists())


if __name__ == "__main__":
    unittest.main()
