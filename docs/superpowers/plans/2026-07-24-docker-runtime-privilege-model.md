# Docker Runtime Privilege Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Docker startup path so only a bounded init phase runs as root and Python/Uvicorn always runs as a validated non-root UID/GID with only `CAP_NET_BIND_SERVICE`.

**Architecture:** Keep the existing single-container `PUID`/`PGID` model. Validate IDs before privileged work, restrict init capabilities in Compose, fail closed on ownership errors, then replace the init process with `gosu` and an `exec`-launched Python PID 1. Verify the boundary against a real production image and running integration container.

**Tech Stack:** POSIX shell, Docker/BuildKit, Docker Compose, Linux capabilities, Python 3.13/Uvicorn, GitHub Actions

## Global Constraints

- `PUID` and `PGID` remain configurable for named volumes, NAS systems, and bind mounts.
- Accepted IDs are decimal integers from `1` through `2147483647`; UID 0 and GID 0 are forbidden.
- Root init may modify only `/app/data`, `/app/logs`, and the opt-in system certificate store.
- Runtime capabilities are exactly `CHOWN`, `DAC_OVERRIDE`, `SETGID`, `SETUID`, and `NET_BIND_SERVICE` before the privilege drop.
- The Python application process may retain only `NET_BIND_SERVICE` after the privilege drop.
- No privileged mode, Docker socket, device mount, `video`/`dialout` group, `SYS_ADMIN`, `NET_ADMIN`, or `NET_RAW` may be added.
- Existing printer, camera, FFmpeg, named-volume, bind-mount, and custom non-root-ID behavior must remain functional.
- Ownership and certificate failures must fail closed with actionable output and no secret material.

## File Structure

- Create `tests/docker/runtime-security.sh`: black-box tests against the production image for ID validation, ownership safety, privilege drop, effective capabilities, and privileged-port binding.
- Create `tests/docker/assert-running-container.sh`: assertions against the live Compose integration container for PID 1, process UIDs, and effective capabilities.
- Modify `deploy/docker-entrypoint.sh`: validated init boundary, fail-closed ownership handling, symlink-safe ownership changes, and explicit privilege-drop logging.
- Modify `Dockerfile`: ensure the shell replaces itself with `python -m uvicorn`, making Python the non-root PID 1.
- Modify `docker-compose.yml`: drop all default capabilities and add only the five required init/runtime capabilities.
- Modify `docker-compose.test.yml`: run the integration service under the production capability policy.
- Modify `test_docker.sh`: invoke both Docker security regression suites locally.
- Modify `.github/workflows/ci.yml`: enforce the same regression suites in the Docker Build job.
- Create `docs/docker-runtime-security.md`: durable operator-facing privilege and migration documentation.
- Modify `docs/README.md`: link the new durable Docker security reference.
- Modify `DOCKERHUB.md`: explain `PUID`/`PGID`, short-lived root init, and explicit `user:` behavior near the quick-start configuration.

---

### Task 1: Fail-Closed Entrypoint Boundary

**Files:**
- Create: `tests/docker/runtime-security.sh`
- Modify: `deploy/docker-entrypoint.sh:1-100`

**Interfaces:**
- Consumes: production image name as optional argument `$1`, defaulting to `printops:test`.
- Produces: `validate_id NAME VALUE`, `fatal MESSAGE`, and a root init path that always ends in `exec gosu "${PUID}:${PGID}" "$@"`.

- [ ] **Step 1: Write the failing black-box tests**

Create `tests/docker/runtime-security.sh` with executable mode and this initial content:

```bash
#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:-printops:test}"
CAPS=(
  --cap-drop ALL
  --cap-add CHOWN
  --cap-add DAC_OVERRIDE
  --cap-add SETGID
  --cap-add SETUID
  --cap-add NET_BIND_SERVICE
)

run_hardened() {
  docker run --rm "${CAPS[@]}" "$@"
}

assert_invalid_id() {
  local name="$1" value="$2" output
  if output="$(run_hardened -e "${name}=${value}" "$IMAGE" true 2>&1)"; then
    echo "expected ${name}=${value@Q} to fail" >&2
    exit 1
  fi
  grep -Fq "[entrypoint] error: ${name} must be a decimal integer from 1 to 2147483647" <<<"$output"
  if grep -Fq "chown -R" <<<"$output"; then
    echo "filesystem mutation occurred before ${name} validation" >&2
    exit 1
  fi
}

for value in "" 0 -1 abc "1 " 2147483648; do
  assert_invalid_id PUID "$value"
  assert_invalid_id PGID "$value"
done

docker run --rm --user 1234:1234 -e PUID=1234 -e PGID=1234 "$IMAGE" \
  sh -c 'test "$(id -u):$(id -g)" = "1234:1234"'

if docker run --rm --cap-drop ALL --cap-add SETUID --cap-add SETGID \
  -e PUID=1234 -e PGID=1234 "$IMAGE" true; then
  echo "entrypoint ignored a required ownership failure" >&2
  exit 1
fi

run_hardened --entrypoint /bin/sh -e PUID=1234 -e PGID=1234 "$IMAGE" -c '
  rm -rf /app/data/* /tmp/printops-outside
  printf protected >/tmp/printops-outside
  chown 0:0 /tmp/printops-outside /app/data
  ln -s /tmp/printops-outside /app/data/outside-link
  /usr/local/bin/docker-entrypoint.sh sh -c '\''
    test "$(stat -c %u:%g /tmp/printops-outside)" = "0:0"
  '\''
'

echo "Docker entrypoint boundary checks passed"
```

- [ ] **Step 2: Run the tests and verify the current image fails**

Run:

```bash
docker build -t printops:test .
bash tests/docker/runtime-security.sh printops:test
```

Expected: FAIL at `PUID=0`, at the fail-closed ownership check, or at the symlink ownership check against the current entrypoint.

- [ ] **Step 3: Add validation and fail-closed helpers before privileged work**

Replace the current `PUID`/`PGID` assignment and ownership helper in `deploy/docker-entrypoint.sh` with:

```sh
fatal() {
    echo "[entrypoint] error: $*" >&2
    exit 1
}

validate_id() {
    name="$1"
    value="$2"
    case "$value" in
        ''|*[!0-9]*)
            fatal "${name} must be a decimal integer from 1 to 2147483647"
            ;;
    esac
    if [ "$value" -lt 1 ] || [ "$value" -gt 2147483647 ]; then
        fatal "${name} must be a decimal integer from 1 to 2147483647"
    fi
}

PUID="${PUID-1000}"
PGID="${PGID-1000}"
validate_id PUID "$PUID"
validate_id PGID "$PGID"
echo "[entrypoint] target identity ${PUID}:${PGID} validated"
```

Keep validation immediately after `set -eu`, before certificate or filesystem operations. Replace certificate-path `echo ...; exit 1` branches with `fatal ...`.

Replace `chown_if_needed` with:

```sh
chown_if_needed() {
    target="$1"
    [ -d "$target" ] || mkdir -p -- "$target" || fatal "cannot create ${target}"
    current="$(stat -c '%u:%g' "$target" 2>/dev/null || echo '')"
    if [ "$current" != "$PUID:$PGID" ]; then
        echo "[entrypoint] normalizing ownership of ${target} to ${PUID}:${PGID}"
        chown -R -h -- "${PUID}:${PGID}" "$target" \
            || fatal "cannot set ownership of ${target}; check the mount and PUID/PGID"
    fi
}
```

Remove the redundant nested `/app/data/virtual_printer` ownership pass because it is already inside the constant `/app/data` tree. Before the final command, log and retain the existing irreversible replacement:

```sh
echo "[entrypoint] starting application as ${PUID}:${PGID}"
exec gosu "${PUID}:${PGID}" "$@"
```

- [ ] **Step 4: Rebuild and verify the entrypoint tests pass**

Run:

```bash
docker build -t printops:test .
bash -n deploy/docker-entrypoint.sh tests/docker/runtime-security.sh
bash tests/docker/runtime-security.sh printops:test
```

Expected: `Docker entrypoint boundary checks passed`, exit 0.

- [ ] **Step 5: Commit the entrypoint boundary**

```bash
git add deploy/docker-entrypoint.sh tests/docker/runtime-security.sh
git commit -m "fix(docker): fail closed before privilege drop"
```

### Task 2: Minimal Capabilities and Python PID 1

**Files:**
- Modify: `tests/docker/runtime-security.sh`
- Modify: `Dockerfile:154-164`
- Modify: `docker-compose.yml:8-21`

**Interfaces:**
- Consumes: `run_hardened` and `CAPS` from Task 1.
- Produces: Python invoked through `exec python -m uvicorn`; Compose capability allowlist of `CHOWN`, `DAC_OVERRIDE`, `SETGID`, `SETUID`, and `NET_BIND_SERVICE`.

- [ ] **Step 1: Extend the black-box test with capability and port assertions**

Insert before the final success message in `tests/docker/runtime-security.sh`:

```bash
run_hardened -i "$IMAGE" python - <<'PY'
from pathlib import Path
import socket

status = Path("/proc/self/status").read_text(encoding="utf-8")
cap_eff = next(line.split()[1] for line in status.splitlines() if line.startswith("CapEff:"))
assert int(cap_eff, 16) == 1 << 10, cap_eff  # CAP_NET_BIND_SERVICE

sockets = []
try:
    for port in (322, 990):
        sock = socket.socket()
        sock.bind(("127.0.0.1", port))
        sockets.append(sock)
finally:
    for sock in sockets:
        sock.close()
PY

python - <<'PY'
import json
import subprocess

config = subprocess.check_output(
    ["docker", "compose", "config", "--format", "json"], text=True
)
service = json.loads(config)["services"]["printops"]
assert service.get("cap_drop") == ["ALL"], service.get("cap_drop")
cap_add = service.get("cap_add", [])
expected = {"CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID", "NET_BIND_SERVICE"}
assert len(cap_add) == len(expected) and set(cap_add) == expected, cap_add
PY
```

- [ ] **Step 2: Run the extended test and verify it fails against current Compose**

Run:

```bash
bash tests/docker/runtime-security.sh printops:test
```

Expected: FAIL because Compose does not drop all capabilities or declare the complete allowlist.

- [ ] **Step 3: Restrict Compose and make Python PID 1**

Replace the current capability block in `docker-compose.yml` with:

```yaml
    # Root exists only during entrypoint initialization. Drop Docker's broad
    # default set and allow only volume ownership, UID/GID transition, and the
    # two privileged virtual-printer ports. Python retains only
    # NET_BIND_SERVICE after gosu + exec.
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - DAC_OVERRIDE
      - SETGID
      - SETUID
      - NET_BIND_SERVICE
```

Replace the final Dockerfile command with:

```dockerfile
CMD ["sh", "-c", "exec python -m uvicorn backend.app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000} --loop asyncio"]
```

Update the adjacent comments to state that the shell performs environment expansion and then replaces itself, so Python becomes PID 1.

- [ ] **Step 4: Rebuild and verify the reduced capability model**

Run:

```bash
docker build -t printops:test .
docker compose config --quiet
bash tests/docker/runtime-security.sh printops:test
```

Expected: all entrypoint, effective-capability, port-binding, and Compose allowlist checks pass.

- [ ] **Step 5: Commit the capability boundary**

```bash
git add Dockerfile docker-compose.yml tests/docker/runtime-security.sh
git commit -m "security(docker): minimize runtime capabilities"
```

### Task 3: Running-Container Regression Gate

**Files:**
- Create: `tests/docker/assert-running-container.sh`
- Modify: `docker-compose.test.yml:22-39`
- Modify: `test_docker.sh:176-227`
- Modify: `.github/workflows/ci.yml:329-384`

**Interfaces:**
- Consumes: running container name `$1`, expected UID `$2`, and expected GID `$3`.
- Produces: exit 0 only when the container capability allowlist is exact, PID 1 is non-root, every PID 1 descendant is non-root, and PID 1 has exactly `CAP_NET_BIND_SERVICE`.

- [ ] **Step 1: Write the failing live-container assertion**

Create `tests/docker/assert-running-container.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

container="${1:?container name required}"
expected_uid="${2:-1000}"
expected_gid="${3:-1000}"

python - "$container" <<'PY'
import json
import subprocess
import sys

container = json.loads(
    subprocess.check_output(["docker", "inspect", sys.argv[1]], text=True)
)[0]
host_config = container["HostConfig"]
assert host_config["CapDrop"] == ["ALL"], host_config["CapDrop"]
cap_add = host_config["CapAdd"] or []
expected = {"CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID", "NET_BIND_SERVICE"}
assert len(cap_add) == len(expected) and set(cap_add) == expected, cap_add
PY

docker exec -i --user "${expected_uid}:${expected_gid}" \
  -e EXPECTED_UID="$expected_uid" -e EXPECTED_GID="$expected_gid" \
  "$container" python - <<'PY'
import os
from pathlib import Path

expected_uid = int(os.environ["EXPECTED_UID"])
expected_gid = int(os.environ["EXPECTED_GID"])
status = Path("/proc/1/status").read_text(encoding="utf-8")
fields = {line.split(":", 1)[0]: line.split(":", 1)[1].split() for line in status.splitlines() if ":" in line}
assert int(fields["Uid"][0]) == expected_uid, fields["Uid"]
assert int(fields["Gid"][0]) == expected_gid, fields["Gid"]
assert int(fields["CapEff"][0], 16) == 1 << 10, fields["CapEff"]

processes = {}
for status_path in Path("/proc").glob("[0-9]*/status"):
    try:
        process = status_path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        continue
    process_fields = {
        line.split(":", 1)[0]: line.split(":", 1)[1].split()
        for line in process.splitlines()
        if ":" in line
    }
    if "Uid" in process_fields and "PPid" in process_fields:
        processes[int(status_path.parent.name)] = (
            int(process_fields["PPid"][0]),
            int(process_fields["Uid"][0]),
        )

root_descendants = []
for pid, (_, uid) in processes.items():
    ancestor = pid
    seen = set()
    while ancestor in processes and ancestor not in seen:
        seen.add(ancestor)
        if ancestor == 1:
            if uid == 0:
                root_descendants.append(pid)
            break
        ancestor = processes[ancestor][0]
assert not root_descendants, root_descendants
PY

echo "Running container privilege checks passed"
```

- [ ] **Step 2: Start the current integration service and verify the assertion fails before its Compose policy is updated**

Run:

```bash
docker compose -f docker-compose.test.yml up -d --build integration
bash tests/docker/assert-running-container.sh printops-integration-test 1000 1000
```

Expected: FAIL because the integration service still uses Docker's default capability policy.

- [ ] **Step 3: Apply the production capability policy to integration tests**

Add to `docker-compose.test.yml` under `integration`:

```yaml
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - DAC_OVERRIDE
      - SETGID
      - SETUID
      - NET_BIND_SERVICE
```

In `test_docker.sh`, after the integration container becomes healthy, add:

```bash
        if bash tests/docker/assert-running-container.sh printops-integration-test 1000 1000; then
            print_success "Application runtime is non-root with minimal capabilities"
        else
            print_failure "Application runtime privilege check failed"
        fi
```

In `.github/workflows/ci.yml`, immediately after `Test health endpoint`, add:

```yaml
      - name: Test non-root runtime boundary
        run: bash tests/docker/assert-running-container.sh printops-integration-test 1000 1000

      - name: Test entrypoint and capability policy
        run: bash tests/docker/runtime-security.sh printops:test
```

- [ ] **Step 4: Run both local Docker security gates**

Run:

```bash
docker compose -f docker-compose.test.yml up -d --build integration
bash tests/docker/assert-running-container.sh printops-integration-test 1000 1000
bash tests/docker/runtime-security.sh printops:test
curl --fail http://localhost:8001/health
docker compose -f docker-compose.test.yml down -v --remove-orphans
```

Expected: both scripts print their success messages, health returns HTTP 200, and cleanup exits 0.

- [ ] **Step 5: Commit the CI regression gate**

```bash
git add tests/docker/assert-running-container.sh docker-compose.test.yml test_docker.sh .github/workflows/ci.yml
git commit -m "test(docker): enforce non-root application runtime"
```

### Task 4: Durable Operator Documentation

**Files:**
- Create: `docs/docker-runtime-security.md`
- Modify: `docs/README.md`
- Modify: `DOCKERHUB.md`

**Interfaces:**
- Consumes: final capability and startup behavior from Tasks 1-3.
- Produces: operator guidance for normal Compose, custom IDs, explicit `user:`, certificate opt-in, and migration from UID/GID 0.

- [ ] **Step 1: Write the durable runtime reference**

Create `docs/docker-runtime-security.md` with these exact sections and facts:

```markdown
# Docker runtime security

PrintOps uses a short root initialization phase so named volumes and bind mounts
remain compatible with configurable host user IDs. The Python application does
not run as root.

## Startup sequence

1. Validate `PUID` and `PGID` as decimal values from 1 through 2147483647.
2. Normalize ownership of `/app/data` and `/app/logs` when required.
3. Optionally update the system trust store when `USE_SYSTEM_TRUST_STORE` is set.
4. Replace the init process with `gosu PUID:PGID` and `python -m uvicorn`.

Python becomes PID 1 and retains only `CAP_NET_BIND_SERVICE`, which is required
for the virtual-printer listeners on ports 322 and 990.

## Capability allowlist

The init phase receives only `CHOWN`, `DAC_OVERRIDE`, `SETGID`, `SETUID`, and
`NET_BIND_SERVICE`. PrintOps does not require privileged mode, the Docker
socket, host devices, `video` or `dialout` membership, `SYS_ADMIN`, `NET_ADMIN`,
or `NET_RAW`. Printers and camera streams are accessed over the network; FFmpeg
runs in userspace.

## Choosing PUID and PGID

The defaults are `1000:1000`. For bind mounts, use `id -u` and `id -g` on the
Docker host and set the matching values in `.env`. Values of 0 are rejected.

## Explicit Docker user mode

When `user:` or `docker run --user` starts the container as non-root, the
entrypoint cannot change volume ownership or the system trust store. Prepare
both on the host first. `USE_SYSTEM_TRUST_STORE` intentionally fails in this
mode rather than being ignored.

## Migration

Installations already using non-root IDs need no change. Installations with
`PUID=0` or `PGID=0` must switch to a non-root host identity before upgrading.
If startup reports an ownership error, correct the host mount permissions or
select matching IDs; PrintOps will not continue with unsafe permissions.
```

- [ ] **Step 2: Link the reference from the docs index and Docker Hub page**

Add this row to the documentation table in `docs/README.md`:

```markdown
| Betrieb | [Docker-Laufzeitsicherheit](docker-runtime-security.md) | Root-Init, PUID/PGID, Capabilities und Volume-Rechte |
```

After the `PUID`/`PGID` configuration table in `DOCKERHUB.md`, add a concise
`Runtime security` section linking to `docs/docker-runtime-security.md` and
stating that the application runs non-root after the bounded init phase.

- [ ] **Step 3: Validate documentation and repository formatting**

Run:

```bash
git diff --check
rg -n "PUID=0|PGID=0|privileged mode|NET_BIND_SERVICE|docker-runtime-security" \
  docs/docker-runtime-security.md docs/README.md DOCKERHUB.md
rg -n "unfinished implementation marker" docs/docker-runtime-security.md
```

Expected: `git diff --check` exits 0, all required concepts are found, and the placeholder scan has no matches.

- [ ] **Step 4: Commit the operator documentation**

```bash
git add docs/docker-runtime-security.md docs/README.md DOCKERHUB.md
git commit -m "docs(docker): document runtime privilege boundary"
```

### Task 5: Full Verification, Pull Request, and Merge

**Files:**
- Verify only; no new files expected.

**Interfaces:**
- Consumes: all commits from Tasks 1-4.
- Produces: rebased branch, green CI, merged pull request, and closed DS-0002 work item.

- [ ] **Step 1: Run deterministic local checks**

```bash
bash -n deploy/docker-entrypoint.sh tests/docker/runtime-security.sh tests/docker/assert-running-container.sh test_docker.sh
docker compose config --quiet
docker compose -f docker-compose.test.yml config --quiet
docker build -t printops:test .
bash tests/docker/runtime-security.sh printops:test
docker compose -f docker-compose.test.yml up -d integration
bash tests/docker/assert-running-container.sh printops-integration-test 1000 1000
curl --fail http://localhost:8001/health
docker compose -f docker-compose.test.yml down -v --remove-orphans
git diff --check origin/main...HEAD
git status --short
```

Expected: syntax and Compose checks exit 0; image builds; both security scripts pass; health returns HTTP 200; no container remains; only the pre-existing `static/index.html` line-ending artifact may remain unstaged.

- [ ] **Step 2: Rebase on current main and repeat the focused gates**

```bash
git fetch origin
git rebase origin/main
docker compose config --quiet
docker build -t printops:test .
bash tests/docker/runtime-security.sh printops:test
```

Expected: clean rebase and all focused gates pass.

- [ ] **Step 3: Push and create the pull request**

```bash
git push -u origin codex/docker-root-init-hardening
gh pr create \
  --base main \
  --head codex/docker-root-init-hardening \
  --title "security(docker): harden non-root runtime boundary" \
  --body "Closes DS-0002 by validating non-root IDs, minimizing init capabilities, failing closed on ownership errors, making Python the non-root PID 1, and adding Docker runtime regression coverage. PUID/PGID, named-volume, bind-mount, certificate, FFmpeg, camera, and virtual-printer compatibility are retained."
```

Expected: branch push succeeds and GitHub returns the new pull-request URL.

- [ ] **Step 4: Wait for every required check and resolve only in-scope failures**

```bash
gh pr checks --watch
```

Expected: every required check is green. If a Docker-runtime check fails, reproduce it locally, add a regression, fix minimally, rerun Tasks 1-5 focused checks, commit, and push. Do not modify unrelated active-session work.

- [ ] **Step 5: Merge and verify main**

```bash
gh pr merge --squash --delete-branch
git fetch origin
gh pr view --json state,mergedAt,mergeCommit,url
gh run list --branch main --limit 10
```

Expected: PR state is `MERGED`, a merge commit and timestamp are present, and the resulting `main` workflows are green.

## Self-Review

- **Spec coverage:** Tasks 1-4 cover validation, bounded root actions, fail-closed ownership, privilege drop, exact capabilities, ports, PID 1, process tree, volumes, certificates, migration, CI, and durable documentation. Task 5 covers release verification and merge.
- **Placeholder scan:** The plan contains no deferred implementation markers or unspecified test requests.
- **Interface consistency:** Both Docker scripts consistently accept image/container and identity arguments; the same five-capability allowlist appears in production Compose, test Compose, black-box tests, and documentation.
- **Scope:** No printer, camera, FFmpeg, device, frontend, backend API, or data-model behavior is changed.
