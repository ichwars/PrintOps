"""Fail-closed scheduling, isolation and unfinished-work retention."""

import fcntl
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import run_security_maintenance as maintenance


class MaintenanceTests(unittest.TestCase):
    def test_fork_origin_is_rejected_before_github_access(self):
        repo = Path("/authorized/repo")
        with (
            patch.object(maintenance.shutil, "which", return_value="tool"),
            patch.object(
                maintenance, "command", side_effect=[str(repo), "https://github.com/other/PrintOps.git"]
            ) as command,
        ):
            with self.assertRaisesRegex(ValueError, "authorized PrintOps"):
                maintenance.preflight(repo, "codex")
            self.assertEqual(command.call_count, 2)

    def test_missing_write_permission_fails_before_agent(self):
        repo = Path("/authorized/repo")
        with (
            patch.object(maintenance.shutil, "which", return_value="tool"),
            patch.object(
                maintenance,
                "command",
                side_effect=[str(repo), "https://github.com/ichwars/PrintOps.git", "false"],
            ),
            patch.object(maintenance.subprocess, "run") as agent,
        ):
            with self.assertRaisesRegex(ValueError, "write access"):
                maintenance.preflight(repo, "codex")
            agent.assert_not_called()

    def test_parallel_run_is_rejected_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with (state / "run.lock").open("a") as lock, patch.object(maintenance, "preflight") as preflight:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(ValueError, "already running"):
                    maintenance.run(state, state, "codex", "trusted prompt")
                preflight.assert_not_called()

    def test_failed_agent_keeps_its_own_checkout_and_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def command(*args, **kwargs):
                if args[1:3] == ("worktree", "add"):
                    Path(args[-2]).mkdir()
                return "a" * 40

            def agent(args, **kwargs):
                checkout = Path(args[args.index("-C") + 1])
                (checkout / "unfinished-fix").write_text("preserve")
                self.assertIn("--approve-for-me", args)
                self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
                self.assertEqual(kwargs["input"], "trusted prompt")
                return SimpleNamespace(returncode=7)

            with (
                patch.object(maintenance, "preflight"),
                patch.object(maintenance, "command", command),
                patch.object(maintenance.subprocess, "run", agent),
            ):
                self.assertEqual(maintenance.run(root, root / "state", "codex", "trusted prompt"), 7)
            self.assertEqual(next((root / "state").glob("*/checkout/unfinished-fix")).read_text(), "preserve")
            self.assertEqual(next((root / "state").glob("*/exit-code")).read_text(), "7\n")


if __name__ == "__main__":
    unittest.main()
