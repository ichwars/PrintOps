# Inventory color sorting and toast readability

This describes the selected inventory, notification, camera-entry and language
improvements from issue #156. Candidate evaluation and persistent inventory
filters are documented in `optional-ui-parity.md` for #97 and #196.

## Actual-color sorting

Click **Color** in the inventory table header, or the color-sort button next to
the view controls. The button also works in cards view and has an accessible
name when its text is hidden on small screens. Table headers support keyboard
activation and expose the active direction with `aria-sort`.

Ascending order is:

1. Neutral colors, from dark to light.
2. Brown colors, from dark to light.
3. Chromatic colors, following the hue spectrum from red through blue to magenta.
4. Transparent and translucent colors.
5. Multicolor spools.
6. Missing or malformed colors.

The comparison reads the displayed RGB/alpha values, independently of the color
name or material. As in the shared swatch renderer, valid extra color stops take
precedence over the base RGBA. Equivalent six/eight-digit hex values and repeated
stops normalize to the same color. Fully transparent stops form the transparency
group; two or more distinct stops with at least one nonzero alpha form the
multicolor group. Partial alpha on a single color forms the transparency group.

Neutral colors have HSL saturation below 15%, lightness below 15%, or lightness
above 85%. Brown colors have hue from 15° to below 70° and lightness below 45%
(below 40% for hues from 45°). These fixed thresholds make classification
repeatable. Color values and finally the spool ID break ties, so the backend
response order cannot change the result. Descending reverses this order.

The existing sort preference stores the chosen column and direction. Filtering,
grouping, pagination, and the existing gradient/checkerboard rendering continue
to use their current behavior.

## Readable notifications

Ordinary error and warning toasts remain for at least ten seconds. Longer
messages receive 60 milliseconds per character, capped at thirty seconds.
Hovering or focusing a toast pauses its timer; after both leave, the full reading
interval starts again. An explicitly labeled dismiss control is always
available. Error/warning messages use an alert role, and other messages use a
status role. Long words and preserved line breaks fit the toast viewport.

Success/info/loading notifications keep their three-second duration. Persistent
notifications and background dispatch progress keep their existing lifecycle.

## Camera-entry preference

Each printer's camera entry offers Default (Stream), Stream and Snapshot. The
choice is scoped to the current user, browser origin and printer. In an
auth-disabled installation it uses a separate local appliance scope; it never
inherits an authenticated user's choice. Default removes the explicit preference.
The global window/embedded setting continues to choose the presentation surface;
the printer preference determines its initial stream/snapshot mode.

Camera-window launches carry a nonsecret view hint so the selected mode still
works if browser storage cannot be written. The camera page and embedded viewer
honor the initial mode and allow switching during viewing. Invalid/obsolete
records use Stream; unavailable storage does not prevent opening the camera.
No camera credentials, authentication tokens or source URLs are stored in these
preferences. The existing camera authorization and URL security remain in use.

## Dutch locale

Nederlands is offered in the language picker and loaded through the existing
lazy locale loader. Its key, plural and interpolation-placeholder sets match
English, including PrintOps orders, customers, commercial documents, warehouse,
business settings and the new camera controls. The strict untranslated-English
check applies to Dutch; only genuine cognates, brands and technical tokens have
narrow exceptions. Translations adapted from Bambuddy are source-aligned;
PrintOps-only or changed strings are explicitly translated.

Runtime bindings also cover calculations, invoices, business-dashboard data and
CSV headings, material management, device/numbering settings and existing classic
dialogs. Literal translation calls are checked against the catalog, and table
column arrays retain their actual array shape. Inventory headers and composed
archive/tag/printer counts use translated labels and plural forms. The inventory
header actions wrap on narrow screens rather than clipping translated text.

The backend's existing notification events support `en`, `de` and `nl` with the
same event keys and formatting placeholders. The UI language does not add Dutch
legal-document templates: generated commercial documents retain their existing
German/English output support. For the other nine existing UI locales, newly
extracted runtime labels use explicitly listed English entries until translations
are supplied. This finite allowance never applies to Dutch or German; these
English entries are not claimed as new translations for the other locales.

The parity gate verifies structure and placeholders rather than asserting a
native-speaker review of every term. Existing PrintOps branding and navigation
are retained.
