# Updating PrintOps

Use the procedure for the installed package type. Release-specific changes are
listed in [CHANGELOG.md](CHANGELOG.md); the next release preparation is described
in [the 1.2.8.0 notes](docs/releases/1.2.8.0.md). A prepared version is available
for installation only after its release artifacts have actually been published.

## Before upgrading

Create a full backup in **Settings → Backup → Create Backup** and keep it outside
the installation directory. Include the database, uploaded files, issued document
assets/evidence, configuration and secrets in the recovery plan. A Docker volume
or an existing directory is not a separate backup. Review your custom compose,
environment and service configuration before applying upstream examples.

## Docker

Keep the image on a published version tag or the stable `latest` channel:

```yaml
image: ghcr.io/ichwars/printops:latest
```

For a fixed version, choose its exact tag from the published GitHub release;
do not copy an old version pin from an upgrade example. Preserve your configured
volumes, ports and environment, then run:

```bash
docker compose pull
docker compose up -d
```

When the release changes compose options, download the example separately and
merge the relevant settings into your own file:

```bash
curl -fsSL https://raw.githubusercontent.com/ichwars/PrintOps/main/docker-compose.yml \
  -o docker-compose.yml.new
# Compare docker-compose.yml.new with the configured file before changing it.
```

These commands do not remove data volumes. After startup, inspect the application
logs and check `/health` and `/api/v1/document-render/readiness`.

## Native Git installation

The supported updater scripts fetch code, update the hash-locked Python
dependencies, rebuild the frontend when npm is available, refresh the verified
PDF validator and restart the service. They attempt code/runtime rollback after
a failed later step; they do not replace a verified backup. `BACKUP_MODE=require`
stops an update if the running application's backup API cannot supply a backup.
An authenticated installation may need its authorized backup API key configured.

Linux:

```bash
sudo env BACKUP_MODE=require /opt/printops/install/update.sh
```

macOS, using the actual installation path and the same user as its LaunchAgent:

```bash
env BACKUP_MODE=require /path/to/printops/install/update_macos.sh
```

Review any prompt about local changes and preserve those changes before proceeding.
Do not use a force flag to discard customizations without inspecting them.

### Manual Linux equivalent

Take the backup first. Confirm a clean checkout and a fast-forward update before
stopping the service; if the following checks fail, preserve local changes or
resolve the divergence before updating:

```bash
cd /opt/printops
sudo -u printops git fetch origin &&
sudo -u printops sh -c 'test -z "$(git status --porcelain)"' &&
sudo -u printops git merge-base --is-ancestor HEAD origin/main
```

With those checks successful, update under the installation's service user:

```bash
sudo systemctl stop printops
sudo -u printops bash -eu <<'UPDATE' && sudo systemctl start printops
cd /opt/printops
git merge --ff-only origin/main
venv/bin/pip install --require-hashes -r requirements.lock.txt
if command -v npm >/dev/null 2>&1; then
    (cd frontend && npm ci && npm run build)
else
    # Existing native fallback: use the complete frontend supplied in Git.
    test -f static/index.html
fi
venv/bin/python scripts/vendor_pdf_runtime.py \
    --destination runtime/verapdf --cache-dir .cache/pdf-runtime
UPDATE
```

Replace the path, service name and service user with the configured values. A
failed update command leaves the service stopped for recovery; inspect the error
and restore the previous complete installation/backup before restarting. macOS
uses its LaunchAgent lifecycle instead of `systemctl`; prefer its updater script.

The vendor step needs the existing documented Java/GnuPG/PDF prerequisites; see
[PDF runtime updates](docs/pdf-runtime-updates.md). Database migrations run on
startup. Verify the displayed version, health and document-render readiness after
restarting, then check the workflows used by the installation.

## Windows installer

Use the matching installer from a published GitHub release and follow the
[Windows installation guide](installers/windows/README.md). Back up persistent
data first. Compare its checksum with the release's `SHA256SUMS.txt`; installers
remain explicitly unsigned, as explained in
[release integrity](docs/release-security.md). The installer stages its own
frontend and PDF runtime.

## GitHub ZIP or tarball source snapshots

Source snapshots do not contain `.git`, so Git-based updater scripts cannot
update them. Preserve the existing installation and its verified backup. Use the
[supported installation guide](install/README.md) to prepare a separate install
path/service or an isolated replacement host, then restore and verify the backup
before switching the live service. An isolated restore test must not have access
to live printers. Do not delete the original directory or overwrite its data with
source files as an update step.

## Document-format migration

The document-format release adds versioned layout, asset, preview-job,
publication, audit and artifact tables. Database migrations run automatically
at startup. Every existing business profile receives exactly one unpublished
Classic/A4 draft; the migration is idempotent and never publishes a layout on
the user's behalf.

Before upgrading, create a full backup. The current backup format includes
layout rows, content-addressed logo/letterhead/font assets, issued PDF/XML
evidence and validator reports. Restore verifies every stored SHA-256 and
rejects damaged evidence instead of accepting a partial document history.

Native and Windows-package upgrades must also refresh the pinned WeasyPrint,
Pango, ICC and veraPDF runtime bundle. Container upgrades obtain these
components from the image. There are no runtime downloads. After restart,
check GET /api/v1/document-render/readiness; previews remain available and
clearly marked when validation is unavailable, but publication and final
document export stay blocked until the complete runtime is ready.
