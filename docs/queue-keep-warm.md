# Optional bed keep-warm between queue jobs

`queue_keep_bed_warm` defaults to `false`. Enable it in Settings → Printers &
Production → Print Process → Preheat & Heat Soak. It also requires ordinary
preheat and plate-clear confirmation to be enabled. The maximum hold defaults
to ten minutes and accepts one through thirty minutes. No heater command is
sent merely by saving these settings.

The implementation holds only the bed on P2S and X1C, using their existing bed
temperature command. These models have chamber sensors, but no active chamber
heater; no chamber or nozzle command is introduced. Both the last completed
job and the next pending job must prove all of the following:

- Their original sliced 3MF files still exist, have no variants or G-code/
  filament overrides, and were sliced for the actual printer model.
- Both queue items identify a real selected plate. Its parsed bed temperature
  is the same, within 40–110°C, and the plate type agrees.
- Every filament actually consumed by that plate has an explicit AMS or
  external-spool mapping, matching both the other job and the loaded material.
  Parked filaments are excluded when deriving the chamber target.
- The positive chamber requirement is the same. Live bed and chamber readings
  show that the prior job has already warmed them to within the existing
  preheat tolerance. No fallback bed target is guessed.
- Firmware is connected in FINISH and its task ID matches the last completed
  archive. The completion is at most thirty minutes old. The bed target is
  currently zero, so an existing manual heating session cannot be claimed.

The next job can use either an archive or a library file. Library files require
their parsed `sliced_for_model` metadata; a manually assigned variant target
model is insufficient. Bed target, plate type and used filament evidence still
come from the selected plate in the actual sliced file.

Holding occurs while the next job is waiting for plate-clear confirmation.
Manual-start, future-scheduled, filament-short, preheat-disabled, interlocked,
failed/unknown-prior and drying-reserved paths do not start a hold. Drying
telemetry and scheduler reservations are checked again immediately before heat
is claimed. Missing selected-plate metadata, material mapping, task identity or
temperatures keeps that path disabled. H2C and other models remain ineligible
because this feature has no verified warm-hold contract for their heater path.

The first command records durable heater ownership and starts an absolute
deadline. Scheduler passes neither repeat the command nor renew the deadline.
Expiry stops owned heat without failing the still-pending job; that same job
cannot immediately re-arm a new hold. Queue end, settings disable, cancellation,
an incompatible next job, a safety interlock or drying reservation releases the
hold. Failed dispatch claims, vanished rows and a skipped preheat stage release
the hold before upload. A successful claim transfers the same lease into normal
preheat/upload; ordinary warm-up and soak remain in force. Failed uploads and
cancellation unwind ownership, while MQTT publish alone never transfers it to a
print. Firmware must confirm an actual print start.

Manual PrintOps temperature commands supersede ownership even at the same
numeric target: the hold cannot stop, adopt or re-arm that session. Changed
targets and a confirmed print are also preserved. Automatic SmartPlug shutdown
respects the shared heater lease. Unverifiable targets after a restart or MQTT
session replacement retain the conservative power-off interlock described in
[preheat ownership](preheat-ownership.md).

Tests exercise real sliced-plate ZIP files, actual SQLite queue relationships,
settings round trips, upload/cancellation races, deadlines, SmartPlug guards and
the shared UI autosave. They send no physical printer commands. The user's
P2S firmware 01.03.00.00 and X1C firmware 01.12.00.00 have not been exercised on
hardware by this change; the implementation reuses the existing bed protocol
and conservatively disables any path whose software evidence is incomplete.
