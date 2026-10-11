# Spool printer profiles

The spool editor's **Printer profiles** tab supports one filament preset override
per printer model, in both local inventory and Spoolman mode. Model keys come
from PrintOps's existing printer-model registry; long model names and documented
internal codes normalize to the same key. Unknown model keys are rejected.

The resolution order is:

1. An override for the target printer's persisted model.
2. The spool's existing general preset, when that model has no override.
3. The material's generic preset when the selected preset cannot be resolved.

Choosing **Generic material preset** writes an explicit empty override. It does
not inherit the general preset or the previous spool's AMS preset. Choosing
**Use general preset** removes the override. Copies and bulk-created spools
receive their configured overrides; ordinary edits preserve untouched mappings.
If the separate model-map save fails, the editor retains the draft and saved
spool IDs. Retrying saves the profiles without repeating a successful spool
create or update; bulk retries reuse every created ID. The editor reports success
and closes only after the requested profiles are saved.
The assignment paths and slot display use the same model resolver. RFID paths
keep the firmware's tag metadata and use existing calibration selection commands.

Overrides are application-owned records in `spool_filament_preset` and
`spoolman_filament_preset`. Normal database startup creates these tables on both
SQLite and PostgreSQL, including existing installations. Existing spool columns
and presets remain intact; no backfill guesses which model they belong to.
Spoolman overrides live in PrintOps, alongside its existing K-profile records,
and are not written into Spoolman's filament catalog. Protect the PrintOps
database backup when migrating these records. Inventory read/update permissions
gate the new GET/PUT endpoints. The change does not alter weights, reservations,
commercial variants or print release rules.

Calibration selection keys include printer, diameter, reported extruder and
reported HS/HH flow. Saving a reused index never chooses the first row from a
different diameter or flow. Legacy keys are resolved only when exactly one
compatible entry exists. Missing or ambiguous calibration metadata remains
gated by the shared backend resolver. The editor keeps the existing limit of
one stored K selection per printer/extruder/diameter in Spoolman mode; it does
not migrate that table's uniqueness constraint to retain two simultaneous flow
variants for the same diameter. The selected flow is saved explicitly.

The software tests use synthetic MQTT payloads. X1C firmware 01.12.00.00 and
P2S firmware 01.03.00.00 have not been validated against real device telemetry
in this change. H2 hotend/rack numbering is deliberately not inferred: unknown
physical hotend contexts remain blocked for automatic K selection. This covers
the model-preset and context-safe software portions of #149; live device
acceptance and H2 hotend mapping remain open.
