import unittest

from tools.check_release_readiness import REQUIRED, require_successful_runs


class ReleaseReadinessTests(unittest.TestCase):
    def runs(self):
        return [
            {
                "id": index + 1,
                "path": path,
                "head_sha": "abc",
                "head_branch": "v1.2.8.1",
                "event": "push",
                "status": "completed",
                "conclusion": "success",
            }
            for index, path in enumerate(sorted(REQUIRED))
        ]

    def test_all_exact_commit_checks_allow_promotion(self):
        require_successful_runs(self.runs(), "abc", "v1.2.8.1")

    def test_windows_or_attestation_failure_prevents_promotion(self):
        for path in (".github/workflows/windows-installer.yml", ".github/workflows/release-container.yml"):
            runs = self.runs()
            next(run for run in runs if run["path"] == path)["conclusion"] = "failure"
            with self.subTest(path=path), self.assertRaises(ValueError):
                require_successful_runs(runs, "abc", "v1.2.8.1")

    def test_missing_pending_or_other_commit_checks_do_not_count(self):
        for change in ("missing", "pending", "wrong_sha"):
            runs = self.runs()
            if change == "missing":
                runs.pop()
            elif change == "pending":
                runs[0]["status"] = "in_progress"
            else:
                runs[0]["head_sha"] = "other"
            with self.subTest(change=change), self.assertRaises(ValueError):
                require_successful_runs(runs, "abc", "v1.2.8.1")

    def test_newer_failed_attempt_cannot_use_an_older_success(self):
        runs = self.runs()
        runs.append({**runs[0], "run_attempt": 2, "conclusion": "failure"})
        with self.assertRaises(ValueError):
            require_successful_runs(runs, "abc", "v1.2.8.1")


if __name__ == "__main__":
    unittest.main()
