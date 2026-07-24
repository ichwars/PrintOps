# Updating PrintOps

> **0.2.3 note:** the in-app **Update** button is unreliable when upgrading from
> older releases. Use the commands below instead — they cover every supported
> install path and are safe to run repeatedly.

Pick the section that matches how PrintOps was installed.

---

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

## Docker

```bash
# 1. Make sure your compose file isn't pinned to an old version.
#    The image line should read one of:
#      image: ghcr.io/ichwars/printops:latest
#      image: ghcr.io/ichwars/printops:0.2.3
#    If it pins an older tag (e.g. :0.2.2.2), edit it first.

# 2. Pull and restart
docker compose pull
docker compose up -d
```

**If your `docker-compose.yml` is older than 0.2.3,** also refresh it from the
repo — recent releases added `cap_add: NET_BIND_SERVICE`, extra virtual-printer
ports for bridge mode, and an optional Postgres block:

```bash
curl -fsSL https://raw.githubusercontent.com/ichwars/PrintOps/main/docker-compose.yml \
  -o docker-compose.yml.new
# Diff against yours, merge by hand, then:
docker compose up -d
```

---

## Native install (`install.sh` or manual `git clone`)

Both paths produce a git working tree at the install directory, so the update
is the same. Preferred:

```bash
sudo /opt/printops/install/update.sh
```

`update.sh` stops the service, snapshots the database via the built-in backup
API, fast-forwards to `origin/main`, installs Python deps, rebuilds the
frontend, and restarts the service. It rolls back automatically if any step
fails.

### Manual equivalent

If you'd rather run the steps yourself:

```bash
cd /opt/printops
sudo systemctl stop printops
sudo -u printops git fetch origin
sudo -u printops git reset --hard origin/main
sudo -u printops venv/bin/pip install -r requirements.txt
sudo systemctl start printops
```

Replace `/opt/printops` with your install path if different. Database schema
migrations run automatically on startup — no Alembic step is required.

---

## Installed from a GitHub ZIP or tarball download

These installs have no `.git` directory, so neither `update.sh` nor a plain
`git pull` will work. Reinstall cleanly:

```bash
# 1. Back up your stateful data
sudo systemctl stop printops
sudo tar czf ~/printops-backup.tgz -C /opt/printops \
  data printops.db printops.db-shm printops.db-wal \
  virtual_printer archive projects icons .env 2>/dev/null || true

# 2. Remove the old install and reinstall via install.sh
sudo rm -rf /opt/printops
curl -fsSL https://raw.githubusercontent.com/ichwars/PrintOps/main/install/install.sh \
  -o /tmp/install.sh && sudo bash /tmp/install.sh --path /opt/printops

# 3. Restore your data
sudo systemctl stop printops
sudo tar xzf ~/printops-backup.tgz -C /opt/printops
sudo systemctl start printops
```

---

## Before you upgrade

Take a backup. Settings → Backup → **Create Backup** downloads a ZIP containing
the database and all stateful directories. Any bare-metal update via
`update.sh` does this automatically; Docker and manual upgrades do not.
