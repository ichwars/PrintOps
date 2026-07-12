# First Release Candidate and GHCR Package Design

## Goal

Publish PrintOps `v0.2.5rc1` as the repository's first GitHub prerelease and create the first public multi-architecture GHCR package in the same release flow.

## Release contents

- Include the changes from pull request #9.
- Set `APP_VERSION` to `0.2.5rc1` before tagging.
- Create the annotated release tag `v0.2.5rc1` from the merged `main` revision.
- Create a GitHub prerelease with generated release notes.
- Keep stable-release aliases such as `latest` unchanged.

## GitHub Actions workflow

A tag-triggered workflow owns container publication. It runs only for tags matching `v*`, with least-privilege permissions `contents: read` and `packages: write`.

The workflow:

1. Checks out the tagged revision.
2. Sets up QEMU and Docker Buildx.
3. Authenticates to GHCR with the workflow-scoped `GITHUB_TOKEN`.
4. Builds the production Dockerfile for `linux/amd64` and `linux/arm64`.
5. Pushes `ghcr.io/ichwars/printops:0.2.5rc1` and `ghcr.io/ichwars/printops:rc`.
6. Publishes OCI labels linking the package to `https://github.com/ichwars/PrintOps` so GitHub associates the package with the repository.

The existing Windows Installer workflow continues to react to the same tag and attaches its installer to the GitHub prerelease.

## Failure handling

- The GitHub prerelease is created before the tag-triggered builds begin so the installer workflow has a release to update.
- A failed image build leaves the prerelease clearly marked as prerelease and does not affect `latest`.
- Publication is successful only after both architecture manifests and the `rc` alias can be inspected from GHCR.
- If GitHub creates the initial package as private, package visibility is changed to public after the first successful push and anonymous registry access is verified.

## Verification

- Validate workflow YAML and repository formatting/lint checks before merge.
- Require PR #9 security checks to remain green.
- Verify the GitHub release is a prerelease for tag `v0.2.5rc1`.
- Verify the GHCR manifest contains `linux/amd64` and `linux/arm64`.
- Verify anonymous access to `ghcr.io/ichwars/printops:0.2.5rc1`.
- Re-run the repository-statistics workflow only after the package is public.

## Deliberate exclusions

- Do not publish or overwrite `latest`.
- Do not publish to Docker Hub in this first RC flow.
- Do not publish sidecar images.
- Do not create a stable GitHub release.
