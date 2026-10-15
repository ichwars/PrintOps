# Maintainer Guide

This document provides setup instructions for repository maintainers.

## Branch Protection Setup

To protect the `main` branch, go to **Settings > Rules > Rulesets > New ruleset > New branch ruleset**.

### Step 1: Basic Settings

| Field | Value |
|-------|-------|
| Ruleset name | `Protect main` |
| Enforcement status | `Active` |

### Step 2: Bypass List (optional)

Add yourself (`@ichwars`) to bypass if you want to push directly in emergencies.
Set "Always" or "Pull requests only" based on preference.

### Step 3: Target Branches

Click **Add target** > **Include by pattern** and enter: `main`

### Step 4: Branch Rules

Enable these rules:

**Restrict deletions** - Prevents branch deletion

**Require a pull request before merging**
- Required approvals: `1` while `@ichwars` is the only active reviewer.
- Raise to `2` only after a second named maintainer or maintainer team has
  been added to `CODEOWNERS` and can approve protected-branch PRs.
- [x] Dismiss stale pull request approvals when new commits are pushed
- [x] Require review from Code Owners
- [x] Require approval of the most recent reviewable push

**Require status checks to pass**
- [x] Require branches to be up to date before merging
- Add these status checks (they appear after CI runs once):
  - `Backend Lint`
  - `Backend Tests`
  - `Frontend Lint`
  - `Frontend Type Check`
  - `Frontend Tests`
  - `Frontend Build`
  - `Docker Build`

**Block force pushes** - Prevents history rewriting

### Sensitive Change Policy

Changes touching authentication, permissions, release automation, dependency
locks, Docker/runtime boundaries, database migrations, or document issuance need
two independent human approvals before merge once the repository has at least
two active maintainers. Until then, these changes must be merged only after all
CI, CodeQL, security audit checks, and review conversations are resolved; the
single maintainer may not count emergency bypass as a normal review path.

Sensitive paths include:

- `.github/`
- `Dockerfile*`
- `docker-compose*.yml`
- `requirements*.txt`
- `backend/app/core/auth.py`
- `backend/app/core/permissions.py`
- `backend/app/core/database.py`
- `backend/migrations/`
- `backend/app/api/routes/auth.py`
- `backend/app/services/commercial_documents.py`
- `backend/app/services/document_*`
- `scripts/`

Emergency recovery may use a documented bypass only when production users are
blocked or exposed to an active security issue. The bypassing maintainer must
open a follow-up PR or issue with the commit hash, reason, and verification.

### Bus-Factor Gate

`CODEOWNERS` currently requests `@ichwars` for every path. That protects review
routing, but it does not provide independent approval capacity. Do not raise
required approvals above `1`, enable stricter release-environment reviewer
rules, or require two-person sensitive-change approval until a second real
collaborator or GitHub team is present.

Activation checklist for the second reviewer:

1. Add the named account or team to `.github/CODEOWNERS` for at least the
   security-sensitive paths listed above.
2. Confirm the account can review a test PR without relying on bypass.
3. Raise branch-protection required approvals from `1` to `2`.
4. Add the same account or team as a required reviewer on the protected
   `release` environment with "Prevent self-review" enabled.
5. Re-run this guide after the first sensitive PR to verify CODEOWNERS,
   branch protection, and release-environment review all trigger as expected.

### Optional (stricter)

- [ ] Require conversation resolution before merging
- [ ] Require signed commits
- [ ] Require linear history

## CI Workflow

The CI workflow (`.github/workflows/ci.yml`) runs on:
- All pull requests to `main`
- All pushes to `main`

### Jobs

| Job | Purpose | Required for PR |
|-----|---------|-----------------|
| `backend-lint` | Ruff linting + format check | Yes |
| `backend-tests` | Unit tests | Yes |
| `frontend-lint` | ESLint | Yes |
| `frontend-typecheck` | TypeScript compilation | Yes |
| `frontend-tests` | Vitest unit tests | Yes |
| `frontend-build` | Vite production build | Yes |
| `docker-build` | Docker image builds | Yes |

### Fixing CI Failures

**Backend lint failures:**
```bash
ruff check --fix backend/
ruff format backend/
```

**Frontend lint failures:**
```bash
cd frontend
npm run lint -- --fix
```

**Frontend type errors:**
```bash
cd frontend
npm run typecheck
# Fix the errors shown
```

**Frontend test failures:**
```bash
cd frontend
npm run test:run
# Fix failing tests
```

## CODEOWNERS

The `CODEOWNERS` file automatically requests reviews from `@ichwars` for all changes.
This is still a bus-factor risk until a second maintainer is added to the
repository or to a dedicated GitHub team.

To add more code owners:
1. Edit `.github/CODEOWNERS`
2. Add GitHub usernames with `@` prefix
3. Assign specific paths to specific owners
4. Enable "Require review from Code Owners" in the `main` branch ruleset
5. Confirm the new owner can approve PRs without also relying on emergency bypass

Example:
```
/backend/ @ichwars @backend-contributor
/frontend/ @ichwars @frontend-contributor
```

Do not add placeholder users or teams to CODEOWNERS. Add only accounts that are
already members or collaborators with review authority.

## Release Process

1. Align the source fallback in `backend/app/core/config.py`, the package version
   in `pyproject.toml`, and the default `APP_VERSION` build argument in `Dockerfile`.
2. Update `CHANGELOG.md` and the release notes under `docs/releases/`. Rebuild
   the intentional native delivery bundle with `cd frontend && npm ci && npm run build`.
   See [repository layout](../docs/repository-layout.md) before removing generated files.
3. Create a PR with these changes and review its completed checks. After merge,
   also verify the complete CI run on the actual main commit.
4. Publish only after the release decision. For signed-tag native update trust,
   create and verify a signed annotated tag before pushing it:
   ```bash
   git tag -s v1.2.8.0 -m "PrintOps v1.2.8.0"
   git verify-tag v1.2.8.0
   git push origin v1.2.8.0
   ```
   Signed-tag trust is optional as described in the release-integrity guide.
   Pushing a supported release tag starts publication; preparing a version PR
   alone does not publish a release.
5. The protected GitHub Actions release workflows publish the explicitly unsigned
   Windows installer with checksums and the attested multi-architecture container
   image. Verify their actual artifacts and workflow results.

The complete one-time setup, trust-anchor rotation, required GitHub
environment variables, and verification commands are documented in
[`docs/release-security.md`](../docs/release-security.md).

## Dependabot (Optional)

To enable automated dependency updates, create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      python-dependencies:
        patterns:
          - "*"

  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
    groups:
      npm-dependencies:
        patterns:
          - "*"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```
