# Security Policy

## Reporting a Vulnerability

The PrintOps team takes security seriously. We appreciate your efforts to
responsibly disclose findings.

**Do not report vulnerabilities in a public issue, discussion, or pull
request.** Submit a private report through
[GitHub Private Vulnerability Reporting](https://github.com/ichwars/PrintOps/security/advisories/new).
The repository maintainers use that private advisory to discuss the report,
coordinate a fix, request a CVE when appropriate, and credit the reporter.

### What to Include

Please include the following information in your report:

- **Description** of the vulnerability
- **Steps to reproduce** the issue
- **Affected versions** of PrintOps
- **Potential impact** of the vulnerability
- **Any suggested fixes** (if you have them)
- **Whether and when you plan to disclose the issue publicly**

### What to Expect

- **Acknowledgment**: We aim to acknowledge the report within 48 hours.
- **Assessment**: We aim to provide an initial validation and severity
  assessment within 7 days.
- **Updates**: We will provide a status update at least every 7 days while a
  confirmed issue remains open.
- **Resolution**: We aim to release a fix within 30 days for critical issues.
  Complex or ecosystem-dependent fixes may require a mutually agreed timeline.
- **Credit**: We will credit you in the advisory and release notes unless you
  prefer to remain anonymous.

Please allow us to coordinate publication through the private advisory. We
will not pursue legal action against good-faith research that avoids privacy
violations, data destruction, service disruption, social engineering, and
access beyond what is necessary to demonstrate the issue.

### Maintainer Process

1. A maintainer acknowledges and privately triages the report.
2. Confirmed issues receive a severity, affected-version range, remediation
   owner, and target release.
3. Fixes are developed without exposing exploit details and receive
   security-focused review.
4. The fix and advisory are published together when practical. Reporters are
   notified before coordinated disclosure.
5. Follow-up actions are tracked after release, including dependency or
   configuration hardening where relevant.

## Supported Versions

The latest published PrintOps release receives security fixes. Older releases
are supported on a best-effort basis; reporters should still include every
version they have confirmed as affected.

## Security Considerations

### Network Security

PrintOps communicates with your printers over your local network using:

- **MQTT over TLS** (port 8883) - Encrypted printer communication
- **FTPS** (port 990) - Encrypted file transfers

### Recommendations

1. **Run on trusted network**: PrintOps should only be accessible on your local network
2. **Use reverse proxy**: If exposing to the internet, use a reverse proxy with HTTPS
3. **Keep updated**: Always run the latest version for security patches
4. **Secure API keys**: Treat API keys like passwords; don't share them publicly
5. **Developer Mode**: Use your printer's Developer Mode access code; don't share it

### Known Security Features

- API key authentication for external access
- No default credentials
- Local-only by default (no cloud dependency)
- TLS encryption for printer communication

## Scope

The following are **in scope** for security reports:

- Authentication/authorization bypasses
- Remote code execution
- SQL injection
- Cross-site scripting (XSS)
- Cross-site request forgery (CSRF)
- Sensitive data exposure
- Insecure direct object references
- Vulnerabilities in dependencies shipped by PrintOps when they affect a
  supported PrintOps artifact or configuration

The following are **out of scope**:

- Social engineering attacks
- Physical attacks
- Denial of service claims that rely only on unrealistic traffic volumes
- Issues requiring physical access to the server
- Automated scanner output without a reproducible impact on PrintOps

## PrintOps Security Stance

The following rules apply to every PR that touches authentication,
authorization, permission gating, secret handling, or any code that
decides whether to allow or deny an action. They are not aspirational —
each one is enforced by a CI test that fails the build on violation.

### 1. Default-deny, allowlist over denylist

At any security boundary, the safe default is to deny and the
exceptions are listed explicitly. Denylists fail open on growth — every
new resource added to the codebase is implicitly granted access until
someone remembers to deny it. Allowlists fail closed: an unmapped new
resource gets a 403, which is loud and recoverable.

Concretely:

- `_APIKEY_SCOPE_BY_PERMISSION` in `backend/app/core/auth.py` is the
  load-bearing API-key authorization map. Every `Permission` enum value
  must be either present here with a scope flag, or present in
  `_APIKEY_DENIED_PERMISSIONS`. Unmapped permissions return 403.
- Route auth dependencies are explicit, not implicit. A route without a
  `Depends(require_*)` decorator must be listed in the route-audit
  `PUBLIC_ROUTES` allowlist with a justification comment, or CI fails.

### 2. Fail-closed in auth code

No `except Exception:` (or bare `except:`) in authentication,
authorization, or permission code may return a permissive value
(`None`, `True`, an admin user, an empty filter that lets everything
through, etc.). The catch-all either re-raises or returns a denial.
This is CWE-636 "Not Failing Securely" — see
<https://cwe.mitre.org/data/definitions/636.html>.

The lint scope is `backend/app/core/auth.py`,
`backend/app/core/permissions.py`,
`backend/app/api/routes/auth*.py`. Any `except Exception:` block in
those files must be tagged `# SEC-AUTH-EXC: <reason>` on the same
line; CI fails otherwise. (We use a standalone marker rather than
`# noqa: ...` because ruff reserves the latter syntax for its own
error codes.)

### 3. No hardcoded fallback secrets

Production secrets (JWT signing keys, encryption keys, OAuth client
secrets, API tokens) have no string-literal fallback in source. The
codebase reads them from env vars or generates them on first run; if a
secret is missing AND cannot be generated, the app refuses to start
rather than booting with a known value. CI greps the source for
`-change-in-production`-shaped strings and fails on any hit.

### 4. Negative-path tests required for any auth change

Any PR that adds or modifies an auth dependency, permission check, or
scope flag includes tests for the negative paths:

- "No credentials → 401"
- "Wrong credentials → 401"
- "Right credentials, wrong scope → 403"
- "Expired / revoked credentials → 401"

A test asserting the happy path passes is necessary but not sufficient.
The failure modes are where the vulnerabilities live. The structural
backstops above catch *categories* of regression; the negative-path
tests catch *specific* regressions in the new code.

### 5. Path joins under a trusted parent use the safe-join helper

Anywhere a PrintOps code path joins a string from outside the function's
scope (request body, query/path param, `UploadFile.filename`, ZIP
`namelist()` entry, tarfile member, **printer FTP-listing entry**) under
a trusted directory, the join must route through
`backend.app.utils.safe_path.safe_join_under(parent, *parts)`. The helper
resolves the joined path and asserts it is a descendant of the parent —
defeating both absolute-path collapse (`Path("/a") / "/b"` → `Path("/b")`)
and `..` traversal.

Sites that have an inline guard (an explicit resolve + `is_relative_to`,
a basename-stripping helper like `_safe_filename`, or a pre-validated
alphanumeric filter) carry a `# SEC-PATH-OK: <reason>` marker on the
same line. CI walks **both** `backend/app/api/routes/` and
`backend/app/services/` and fails the build on any
``<dir-like> / <variable>`` join without either the helper or the
marker. The services layer is in scope because it receives values from
the routes verbatim and from external sources PrintOps has no control
over (the compromised-printer threat model: a malicious printer can
serve crafted FTP-listing entries that flow straight into a path join).

### Where these rules live in the codebase

| Rule | Enforcement | Location |
|------|-------------|----------|
| 1. Allowlist over denylist (Permission) | `test_every_permission_has_a_classification` | `backend/tests/integration/test_auth_apikey_rbac.py` |
| 1. Allowlist over denylist (routes) | `test_routes_have_explicit_auth_deps` | `backend/tests/unit/test_route_auth_coverage.py` |
| 2. Fail-closed in auth code | `test_no_fail_open_in_auth_modules` | `backend/tests/unit/test_no_fail_open_in_auth.py` |
| 3. No hardcoded fallback secrets | `test_no_hardcoded_secrets` | `backend/tests/unit/test_no_hardcoded_secrets.py` |
| 4. Negative-path tests required | Reviewer responsibility (no automated CI gate yet) | PR review |
| 5. Safe-join under trusted parent | `test_route_path_arithmetic_is_safe_joined_or_marked` | `backend/tests/unit/test_no_unsafe_path_joins.py` |

If you are adding a CI rule, update this table. If you are removing a
CI rule, you are removing a security backstop and the PR description
must explain why.

---

Thank you for helping keep PrintOps and its users safe!
