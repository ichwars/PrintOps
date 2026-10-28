"""Telegram flood control and a restarted update stream, without live services."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import test_upstream_telegram as selection

workflow = selection.workflow
DAY = 86_400


class DeliveryTests(unittest.TestCase):
    def sent_times(self, chat, count):
        clock, sent = [1000.0], []

        def sleep(delay):
            clock[0] += delay

        def request(*args, **kwargs):
            sent.append(clock[0])
            return {"ok": True, "result": {"message_id": len(sent)}}

        with (
            patch.object(workflow.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(workflow.time, "sleep", side_effect=sleep),
            patch.object(workflow, "request_json", side_effect=request),
        ):
            telegram = workflow.Telegram("123456:TEST_TOKEN", chat, None)
            for number in range(count):
                telegram.send(str(number))
        return sent

    def test_large_group_report_stays_within_twenty_messages_per_minute(self):
        for chat in ("-100123", "@printops_group"):
            with self.subTest(chat=chat):
                sent = self.sent_times(chat, 45)
                self.assertEqual(len(sent), 45)
                self.assertLessEqual(max(sum(0 <= item - start < 60 for item in sent) for start in sent), 20)

    def test_private_chat_keeps_its_existing_single_chat_pacing(self):
        sent = self.sent_times("123", 3)
        self.assertAlmostEqual(sent[1] - sent[0], 1.1)
        self.assertAlmostEqual(sent[2] - sent[1], 1.1)

    def test_http_429_waits_for_server_delay_then_completes_the_same_message(self):
        body = {"ok": False, "error_code": 429, "parameters": {"retry_after": 4}}
        error = HTTPError("https://example.invalid/TEST_TOKEN", 429, "limit", {}, io.BytesIO(json.dumps(body).encode()))
        reply = MagicMock()
        reply.__enter__.return_value.read.return_value = json.dumps({"ok": True, "result": {"message_id": 8}}).encode()
        opener = MagicMock()
        opener.open.side_effect = [error, reply]
        with (
            patch.object(workflow, "build_opener", return_value=opener),
            patch.object(workflow.time, "sleep") as sleep,
        ):
            result = workflow.Telegram("123456:TEST_TOKEN", "-100123", 42).send("same message", reply_to=3)
        self.assertEqual(result, 8)
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_any_call(4)
        first, second = [json.loads(call.args[0].data) for call in opener.open.call_args_list]
        self.assertEqual(first, second)
        self.assertEqual(first["message_thread_id"], 42)
        self.assertEqual(first["reply_parameters"], {"message_id": 3})

    def test_persistent_flood_control_is_bounded_and_does_not_expose_response_text(self):
        response = {
            "ok": False,
            "error_code": 429,
            "description": "secret TEST_TOKEN",
            "parameters": {"retry_after": 2},
        }
        with (
            patch.object(workflow, "request_json", return_value=response) as request,
            patch.object(workflow.time, "sleep") as sleep,
            self.assertRaises(ValueError) as raised,
        ):
            workflow.Telegram("123456:TEST_TOKEN", "-100123", None).call("sendMessage", {"text": "one"})
        self.assertEqual(request.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 2, 2])
        self.assertNotIn("TEST_TOKEN", str(raised.exception))

    def test_invalid_rate_limits_and_other_failures_are_not_retried(self):
        for response in (
            {"ok": False, "error_code": 403, "parameters": {"retry_after": 2}},
            {"ok": False, "error_code": 429, "parameters": {"retry_after": "TEST_TOKEN"}},
            {"ok": False, "error_code": 429, "parameters": {"retry_after": True}},
            {"ok": False, "error_code": 429, "parameters": {"retry_after": 999_999}},
        ):
            with (
                self.subTest(response=response),
                patch.object(workflow, "request_json", return_value=response) as request,
                patch.object(workflow.time, "sleep") as sleep,
                self.assertRaises(ValueError) as raised,
            ):
                workflow.Telegram("123456:TEST_TOKEN", "-100123", None).call("sendMessage")
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()
            self.assertNotIn("TEST_TOKEN", str(raised.exception))

    def test_invalid_http_error_bodies_are_closed_and_redacted_without_retry(self):
        for body in (b"TEST_TOKEN", b"[" * 2000 + b"]" * 2000, b"x" * 65_537):
            stream = io.BytesIO(body)
            error = HTTPError("https://example.invalid/TEST_TOKEN", 429, "TEST_TOKEN", {}, stream)
            opener = MagicMock()
            opener.open.side_effect = error
            with (
                self.subTest(size=len(body)),
                patch.object(workflow, "build_opener", return_value=opener),
                patch.object(workflow.time, "sleep") as sleep,
                self.assertRaises(ValueError) as raised,
            ):
                workflow.Telegram("123456:TEST_TOKEN", "-100123", None).call("sendMessage")
            self.assertTrue(stream.closed)
            self.assertNotIn("TEST_TOKEN", str(raised.exception))
            self.assertEqual(opener.open.call_count, 1)
            sleep.assert_not_called()

    def test_ambiguous_network_failure_is_not_retried(self):
        opener = MagicMock()
        opener.open.side_effect = URLError("TEST_TOKEN")
        with (
            patch.object(workflow, "build_opener", return_value=opener),
            patch.object(workflow.time, "sleep") as sleep,
            self.assertRaises(ValueError) as raised,
        ):
            workflow.Telegram("123456:TEST_TOKEN", "-100123", None).call("sendMessage")
        self.assertNotIn("TEST_TOKEN", str(raised.exception))
        self.assertEqual(opener.open.call_count, 1)
        sleep.assert_not_called()


class CursorTests(unittest.TestCase):
    def check_stream(self, age, *, legacy=False, authorized=True, already_created=False, processing_delay=0):
        module = selection.listener()
        now = 2_000_000
        clock = [now]
        github = selection.FakeGitHub()
        if already_created:
            github.issues["a" * 40] = "https://github.com/ichwars/PrintOps/issues/55"
        requests = []
        sends = []
        create = github.create

        def delayed_create(*args):
            clock[0] += processing_delay
            return create(*args)

        github.create = delayed_create
        update = {
            "update_id": 500,
            "message": {
                "message_id": 8,
                "date": now,
                "chat": {"id": -100123},
                "message_thread_id": 42,
                "from": {"id": 77 if authorized else 99, "is_bot": False},
                "text": "1",
            },
        }

        def call(method, data=None, **kwargs):
            if method == "getWebhookInfo":
                return {"url": ""}
            if method == "sendMessage":
                sends.append(data)
                return {"message_id": 9}
            self.assertEqual(method, "getUpdates")
            requests.append(data)
            # Telegram confirms lower IDs at the server, before the client sees them.
            current = {
                **update,
                "update_id": 100 if clock[0] > now else 500,
                "message": {**update["message"], "date": clock[0]},
            }
            return [current] if data["offset"] <= current["update_id"] else []

        with tempfile.TemporaryDirectory() as directory:
            catalog = workflow.Catalog(Path(directory))
            catalog.bind("123456:TEST_TOKEN", "-100123", 42)
            catalog.put("accept_since", now - 8 * DAY)
            catalog.register(selection.manifest("a" * 40))
            catalog.publish([1])
            catalog.put("offset", 1001)  # Existing installations have only this legacy checkpoint.
            if not legacy:
                catalog.put("cursor", {"offset": 1001, "received_at": now - age})
            catalog.close()
            with (
                patch.dict(
                    os.environ,
                    {
                        "TELEGRAM_BOT_TOKEN": "123456:TEST_TOKEN",
                        "TELEGRAM_CHAT_ID": "-100123",
                        "TELEGRAM_THREAD_ID": "42",
                        "TELEGRAM_ALLOWED_USER_IDS": "77",
                        "GITHUB_TOKEN": "TEST_GITHUB_TOKEN",
                    },
                ),
                patch.object(module.time, "time", side_effect=lambda: clock[0]),
                patch.object(module, "GitHub", return_value=github),
                patch.object(workflow.Telegram, "call", side_effect=call),
                patch.object(workflow.time, "sleep"),
            ):
                self.assertEqual(module.main(["--state-dir", directory, "--once"]), 0)
                old_or_unknown = legacy or age >= 5 * DAY
                self.assertEqual(requests[0]["offset"], 0 if old_or_unknown else 1001)
                self.assertEqual(github.creations, int(old_or_unknown and authorized and not already_created))
                # Restart must acknowledge the new stream instead of replaying it.
                self.assertEqual(module.main(["--state-dir", directory, "--once"]), 0)
                next_offset = (0 if processing_delay >= 5 * DAY else 501) if old_or_unknown else 1001
                self.assertEqual(requests[-1]["offset"], next_offset)
                self.assertEqual(github.creations, int(old_or_unknown and authorized and not already_created))
                if processing_delay:
                    self.assertEqual(len(sends), 2)

    def test_weekly_idle_stream_resets_before_sending_an_obsolete_offset(self):
        self.check_stream(7 * DAY)

    def test_reset_has_margin_before_the_server_week_boundary(self):
        self.check_stream(5 * DAY)
        self.check_stream(5 * DAY - 1)

    def test_existing_offset_without_a_timestamp_is_migrated_safely(self):
        self.check_stream(0, legacy=True)

    def test_current_cursor_does_not_reprocess_lower_duplicate_ids(self):
        self.check_stream(0)

    def test_idle_reset_keeps_the_sender_allowlist(self):
        self.check_stream(7 * DAY, authorized=False)

    def test_legacy_checkpoint_replay_reuses_the_existing_issue(self):
        self.check_stream(0, legacy=True, already_created=True)

    def test_processing_or_host_suspend_does_not_renew_an_old_update_epoch(self):
        self.check_stream(0, legacy=True, processing_delay=7 * DAY)


if __name__ == "__main__":
    unittest.main()
