# Slicer-API sidecar (optional)

Self-contained Docker Compose stack that runs HTTP wrappers around the
OrcaSlicer and/or Bambu Studio CLI. PrintOps's **Slice** action calls
these to slice models server-side, no desktop slicer required.

This folder is **optional**. PrintOps works without it — Slice falls back
to opening the model in the user's local desktop slicer via URI scheme.
Enable the API path by:

1. Starting one or both services here
2. **Settings → Slicer → Use Slicer API** = on
3. Set **Slicer sidecar URL** for whichever slicer you've started

## Quick start

```bash
cd slicer-api/
cp .env.example .env       # edit ports if you like

# OrcaSlicer only (default profile):
docker compose up -d
curl http://localhost:3003/health

# Both slicers:
docker compose --profile bambu up -d
curl http://localhost:3001/health   # bambu-studio-api
curl http://localhost:3003/health   # orca-slicer-api
```

The default stack pulls the existing third-party GHCR images. Their tags and
platform availability are controlled by the image maintainer, independently of
PrintOps releases. Keep the existing AMD64 route if you already use it.

## Native OrcaSlicer on ARM64 or AMD64 Linux

An explicit local-build override packages **official OrcaSlicer 2.4.2** for
`linux/arm64` or `linux/amd64`, with the existing profile-resolving HTTP wrapper.
**Existing installation:** migrate saved profiles/bundles using the
[data-switch instructions below](#data-persistence-and-switching-an-existing-installation)
before your first native start; this option uses a separate named volume.

```bash
cd slicer-api/
cp .env.example .env  # first setup only; preserve an existing .env
# Run on the target architecture; Docker selects its native platform.
docker compose -f docker-compose.yml -f compose.native.yml up -d --build
curl --fail http://localhost:3003/health
```

This builds a local `printops-orca-native:2.4.2` image; nothing is published or
pulled under that name. BuildKit/Docker Compose v2, a 64-bit Linux host, internet
access to GitHub, npm and the OS repositories, and space for build layers are
required. The Ubuntu 24.04 userspace is inside the container. Build/slice memory
and duration depend on the model; **2 GB operation has not been measured**.
A Raspberry Pi requires a 64-bit OS. Docker Desktop on Apple Silicon runs this
inside its Linux VM; this is not a macOS-native executable. ARMv7/32-bit is not
supported. The new option only changes Orca; it adds no Bambu Studio ARM64 build.

Do not set `DOCKER_DEFAULT_PLATFORM=linux/amd64` on an ARM64 host. Cross-building
with QEMU is not evidence of native slicing. The dedicated
[CI workflow](../.github/workflows/slicer-native.yml) uses `ubuntu-24.04-arm` and
`ubuntu-24.04` without QEMU: it checks host, image and ELF architecture, engine
version, bundled/inherited profiles, real multipart slices to G-code and 3MF,
renamed printer profiles, positive metadata headers and invalid-input errors.
Download its `native-orca-*` artifacts for output files and logs. Only a passed
run on the reviewed commit establishes that native runtime check.

### Data persistence and switching an existing installation

The native image runs the wrapper and engine as UID/GID **10001:10001**, with
writable home `/home/orca` (including engine logs) and data directory `/app/data`.
Program files remain root-owned and read-only to that user. The native Compose
override replaces the default `./data/orca` bind mount with the project-scoped
`orca-native-data` named volume. Docker initializes a fresh volume with the
image's ownership; you do not need to change host-directory permissions.

For a new installation, the quick-start command creates the empty volume.
For an existing prebuilt installation, `/app/data` contains saved printer,
process and filament profiles plus imported bundles. **Migrate before switching**
if you need those saved entries. The original `data/orca` directory stays intact;
it is not automatically imported, and a fresh native volume starts empty.
Keep the same Compose project name and directory for migration and later starts.
From `slicer-api/`, after backing up your existing data:

```bash
# Stop the existing writer before taking a consistent copy.
docker compose stop orca-slicer-api
docker compose -f docker-compose.yml -f compose.native.yml build
# This one-off copy runs as root; the service itself always defaults to 10001.
# The old host data is mounted read-only. Refuse to overwrite a non-empty target.
docker compose -f docker-compose.yml -f compose.native.yml run \
  --rm --no-deps --pull never -T --user 0:0 --entrypoint sh \
  -v "$PWD/data/orca:/migration:ro" orca-slicer-api -ec '
    test -z "$(find /app/data -mindepth 1 -print -quit)" || {
      echo "Native data volume is not empty; stop and reconcile it first." >&2
      exit 1
    }
    cp -a /migration/. /app/data/
    chown -R 10001:10001 /app/data
  '
docker compose -f docker-compose.yml -f compose.native.yml up -d
```

If the copy fails, keep the original directory and backup; the non-empty target
check prevents silently overwriting a partial copy on retry. Inspect/reconcile
that target before repeating the migration. Container recreation preserves the
named volume. Do not use `down --volumes` on your real installation unless you
intend to delete that native data.

Rollback to the prebuilt service uses `docker compose up -d orca-slicer-api`
without the native override. It reads the original host directory. Changes made
while using the native service remain in its named volume and are not copied
back automatically; export/back them up before a rollback that must retain them.
The Bambu service continues using its existing bind mount unchanged.

The optional sidecar is an unauthenticated HTTP service. Expose it only to the
PrintOps backend on a trusted network; avoid forwarding its port to the public
internet. When PrintOps itself runs in a container, `localhost` refers to that
container: configure a reachable sidecar host/address in Settings → Slicer.

## Ports

| Service | Default host port | Why this port |
|---|---|---|
| `orca-slicer-api` | **3003** | PrintOps's virtual-printer feature reserves 3000 and 3002 |
| `bambu-studio-api` | **3001** | First free port in that range |

Override via `ORCA_API_PORT` / `BAMBU_API_PORT` in `.env`.

## PrintOps wiring

In the PrintOps UI: **Settings → Slicer**:

- **Preferred Slicer**: pick OrcaSlicer or Bambu Studio.
- **Use Slicer API**: turn on.
- **Sidecar URL**: paste the full URL of the chosen slicer's sidecar.
  Default values match the Compose defaults:
  - OrcaSlicer: `http://localhost:3003`
  - Bambu Studio: `http://localhost:3001`

Leaving the URL field blank uses the `SLICER_API_URL` /
`BAMBU_STUDIO_API_URL` environment defaults from PrintOps's config.

## Sources and integrity

The unchanged default services reference `ghcr.io/maziggy/orca-slicer-api` and
`ghcr.io/maziggy/bambu-studio-api`. `SIDECAR_TAG` selects an existing tag there;
PrintOps does not publish those repositories or guarantee `printops-X.Y.Z` tags.

The local native image pins the
[`maziggy/orca-slicer-api`](https://github.com/maziggy/orca-slicer-api/tree/4c05506e40a0057db33234837db164143cbf3ad3)
wrapper from `bambuddy/profile-resolver` at
`4c05506e40a0057db33234837db164143cbf3ad3`. Its archive SHA256 is
`911047b9f86d5400c823dc842b700c334376601c9b2943a25860534a58efb05f`.
The fork preserves inherited profile flattening, user/clone normalization,
sentinel removal, companion templates, library profiles, renamed printer
compatibility and existing upload limits. Its locked npm dependencies are
installed with `npm ci --ignore-scripts`, compiled and pruned for production.
A reviewed manifest/lock overlay keeps the pinned application source, engine
and production dependency artifacts unchanged from the previous security overlay:

| File | SHA256 |
|---|---|
| `package.json` | `129702617cc09053039e8ed01e5dccafe73415d83b41eff5d7fb5d5b068ca031` |
| `package-lock.json` | `cd52e04cd0dde9ffa4b8174fdd9513d401b234d30537dd77a1000df020cd48be` |

The development overlay uses exact `fix-esm-import-path` 1.10.3 in place of
`tsc-esm-fix` and its unpatched glob/parser dependency chain. Vitest 4.1.12
fixes the manual mock registration and Windows redirect traversal advisories;
the explicit Vite 7 dependency retains the existing test toolchain. The build
compiles the upstream TypeScript and fixes its relative ESM imports.
Production dependencies retain the
previous fixes, including Multer 2.4.0, body-parser 2.3.0, brace-expansion 2.1.7,
lodash 4.18.1, path-to-regexp 8.4.2, proxy-addr 2.0.8 and qs 6.16.0.

When the dependency build layer executes, it runs a full `npm audit` before
compilation, the existing wrapper unit tests, and `npm audit --omit=dev` after
pruning. Any reported vulnerability or audit-service failure fails that build.
Docker may reuse a previously successful cached layer, including its old audit result. Use
`docker compose -f docker-compose.yml -f compose.native.yml build --no-cache --pull`
when you need a fresh advisory check; `--pull` alone does not invalidate that
layer. The npm audits do not cover OS packages or the independently maintained
prebuilt images used by the default services. For dependency updates, extract
the pinned wrapper and apply both tracked metadata overlays before running
`npm audit fix --package-lock-only --ignore-scripts`. Review the complete diff,
verify a clean install, build, unit tests and native HTTP smoke on both
architectures, then update both metadata files and their Dockerfile checksums.
For a wrapper-source update, also reconcile the overlay with its new manifest.
Do not refresh dependencies silently during a build.

The image includes the AGPL license and corresponding wrapper source under
`/app/wrapper-source`; the linked pinned repository contains the complete source.

Official assets from the
[OrcaSlicer 2.4.2 release](https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/v2.4.2):

| Platform | Ubuntu2404 AppImage | SHA256 |
|---|---|---|
| ARM64 | `OrcaSlicer_Linux_AppImage_Ubuntu2404_aarch64_V2.4.2.AppImage` | `e1a07275a25f176626c55a5df39e91bc4476d8c28ee4a3192ff758e29dd5c3ba` |
| AMD64 | `OrcaSlicer_Linux_AppImage_Ubuntu2404_V2.4.2.AppImage` | `d12fb8c8eac1aecd2dfb6377acd48f994f8fa439ed5292fa532dd82880f029fd` |

`native_build.py` verifies each archive before extraction and verifies both the
AppImage runtime and extracted engine's 64-bit little-endian ELF machine.
Unsupported or mismatching architectures fail the build. Native extraction
needs no FUSE device. Docker base indexes are digest-pinned; OS packages still
come from their signed live repositories, so rebuilds are not byte-identical.

## Updating and fallback

For the existing prebuilt route:

```bash
docker compose pull
docker compose --profile bambu up -d
```

For the native route, update the reviewed source/asset pins in `native_build.py`
and the base digests in `Dockerfile`, verify primary release metadata, and run
both native CI architectures before adopting a new engine. Rebuild explicitly:

```bash
docker compose -f docker-compose.yml -f compose.native.yml build --pull
docker compose -f docker-compose.yml -f compose.native.yml up -d
```

`SIDECAR_TAG` does not alter the native engine or wrapper. To return to the
existing prebuilt Orca service on a compatible AMD64 host, run the default
Compose commands without the override. On an unsupported host, run the sidecar
on a separate supported Linux machine and configure its reachable URL. Disabling
**Use Slicer API** restores PrintOps's local desktop-slicer URI flow.

Local integrity tests and the disposable-container HTTP smoke:

```bash
python3 -m unittest discover -s slicer-api/tests -v  # from repository root
# With printops-orca-native:2.4.2 built, verify non-root, migration, persistence,
# and all ten real HTTP tests in a unique disposable Compose project:
SIDECAR_SMOKE_PORT=13038 bash slicer-api/tests/nonroot_native.sh
# Or test HTTP only against an already running disposable sidecar:
SIDECAR_URL=http://127.0.0.1:3003 python3 slicer-api/tests/smoke_native.py
```

The smoke test only accepts a loopback URL and does not contact a printer.

## Troubleshooting

- **`address already in use` on port 3000 or 3002** — PrintOps's
  virtual-printer feature owns those. Don't change `ORCA_API_PORT` to
  3000 or 3002.
- **`/health` reports `version: "unknown"`** — the wrapper could not parse
  the version. Check `checks.orcaslicer.available` and run `AppRun --help`;
  the native Orca build must report 2.4.2. BambuStudio may use a different
  help-output format.
- **Slice returns "Failed to slice the model"** — inspect the response
  `details` and container logs. For a retained input/profile triplet, re-run
  inside the container:

  ```bash
  docker exec orca-slicer-api /app/squashfs-root/AppRun --slice 1 \
      --load-settings "/path/to/printer.json;/path/to/preset.json" \
      --load-filaments /path/to/filament.json \
      --allow-newer-file --outputdir /tmp/out /path/to/model.3mf
  ```
