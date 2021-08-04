from .adjacencies import adjacencies
from .assign import assign
from .indexed_geometries import IndexedGeometries
from .intersections import intersections, prorate
from .repair import close_gaps, resolve_overlaps, make_valid, autorepair, snap_to_grid, crop_to, expand_to, doctor
from .normalize import normalize
from .progress_bar import progress

__version__ = "1.0.3"
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
