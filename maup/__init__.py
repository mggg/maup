from .adjacencies import adjacencies
from .assign import assign
from .indexed_geometries import IndexedGeometries
from .intersections import intersections, prorate
from .repair import close_gaps, resolve_overlaps, autorepair, snap_to_grid, crop_to, doctor
from .normalize import normalize
from .progress_bar import progress

# Moved the source for the import of make_valid from .repair to shapely since it lives
# there now and the maup version should be removed.  (Also removing make_valid from the
# __all__ list below.)
from shapely import make_valid 

import geopandas

# warn about https://github.com/geopandas/geopandas/issues/2199
if geopandas.options.use_pygeos:
    raise ImportError(
        "GerryChain cannot use GeoPandas when PyGeos is enabled. Disable or "
        "uninstall PyGeos. You can disable PyGeos in GeoPandas by setting "
        "`geopandas.options.use_pygeos = False` before importing your shapefile."
    )

__version__ = "1.0.8"
__all__ = [
    "adjacencies",
    "assign",
    "IndexedGeometries",
    "intersections",
    "prorate",
    "close_gaps",
    "resolve_overlaps",
    "autorepair",
    "snap_to_grid",
    "crop_to",
    "doctor",
    "normalize",
    "progress",
    "make_valid"
]

