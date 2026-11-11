# Printer video files

Open a printer's **File Manager** and choose **Videos** to browse `/ipcam`,
or **Timelapse** to browse `/timelapse`. Available directories and MP4/AVI
files depend on the printer model, firmware, recording settings and SD card.
The file manager downloads recordings as they are stored; it does not change
archive or timelapse matching.

Click a file's checkbox, then Shift-click another checkbox to select the
contiguous range in the current sort order. Filtering limits the range to
visible files. Changing the directory, filter or sort resets the range anchor.

Selections containing videos download files individually in order. The manager
shows the file count plus byte progress, speed and remaining time when the
printer reports the file size. A failed file stays selected and its error remains
visible; the remaining files continue. Cancel stops the active transfer and
leaves failed and unfinished files selected. Closing the manager also cancels
the transfer. Selections without videos retain the existing ZIP download.

Downloads use the existing authenticated printer-file endpoint and permission.
The server forwards bounded FTPS chunks directly to the HTTP response, uses the
configured FTPS socket timeout and retries, and shares the printer download gate.
It retries only before the first bytes are sent. A connection failure after
streaming starts interrupts that file instead of replaying or silently completing
it. A reliable FTP size is checked and included as the HTTP content length.

The normal browser download uses an authenticated fetch and a per-file Blob,
which can require browser memory proportional to one recording. Where the
browser supports the File System Access API in a secure context, **Save videos
to folder** writes the HTTP stream directly to the chosen directory. That optional
flow avoids holding the recording in browser memory; it asks the browser for
write access once. Existing files of the same name are replaced only after a
successful stream. The normal download remains available without this browser
feature or folder permission. Browsers may ask to allow multiple downloads.


## Attaching large timelapses

When attaching a printer recording to an archive, a known file size extends
the overall transfer budget for a slow connection. The configured socket
inactivity timeout still applies. Manual selection, archive scanning and
background attachment pass the listing size and release their database
connection before the longer download.


## Slow directory listings

The file manager distinguishes a slow directory listing from an unavailable
printer file service and an empty folder. Refresh joins a listing that is
still running instead of starting another FTP session. Selection survives a
slow response and remains available after a successful refresh. Listing times
without a year use the UTC date, allowing a day of tolerance for firmware
that reports a local clock.

## Preview downloads and transfer failures

Plate selection and thumbnails share one download of the same printer file.
Successful downloads remain cached for up to 60 seconds, within fixed byte and
entry limits. Deleting a file, uploading its replacement or changing the printer
connection invalidates its previews, including a download still in progress.

Preview downloads reject empty, truncated and oversized transfers. Missing files,
failed transfers, printer cooldowns and transfer deadlines produce distinct
errors. Cancellation requests stop the FTP worker cooperatively; cleanup has a
bounded waiting period. An overdue worker does not trigger a second transfer.

## Unreadable cards and automatic attachment

Automatic attachment requires a trustworthy snapshot of the card from before
the recording finished. An unread directory does not count as an empty card.
A reliable stored snapshot survives a restart; an uncertain replacement does
not overwrite it during recovery. When the initial read fails, PrintOps reads
again only while the same print is active and recording a timelapse. Failed
rounds back off from two to thirty minutes and stop after five failures.

A stalled file service pauses background scans for five minutes. Manual file
browsing and print dispatch retain their existing transfer behavior. A successful
directory listing lifts the background pause; connecting alone does not. If the
baseline remains uncertain, automatic attachment leaves the video on the printer
for manual selection. A printer out of FTP sessions reports that specific error
and suggests a restart if the condition persists.

## Recordings belong to their print run

A download or camera stitch that finishes after the archive starts another
run cannot attach its old video to that new run. Deleting the archive or
attaching another video during a pending file write also prevents the stale
write from claiming the recording. A recording from the configured external
camera can replace the printer recording of the same run. Replaced or deleted
files remain on disk while another archive references them. Existing video
files are not overwritten by a new attachment or conversion.

Automatic matching excludes recordings already held by another archive on the
same printer, including recordings whose AVI extension became MP4. Manual
selection still offers them so an earlier wrong association can be corrected.
Attachments, deletions and finished conversions refresh open Archives pages.

Starting a new print clears the archive's active recording link so the next
scan and finish photo use the current run. PrintOps removes the previous
video only when it belongs to the same known plate and no archive references
it. Videos of other plates and older videos with no recorded plate stay in
the archive directory. The archive card shows the currently linked video.

Layer recordings get between five minutes and one hour to encode, based on
their frame count. If encoding fails after it starts, the source frames and
their frame list remain available for 24 hours. The cleanup skips recordings
that are capturing or encoding.

Layer recordings preserve their aspect ratio and scale down to about two
megapixels for encoding. The layer recorder and archive editor limit H.264
encoder threads and lookahead. Cancelling a camera snapshot releases its
local FFmpeg process and connection.

Portrait videos keep their aspect ratio in the archive player and editor.
The preview fits within the viewport, and the editor scrolls on short screens.

## Live camera connections

Viewers of a printer's USB camera share one capture. Closing one viewer leaves
the stream running for the others. After the last viewer leaves, PrintOps keeps
the capture for five seconds to allow a quick return. Opening a changed USB
camera waits for the previous capture to close.

External RTSP live views reconnect if the JPEG output repeats for too long.
The check starts at 20 seconds, adapts to slow scene changes and rechecks
unchanged scenes after five minutes. Periodic process cleanup works with the
stream subprocess handles opened by the current PrintOps instance.

Snapshots and connection tests reuse a recent frame from the camera already
in use by the live view. If the first frame is pending or the buffer is older
than ten seconds, the snapshot endpoint returns a temporary error. The camera
page retries after two seconds, and the camera wall tries at the next refresh.
An external camera's dedicated snapshot URL still supplies full-quality
snapshots. For an MSE-only viewer, PrintOps requests a JPEG from the registered
go2rtc stream.

Each camera view releases its connection when closed. Minimizing the
floating viewer also releases its image or video connection. Other viewers
of that printer keep their live picture. Sideways feeds fit the space
available inside the tile, viewer or overlay.

The camera wall and floating viewer reopen their feed after a picture error.
PrintOps closes the old connection before opening a replacement.

When login is enabled, a browser stream token follows the session or API
key that issued it. PrintOps checks access when a live MJPEG or MSE stream
opens and rechecks it every 30 seconds, including while the stream is idle.
Signing out, disabling a key, revoking a share or removing required
permissions closes affected connections at the next check. Overlay access
also follows the share owner's current printer assignments.

A Cam Wall share link automatically retries after a temporary server error.
The rejected-token message indicates that a new or renewed share is needed.

Open the Cameras subpage under Printers & Production to configure external
cameras, chamber lighting, camera tokens and streaming overlays. The USB
picker lists the capture devices visible to PrintOps. A container must
receive the device, for example with `--device /dev/video0:/dev/video0`.
A disconnected camera keeps its saved device path.

The Cam Wall has its own tile size. Its standalone URL accepts `size=s`,
`size=m`, `size=l` or `size=xl`. A camera opened from the sidebar stays open
during navigation in that tab. An overlay opened from a printer card stays
with the Printers page.

Automatic chamber lighting is off by default. Set it for all printers or
select printers individually. Live camera connections keep the light on
while in use. The snapshot delay lets the exposure settle before a capture.
When the last viewer or capture releases the light, PrintOps turns it off
if it switched the light on. A manual light command takes precedence.

The timelapse editor shows background encoding progress and can cancel the
running edit. The original video remains available during encoding. If the
original changes before the edit finishes, reopen the editor to work with
the new version.

If the automatic plate check switched on the chamber light, overlapping
live views hold it on until the last camera use ends. A manual light command
takes precedence. Plate checks, layer timelapses, Obico and finish photos
can reuse the current frame of a matching external camera.

## Cleanup while another print is active

Post-print SD cleanup leaves a file in place when current printer telemetry
reports it in use. The check includes preparation and pause states and runs
again before each retry, so a new print can stop a later delete attempt.
Cleanup still handles finished prints and missing files within its existing
time budget.

## Recordings in print history

An archive can hold prints from several printers. Open its print history to see
the photos and recording for each run you can access. The video count on the
archive opens the run history when several recordings are available. Starting a
new print of the same plate replaces that plate's recording. Videos for other
plates and finish photos stay linked to their original runs.

An API client can read `latest_run_id` on an archive and choose a specific run
with `GET /api/v1/archives/{id}?run_id={run_id}`. The run history at
`/api/v1/archives/{id}/runs` includes the plate, time and material estimates,
photo names and whether the run has a timelapse. Pass `run_id` to the archive
photo or timelapse endpoint to retrieve that run's media. The same archive
ownership and printer permissions apply to these requests.
