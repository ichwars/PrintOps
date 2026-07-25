#!/usr/bin/env bash
set -euo pipefail

export MSYS_NO_PATHCONV=1

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
cap_add = [value.removeprefix("CAP_") for value in (host_config["CapAdd"] or [])]
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
fields = {
    line.split(":", 1)[0]: line.split(":", 1)[1].split()
    for line in status.splitlines()
    if ":" in line
}
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
