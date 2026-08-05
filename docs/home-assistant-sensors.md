# Home Assistant sensors and print interlocks

PrintOps can bind `binary_sensor.*` and numeric `sensor.*` entities to a
printer. Their cached, read-only state is shown on the printer card and never
controls the print queue unless **Hold prints while alerting** is enabled.

An interlock keeps work pending and re-evaluates it on every scheduler pass.
The unsafe state is configured explicitly (`on`/`off` for binary sensors or a
numeric threshold). Unknown, unavailable, missing and stale readings follow
the selected failure strategy. Automatic mode fails closed for `smoke`, `gas`,
`moisture`, `problem` and `safety` device classes, and fails open for ordinary
readiness sensors. An administrator with queue-wide update permission can
temporarily override an uncertain fail-closed reading by supplying a reason;
the user, printer and reason are written to the application log. A confirmed
unsafe reading is never bypassed by that override.

These interlocks are operational assistance, not certified physical safety
equipment. Use appropriate independent guards, emergency stops and fire
protection for the printer and its enclosure. Do not rely on Home Assistant,
the network or PrintOps as the sole protection against injury or fire.
