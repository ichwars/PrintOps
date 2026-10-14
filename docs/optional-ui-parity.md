# Selective camera, filter and UI parity

This records the decision for issue #97 and its accepted follow-up issues.
PrintOps navigation, permissions and commercial domains remain authoritative.
The decision is about functional benefit, accessibility and maintenance; it is
not an acceptance of an upstream theme or branding.

| Candidate | User benefit and decision | Accessibility | Maintenance and dependencies |
| --- | --- | --- | --- |
| Camera temperature overlay | Accepted and delivered in #101: operators can see relevant temperatures alongside the camera image. | The existing text overlay and labeled toggle expose values independently of image detail. Contrast against arbitrary live footage remains a device-specific observation, not a claimed hardware test. | Uses existing telemetry and camera pipeline (#82); no independent temperature source or command path. |
| External-camera URL builder | Accepted and delivered in #102: operators can construct a camera address from host, port, path and credentials. | Existing labeled fields and password concealment remain in use; the builder has targeted UI tests. | The resulting address goes through the existing backend validation. The SSRF protection in #84 is mandatory; redirects and arbitrary target access are not enabled by this UI. |
| Persistent inventory filters | Accepted as separate follow-up #196: returning to inventory restores an operator's filter selection and search. | Reuses the existing labeled search, tab buttons, comboboxes and clear control. Restored values are visible in those controls; reset and keyboard interactions are tested. | A small versioned frontend record is scoped to the current authenticated user, browser origin and local/Spoolman data source. No new dependencies, backend permissions or inventory mutations. |
| Printer-card scaling and similar cosmetic changes | No additional scaling feature selected. An upstream visual resemblance alone does not establish a user benefit. Keep the existing responsive layout; fix a concrete reproduced clipping, zoom or touch problem separately if one occurs. | The camera-entry addition is checked at desktop and mobile widths, including keyboard access and control bounds. | Avoids a parallel card system and unnecessary theme/navigation maintenance. |

Accepted candidates have their own small follow-up issues: #101, #102 and #196.
Issue #156 extends this work with actual-color sorting, multicolor/transparent
swatches, readable notifications, per-printer camera defaults and a complete
Dutch locale. It does not reimplement the overlay or URL builder.

## Inventory filter contract

Ordinary visits remember archive, usage, material, brand, category, spool-catalog,
stock and search filters. Preferences belong to the authenticated user; when
authentication is disabled they belong to an explicit local appliance scope.
Loading authentication or a signed-out authenticated session cannot read an
authenticated user's preference. Identity and data-source changes reset the
visible state immediately before loading the new scope.

Storage is local to the browser origin and uses a `v1` schema. Old unscoped
preferences are not migrated into a user account. Broken JSON, unknown versions,
invalid enum values and unavailable storage use safe defaults while the current
view remains usable. These records contain UI choices, never credentials or
access grants. Logout stops displaying the user's values; signing back in as the
same user can restore their own choices on that browser.

Dashboard-focus, location and spool-edit links take precedence over remembered
ordinary filters. Their view is transient for the visit, including after a
handled link parameter disappears, and never overwrites the ordinary preference.
The legacy `/inventory` entry preserves query and hash while redirecting to
`/warehouse/filament`, including existing spool links from printer controls.
A location chosen inside the current view keeps its visible filters and follows
the same transient behavior. Returning through an ordinary inventory entry
restores the saved ordinary view. Clearing ordinary filters removes the saved
record; clearing a linked view resets only that view. Current page, selected
spools and dashboard/location link parameters are not stored.

## Verification scope

The filter tests cover actual return/reset behavior in the inventory page,
identity transitions, local/Spoolman separation, batched updates, URL priority,
corrupt and obsolete storage, and denied storage. Existing spool-edit and
Spoolman-location tests cover interaction with the existing routes. Camera and
locale checks cover the extensions from #156. Rendered checks use a controlled
API fixture; they do not claim a live video stream or device acceptance.
The rendered checks cover persistence, linked-view priority, clear/reset and the
camera snapshot/default controls at 1440 and 390 pixels. The snapshot fixture is
explicitly synthetic. Financial values, payloads and CSV field values are covered
by the existing commerce suites and focused Dutch rendering tests.

## Camera launch placement (O13c, #220)

The printer-card camera button opens the last placement selected in its adjacent
menu: a separate window or the embedded viewer. With no local choice, it follows
Settings → camera view mode. Choosing a menu item opens that placement immediately;
the separate Stream/Snapshot control remains independent. This local menu never
updates global settings and is available to users with camera viewing permission.
Both launch controls wait for verified authentication and preferences and require
a connected printer. If auth-status discovery fails, they remain disabled until
it succeeds; public camera-token routes remain independently usable.
Keyboard users can open the menu, navigate with arrows/Home/End, select with
Enter/Space, and dismiss with Escape, Tab or an outside click.

Both camera preferences use the browser origin, the verified session-bound account
subject and the printer hardware serial. Explicitly verified authentication-off
installations use the appliance scope. Missing identity proof or hardware serial
allows only transient choices. With verified authentication but a missing serial,
an Embedded launch falls back synchronously to the existing separate window,
including its current Stream/Snapshot choice. Anonymous camera links never read
or write account defaults. Old numeric account/printer keys are deliberately not migrated because
those IDs can be reused after deletion. Existing stream/snapshot choices therefore
return once to the default Stream until selected again. Blocked browser storage
keeps choices usable within the current tab and identity.

Separate windows retain the existing opener/sessionStorage authentication and
narrow camera-token flow. Hosts without an embedded-view callback fall back to the
existing separate window. Tests use software fixtures and do not contact a camera,
physical printer or notification provider. The existing card scale and external
spool visibility controls remain independent of camera placement.

Open embedded viewers also restore across navigation/reload using a separate,
verified account-scoped list of hardware serials. Only currently accessible
printers with camera viewing permission are rendered. The old unscoped
`openEmbeddedCameras` ID list is not migrated; previously open viewers need to be
opened once again. The camera-wall entry continues to follow its existing global
placement setting and uses the same verified overlay restoration list.

The global placement setting now supplies the initial launch fallback only.
Changing it to Window does not dismiss locally opened overlays; use their existing
close button to dismiss them. This avoids immediately closing an Overlay chosen
from the new menu while the global fallback is Window.

Embedded viewers and ordinary camera pages wait for the first printer-information
request to finish before enabling Stream/Snapshot changes. Existing image loading
continues during that request. If the response has no serial, or the request fails,
mode changes remain usable for the current view without saving a printer default.
Public camera-token links remain switchable while metadata loads; later metadata
or authentication discovery does not discard their current choice. Opening a
different public link starts its own requested/default view, even on the same
printer route, without saving the link token or its choices.
