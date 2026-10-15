# Repository files and generated output

The repository contains application source, dependency locks, tests and their
fixtures, installation and release tooling, licenses, and maintained project
documentation. Reviewed upstream comparison tables remain historical references
linked from the documentation index.

Keep credentials, local environment overrides, databases and their journal files,
user uploads, backups, logs, support bundles, caches, editor recovery files,
worktrees and temporary agent/session documents outside Git. `.gitignore` covers
these categories. `.env.example` and other explicitly named environment example
templates may be committed after verifying that they contain no credentials.
Ignoring a path does not remove a file that is already tracked.

## Frontend delivery bundle

`frontend/` is the editable source. `npm ci && npm run build` in that directory
recreates `static/`; Vite empties its output directory before writing the current
bundle. Changes to source assets belong in `frontend/public/`.

The checked-in `static/` bundle is intentional: the native in-app updater in
`backend/app/api/routes/updates.py` supports installations without `npm` and uses
the supplied bundle in that case. Keep this existing installation path working.
Before preparing a release, rebuild from the current source and commit the
complete resulting delivery bundle, including deleted obsolete chunks. Docker
and Windows installer builds independently rebuild the frontend from source.

`gcode_viewer/` is a separate runtime component and is not emitted by Vite. Its
vendored code, source/license notices and other runtime resources must remain
available. Public verification keys, licensed schemas, fonts and test PDFs are
also required inputs; their file type alone is not a reason to remove them.

## Verification before a release

Run the required application tests and production build. Verify that the bundle
loads, all referenced local assets exist, and third-party notices are included.
Check the staged diff and ignored-but-tracked paths before pushing. Review each
new binary file against its source and use; never include live application data
to make a test or build pass. Release publication is separate from preparing
version metadata and release notes.
