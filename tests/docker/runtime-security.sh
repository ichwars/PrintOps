#!/usr/bin/env bash
set -euo pipefail

# Git Bash rewrites Linux container paths into Windows host paths unless path
# conversion is disabled for Docker CLI arguments.
export MSYS_NO_PATHCONV=1

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

# A nested bind mount can be root-owned even when its parent already matches
# PUID:PGID. The entrypoint must normalize it independently.
run_hardened --entrypoint /bin/sh -e PUID=1234 -e PGID=1234 "$IMAGE" -c '
  rm -rf /app/data/virtual_printer
  mkdir -p /app/data/virtual_printer
  chown 1234:1234 /app/data
  chown 0:0 /app/data/virtual_printer
  /usr/local/bin/docker-entrypoint.sh sh -c '\''
    test "$(stat -c %u:%g /app/data/virtual_printer)" = "1234:1234"
  '\''
'

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

python - "$IMAGE" <<'PY'
import json
import subprocess
import sys

config = subprocess.check_output(
    ["docker", "compose", "config", "--format", "json"], text=True
)
service = json.loads(config)["services"]["printops"]
assert service.get("cap_drop") == ["ALL"], service.get("cap_drop")
cap_add = service.get("cap_add", [])
expected = {"CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID", "NET_BIND_SERVICE"}
assert len(cap_add) == len(expected) and set(cap_add) == expected, cap_add

image = json.loads(
    subprocess.check_output(["docker", "image", "inspect", sys.argv[1]], text=True)
)[0]
healthcheck = image["Config"]["Healthcheck"]["Test"]
assert healthcheck[0] == "CMD-SHELL", healthcheck
assert healthcheck[1].startswith("exec gosu "), healthcheck
assert "os.getuid()" in healthcheck[1] and "os.getgid()" in healthcheck[1], healthcheck
PY

echo "Docker entrypoint boundary checks passed"
