from .adjacencies import adjacencies
from .assign import assign
from .indexed_geometries import IndexedGeometries
from .intersections import intersections, prorate
from .repair import close_gaps, resolve_overlaps, make_valid, autorepair, snap_to_grid, crop_to, expand_to, doctor
from .normalize import normalize
from .progress_bar import progress

import geopandas

# warn about https://github.com/geopandas/geopandas/issues/2199
if geopandas.options.use_pygeos:
    raise ImportError(
        "GerryChain cannot use GeoPandas when PyGeos is enabled. Disable or "
        "uninstall PyGeos. You can disable PyGeos in GeoPandas by setting "
        "`geopandas.options.use_pygeos = False` before importing your shapefile."
    )

__version__ = "1.0.7"
__all__ = [
    "assign",
    "intersections",
    "prorate",
    "adjacencies",
    "close_gaps",
    "resolve_overlaps",
    "snap_to_grid",
    "IndexedGeometries",
    "normalize",
    "progress",
    "make_valid",
    "autorepair",
    "doctor"
]
