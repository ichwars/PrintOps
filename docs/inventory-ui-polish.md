# Inventory color sorting and toast readability

This implements the color-sorting and notification-readability parts of issue
#156. The issue permits selected improvements; this change does not complete
every item in that issue.

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

## Remaining issue scope

Persistent filters and card scaling belong to assigned issue #97. The camera
overlay and URL builder are already covered by closed issues #101 and #102.
The existing camera page offers stream/snapshot switching; adding a separate
per-printer preference at the printer entry requires a further API and settings
change and is deferred here. The repository has eleven complete locale packs
and no Dutch pack. The new control is translated in all eleven; a full Dutch
translation is deferred rather than introduced as an incomplete locale.
