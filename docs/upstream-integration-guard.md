# Upstream Integration Guard

PrintOps tracks Bambuddy for printer, queue, AMS, slicer, camera, cloud, and
security fixes. Bambuddy does not contain PrintOps-specific commerce domains, so
a direct upstream merge can legitimately present those files as deletions.

Before accepting an upstream integration, run:

```bash
python tools/check_printops_domain_guard.py --base main --head upstream/main
```

For a local integration branch, use:

```bash
python tools/check_printops_domain_guard.py --base origin/main --head HEAD
```

The guard fails when protected PrintOps paths are deleted. Protected areas
include:

- orders, offers, calculations, customers, and business profiles
- warehouse material, procurement, suppliers, stock reservations, and numbering
- commercial documents, document layouts, e-invoice, PDF runtime resources, and
  tax decisions
- related frontend pages, settings panels, APIs, and permanent docs

Intentional removals must be reviewed explicitly and documented in the change.
For that narrow case, run with `--allow-protected-deletions` only after the
review note explains why the deletion is correct.
