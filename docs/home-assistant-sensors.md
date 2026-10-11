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

## Storage locations and dry boxes

Open **Inventory → Locations → Sensors** on an existing location to bind a
Home Assistant temperature or humidity entity. The picker only offers
`sensor.*` entities with the `temperature` or `humidity` device class and
matching units (`°C`, `°F`, `K`, or `%`). The location catalog remains usable
when Home Assistant is disabled or unconfigured.

The Locations list shows the numeric value, unit, freshness status and time
of the last successful reading. **Fresh** means a successful read within the
last 45 seconds. **Stale** means the poller has no recent successful reading;
**Unavailable** means the last attempt failed, the value was invalid, or the
entity changed its unit/device class. **Awaiting reading** appears before the
first successful poll. Failed attempts preserve the last successful read time
but do not display the old value as current. Storage and printer sensors share
one 15-second polling loop and fetch each distinct entity once per pass.

Optional upper/lower thresholds color the reading when it exceeds the upper
bound or falls below the lower bound; equality is within range. Enable
**Notify on alert** on the binding and **Storage sensor alerts** on a
notification provider with no printer filter to receive transition alerts.
An ongoing alert sends no repeated message, including after outages. A cold
cache on restart or a changed binding establishes a baseline without sending
an alert. Provider failures do not interrupt polling. Storage alerts have their
own notification template and event (`storage_sensor_alert`).

The `/api/v1/storage-ha-sensors` endpoints require `inventory:read` for
bindings, readings and the entity picker, and `inventory:update` for binding
changes. A location can contain multiple sensors; the same entity can be used
at different locations, but duplicate bindings at one location are rejected.
Deleting an unused location also removes its sensor bindings.

These readings are informational. They never change spool weights, warehouse
stock, reservations, order state, or print release. Print-start interlocks
remain separately configured under printer sensors.
