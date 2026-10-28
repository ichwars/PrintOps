"""Test local Git orchestration and Telegram uploads without external services."""

from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

import test_compare_upstream as history_tests

RUNNER_SCRIPT = Path(__file__).resolve().parents[1] / "run_upstream_comparison.py"
TOKEN = "123456:TEST_TOKEN"


def load_runner():
    if not RUNNER_SCRIPT.exists():
        raise AssertionError("The local comparison runner has not been implemented")
    spec = importlib.util.spec_from_file_location("local_upstream_runner", RUNNER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", [str(RUNNER_SCRIPT.parent), *sys.path]):
        spec.loader.exec_module(module)
    return module


class TelegramServerMixin:
    def start_server(self, response=None, status=200, extra_headers=None):
        captured = []
        response = response if response is not None else {"ok": True, "result": {"message_id": 1}}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                message = BytesParser(policy=default).parsebytes(
                    f"Content-Type: {self.headers['Content-Type']}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
                )
                captured.append((self.path, message))
                payload = response if isinstance(response, bytes) else json.dumps(response).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                for name, value in (extra_headers or {}).items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.addCleanup(cleanup)
        return f"http://127.0.0.1:{server.server_port}", captured


class LocalRunnerTests(TelegramServerMixin, unittest.TestCase):
    def setUp(self):
        self.history = history_tests.UpstreamComparisonTests()
        self.history.setUp()
        self.addCleanup(self.history.doCleanups)
        self.root = self.history.root
        self.history.commit("commerce.py", "own\n", "PrintOps commerce")
        self.history.git("checkout", "bambuddy")
        self.upstream_sha = self.history.commit("queue.py", "fix\n", "Fix queue dispatch")
        self.printops_remote = self.root / "printops.git"
        self.upstream_remote = self.root / "upstream.git"
        for branch, remote in (("printops", self.printops_remote), ("bambuddy", self.upstream_remote)):
            self.history.git(
                "clone", "--bare", "--single-branch", "--branch", branch, str(self.history.repo), str(remote)
            )
            subprocess.run(
                ["git", "-C", str(remote), "branch", "-m", "main"],
                check=True,
                capture_output=True,
                env=self.history.env,
            )
        self.state = self.root / "state"
        self.env = {key: value for key, value in self.history.env.items() if not key.startswith("TELEGRAM_")}
        self.args = [
            "--config",
            str(self.history.config),
            "--state-dir",
            str(self.state),
            "--printops-url",
            str(self.printops_remote),
            "--upstream-url",
            str(self.upstream_remote),
        ]

    def run_cli(self, *extra, env=None):
        return subprocess.run(
            [sys.executable, str(RUNNER_SCRIPT), *self.args, *extra],
            cwd=self.history.repo,
            env=env or self.env,
            capture_output=True,
            text=True,
        )

    def test_dry_run_fetches_real_histories_and_packages_every_report_without_credentials(self):
        before = self.history.git("rev-parse", "HEAD")
        result = self.run_cli("--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        archives = list(self.state.glob("reports/*/bambuddy-comparison.zip"))
        self.assertEqual(len(archives), 1)
        with zipfile.ZipFile(archives[0]) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {
                    "report.md",
                    "commits.csv",
                    "summary.md",
                    "notification.txt",
                    "selection.json",
                    "numbered-selection.json",
                },
            )
            rows = list(csv.DictReader(io.StringIO(archive.read("commits.csv").decode())))
            self.assertEqual([row["sha"] for row in rows], [self.upstream_sha])
            self.assertIn("Fix queue dispatch", archive.read("report.md").decode())
            self.assertIn("Neue divergierende Commits: 1", archive.read("notification.txt").decode())
        self.assertEqual(self.history.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.history.git("status", "--porcelain"), "")
        self.assertEqual(archives[0].stat().st_mode & 0o077, 0)

    def test_missing_credentials_fail_before_fetching(self):
        result = self.run_cli()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TELEGRAM_BOT_TOKEN", result.stderr)
        self.assertIn("TELEGRAM_CHAT_ID", result.stderr)
        self.assertFalse(self.state.exists())

    def test_fetch_failure_does_not_turn_an_old_report_into_a_new_success(self):
        first = self.run_cli("--dry-run")
        self.assertEqual(first.returncode, 0, first.stderr)
        result = self.run_cli("--dry-run", "--upstream-url", str(self.root / "missing.git"))

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(list(self.state.glob("reports/*/bambuddy-comparison.zip"))), 1)
        self.assertIn("fehlgeschlagen", result.stderr)

    def test_invalid_review_baseline_does_not_package_a_success(self):
        self.history.write_config("0" * 40)
        result = self.run_cli("--dry-run")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.state.glob("reports/*/bambuddy-comparison.zip")), [])
        self.assertIn("Abgleich fehlgeschlagen", result.stderr)

    def test_numbered_mode_requires_explicit_permissions_before_any_fetch_or_send(self):
        env = {**self.env, "TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "-100123"}
        for extra, expected in [
            ({}, "TELEGRAM_ALLOWED_USER_IDS"),
            ({"TELEGRAM_ALLOWED_USER_IDS": "77"}, "GITHUB_TOKEN"),
        ]:
            with self.subTest(expected=expected):
                result = self.run_cli("--numbered", env={**env, **extra})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertFalse(self.state.exists())

    def test_complete_run_delivers_the_current_zip_to_the_selected_telegram_chat(self):
        runner = load_runner()
        base_url, captured = self.start_server()
        with (
            patch.dict(
                os.environ,
                {
                    **self.env,
                    "TELEGRAM_BOT_TOKEN": TOKEN,
                    "TELEGRAM_CHAT_ID": "-100123",
                    "TELEGRAM_THREAD_ID": "42",
                    "TELEGRAM_ALLOWED_USER_IDS": "77",
                    "GITHUB_TOKEN": "TEST_GITHUB_TOKEN",
                },
                clear=True,
            ),
            patch.object(runner, "TELEGRAM_API_ROOT", base_url),
            patch.object(runner, "Telegram"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = runner.main([*self.args, "--numbered"])

        self.assertEqual(result, 0)
        self.assertEqual(len(captured), 1)
        request_path, message = captured[0]
        self.assertEqual(request_path, f"/bot{TOKEN}/sendDocument")
        fields = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
        self.assertEqual(fields["chat_id"].get_payload(decode=True), b"-100123")
        self.assertEqual(fields["message_thread_id"].get_payload(decode=True), b"42")
        self.assertIn("Neue divergierende Commits: 1", fields["caption"].get_payload(decode=True).decode())
        with zipfile.ZipFile(io.BytesIO(fields["document"].get_payload(decode=True))) as archive:
            self.assertIn(self.upstream_sha, archive.read("commits.csv").decode())

    def test_existing_report_can_be_delivered_without_refetching(self):
        result = self.run_cli("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        report_dir = next(self.state.glob("reports/*"))
        # Pre-existing four-file reports must remain resendable in the existing ZIP-only mode.
        (report_dir / "selection.json").unlink()
        (report_dir / "numbered-selection.json").unlink()
        runner = load_runner()
        base_url, captured = self.start_server()
        args = [*self.args, "--send-existing", str(report_dir), "--upstream-url", str(self.root / "missing.git")]
        with (
            patch.dict(
                os.environ, {**self.env, "TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "-100123"}, clear=True
            ),
            patch.object(runner, "TELEGRAM_API_ROOT", base_url),
            patch.object(runner, "Telegram") as telegram,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(runner.main(args), 0)
        self.assertEqual(len(captured), 1)
        telegram.assert_not_called()


class TelegramUploadTests(TelegramServerMixin, unittest.TestCase):
    def setUp(self):
        self.runner = load_runner()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / "report.zip"
        with zipfile.ZipFile(self.archive, "w") as target:
            target.writestr("report.md", "Complete report ü")

    def test_upload_preserves_file_bytes_and_keeps_caption_plain_and_within_telegram_limit(self):
        base_url, captured = self.start_server()
        caption = "Special <markup> `and` _characters_ " + "😀" * 1500
        with patch.object(self.runner, "TELEGRAM_API_ROOT", base_url):
            self.runner.send_telegram(TOKEN, "-100123", self.archive, caption)

        _, message = captured[0]
        fields = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
        self.assertNotIn("parse_mode", fields)
        self.assertEqual(fields["document"].get_payload(decode=True), self.archive.read_bytes())
        uploaded_caption = fields["caption"].get_payload(decode=True).decode()
        self.assertTrue(uploaded_caption.startswith("Special <markup> `and` _characters_"))
        self.assertLessEqual(len(uploaded_caption.encode("utf-16-le")) // 2, 1024)

    def test_telegram_api_failure_is_not_treated_as_delivery_success(self):
        base_url, _ = self.start_server({"ok": False, "error_code": 403, "description": "bot blocked " + TOKEN})
        with patch.object(self.runner, "TELEGRAM_API_ROOT", base_url), self.assertRaises(ValueError) as raised:
            self.runner.send_telegram(TOKEN, "-100123", self.archive, "caption")
        self.assertIn("403", str(raised.exception))
        self.assertNotIn(TOKEN, str(raised.exception))

    def test_http_failure_redacts_the_token(self):
        base_url, _ = self.start_server({"ok": False, "description": TOKEN}, status=401)
        with patch.object(self.runner, "TELEGRAM_API_ROOT", base_url), self.assertRaises(ValueError) as raised:
            self.runner.send_telegram(TOKEN, "-100123", self.archive, "caption")
        self.assertIn("401", str(raised.exception))
        self.assertNotIn(TOKEN, str(raised.exception))

    def test_upload_refuses_redirects_instead_of_forwarding_to_another_target(self):
        headers = {}
        base_url, captured = self.start_server(status=302, extra_headers=headers)
        headers["Location"] = base_url + "/redirect-target"
        with patch.object(self.runner, "TELEGRAM_API_ROOT", base_url), self.assertRaises(ValueError) as raised:
            self.runner.send_telegram(TOKEN, "-100123", self.archive, "caption")
        self.assertIn("302", str(raised.exception))
        self.assertEqual(len(captured), 1)

    def test_malformed_api_response_fails(self):
        base_url, _ = self.start_server(b"not JSON")
        with patch.object(self.runner, "TELEGRAM_API_ROOT", base_url), self.assertRaises(ValueError):
            self.runner.send_telegram(TOKEN, "-100123", self.archive, "caption")

    def test_oversized_archives_fail_before_upload(self):
        with self.archive.open("wb") as target:
            target.truncate(50_000_001)
        with self.assertRaises(ValueError) as raised:
            self.runner.send_telegram(TOKEN, "-100123", self.archive, "caption")
        self.assertIn("50 MB", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
