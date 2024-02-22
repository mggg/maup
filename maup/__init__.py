import geopandas
from .adjacencies import adjacencies
from .assign import assign
from .indexed_geometries import IndexedGeometries
from .intersections import intersections, prorate
from .repair import close_gaps, resolve_overlaps, quick_repair, snap_to_grid, crop_to, expand_to, doctor
from .smart_repair import smart_repair
from .normalize import normalize
from .progress_bar import progress

# warn about https://github.com/geopandas/geopandas/issues/2199
if geopandas.options.use_pygeos:
    raise ImportError(
        "GerryChain cannot use GeoPandas when PyGeos is enabled. Disable or "
        "uninstall PyGeos. You can disable PyGeos in GeoPandas by setting "
        "`geopandas.options.use_pygeos = False` before importing your shapefile."
    )

__version__ = "2.0.2"
__all__ = [
    "adjacencies",
    "assign",
    "IndexedGeometries",
    "intersections",
    "prorate",
    "close_gaps",
    "resolve_overlaps",
    "quick_repair",
    "snap_to_grid",
    "crop_to",
    "expand_to",
    "doctor",
    "smart_repair",
    "normalize",
    "progress"
]
