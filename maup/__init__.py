import geopandas
from .adjacencies import adjacencies
from .assign import assign
from .indexed_geometries import IndexedGeometries
from .intersections import intersections, prorate
from .repair import close_gaps, autorepair, snap_to_grid, crop_to, doctor, resolve_overlaps
from .normalize import normalize
from .progress_bar import progress


# warn about https://github.com/geopandas/geopandas/issues/2199
if geopandas.options.use_pygeos:
    raise ImportError(
        "GerryChain cannot use GeoPandas when PyGeos is enabled. Disable or "
        "uninstall PyGeos. You can disable PyGeos in GeoPandas by setting "
        "`geopandas.options.use_pygeos = False` before importing your shapefile."
    )

__version__ = "1.1.0"
__all__ = [
    "adjacencies",
    "assign",
    "IndexedGeometries",
    "intersections",
    "prorate",
    "close_gaps",
    "autorepair",
    "resolve_overlaps",
    "snap_to_grid",
    "crop_to",
    "doctor",
    "normalize",
    "progress"
]