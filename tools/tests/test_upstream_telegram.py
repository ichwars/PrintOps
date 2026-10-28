"""Number selection, authorization, crash recovery and API contracts without live services."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

import test_run_upstream_comparison as runner_tests

runner_tests.load_runner()
workflow = sys.modules["upstream_telegram"]


def manifest(*shas):
    return {
        "schema": 1,
        "repository": "ichwars/PrintOps",
        "printops": "d" * 40,
        "upstream": "e" * 40,
        "reviewed": "f" * 40,
        "entries": [
            {
                "sha": sha,
                "subject": "Fix printer <markup> @someone",
                "paths": ["backend/queue.py"],
                "patch_status": "kein_identischer_patch",
                "subject_matches": [],
            }
            for sha in shas
        ],
    }


class FakeGitHub:
    def __init__(self):
        self.issues = {}
        self.creations = 0
        self.fail_after_creation = False

    def existing(self):
        return dict(self.issues)

    def create(self, number, document):
        self.creations += 1
        url = f"https://github.com/ichwars/PrintOps/issues/{number + 300}"
        self.issues[document["sha"]] = url
        if self.fail_after_creation:
            raise ValueError("Simulated lost response after GitHub accepted creation")
        return url


class FakeTelegram:
    chat = "-100123"
    thread = 42

    def __init__(self):
        self.messages = []

    def send(self, text, **kwargs):
        self.messages.append((text, kwargs))
        return len(self.messages)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = workflow.Catalog(self.root)
        self.addCleanup(self.catalog.close)
        self.catalog.bind("123456:TEST_TOKEN", "-100123", 42)
        self.catalog.put("accept_since", 100)
        self.entries = self.catalog.register(manifest("a" * 40, "b" * 40))
        self.numbers = [entry["number"] for entry in self.entries]
        self.catalog.publish(self.numbers)
        self.github = FakeGitHub()
        self.telegram = FakeTelegram()

    def update(self, text="1, 2", **changes):
        message = {
            "message_id": 3,
            "date": 101,
            "chat": {"id": -100123},
            "message_thread_id": 42,
            "from": {"id": 77, "is_bot": False},
            "text": text,
            **changes,
        }
        return {"update_id": 10, "message": message}

    def process(self, update):
        workflow.process_update(update, self.catalog, self.telegram, self.github, {77})

    def test_numbers_remain_stable_after_new_report_and_restart(self):
        second = self.catalog.register(manifest("b" * 40, "c" * 40, "a" * 40))
        self.assertEqual(second[0]["number"], self.numbers[1])
        self.assertEqual(second[2]["number"], self.numbers[0])
        self.assertGreater(second[1]["number"], max(self.numbers))
        reopened = workflow.Catalog(self.root)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.selected(self.numbers)[0]["sha"], "a" * 40)
        self.assertEqual((self.root / "selections.sqlite3").stat().st_mode & 0o077, 0)

    def test_selected_numbers_create_one_issue_each_and_reply_with_links(self):
        self.process(self.update("1, 2, 1"))
        self.assertEqual(self.github.creations, 2)
        self.assertIn("issues/301", self.telegram.messages[0][0])
        self.assertIn("issues/302", self.telegram.messages[0][0])
        self.assertEqual(self.telegram.messages[0][1], {"reply_to": 3})
        self.process(self.update("2, 1"))
        self.assertEqual(self.github.creations, 2)
        self.assertIn("vorhanden", self.telegram.messages[-1][0])

    def test_unknown_number_prevents_partial_creation(self):
        self.process(self.update("1, 999"))
        self.assertEqual(self.github.creations, 0)
        self.assertIn("noch nicht veröffentlicht", self.telegram.messages[0][0])

    def test_unpublished_number_is_not_authorized_by_guessing(self):
        entry = self.catalog.register(manifest("c" * 40))[0]
        self.process(self.update(str(entry["number"])))
        self.assertEqual(self.github.creations, 0)

    def test_wrong_user_chat_topic_bot_forward_and_old_messages_never_create_issues(self):
        variants = [
            {"from": {"id": 99, "is_bot": False}},
            {"from": {"id": 77, "is_bot": True}},
            {"from": {"id": 77}},
            {"from": {}},
            {"chat": {"id": -100999}},
            {"message_thread_id": 43},
            {"message_thread_id": None},
            {"sender_chat": {"id": -100123}},
            {"forward_origin": {"type": "user"}},
            {"forward_date": 100},
            {"date": 99},
            {"date": "101"},
        ]
        for changes in variants:
            with self.subTest(changes=changes):
                self.process(self.update(**changes))
        self.process({"update_id": 11, "edited_message": self.update()["message"]})
        self.assertEqual(self.github.creations, 0)
        self.assertEqual(self.telegram.messages, [])

    def test_timeout_after_creation_reconciles_instead_of_creating_twice(self):
        self.github.fail_after_creation = True
        self.process(self.update("1"))
        self.assertEqual(self.github.creations, 1)
        self.assertIn("unklar", self.telegram.messages[-1][0])
        self.process(self.update("1"))
        self.assertEqual(self.github.creations, 1)
        self.assertIn("issues/301", self.telegram.messages[-1][0])

    def test_uncertain_creation_without_server_record_does_not_retry_post(self):
        self.catalog.claim(1)
        self.process(self.update("1"))
        self.assertEqual(self.github.creations, 0)
        self.assertIn("manuell prüfen", self.telegram.messages[-1][0])

    def test_existing_closed_or_manually_linked_issue_is_reused(self):
        self.github.issues["a" * 40] = "https://github.com/ichwars/PrintOps/issues/55"
        self.process(self.update("1"))
        self.assertEqual(self.github.creations, 0)
        self.assertIn("issues/55", self.telegram.messages[-1][0])

    def test_catalog_cannot_be_reused_for_another_chat_bot_or_topic(self):
        for scope in [
            ("123456:TEST_TOKEN", "99", 42),
            ("987654:TEST_TOKEN", "-100123", 42),
            ("123456:TEST_TOKEN", "-100123", None),
        ]:
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                self.catalog.bind(*scope)

    def test_number_parser_rejects_commands_ranges_and_injected_shell_text(self):
        self.assertEqual(workflow.parse_numbers("/issues 2, 5 7"), [2, 5, 7])
        for text in [
            "",
            "0",
            "-1",
            "2-5",
            "1, $(whoami)",
            "1; rm -rf /",
            "１２",
            "1.0",
            None,
            "9" * 1001,
            ",".join(str(i) for i in range(1, 52)),
        ]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                workflow.parse_numbers(text)

    def test_numbered_messages_keep_all_entries_and_obey_unicode_size_limit(self):
        document = manifest(*[f"{i:040x}" for i in range(1, 41)])
        for entry in document["entries"]:
            entry["subject"] = "😀" * 300
            entry["paths"] = ["é" * 300] * 10
        entries = self.catalog.register(document)
        chunks = workflow.numbered_messages(entries)
        self.assertEqual([number for _, numbers in chunks for number in numbers], [e["number"] for e in entries])
        self.assertTrue(all(text and len(text.encode("utf-16-le")) // 2 <= 3500 for text, _ in chunks))

    def test_failed_delivery_does_not_publish_unsent_numbers(self):
        report = self.root / "report"
        report.mkdir()
        (report / "selection.json").write_text(json.dumps(manifest("c" * 40)))
        with (
            patch.object(self.telegram, "send", side_effect=[1, ValueError("delivery failed")]),
            self.assertRaises(ValueError),
        ):
            workflow.deliver_numbered(report, self.catalog, self.telegram)
        entry = json.loads((report / "numbered-selection.json").read_text())[0]
        with self.assertRaises(ValueError):
            self.catalog.selected([entry["number"]])


class ApiContractTests(unittest.TestCase):
    def test_github_lists_all_pages_including_closed_issues_and_excludes_prs(self):
        first = [{"body": "", "html_url": "https://github.com/ichwars/PrintOps/issues/1"}] * 100
        second = [
            {"body": workflow.UPSTREAM + "a" * 40, "html_url": "https://github.com/ichwars/PrintOps/issues/2"},
            {"body": workflow.UPSTREAM + "b" * 40, "html_url": "ignored", "pull_request": {}},
        ]
        with patch.object(workflow, "request_json", side_effect=[first, second]) as request:
            result = workflow.GitHub("TEST_GITHUB_TOKEN").existing()
        self.assertEqual(result, {"a" * 40: "https://github.com/ichwars/PrintOps/issues/2"})
        self.assertIn("state=all", request.call_args_list[0].args[0])
        self.assertIn("page=2", request.call_args_list[1].args[0])

    def test_issue_body_pins_commits_and_preserves_printops_requirements(self):
        document = {**manifest("a" * 40), **manifest("a" * 40)["entries"][0]}
        with patch.object(
            workflow, "request_json", return_value={"html_url": "https://github.com/ichwars/PrintOps/issues/8"}
        ) as request:
            workflow.GitHub("TEST_GITHUB_TOKEN").create(1, document)
        data = request.call_args.kwargs["data"]
        self.assertIn("printops-bambuddy:" + "a" * 40, data["body"])
        self.assertIn("Erhalt eigener", data["body"])
        self.assertIn("d" * 40, data["body"])
        self.assertNotIn("@someone", data["body"])
        self.assertNotIn("TEST_GITHUB_TOKEN", data["body"])

    def test_telegram_send_uses_plain_text_and_keeps_chat_thread_reply(self):
        with patch.object(workflow, "request_json", return_value={"ok": True, "result": {"message_id": 20}}) as request:
            workflow.Telegram("123456:TEST_TOKEN", "-100123", 42).send("1. <special> _text_", reply_to=3)
        data = request.call_args.kwargs["data"]
        self.assertNotIn("parse_mode", data)
        self.assertEqual(data["message_thread_id"], 42)
        self.assertEqual(data["reply_parameters"], {"message_id": 3})


class WireFlowTests(unittest.TestCase):
    def test_list_send_number_reply_issue_creation_and_repeat_over_local_http(self):
        issues, messages, calls = [], [], []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(("GET", self.path))
                self.respond(issues)

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append(("POST", self.path))
                if self.path == "/repos/ichwars/PrintOps/issues":
                    item = {**data, "html_url": f"https://github.com/ichwars/PrintOps/issues/{len(issues) + 500}"}
                    issues.append(item)
                    self.respond(item)
                else:
                    messages.append(data)
                    self.respond({"ok": True, "result": {"message_id": len(messages)}})

            def respond(self, value):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(value).encode())

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        api = f"http://127.0.0.1:{server.server_port}"
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(workflow, "TELEGRAM_API", api),
            patch.object(workflow, "GITHUB_API", api),
            patch.object(workflow.time, "sleep"),
        ):
            root = Path(directory)
            catalog = workflow.Catalog(root)
            self.addCleanup(catalog.close)
            catalog.put("accept_since", 100)
            catalog.bind("123456:TEST_TOKEN", "-100123", 42)
            report = root / "report"
            report.mkdir()
            (report / "selection.json").write_text(json.dumps(manifest("a" * 40, "b" * 40)))
            telegram = workflow.Telegram("123456:TEST_TOKEN", "-100123", 42)
            workflow.deliver_numbered(report, catalog, telegram)
            self.assertIn("1. Fix printer", messages[1]["text"])
            self.assertIn("2. Fix printer", messages[1]["text"])
            update = {
                "update_id": 20,
                "message": {
                    "message_id": 99,
                    "date": 101,
                    "chat": {"id": -100123},
                    "message_thread_id": 42,
                    "from": {"id": 77, "is_bot": False},
                    "text": "1, 2",
                },
            }
            github = workflow.GitHub("TEST_GITHUB_TOKEN")
            workflow.process_update(update, catalog, telegram, github, {77})
            workflow.process_update(update, catalog, telegram, github, {77})
            self.assertEqual(len(issues), 2)
            self.assertIn("issues/500", messages[-1]["text"])
            self.assertIn("issues/501", messages[-1]["text"])
            self.assertEqual(messages[-1]["reply_parameters"]["message_id"], 99)
            self.assertEqual(len([c for c in calls if c == ("POST", "/repos/ichwars/PrintOps/issues")]), 2)


def listener():
    script = Path(__file__).resolve().parents[1] / "listen_upstream_selections.py"
    spec = importlib.util.spec_from_file_location("selection_listener", script)
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", [str(script.parent), *sys.path]):
        spec.loader.exec_module(module)
    return module


class ListenerTests(unittest.TestCase):
    def test_allowlist_is_explicit_and_has_no_empty_or_wildcard_fallback(self):
        module = listener()
        for value in ["", "*", "-100123", "@someone", "1,", "0", "１"]:
            with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USER_IDS": value}), self.assertRaises(ValueError):
                module.allowed_users()

    def test_webhook_is_not_removed_and_no_updates_are_consumed(self):
        module = listener()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {
                    "TELEGRAM_BOT_TOKEN": "123456:TEST_TOKEN",
                    "TELEGRAM_CHAT_ID": "-100123",
                    "TELEGRAM_ALLOWED_USER_IDS": "77",
                    "GITHUB_TOKEN": "TEST_GITHUB_TOKEN",
                },
            ),
            patch.object(workflow.Telegram, "call", return_value={"url": "https://existing.example/hook"}) as call,
        ):
            self.assertEqual(module.main(["--state-dir", directory, "--once"]), 1)
            self.assertEqual([args.args[0] for args in call.call_args_list], ["getWebhookInfo"])
            self.assertFalse((Path(directory) / "selections.sqlite3").exists())

    def test_poll_cursor_survives_restart_and_skips_acked_updates(self):
        module = listener()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {
                    "TELEGRAM_BOT_TOKEN": "123456:TEST_TOKEN",
                    "TELEGRAM_CHAT_ID": "-100123",
                    "TELEGRAM_ALLOWED_USER_IDS": "77",
                    "GITHUB_TOKEN": "TEST_GITHUB_TOKEN",
                },
            ),
            patch.object(
                workflow.Telegram, "call", side_effect=[{"url": ""}, [{"update_id": 25}], {"url": ""}, []]
            ) as call,
        ):
            self.assertEqual(module.main(["--state-dir", directory, "--once"]), 0)
            self.assertEqual(module.main(["--state-dir", directory, "--once"]), 0)
            self.assertEqual(call.call_args_list[-1].args[1]["offset"], 26)


if __name__ == "__main__":
    unittest.main()
