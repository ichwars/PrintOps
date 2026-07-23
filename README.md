# PrintOps

<p align="center">
  <img src="static/img/printops_logo.svg" alt="PrintOps Logo" width="360">
</p>

PrintOps is being evolved into a local, self-hosted operations platform for 3D printing businesses. The technical foundation intentionally preserves the proven printer-control workflows from the original project, while the product direction adds warehouse, order, costing, quotation, and invoicing workflows step by step.

## Current Status

- Repository: `https://github.com/ichwars/PrintOps`
- Foundation: local printer control, inventory, queue, archive, files, and Bambu Lab focused workflows
- PrintOps extension: first navigation and foundation pages for `Warehouse` and `Orders`
- Brand assets: transparent SVG files for the icon and wordmark

## Product Goal

PrintOps is intended to bring the operational work around 3D printing orders into one place:

- Manage printers, the print queue, and the archive
- Track filament and material inventory
- Prepare customers, orders, quotations, and invoices
- Connect costing and reservations with the print workflow
- Keep existing printer-control functionality usable without a hard migration

## Document Layouts and PDF Evidence

Settings -> Order Management -> Format & Preview provides a versioned,
structured editor for all commercial-document layouts. It renders genuine
multi-page A4 or Letter PDFs on the left and keeps the compact layout controls
on the right. Draft changes autosave; only blocker-free, validated versions can
be published.

The same offline renderer is used for previews, final PDFs and external
snapshot exports. Final commercial PDFs are PDF/A-3u. ZUGFeRD keeps the PDF as
the original with validated XML attached; XRechnung keeps the XML as the
original and labels its PDF as a separate visual copy. Layout assets, issued
artifacts, XML evidence and validation reports are included in local and
private-Git backups with SHA-256 receipts.

WeasyPrint and veraPDF are pinned build/runtime components. Production and
installer builds must stage them before startup; PrintOps never downloads a
renderer or validator while processing a document. The readiness endpoint
/api/v1/document-render/readiness reports the installed versions and blocks
final release when a required component is unavailable.

## Development

```bash
cd frontend
npm install
npm run build
```

The frontend build writes to `static/`, where the backend serves the compiled assets.

## License and Origin

PrintOps follows the original project's licensing model. The code is licensed under `AGPL-3.0`; see [LICENSE](LICENSE) for details.

When publishing, hosting, or providing network access to a modified version, the corresponding source code must be made available according to the AGPL.
