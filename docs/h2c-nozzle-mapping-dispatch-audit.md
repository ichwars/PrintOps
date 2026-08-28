# H2C nozzle-mapping dispatch audit

Status: software safety boundary implemented; hardware release pending.

## Data flow and owner

The Virtual Printer receives Bambu Studio's `project_file` MQTT payload and
stores its opaque `nozzle_mapping` on the queue item. The scheduler transports
that value unchanged. The canonical safety owner is the MQTT command builder
in `backend/app/services/bambu_mqtt.py`, because that is the last point before
physical IDs reach a printer.

Printer records now keep three facts separately:

- `model`: the human-readable display model, for example `H2C`;
- `model_code`: the raw/internal code, currently `O1C` or `O1C2` for H2C;
- `firmware_version`: the last version reported by MQTT `get_version`.

An H2C cannot be newly registered without selecting its raw model code.
Discovery preserves the raw code instead of discarding it during display-name
normalization.

## Safe mapping boundary

Only flat physical arrays with 8 or 32 entries are structurally eligible.
Accepted entries are `-1`, fixed-carriage ID `1`, and rack IDs `16` through
`21`. Compact logical indices, nested/multi-group values, unknown physical
IDs, empty arrays, invalid JSON, and all other lengths are rejected.

Structural validity does not enable dispatch. The capability table
`H2C_NOZZLE_MAPPING_MIN_FIRMWARE` is intentionally empty. Consequently no
H2C/O1C/O1C2 physical mapping is emitted, and H2D, H2D Pro, X2D, and other
models never inherit the H2C field. The fallback is logged with display model,
raw code, firmware and a machine-readable reason; the print command itself is
still sent without `nozzle_mapping`.

## Hardware release checklist

Before adding any entry to the capability table, record all of the following
for the exact raw model code:

1. device-reported raw model code and display model;
2. exact firmware version and the proposed minimum firmware boundary;
3. anonymized native Bambu Studio `project_file` payloads for a fixed-nozzle,
   rack-only, and mixed plate;
4. the corresponding PrintOps payloads after queue intake and immediately
   before MQTT publish;
5. successful A/B prints for all three cases, including cleaning, ABL,
   carriage selection, first layer and final part placement;
6. regression results showing no changed mapping behavior for H2D, H2D Pro,
   X2D, single-nozzle models, delayed Virtual Printer MQTT, or retry paths.

The upstream H2C test at firmware `01.02.00.00` is useful evidence but is not a
PrintOps minimum-firmware claim: its raw device code was not recorded and the
local PrintOps installation has no H2C hardware. Until the checklist is
completed, the empty capability table is the required production state.
