# Printer card queue preview

The existing expanded printer card links to the queue and shows one **queued
candidate**, its name and a status. The badge counts the caller's visible,
filament-compatible pending entries. An empty compatible queue has no preview.
Disconnected cards retain their existing offline state and omit the preview.

The preview uses the scheduler's position/ID order, or shortest-job-first when
enabled: jumped entries first, persisted queue duration ascending (unknown
last), position, then ID. Archive/library display estimates may differ from
that persisted duration, so they are not used to choose the candidate.

Entries with known manual, future schedule, dispatch or last-reported waiting
holds are not preferred over an entry awaiting checks. If every visible entry
has a known hold, the first in scheduling order is shown with that hold:

- Manual start required.
- Scheduled, with a localized date and time.
- Blocked at last check. The last waiting reason may become stale.
- Dispatch in progress.

**Awaiting printer checks is not a promise of immediate or next execution.**
The scheduler still owns live availability, paused/busy state, plate-clear,
sensor interlocks, dispatch claims/holds, drying ownership and manual-drying
protection, predecessor success, spool deficits, model allocation and source
file conflicts. The card's existing printer status and plate controls remain
visible beside the preview. Batch intent/remaining quantities are not invented
as queue jobs: only existing authorized pending run rows are summarized.

The queue and displayed time refresh every 30 seconds, and normal queue
invalidations refresh both the badge and preview. Crossing a scheduled time
updates the status even if the server's rows did not change.

The existing queue list applies owner and printer permissions before returning
rows. An explicit inaccessible printer returns 404, including requests for
unassigned model candidates. Its additive read-only snapshot fields are:

- `scheduler_print_time_seconds`: persisted queue duration used by SJF.
- `dispatching`: whether that row currently has a dispatch claim.
- `scheduler_shortest_first`: effective ordering, exposed only by the list;
  other queue response routes leave this nullable field unknown.

Queue readers can see this ordering bit without `settings:read`; the full
settings endpoint retains its own permission. Badge/preview query caches use
verified auth state, public subject when available, and credential session
generation. Numeric account IDs are never cache identity, and unverified,
unauthorized or failed queries cannot keep displaying an older cached job.
No queue mutation, dispatch, Batch, or drying policy changes are introduced.
