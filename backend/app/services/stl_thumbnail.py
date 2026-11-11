"""STL Thumbnail Generation Service.

Generates thumbnail images from STL files using trimesh and matplotlib.
"""

import logging
import os
import uuid
from pathlib import Path

from backend.app.services.thumbnail_lighting import BACKGROUND_COLOR as BACKGROUND_COLOR, BAMBU_GREEN as BAMBU_GREEN

logger = logging.getLogger(__name__)

# Matplotlib's font_manager emits one INFO line per font on first import
# while it builds its cache, including a noisy "Failed to extract font
# properties from NotoColorEmoji.ttf" for the COLR/COLR1 emoji format it
# doesn't support. These are not actionable — demote to WARNING so real
# font issues still surface but the first STL upload doesn't produce a
# multi-line matplotlib preamble in the journal.
logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)


def _configure_matplotlib_cache() -> None:
    """Point matplotlib's config/cache directory at a writable persistent path.

    Without this, matplotlib falls back to ``/tmp/matplotlib-XXXXXX`` whenever
    ``$HOME/.config/matplotlib`` isn't writable — which is the case under
    PrintOps's container / systemd-service deployments where ``$HOME`` is set
    to a non-writable path. The fallback emits a WARNING on every cold start
    AND loses the font cache on host reboot, so font_manager rebuilds it
    every time → another batch of INFO lines.

    Setting ``MPLCONFIGDIR`` to ``settings.base_dir / .cache / matplotlib``
    eliminates both: the warning never fires, and the cache survives across
    restarts so the per-font scan only runs once per deployment.
    Idempotent — respects an externally-set ``MPLCONFIGDIR`` if the operator
    chose their own path.
    """
    if os.environ.get("MPLCONFIGDIR"):
        return
    try:
        from backend.app.core.config import settings

        cache_dir = Path(settings.base_dir) / ".cache" / "matplotlib"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ["MPLCONFIGDIR"] = str(cache_dir)
    except Exception as exc:
        # Best-effort. If settings isn't importable or the mkdir fails (read-only
        # FS, permission denied), let matplotlib fall back to /tmp with its
        # built-in warning — same as today's behaviour, no worse.
        logger.debug("Could not configure MPLCONFIGDIR: %s", exc)


# Maximum vertices before simplification
MAX_VERTICES = 100000

# Minimum STL file size that could possibly contain a usable mesh:
# - Binary STL with one triangle: 80B header + 4B count + 50B triangle = 134B
# - ASCII STL with one triangle: header + "facet ... endfacet" + footer ≈ 150B
# Files below this are stubs / placeholders / corrupted; trimesh would return an
# empty mesh anyway. Pre-skipping at the call sites suppresses the warning storm
# bulk-uploaded ZIPs of small test STLs used to produce.
MIN_USABLE_STL_BYTES = 200


def generate_stl_thumbnail(
    stl_path: Path,
    thumbnails_dir: Path,
    size: int = 256,
) -> str | None:
    """Generate a thumbnail image from an STL file.

    Args:
        stl_path: Path to the STL file
        thumbnails_dir: Directory to save the thumbnail
        size: Thumbnail size in pixels (default 256x256)

    Returns:
        Path to the generated thumbnail, or None on failure
    """
    # Callers historically pass either Path or str; coerce so the `thumbnails_dir
    # / thumb_filename` join at the end of this function can't fail with the
    # str-divided-by-str TypeError (see #1299).
    stl_path = Path(stl_path)
    thumbnails_dir = Path(thumbnails_dir)

    try:
        # Must precede the matplotlib import — MPLCONFIGDIR is read at
        # matplotlib import time, not on subsequent attribute access.
        _configure_matplotlib_cache()

        import trimesh

        from backend.app.services.plate_thumbnail import render_mesh_png

        # Load the STL file
        mesh = trimesh.load(str(stl_path), force="mesh")

        if mesh is None or not hasattr(mesh, "vertices") or len(mesh.vertices) == 0:
            # Demoted from warning to debug: this is a per-file content
            # observation (the STL is empty / stub / corrupted), not an
            # actionable error. The caller proceeds correctly with no
            # thumbnail. The call sites also pre-skip files below
            # MIN_USABLE_STL_BYTES so the common stub-STL case never gets
            # this far — this branch now catches only the rare "large
            # enough but trimesh still can't parse it" case.
            logger.debug("Failed to load STL or empty mesh: %s", stl_path)
            return None

        # Simplify large meshes for performance
        if len(mesh.vertices) > MAX_VERTICES:
            logger.info("Simplifying mesh from %s vertices", len(mesh.vertices))
            try:
                # Calculate reduction ratio (0-1 range)
                # e.g., 124633 vertices -> 100000 means keep ~80%, so reduce by ~20%
                keep_ratio = MAX_VERTICES / len(mesh.vertices)
                target_reduction = 1.0 - keep_ratio
                # Clamp to valid range (0.01 to 0.99)
                target_reduction = max(0.01, min(0.99, target_reduction))
                mesh = mesh.simplify_quadric_decimation(target_reduction)
                logger.info("Simplified mesh to %s vertices", len(mesh.vertices))
            except Exception as e:
                logger.warning("Mesh simplification failed, using original: %s", e)

        png = render_mesh_png(mesh, size=size, label=stl_path.name)
        thumb_filename = f"{uuid.uuid4().hex}.png"
        thumb_path = thumbnails_dir / thumb_filename  # SEC-PATH-OK: thumb_filename = uuid.uuid4().hex + ".png"
        thumb_path.write_bytes(png)

        logger.info("Generated STL thumbnail: %s", thumb_path)
        return str(thumb_path)

    except ImportError as e:
        logger.warning("STL thumbnail generation unavailable (missing dependencies): %s", e)
        return None
    except Exception as e:
        # Log the traceback, not just the message: a bare
        # "unsupported operand type(s) for /: 'str' and 'str'" gives no clue
        # which line failed, and the fault is data-/environment-specific
        # enough that it can't be reproduced from a clean STL — the traceback
        # in the next support bundle is what pinpoints it (#1480).
        logger.warning("Failed to generate STL thumbnail for %s: %s", stl_path, e, exc_info=True)
        return None
