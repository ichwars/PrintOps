#!/usr/bin/env bash
set -euo pipefail

# Git Bash rewrites Linux container paths into Windows host paths unless disabled.
export MSYS_NO_PATHCONV=1

IMAGE="${1:-printops:test}"
scratch="$(mktemp -d)"
project="printops-runtime-check-${scratch##*.}"
project="${project,,}"
compose=(
  docker compose -p "$project" -f docker-compose.yml -f "$scratch/compose.yml"
)
compose_active=false
bind_owner=""

cleanup() {
  if "$compose_active"; then
    compose_test down -v --remove-orphans
  fi
  if [ -n "$bind_owner" ]; then
    docker run --rm --network none --user 0:0 --cap-drop ALL \
      --cap-add CHOWN --cap-add DAC_OVERRIDE --entrypoint chown \
      --mount "type=bind,src=$scratch/virtual_printer,dst=/fixture" \
      "$IMAGE" -Rh -- "$bind_owner" /fixture
  fi
  rm -rf -- "$scratch"
}
trap cleanup EXIT

run_hardened() {
  docker run --rm --network none --cap-drop ALL --cap-add NET_BIND_SERVICE "$@"
}

assert_startup_error() {
  local expected="$1" output
  shift
  if output="$(run_hardened "$@" "$IMAGE" true 2>&1)"; then
    echo "expected the entrypoint to reject the supplied configuration" >&2
    exit 1
  fi
  grep -Fq "$expected" <<<"$output"
}

for value in "" 0 -1 abc "1 " 2147483648 999999999999999999999999999; do
  for name in PUID PGID; do
    assert_startup_error "$name must be a decimal integer from 1 to 2147483647" -e "$name=$value"
  done
done
assert_startup_error "the application requires a non-root user and group" --user 0:0 -e PUID=1000 -e PGID=1000
assert_startup_error "run the container as 1234:1000 to match PUID/PGID" -e PUID=1234
assert_startup_error "/app/data is not writable by 1234:2345" --user 1234:2345
assert_startup_error "no .crt files" -e USE_SYSTEM_TRUST_STORE=1

run_hardened -i "$IMAGE" python - <<'PY'
from pathlib import Path
import os
import socket

assert (os.getuid(), os.getgid()) == (1000, 1000)
status = Path("/proc/self/status").read_text(encoding="utf-8")
cap_eff = next(line.split()[1] for line in status.splitlines() if line.startswith("CapEff:"))
assert int(cap_eff, 16) == 1 << 10, cap_eff  # CAP_NET_BIND_SERVICE

for port in (322, 990):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))
PY

# The mount is read-only. A custom CA must be usable without modifying /etc
# or losing the distribution's default trust anchors.
mkdir -m 0755 "$scratch/certs"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=PrintOps test CA" \
  -keyout "$scratch/key.pem" -out "$scratch/certs/test.crt" >/dev/null 2>&1
chmod 0755 "$scratch"
chmod 0644 "$scratch/certs/test.crt"
run_hardened -i -e USE_SYSTEM_TRUST_STORE=1 \
  --mount "type=bind,src=$scratch/certs,dst=/usr/local/share/ca-certificates,readonly" "$IMAGE" python - <<'PY'
import os
from pathlib import Path
import ssl

certificate = Path("/usr/local/share/ca-certificates/test.crt").read_text(encoding="ascii")
custom_der = ssl.PEM_cert_to_DER_cert(certificate)
assert custom_der in ssl.create_default_context().get_ca_certs(binary_form=True)
base_bundle = Path("/etc/ssl/certs/ca-certificates.crt")
assert certificate not in base_bundle.read_text(encoding="ascii")
default_certs = ssl.create_default_context(cafile=str(base_bundle)).get_ca_certs(binary_form=True)
assert set(default_certs) <= set(ssl.create_default_context().get_ca_certs(binary_form=True))
assert Path(os.environ["SSL_CERT_FILE"]).is_file()
PY
printf '%s\n' 'not a PEM certificate' > "$scratch/certs/invalid.crt"
assert_startup_error "invalid CA certificate" -e USE_SYSTEM_TRUST_STORE=1 \
  --mount "type=bind,src=$scratch/certs,dst=/usr/local/share/ca-certificates,readonly"

python - "$IMAGE" <<'PY'
import json
import subprocess
import sys

image = json.loads(
    subprocess.check_output(["docker", "image", "inspect", sys.argv[1]], text=True)
)[0]
assert image["Config"]["User"] == "1000:1000", image["Config"]["User"]
healthcheck = image["Config"]["Healthcheck"]["Test"]
assert healthcheck[0] == "CMD-SHELL", healthcheck
assert "os.getuid()" in healthcheck[1] and "os.getgid()" in healthcheck[1], healthcheck
PY

# Use the production service definitions with a unique project, no host network
# and a temporary nested bind mount. The initializer must work even when the
# parent is already owned by the requested identity.
mkdir -m 0755 "$scratch/virtual_printer"
bind_owner="$(docker run --rm --network none --user 0:0 --cap-drop ALL --entrypoint stat \
  --mount "type=bind,src=$scratch/virtual_printer,dst=/fixture" "$IMAGE" -c "%u:%g" /fixture)"
cat > "$scratch/compose.yml" <<YAML
services:
  printops:
    image: "$IMAGE"
    container_name: "$project-app"
    network_mode: none
    volumes:
      - "$scratch/virtual_printer:/app/data/virtual_printer"
  printops-init:
    image: "$IMAGE"
    volumes:
      - "$scratch/virtual_printer:/app/data/virtual_printer"
YAML

compose_test() {
  PUID=1234 PGID=2345 "${compose[@]}" "$@"
}

compose_active=true
compose_test run --rm --no-deps --pull never --entrypoint /bin/sh printops-init -ec '
  chown -Rh 1234:2345 /app/data
  chown 0:0 /app/data/virtual_printer
  ln -s /etc/passwd /app/logs/outside-link
'
compose_test up --no-build --pull never --wait --wait-timeout 90 printops
initializer="$(compose_test ps -aq printops-init)"
docker inspect "$initializer" --format '{{.HostConfig.NetworkMode}} {{.HostConfig.ReadonlyRootfs}} {{.State.ExitCode}}' \
  | grep -Fx 'none true 0'
runtime="$(compose_test ps -q printops)"
bash tests/docker/assert-running-container.sh "$runtime" 1234 2345
compose_test exec -T printops sh -ec '
  for target in /app/data /app/data/virtual_printer /app/logs; do
    test "$(stat -c "%u:%g" "$target")" = 1234:2345
    test -w "$target"
  done
  test "$(stat -Lc "%u:%g" /app/logs/outside-link)" = 0:0
'

echo "Docker entrypoint boundary checks passed"
