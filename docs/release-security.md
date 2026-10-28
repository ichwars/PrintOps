# Release integrity and supply-chain verification

## Automated security maintenance

The local `printops-security-maintenance.timer` runs every Monday at 09:00
Europe/Berlin (including catch-up after a missed run). It uses the installed
Codex CLI and the current user's GitHub login, with automatic approval review.
The service's working directory must point to the PrintOps checkout. Templates
are in `install/security-maintenance/`; no credentials belong in the units.

Each run uses an isolated worktree and checks security issues, Dependabot,
code-scanning alerts and dependency audits. Confirmed fixes go through a PR,
review and the applicable full tests. Failed/missing checks and required reviews
block merging. Scanner reports must be inspected even when an upload job succeeds.
Resolved issues are closed after verification on main. Incomplete work and private
results remain under `.cache/security-maintenance/` for the next run.

The maintainer authorizes automatic patch releases for fixes to shipped software
or artifacts, after release preparation, CI, builds and artifact verification.
Development-only fixes do not create releases. The workflow does not deploy to
running installations or issue printer commands. Read-only configuration check:
`python3 tools/run_security_maintenance.py --check-config`.

The Windows PDF renderer retains its pinned version. Its separately bundled
native and Python Brotli decoders receive hash-verified security overlays from
MSYS2 UCRT64 and the official PyPI wheel. CI checks native decoder version and
standalone WOFF2-to-PDF rendering before release.

## Release artifacts

PrintOps releases currently avoid external code-signing providers. Windows
installers are published unsigned so releases do not depend on SignPath, Azure
Artifact Signing, commercial certificates, or protected signing secrets.

The remaining release safeguards are:

- GitHub Actions builds release artifacts from repository source;
- release tags must match the supported `v...` version format;
- Windows installer assets include `SHA256SUMS.txt` and
  `WINDOWS_INSTALLER_UNSIGNED.txt`;
- Windows installer and container workflows publish GitHub artifact
  attestations where supported;
- container releases publish BuildKit provenance and SBOM metadata;
- release Actions are pinned to immutable commit SHAs.

## Windows installers

The Windows workflow builds the installer on `windows-latest`, renames every
installer executable with an `-unsigned` suffix, writes `SIGNING_STATUS.txt`,
computes SHA-256 checksums, and uploads all files to a draft release for `v*`
tags. The upload action explicitly keeps the release as a draft; publication is
a separate step after every required build, scan and attestation is verified.

Users should expect Windows SmartScreen to show an unknown-publisher warning.
Before installing, compare the downloaded installer against `SHA256SUMS.txt`
from the same GitHub release.

## Container images

The container workflow validates the release tag format, builds multi-platform
images for `linux/amd64` and `linux/arm64`, publishes BuildKit provenance and
SBOM metadata, then attests the pushed registry digest.

Image tags are assigned by release type:

- stable tags first publish `<version>`; publication of the verified GitHub
  release promotes `latest` only after the exact commit's CI/security, container
  attestation and Windows builds have succeeded;
- release-candidate tags publish `<version>` and `rc`;
- daily tags publish `<version>` and `daily`.

Verify a container attestation by digest or immutable version tag:

```bash
gh attestation verify oci://ghcr.io/ichwars/printops:1.2.7 --repo ichwars/PrintOps
```

## Optional signed tags for native updates

The native in-app updater can still be configured to require signed annotated
Git tags by setting `PRINTOPS_UPDATE_TRUSTED_SIGNERS_FILE` and
`PRINTOPS_UPDATE_SIGNING_PRINCIPAL` on an installation. This is an operator
choice for update trust, not a requirement for publishing GitHub release
artifacts.

When configured, the allowed-signers file must live outside writable PrintOps
data and contain the trusted release principal plus public key:

```text
release@printops ssh-ed25519 AAAAC3...public-key-material...
```

Without that updater trust configuration, GitHub releases remain installable
through the published assets and checksums.
