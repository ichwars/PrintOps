# Release signing and supply-chain verification

PrintOps releases use two independent trust layers:

1. A protected signing provider holds the Authenticode certificate and signs
   the Windows installers. The workflow supports either Azure Artifact Signing
   or SignPath OSS signing through SignPath.io and SignPath Foundation.
2. A dedicated SSH key signs annotated Git release tags. Native in-app updates
   accept only tags signed by that key.

The private keys must never be committed to this repository. The workflows
fail closed when any required identity, signature, or verification step is
missing.

## 1. Protect the GitHub release environment

Create an environment named `release` under **Settings → Environments** and
configure:

- required reviewers and **Prevent self-review**;
- deployment branches/tags restricted to protected release tags (`v*`);
- branch protection or a ruleset that requires pull requests and CODEOWNERS
  approval for `.github/workflows/**`;
- no long-lived Azure client secret.

Set `RELEASE_TAG_SSH_PUBLIC_KEY` for every release configuration. Then choose
exactly one Windows signing provider.

Always set this environment variable:

| Variable | Purpose |
| --- | --- |
| `RELEASE_TAG_SSH_PUBLIC_KEY` | Public half of the dedicated SSH tag-signing key, beginning with `ssh-ed25519` or another supported SSH key type |

For SignPath OSS signing, set these protected environment variables and secret:

| Name | Type | Purpose |
| --- | --- | --- |
| `SIGNPATH_API_TOKEN` | Secret | SignPath API token for a user with submitter permissions on the project/signing policy |
| `SIGNPATH_ORGANIZATION_ID` | Variable | SignPath organization ID |
| `SIGNPATH_PROJECT_SLUG` | Variable | SignPath project slug, for example `printops` |
| `SIGNPATH_SIGNING_POLICY_SLUG` | Variable | Signing policy slug, for example `release-signing` |
| `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` | Variable, optional | Artifact configuration slug when the default SignPath artifact configuration should not be used |

For Azure Artifact Signing, set these protected environment variables:

| Variable | Purpose |
| --- | --- |
| `AZURE_CLIENT_ID` | Entra application/client ID used by workload identity |
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription containing Artifact Signing |
| `AZURE_ARTIFACT_SIGNING_ENDPOINT` | Regional signing endpoint, for example `https://eus.codesigning.azure.net/` |
| `AZURE_ARTIFACT_SIGNING_ACCOUNT` | Artifact Signing account name |
| `AZURE_ARTIFACT_SIGNING_CERTIFICATE_PROFILE` | Code-signing certificate profile |

The public tag key is deliberately a variable, not a secret. Its private half
must remain in a hardware-backed SSH agent or an encrypted maintainer key
store.

The Windows workflow fails closed when both providers are configured, when only
part of a provider is configured, or when a stable release tag has no trusted
signing provider. Prerelease and daily tags may publish clearly marked unsigned
installers for testing.

## 2. Configure SignPath OSS signing

Before enabling the SignPath variables, apply for SignPath Foundation OSS code
signing and create the project, signing policy and artifact configuration in
SignPath.io.

Required project setup:

1. Install the SignPath GitHub App for `ichwars/PrintOps` and link the GitHub
   trusted build system to the SignPath project.
2. Enable origin verification for the signing policy. Open-source signing uses
   SignPath's GitHub connector to verify that the artifact came from a GitHub
   workflow artifact and, for OSS projects, from GitHub-hosted runners.
3. Configure the artifact as a ZIP root because `actions/upload-artifact`
   provides the unsigned installers to SignPath as a GitHub artifact archive.
   The artifact configuration should Authenticode-sign every PrintOps
   installer executable and enforce metadata such as product name `PrintOps`
   and a release-version parameter.
4. Set the protected GitHub `release` environment variables/secrets listed
   above. Keep the SignPath API token as a secret.

The workflow submits the unsigned GitHub artifact to SignPath, waits for manual
approval and completion, replaces the unsigned installer with the signed output,
then verifies the Authenticode signature with SignTool before uploading release
assets.

Free OSS signing is provided by SignPath.io with the certificate issued to
SignPath Foundation. The project must continue to follow SignPath Foundation's
OSS conditions, including an open-source license, documented functionality,
maintained release artifacts, repository/build origin verification, MFA for
maintainers and a published code-signing policy.

## 3. Configure Azure Artifact Signing with OIDC

In Azure:

1. Create an Artifact Signing account, complete identity validation, and create
   a public-trust code-signing certificate profile.
2. Create an Entra application or workload identity and grant only the
   **Artifact Signing Certificate Profile Signer** role at the narrowest
   available account/profile scope.
3. Add a federated credential with audience `api://AzureADTokenExchange` and
   subject:

   ```text
   repo:ichwars/PrintOps:environment:release
   ```

4. Copy the non-secret identifiers into the GitHub `release` environment
   variables listed above. Do not create `AZURE_CLIENT_SECRET`.

The Windows workflow builds without write permissions, then enters the
protected environment, authenticates with OIDC, signs every installer with
SHA-256 plus an RFC 3161 timestamp, and verifies the result with SignTool.
Only the separately uploaded signed artifact is available to the publication
job.

## 4. Create and protect the release-tag key

Create a dedicated Ed25519 key on the authorized maintainer workstation. Use a
strong passphrase or a hardware-backed SSH key:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/printops-release-signing -C release@printops
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/printops-release-signing.pub
git config --global tag.gpgSign true
```

Copy only the public key line (without its trailing comment) into the GitHub
environment variable `RELEASE_TAG_SSH_PUBLIC_KEY`.

For every release:

```bash
git tag -s v1.2.6 -m "PrintOps v1.2.6"
git verify-tag v1.2.6
git push origin v1.2.6
```

Both release workflows reject lightweight or incorrectly signed tags before
building/publishing release outputs.

## 5. Install the native-updater trust anchor

Create an OpenSSH `allowed_signers` file on every native installation. It must
be outside the writable PrintOps data directory:

```text
release@printops ssh-ed25519 AAAAC3...public-key-material...
```

Recommended Linux placement and permissions:

```bash
sudo install -o root -g root -m 0644 release-signers.allowed /etc/printops/release-signers.allowed
```

Add these service environment variables and restart PrintOps:

```text
PRINTOPS_UPDATE_TRUSTED_SIGNERS_FILE=/etc/printops/release-signers.allowed
PRINTOPS_UPDATE_SIGNING_PRINCIPAL=release@printops
```

The updater then:

- accepts only supported `v...` release tags;
- fetches only the selected tag;
- rejects lightweight tags;
- verifies the SSH signature using Git's `verify-tag` and the configured
  allowed-signers file;
- resolves the verified tag once and resets to that immutable commit ID.

Native in-app updates require Git 2.34 or newer because older versions do not
support SSH signatures for Git objects.

If the trust file is missing, relative, empty, stored under writable PrintOps
data, or group/world-writable on POSIX, in-app updating is disabled with an
explicit security error. Existing unsigned or lightweight historical tags are
intentionally not accepted; the first compatible update must be published as
a newly signed annotated tag.

## 6. Provenance, SBOM, and verification

The container workflow publishes BuildKit `mode=max` provenance and an SBOM
for the multi-platform image, then creates a GitHub/Sigstore attestation for
the registry digest. Release Actions are pinned to immutable commit SHAs and
each job receives only its required GitHub token permissions.

Verify a downloaded installer attestation:

```bash
gh attestation verify printops-1.2.6-windows-x64-setup.exe --repo ichwars/PrintOps
```

Verify a container attestation by digest or immutable version tag:

```bash
gh attestation verify oci://ghcr.io/ichwars/printops:1.2.6 --repo ichwars/PrintOps
```

Authenticode can additionally be checked on Windows with:

```powershell
Get-AuthenticodeSignature .\printops-1.2.6-windows-x64-setup.exe
```

## Key rotation

1. Generate and securely distribute the new public key alongside the old one.
2. Update `RELEASE_TAG_SSH_PUBLIC_KEY` and the native allowed-signers files in
   a coordinated maintenance window.
3. Publish the next release tag with the new private key and verify both CI
   workflows before removing the old public key.
4. Revoke the old private key in its key store. Certificate lifecycle and
   revocation remain managed by the selected signing provider.
