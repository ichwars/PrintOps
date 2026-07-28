# Release integrity and supply-chain verification

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
computes SHA-256 checksums, and uploads all files as release assets for `v*`
tags.

Users should expect Windows SmartScreen to show an unknown-publisher warning.
Before installing, compare the downloaded installer against `SHA256SUMS.txt`
from the same GitHub release.

## Container images

The container workflow validates the release tag format, builds multi-platform
images for `linux/amd64` and `linux/arm64`, publishes BuildKit provenance and
SBOM metadata, then attests the pushed registry digest.

Image tags are assigned by release type:

- stable tags publish `<version>` and `latest`;
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
