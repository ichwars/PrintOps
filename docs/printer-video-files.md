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
