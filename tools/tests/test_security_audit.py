import unittest

from tools.check_security_audit import findings


class AuditTests(unittest.TestCase):
    lock = {"packages": {"": {}, "node_modules/dompurify": {}, "node_modules/zod": {"dev": True}}}

    def test_npm_error_or_missing_inventory_never_means_clean(self):
        for report in ({}, {"error": {"code": "ENOAUDIT"}}, {"vulnerabilities": {}}):
            with self.subTest(report=report), self.assertRaises(ValueError):
                findings("npm", report, self.lock)

    def test_valid_clean_npm_report(self):
        self.assertEqual(
            findings("npm", {"vulnerabilities": {}, "metadata": {"vulnerabilities": {"total": 0}}}, self.lock), []
        )

    def test_unfixable_critical_still_blocks_production(self):
        report = {
            "vulnerabilities": {"dompurify": {"severity": "critical", "fixAvailable": False}},
            "metadata": {"vulnerabilities": {"total": 1}},
        }
        self.assertEqual(findings("npm", report, self.lock), [("dompurify", "critical")])

    def test_dev_only_finding_is_not_misreported_as_runtime(self):
        report = {
            "vulnerabilities": {"zod": {"severity": "high"}},
            "metadata": {"vulnerabilities": {"total": 1}},
        }
        self.assertEqual(findings("npm", report, self.lock), [])

    def test_pip_missing_or_skipped_scan_never_means_clean(self):
        for report in ({}, {"dependencies": []}, {"dependencies": [{"name": "x", "skip_reason": "failed"}]}):
            with self.subTest(report=report), self.assertRaises(ValueError):
                findings("pip", report)

    def test_pip_valid_clean_and_vulnerable_reports(self):
        report = {"dependencies": [{"name": "brotli", "version": "1.2.1", "vulns": []}]}
        self.assertEqual(findings("pip", report), [])
        report["dependencies"][0]["vulns"] = [{"id": "GHSA-test"}]
        self.assertEqual(findings("pip", report), [("brotli", "GHSA-test")])


if __name__ == "__main__":
    unittest.main()
