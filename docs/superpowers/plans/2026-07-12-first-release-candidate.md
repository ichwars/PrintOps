# First Release Candidate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish PrintOps `v0.2.5rc1` as a GitHub prerelease and create its first public multi-architecture GHCR package while completing pull request #9.

**Architecture:** A tag-triggered GitHub Actions workflow builds the production Dockerfile and publishes two RC-only GHCR tags using the repository-scoped `GITHUB_TOKEN`. The version and workflow land through PR #9, which is merged before the release tag and prerelease are created.

**Tech Stack:** GitHub Actions, Docker Buildx, GHCR, Python application configuration, GitHub CLI

## Global Constraints

- Release version is exactly `0.2.5rc1`; Git tag is exactly `v0.2.5rc1`.
- Publish `linux/amd64` and `linux/arm64` manifests.
- Publish only GHCR tags `0.2.5rc1` and `rc`; never publish or overwrite `latest`.
- Do not publish Docker Hub or sidecar images.
- The GitHub release must remain a prerelease.
- The package must link to `https://github.com/ichwars/PrintOps` and be anonymously readable before completion.

---

### Task 1: Add RC version and container release workflow

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `.github/workflows/release-container.yml`

**Interfaces:**
- Consumes: tag ref `refs/tags/v0.2.5rc1`, repository `GITHUB_TOKEN`
- Produces: GHCR manifests `ghcr.io/ichwars/printops:0.2.5rc1` and `ghcr.io/ichwars/printops:rc`

- [ ] **Step 1: Set the application version**

Change the existing constant to:

```python
APP_VERSION = "0.2.5rc1"
```

- [ ] **Step 2: Add the tag-triggered workflow**

Create `.github/workflows/release-container.yml` with tag trigger `v*`, permissions `contents: read` and `packages: write`, QEMU, Buildx, GHCR login, Docker metadata, and `docker/build-push-action@v7`. Configure exact tags `0.2.5rc1` from the tag value without `v` and `rc`, platforms `linux/amd64,linux/arm64`, and OCI source label `https://github.com/ichwars/PrintOps`.

- [ ] **Step 3: Validate configuration and workflow syntax**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_updates_api.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -c "import yaml; yaml.safe_load(open('.github/workflows/release-container.yml', encoding='utf-8'))"
.\.venv\Scripts\python.exe -m ruff check backend/app/core/config.py
git diff --check
```

Expected: all commands exit `0`.

- [ ] **Step 4: Commit and update PR #9**

```powershell
git add backend/app/core/config.py .github/workflows/release-container.yml docs/superpowers/plans/2026-07-12-first-release-candidate.md
git commit -m "Add release candidate publishing workflow"
git push origin codex/calculation-workspace-publish
```

Expected: PR #9 contains the version and workflow changes.

### Task 2: Verify and merge pull request #9

**Files:**
- No repository file changes.

**Interfaces:**
- Consumes: PR #9 head with Task 1 commit
- Produces: merged `main` revision containing calculation workspace, security fixes, version, and release workflow

- [ ] **Step 1: Wait for required checks**

Run:

```powershell
gh pr checks 9 --watch --interval 10
```

Expected: all non-skipped checks pass.

- [ ] **Step 2: Confirm mergeability and exact version**

```powershell
gh pr view 9 --json mergeable,mergeStateStatus,state
git show origin/codex/calculation-workspace-publish:backend/app/core/config.py | Select-String 'APP_VERSION = "0.2.5rc1"'
```

Expected: `MERGEABLE`, clean merge state, and exact version match.

- [ ] **Step 3: Merge the PR and synchronize main**

```powershell
gh pr merge 9 --merge --delete-branch
git switch main
git pull --ff-only origin main
```

Expected: PR state is `MERGED` and local `main` matches `origin/main`.

### Task 3: Create the prerelease and release tag

**Files:**
- No repository file changes.

**Interfaces:**
- Consumes: verified merged `main` revision
- Produces: Git tag and GitHub prerelease `v0.2.5rc1`, triggering container and installer workflows

- [ ] **Step 1: Ensure the tag and release do not already exist**

```powershell
git ls-remote --tags origin refs/tags/v0.2.5rc1
gh release view v0.2.5rc1
```

Expected: both report no existing object before creation.

- [ ] **Step 2: Atomically create the prerelease and tag**

```powershell
gh release create v0.2.5rc1 --target main --title "PrintOps 0.2.5 RC1" --prerelease --generate-notes
```

Expected: GitHub creates the tag on merged `main`, publishes the release with `isPrerelease: true`, and starts both tag-triggered workflows.

### Task 4: Verify package, installer, and statistics

**Files:**
- No repository file changes.

**Interfaces:**
- Consumes: tag-triggered workflow runs and first GHCR package
- Produces: verified public RC package, installer asset, and refreshed repository statistics

- [ ] **Step 1: Monitor tag-triggered workflows**

```powershell
$runs = gh run list --branch v0.2.5rc1 --limit 10 --json databaseId,workflowName | ConvertFrom-Json
$containerRun = ($runs | Where-Object workflowName -eq 'Release Container').databaseId
$installerRun = ($runs | Where-Object workflowName -eq 'Windows Installer').databaseId
gh run watch $containerRun --exit-status
gh run watch $installerRun --exit-status
```

Expected: container and Windows Installer workflows succeed.

- [ ] **Step 2: Verify release metadata and installer asset**

```powershell
gh release view v0.2.5rc1 --json tagName,isPrerelease,isDraft,assets
```

Expected: tag is `v0.2.5rc1`, prerelease is true, draft is false, and at least one Windows `.exe` asset exists.

- [ ] **Step 3: Make the initial GHCR package public if required**

Inspect the package endpoint. If anonymous access is denied, change package visibility to public through GitHub package settings, then repeat the anonymous check. Do not report completion while access remains private or absent.

- [ ] **Step 4: Verify both package architectures and tags**

```powershell
docker buildx imagetools inspect ghcr.io/ichwars/printops:0.2.5rc1
docker buildx imagetools inspect ghcr.io/ichwars/printops:rc
```

Expected: both resolve and the versioned manifest lists `linux/amd64` and `linux/arm64`.

- [ ] **Step 5: Re-run repository statistics**

```powershell
gh workflow run repo-stats.yml
```

Resolve and monitor the run with `gh run list --workflow repo-stats.yml --limit 1 --json databaseId`, then pass its `databaseId` to `gh run watch`. Expected: `inject-ghcr-pulls` and the complete workflow succeed.
