# Model and G-code previews

Library STL thumbnails and generated plate thumbnails use the same fixed light
and camera angles. Directional surface shading makes faces and curved surfaces
recognizable without changing the existing green palette, background, mesh
simplification limits or embedded slicer thumbnails. Inconsistent face winding
is repaired where possible; degenerate geometry retains an unlit fallback.

For a specific G-code plate, open `/gcode-viewer?archive=ID&plate=N` or
`/gcode-viewer?library_file=ID&plate=N`. Plate numbers start at 1. The viewer and
both APIs preserve the selection, including zero-padded member filenames.
Invalid selections display an error instead of opening another plate. Missing
plates return 404; nonpositive API indices return 400. Plain G-code has only
plate 1. Without an explicit choice, the lowest numbered plate is selected,
independent of the order in which the slicer stored ZIP members.

The existing PrettyGCode renderer accounts for device pixel ratio when comparing
canvas and viewport dimensions. A stationary high-DPI viewport no longer
reallocates its drawing buffer on every animation frame. Zero-sized containers
are skipped until they become visible; actual viewport changes still update the
camera and buffer.

The renderer replacement in upstream commit
[`08df660f6`](https://github.com/maziggy/bambuddy/commit/08df660f6cf432a555884ac49a0567c12e18c9d5)
was reviewed and deferred. It adds a new G-code parser and a GPU renderer copied
from a built package. Its claimed source/license could not be independently
retrieved during this change, and there is no comparative performance or
cross-platform evidence for PrintOps. A future replacement needs a pinned source
revision, reproducible build, license verification, real-file parser tests and
desktop/mobile performance measurements. This change keeps the existing local
assets and browser policy.
