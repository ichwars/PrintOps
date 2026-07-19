# PrintOps Brand Asset Migration Design

**Date:** 2026-07-19
**Status:** Approved design, pending written-spec review

## Objective

Replace the remaining legacy Bambuddy logo and favicon assets with the approved PrintOps artwork across the application, PWA metadata, service worker, and GitHub README presentation. Preserve unrelated work already present in the working tree.

## Source Assets

- Main logo: `C:\Users\droth\Pictures\Logos\printops_logo.svg`
- Icon master: `E:\IconOnly_Transparent_NoBuffer.png`
- Prepared deterministic icon exports: `outputs/icon-set/`

The source files outside the repository remain unchanged.

## Asset Mapping

The main SVG is copied to both `frontend/public/img/printops_logo.svg` and `static/img/printops_logo.svg`. Only its canvas metadata is normalized: remove fixed root dimensions and use the tight approved view box `90 305 1060 413`. Paths, gradients, colors, and logo content remain unchanged.

The icon exports are copied to both public asset trees with these names and dimensions:

| File | Dimensions | Purpose |
| --- | ---: | --- |
| `printops_icon.png` | 192×192 | Collapsed application sidebar |
| `android-chrome-192x192.png` | 192×192 | PWA/application icon |
| `android-chrome-512x512.png` | 512×512 | PWA/application icon |
| `favicon-16x16.png` | 16×16 | Browser favicon |
| `favicon-32x32.png` | 32×32 | Browser favicon |
| `favicon.png` | 512×512 | Large fallback favicon |
| `apple-touch-icon.png` | 180×180 | Apple touch icon |

The old `printops_icon.svg` is removed after all references have migrated to the PNG assets.

## Application Rendering

- Login, setup, stream overlay, expanded sidebar, compact mobile header, and opened mobile drawer continue to use `/img/printops_logo.svg`.
- The normalized SVG canvas makes existing height-based sizing render the full logo without excessive blank space.
- The collapsed desktop sidebar uses only `/img/printops_icon.png` at `40×40` CSS pixels with `object-contain`.
- No component receives embedded image data or duplicated logo markup.

## Browser, PWA, and Service Worker Metadata

- `frontend/index.html` and the built static HTML use explicit 16×16 and 32×32 favicon PNG links, the 512×512 fallback, and the 180×180 Apple touch icon.
- `manifest.json` contains one 192×192 and one 512×512 PNG icon entry. Duplicate SVG entries are removed.
- The transparent no-buffer icon is not declared `maskable`, because platform masking could crop the artwork.
- Manifest shortcut icons use the 192×192 PNG.
- Service-worker precaching includes the new logo and icon files.
- Web notification icon and badge references use the new PNG assets.

## GitHub Presentation

`README.md` continues to reference `static/img/printops_logo.svg`. Replacing that tracked file updates the logo displayed on GitHub without changing external repository or organization settings.

## Safety and Verification

- Existing unrelated changes in source and generated static bundles are preserved.
- Source/public assets and checked-in static assets are updated explicitly; no uncontrolled production build writes into the dirty `static` directory.
- A verification build writes to a separate temporary output directory.
- Automated checks validate SVG canvas metadata, PNG dimensions and alpha, HTML links, manifest entries, service-worker references, and expanded/collapsed logo selection.
- Visual verification covers login, expanded sidebar, and collapsed sidebar states.

## Out of Scope

- GitHub repository social-preview or organization avatar settings
- Redesigning paths, gradients, colors, or typography
- Rebranding SpoolBuddy-specific assets
- Updating existing application screenshots
