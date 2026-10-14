#!/usr/bin/env bash
# Exercise the actual native Compose data mount under the image's default user.
# Only this script's uniquely named containers/volumes are removed on exit.
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
evidence=${SMOKE_EVIDENCE_DIR:-/tmp/printops-native-smoke-evidence}
mkdir -p "$evidence"
evidence=$(cd "$evidence" && pwd)
port=${SIDECAR_SMOKE_PORT:-3003}
image=printops-orca-native:2.4.2
project="printops-native-smoke-$$"
scratch=$(mktemp -d)
compose=(docker compose -p "$project" -f "$repo/slicer-api/docker-compose.yml"
    -f "$repo/slicer-api/compose.native.yml" -f "$scratch/test.yml")
cleanup() {
    docker logs "$project" > "$evidence/container.log" 2>&1 || true
    "${compose[@]}" down --volumes --remove-orphans || true
    rm -rf "$scratch"
}
trap cleanup EXIT
printf 'services:\n  orca-slicer-api:\n    container_name: %s\n' "$project" > "$scratch/test.yml"
export ORCA_API_PORT="$port"
export SIDECAR_URL="http://127.0.0.1:$port"
export SMOKE_EVIDENCE_DIR="$evidence"

docker image inspect "$image" > "$evidence/nonroot-image.json"
# The image default is checked before exec so a root default cannot be hidden
# behind a test-only --user flag or Compose user override.
runtime_user=$(docker image inspect -f '{{.Config.User}}' "$image")
printf 'Image default user: "%s"; required "10001:10001"\n' "$runtime_user"
test "$runtime_user" = '10001:10001'
"${compose[@]}" config --format json > "$evidence/native-compose.json"
# Match the documented migration: old data is read-only, target must be empty.
mkdir -p "$scratch/legacy/filaments"
printf '{"type":"filament","name":"migration-proof"}\n' > "$scratch/legacy/filaments/migration.json"
"${compose[@]}" run --rm --no-deps --pull never -T --user 0:0 --entrypoint sh \
    -v "$scratch/legacy:/migration:ro" orca-slicer-api -ec '
        test -z "$(find /app/data -mindepth 1 -print -quit)"
        cp -a /migration/. /app/data/
        chown -R 10001:10001 /app/data
    '
# Refuse a second migration, preserving existing target data.
if "${compose[@]}" run --rm --no-deps --pull never -T --user 0:0 --entrypoint sh \
    orca-slicer-api -ec 'test -z "$(find /app/data -mindepth 1 -print -quit)"'; then
    echo "Migration unexpectedly allowed a non-empty target" >&2
    exit 1
fi
"${compose[@]}" up -d --no-build --pull never

test "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Type}}{{end}}{{end}}' "$project")" = volume
docker exec "$project" sh -ec '
    id
    test "$(id -u)" = 10001
    test "$(id -g)" = 10001
    test ! -w /app/dist/index.js
    printf "persisted by unprivileged runtime\n" > /app/data/.printops-smoke
' | tee "$evidence/runtime-identity.txt"

# Recreate the container, not the named volume, to prove actual persistence.
"${compose[@]}" up -d --force-recreate --no-build --pull never
docker exec "$project" sh -ec '
    test "$(id -u)" = 10001
    test "$(cat /app/data/.printops-smoke)" = "persisted by unprivileged runtime"
    test "$(stat -c %u:%g /app/data/filaments/migration.json)" = 10001:10001
    grep -q migration-proof /app/data/filaments/migration.json
    rm /app/data/.printops-smoke
'
cmp "$scratch/legacy/filaments/migration.json" <(printf '{"type":"filament","name":"migration-proof"}\n')
for attempt in $(seq 1 30); do
    if curl -fsS "$SIDECAR_URL/health" > "$evidence/health.json"; then break; fi
    sleep 2
done
curl -fsS "$SIDECAR_URL/profiles/filaments/migration" > "$evidence/migrated-profile.json"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1])) == {"type":"filament","name":"migration-proof"}' "$evidence/migrated-profile.json"
python3 "$repo/slicer-api/tests/smoke_native.py" 2>&1 | tee "$evidence/http-smoke.log"
