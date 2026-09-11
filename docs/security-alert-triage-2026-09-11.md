# Dependabot remediation — 2026-09-11

Tracking: [issue #177](https://github.com/ichwars/PrintOps/issues/177).
All five alerts open at the start of this change are treated as actionable
dependency findings, not dismissed on the basis of limited application exposure.

| Alerts | Dependency / manifests | Vulnerable version | Fixed version |
| --- | --- | --- | --- |
| 21, 22 | `@vitest/mocker`, `vitest`; `frontend/package-lock.json` | 4.1.8 | 4.1.11 |
| 23, 24, 25 | `weasyprint`; `requirements.txt` and both Python lockfiles | 69.0 | 70.0 |

## Boundary and fix

[CVE-2026-84373](https://github.com/advisories/GHSA-82fw-gwwq-j7x9)
allows redirect mocks to bypass Vite's filesystem allow/deny policy. The complete
Vitest package family, including coverage, moves together to the patched v4
release. PrintOps uses jsdom tests, not the optional browser mocker server; this
limits exposure but is not a reason to retain the vulnerable dependency.

[CVE-2026-55073](https://github.com/advisories/GHSA-jf6q-chmf-3h3v)
allows auxiliary stylesheet and XMP URLs to bypass WeasyPrint's original fetcher.
[WeasyPrint 70.0](https://github.com/Kozea/WeasyPrint/releases/tag/v70.0)
threads that fetcher through both entry points, including nested CSS imports.
PrintOps continues using fixed CLI arguments, registered hash-verified assets,
file-only loading, and disabled HTTP redirects. Untrusted options, filenames,
file objects, or independently constructed CSS objects must not be forwarded to
WeasyPrint; explicit trusted file inputs are not URL-fetcher policy inputs.

## Runtime compatibility

- Python requirements and both hash-locked dependency graphs pin 70.0.
- Windows packaging uses the official `weasyprint-windows-onedir.zip`, verified
  against SHA-256 `ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53`.
  The complete runtime, including `_internal` native libraries, is staged at
  the existing `runtime/weasyprint/dist/weasyprint.exe` path.
  Portable packaging tests live under `installers/windows/tests/` and run in
  backend-lint CI; they do not require installer sources in the Docker image.
- New render receipts, cache fingerprints, and PDF producer metadata identify
  WeasyPrint 70.0. Previously issued artifacts and their immutable 69.0 receipts
  are not rewritten. The append-only schema tests intentionally retain the
  historical version in their fixtures.
- veraPDF, its signatures, ICC profiles, pikepdf, fonts, and validation policy
  remain unchanged. A test now verifies the public signing key's canonical hash;
  the existing `.gitattributes` LF rule remains its owner.
- The v70 Windows layout stack places the 80-position stress sample on nine
  pages. Text extraction confirmed every position remains present. Ninety
  positions produce ten pages with every position present, preserving the
  existing ten-page workload test. The timed sample likewise grows from 14 to
  16 repetitions without relaxing its page minimum or ten-second limit.
  This is not a byte-for-byte cross-version
  rendering promise; deterministic output is tested within the pinned runtime.

## Regression evidence

`npm run check:mocker-security` exercises the installed interceptor registration
and load hooks against Vite's real filesystem policy. Both a denied in-root
`.env` fixture and an out-of-root opaque-URL traversal were readable under 4.1.8
and are rejected under 4.1.11; an allowed redirect remains readable. The check
also runs in the required frontend test CI job.

`test_weasyprint_fetcher_security.py` exercises real rendering with owned local
canaries only: HTML-link control, stylesheet, nested import, XMP metadata, and
approved stylesheet/metadata controls. Under 69.0 the three auxiliary rejection
tests fail and the allow-control shows the configured fetcher was never called.
All five pass under 70.0. No internal service, credential, or unrelated user file
is accessed by these tests.

Release verification additionally covers PDF/A-3u with the pinned veraPDF CLI,
document types/languages/page formats/templates, hybrid e-invoices, deterministic
output, font/letterhead handling, Windows packaging, frontend tests/build, and
dependency audits. CI and the linked PR carry the final check results. Closure
requires GitHub to mark alerts 21–25 fixed after merging into the default branch;
no vulnerability dismissal is part of this change.
