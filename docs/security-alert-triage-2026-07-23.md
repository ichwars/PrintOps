# Security Alert Triage — 2026-07-23

This document records the disposition of every alert that was open on the
default branch when the security-hardening work started. It is intentionally
kept as durable evidence for future maintainers; it is not a claim that the
repository can never acquire new alerts.

## Summary

| Source | Open at triage | Confirmed | Not actionable |
| --- | ---: | ---: | ---: |
| GitHub code scanning | 66 | 52 | 14 |
| Dependabot | 1 | 1 | 0 |
| Secret scanning | 0 | 0 | 0 |

Verdicts use two categories:

- **Confirmed** — the shipped artifact or dependency is affected and requires
  remediation.
- **Not actionable** — generated or vendored output produced a scanner match
  that does not represent a PrintOps security boundary or secret.

## Code scanning: CodeQL

All 13 findings point to the generated, minified bundle
`static/assets/FileUploadModal-BZjgVLEt.js`. The matched random-number calls are
vendored Three.js/G-code-preview helpers used for visualization identifiers and
sampling, not authentication, secrets, tokens, or authorization decisions.
Authored frontend sources remain scanned; `.codeql/codeql-config.yml` now
excludes `static/assets/**` so generated third-party copies do not recreate the
same queue.

| Alert | Rule | Verdict | Disposition |
| ---: | --- | --- | --- |
| 582 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 583 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 584 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 585 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 586 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 587 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 588 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 589 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 590 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 591 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 592 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 593 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |
| 594 | `js/insecure-randomness` | Not actionable | Dismiss as false positive; generated visualization code |

## Code scanning: generated secret match

Alert 568 points to
`/app/static/assets/orderMasterDataValidation-IofyWjDo.js`. Trivy interpreted a
concatenated set of country/locale codes in generated frontend data as a
SendGrid token. The bundle contains no SendGrid credential and the value does
not satisfy a secret-bearing application path.

| Alert | Rule | Verdict | Disposition |
| ---: | --- | --- | --- |
| 568 | `sendgrid-api-token` | Not actionable | Dismiss as false positive; generated locale data |

## Code scanning: Tailscale binaries

The 52 findings are confirmed vulnerabilities in Go dependencies embedded in
the `tailscale` and `tailscaled` executables installed in the production image.
PrintOps only needs read-only status data from the host daemon. The Docker image
therefore no longer installs either executable; the integration uses Tailscale
LocalAPI over the explicitly mounted Unix socket. A locally installed external
CLI remains a non-container fallback. Removal of the affected artifacts resolves
all alerts together without suppressing real vulnerabilities.

| Alert | Artifact | Rule | Verdict | Remediation |
| ---: | --- | --- | --- | --- |
| 473 | `/usr/bin/tailscale` | `CVE-2026-39828` | Confirmed | Remove binary from image |
| 474 | `/usr/bin/tailscale` | `CVE-2026-39829` | Confirmed | Remove binary from image |
| 475 | `/usr/bin/tailscale` | `CVE-2026-39830` | Confirmed | Remove binary from image |
| 476 | `/usr/bin/tailscale` | `CVE-2026-39831` | Confirmed | Remove binary from image |
| 477 | `/usr/bin/tailscale` | `CVE-2026-39832` | Confirmed | Remove binary from image |
| 478 | `/usr/bin/tailscale` | `CVE-2026-39835` | Confirmed | Remove binary from image |
| 479 | `/usr/bin/tailscale` | `CVE-2026-42508` | Confirmed | Remove binary from image |
| 480 | `/usr/bin/tailscale` | `CVE-2026-46595` | Confirmed | Remove binary from image |
| 481 | `/usr/bin/tailscale` | `CVE-2026-46597` | Confirmed | Remove binary from image |
| 482 | `/usr/bin/tailscale` | `CVE-2026-39827` | Confirmed | Remove binary from image |
| 483 | `/usr/bin/tailscale` | `CVE-2026-39833` | Confirmed | Remove binary from image |
| 484 | `/usr/bin/tailscale` | `CVE-2026-39834` | Confirmed | Remove binary from image |
| 485 | `/usr/bin/tailscale` | `CVE-2026-46598` | Confirmed | Remove binary from image |
| 487 | `/usr/bin/tailscale` | `CVE-2026-33809` | Confirmed | Remove binary from image |
| 488 | `/usr/bin/tailscale` | `CVE-2026-33812` | Confirmed | Remove binary from image |
| 489 | `/usr/bin/tailscale` | `CVE-2026-33813` | Confirmed | Remove binary from image |
| 490 | `/usr/bin/tailscale` | `CVE-2026-46599` | Confirmed | Remove binary from image |
| 491 | `/usr/bin/tailscale` | `CVE-2026-46601` | Confirmed | Remove binary from image |
| 492 | `/usr/bin/tailscale` | `CVE-2026-42500` | Confirmed | Remove binary from image |
| 493 | `/usr/bin/tailscale` | `CVE-2026-46602` | Confirmed | Remove binary from image |
| 494 | `/usr/bin/tailscale` | `CVE-2026-46604` | Confirmed | Remove binary from image |
| 495 | `/usr/bin/tailscale` | `CVE-2026-25681` | Confirmed | Remove binary from image |
| 496 | `/usr/bin/tailscale` | `CVE-2026-27136` | Confirmed | Remove binary from image |
| 497 | `/usr/bin/tailscale` | `CVE-2026-39821` | Confirmed | Remove binary from image |
| 498 | `/usr/bin/tailscale` | `CVE-2026-25680` | Confirmed | Remove binary from image |
| 499 | `/usr/bin/tailscale` | `CVE-2026-42502` | Confirmed | Remove binary from image |
| 500 | `/usr/bin/tailscale` | `CVE-2026-42506` | Confirmed | Remove binary from image |
| 501 | `/usr/bin/tailscale` | `CVE-2026-39824` | Confirmed | Remove binary from image |
| 507 | `/usr/sbin/tailscaled` | `CVE-2026-39828` | Confirmed | Remove binary from image |
| 508 | `/usr/sbin/tailscaled` | `CVE-2026-39829` | Confirmed | Remove binary from image |
| 509 | `/usr/sbin/tailscaled` | `CVE-2026-39830` | Confirmed | Remove binary from image |
| 510 | `/usr/sbin/tailscaled` | `CVE-2026-39831` | Confirmed | Remove binary from image |
| 511 | `/usr/sbin/tailscaled` | `CVE-2026-39832` | Confirmed | Remove binary from image |
| 512 | `/usr/sbin/tailscaled` | `CVE-2026-39835` | Confirmed | Remove binary from image |
| 513 | `/usr/sbin/tailscaled` | `CVE-2026-42508` | Confirmed | Remove binary from image |
| 514 | `/usr/sbin/tailscaled` | `CVE-2026-46595` | Confirmed | Remove binary from image |
| 515 | `/usr/sbin/tailscaled` | `CVE-2026-46597` | Confirmed | Remove binary from image |
| 516 | `/usr/sbin/tailscaled` | `CVE-2026-39827` | Confirmed | Remove binary from image |
| 517 | `/usr/sbin/tailscaled` | `CVE-2026-39833` | Confirmed | Remove binary from image |
| 518 | `/usr/sbin/tailscaled` | `CVE-2026-39834` | Confirmed | Remove binary from image |
| 519 | `/usr/sbin/tailscaled` | `CVE-2026-46598` | Confirmed | Remove binary from image |
| 521 | `/usr/sbin/tailscaled` | `CVE-2026-25681` | Confirmed | Remove binary from image |
| 522 | `/usr/sbin/tailscaled` | `CVE-2026-27136` | Confirmed | Remove binary from image |
| 523 | `/usr/sbin/tailscaled` | `CVE-2026-39821` | Confirmed | Remove binary from image |
| 524 | `/usr/sbin/tailscaled` | `CVE-2026-25680` | Confirmed | Remove binary from image |
| 525 | `/usr/sbin/tailscaled` | `CVE-2026-42502` | Confirmed | Remove binary from image |
| 526 | `/usr/sbin/tailscaled` | `CVE-2026-42506` | Confirmed | Remove binary from image |
| 527 | `/usr/sbin/tailscaled` | `CVE-2026-39824` | Confirmed | Remove binary from image |
| 559 | `/usr/bin/tailscale` | `CVE-2026-46600` | Confirmed | Remove binary from image |
| 560 | `/usr/bin/tailscale` | `CVE-2026-56852` | Confirmed | Remove binary from image |
| 561 | `/usr/sbin/tailscaled` | `CVE-2026-46600` | Confirmed | Remove binary from image |
| 562 | `/usr/sbin/tailscaled` | `CVE-2026-56852` | Confirmed | Remove binary from image |

## Dependabot

| Alert | Package | Vulnerable range | Verdict | Remediation |
| ---: | --- | --- | --- | --- |
| 1 | `brace-expansion` | `>=3.0.0, <5.0.7` | Confirmed | Override and lock `5.0.7` |

## Closure criteria

- False positives 568 and 582–594 are dismissed with a reference to this
  triage record.
- The next CodeQL run scans authored sources without generated bundles.
- The next Trivy image scan contains neither Tailscale executable and closes
  alerts 473–527 and 559–562.
- Dependabot confirms that `brace-expansion` resolves to 5.0.7 or newer.
- GitHub Private Vulnerability Reporting is enabled and `SECURITY.md` defines
  the private reporting and coordinated-disclosure process.
