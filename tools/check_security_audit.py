"""Validate scanner reports before treating a scan as clean or closing issues."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def findings(kind: str, report: dict, lock: dict | None = None) -> list[tuple[str, str]]:
    if not isinstance(report, dict) or "error" in report:
        raise ValueError("Scanner failed or returned an invalid report")
    if kind == "pip":
        dependencies = report.get("dependencies")
        if not isinstance(dependencies, list) or not dependencies:
            raise ValueError("pip-audit did not return a dependency inventory")
        result = []
        for package in dependencies:
            if (
                not isinstance(package, dict)
                or not isinstance(package.get("name"), str)
                or not isinstance(package.get("version"), str)
                or not isinstance(package.get("vulns"), list)
                or "skip_reason" in package
            ):
                raise ValueError("pip-audit returned an incomplete dependency result")
            for vulnerability in package["vulns"]:
                if not isinstance(vulnerability, dict) or not isinstance(vulnerability.get("id"), str):
                    raise ValueError("pip-audit returned an invalid vulnerability")
                result.append((package["name"], vulnerability["id"]))
        return result
    vulnerabilities = report.get("vulnerabilities")
    metadata = report.get("metadata", {}).get("vulnerabilities", {})
    if not isinstance(vulnerabilities, dict) or metadata.get("total") != len(vulnerabilities):
        raise ValueError("npm audit did not return a complete vulnerability report")
    if not isinstance(lock, dict) or not isinstance(lock.get("packages"), dict) or not lock["packages"]:
        raise ValueError("npm lock has no dependency inventory")
    production = {
        path.split("node_modules/")[-1]
        for path, info in lock["packages"].items()
        if path and not info.get("dev") and not info.get("devOptional")
    }
    result = []
    for name, package in vulnerabilities.items():
        if not isinstance(package, dict) or package.get("severity") not in (
            "info",
            "low",
            "moderate",
            "high",
            "critical",
        ):
            raise ValueError("npm audit returned an invalid vulnerability")
        if name in production and package["severity"] in ("high", "critical"):
            result.append((name, package["severity"]))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("pip", "npm"))
    parser.add_argument("report", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text())
        lock = json.loads(args.lock.read_text()) if args.lock else None
        found = findings(args.kind, report, lock)
        if found and not args.validate_only:
            for name, issue in found:
                print(f"Unresolved {args.kind} finding: {name}: {issue}")
            return 1
        print(f"Valid {args.kind} report; {len(found)} blocking findings")
        return 0
    except (ValueError, OSError, TypeError, AttributeError):
        print("Security audit unavailable, incomplete or invalid; keep existing issues open", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
