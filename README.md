# PrintOps

<p align="center">
  <img src="static/img/printops_logo.svg" alt="PrintOps Logo" width="360">
</p>

PrintOps is a fork of [Bambuddy](https://github.com/maziggy/bambuddy) that is being evolved into a local, self-hosted operations platform for 3D printing businesses. The technical foundation intentionally stays close to the upstream project, while the product direction adds warehouse, order, costing, quotation, and invoicing workflows step by step.

## Current Status

- Fork remote: `https://github.com/ichwars/PrintOps`
- Upstream: `https://github.com/maziggy/bambuddy`
- Foundation: local printer control, inventory, queue, archive, files, and Bambu Lab focused workflows from Bambuddy
- PrintOps extension: first navigation and foundation pages for `Warehouse` and `Orders`
- Brand assets: transparent SVG files for the icon and wordmark

## Product Goal

PrintOps is intended to bring the operational work around 3D printing orders into one place:

- Manage printers, the print queue, and the archive
- Track filament and material inventory
- Prepare customers, orders, quotations, and invoices
- Connect costing and reservations with the print workflow
- Keep existing Bambuddy functionality usable without a hard migration

## Development

```bash
cd frontend
npm install
npm run build
```

The frontend build writes to `static/`, where the backend serves the compiled assets.

## License and Origin

PrintOps is based on Bambuddy and follows its licensing model. The code is licensed under `AGPL-3.0`; see [LICENSE](LICENSE) for details.

When publishing, hosting, or providing network access to a modified version, the corresponding source code must be made available according to the AGPL.
