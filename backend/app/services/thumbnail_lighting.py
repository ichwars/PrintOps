"""Deterministic lighting shared by library and generated plate thumbnails."""

import logging

logger = logging.getLogger(__name__)

VIEW_ELEVATION = 25
VIEW_AZIMUTH = 45
LIGHT_AZIMUTH = 315
LIGHT_ALTITUDE = 45


def thumbnail_faces(mesh, trimesh):
    """Repair inconsistent winding before computing per-face illumination."""
    if len(mesh.faces) and not mesh.is_winding_consistent:
        try:
            trimesh.repair.fix_winding(mesh)
            if mesh.is_watertight:
                trimesh.repair.fix_inversion(mesh)
        except Exception as exc:
            logger.debug("Thumbnail winding repair skipped: %s", exc)
    return mesh.faces


def thumbnail_shading(poly3d):
    """Keep degenerate-only geometry on the existing unlit fallback path."""
    import numpy as np
    from matplotlib.colors import LightSource

    if len(poly3d) == 0:
        return {}
    triangles = np.asarray(poly3d, dtype=float)
    normals = np.cross(triangles[:, 0] - triangles[:, 1], triangles[:, 1] - triangles[:, 2])
    lengths = np.linalg.norm(normals, axis=1)
    if not np.any(np.isfinite(lengths) & (lengths > 0)):
        return {}
    return {"shade": True, "lightsource": LightSource(azdeg=LIGHT_AZIMUTH, altdeg=LIGHT_ALTITUDE)}
