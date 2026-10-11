# Queue preheat ownership and rollback

The existing preheat option remains off by default. The separate
[opt-in bed keep-warm option](queue-keep-warm.md) also defaults off. Both reuse
existing printer commands and model capabilities. P2S and X1C continue to warm the chamber through the bed; only
models already recognized as having a chamber heater receive chamber commands.

When an enabled preheat stage changes a bed or chamber target, PrintOps records
that queue item's ownership in `DATA_DIR/preheat-ownership/<printer-id>.json`
before sending the existing temperature command. Upload failure, rejected print
start, cancellation, queue removal/end and scheduler shutdown stop owned heaters
with the existing zero-temperature commands. Cancellation is checked every three
seconds during warm-up, soak and upload, and cancels the existing upload task.
Failed uploads preserve a concurrent cancellation rather than changing it to a
failure.

Ownership continues after a successful MQTT publish and the queue's optimistic
`printing` status. Only firmware states PREPARE, SLICING, RUNNING or PAUSE transfer
heater ownership to an actual print. The lease includes the configured warm-up
and soak duration, the existing size-based FTP upload/retry budgets, and start
acknowledgment time. It has an absolute 24-hour ceiling; after publish the
remaining acknowledgment period is at most five minutes. An expired dispatch
that is still pending fails and cancels rather than immediately repeating the
warm-up. Cleanup retries while an offline printer or a refused command prevents
confirmed rollback.

Rollback checks each target immediately before stopping it. An already-set
matching target is never claimed, a changed positive target is preserved, and
manual PrintOps temperature commands supersede ownership even when they set the
same numeric target. A confirmed print start prevents further heater shutdown.
An observed zero target permits repeating the existing off command, which also
covers delayed telemetry during immediate upload failures. No nozzle commands
are added.

Automatic SmartPlug time, temperature, scheduled and restart power-off paths
respect both actual printing and preheat ownership. They also recheck ownership
after awaited service configuration. Corrupt records, missing telemetry, offline
printers and unverifiable MQTT sessions keep automatic power-off blocked.

After an unclean restart or MQTT client replacement, a matching numeric target
cannot prove that the previous lease still owns a heater: someone may have
started a new manual heating session. Recovery therefore keeps the interlock
and does not send off commands to that session. A confirmed actual print or
observed changed/off targets resolves the record. If an idle printer still has
unresolved targets, inspect it and use its existing bed/chamber controls to turn
those targets off; recovery observes the change and clears the interlock. The
queue defers dispatch to that printer while ownership remains unresolved. Logs
identify unresolved ownership and persistence failures. The record contains only
printer/queue IDs, targets and a deadline, with no access codes.

Tests use mock MQTT clients and SmartPlug services, including independent SQLite
connections for cancellation races. Hardware validation on P2S/X1C remains
separate; H2C behavior has capability tests and has not been exercised on a real
H2C. Keep-warm is limited to the proven P2S/X1C bed path documented separately.
