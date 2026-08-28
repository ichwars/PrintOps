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
the user, timestamp, printer and reason are written to the durable interlock
audit and the application log. The printer card shows the active override and
lets the same permission holder restore the interlock. Overrides live only for
the current server process, so a restart automatically restores the configured
fail-closed posture. A confirmed unsafe reading is never bypassed by an
override.

The REST surface is available below `/api/v1/ha-sensors/printers/{printer_id}`:

- `GET /interlock-override` reports the active override and which unavailable
  fail-closed sensors are currently eligible.
- `POST /interlock-override` enables a temporary override and requires a
  three-character-or-longer `reason` plus `queue:update_all`.
- `DELETE /interlock-override` restores the interlock.
- `GET /interlock-audit` returns the durable enable/clear history and also
  requires `queue:update_all`.

These interlocks are operational assistance, not certified physical safety
equipment. Use appropriate independent guards, emergency stops and fire
protection for the printer and its enclosure. Do not rely on Home Assistant,
the network or PrintOps as the sole protection against injury or fire.
