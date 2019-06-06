from .adjacencies import adjacencies
from .assign import assign
from .indexed_geometries import IndexedGeometries
from .intersections import intersections, prorate
from .repair import close_gaps, resolve_overlaps

__version__ = "0.5"
__all__ = [
    "assign",
    "intersections",
    "prorate",
    "adjacencies",
    "close_gaps",
    "resolve_overlaps",
    "IndexedGeometries",
]
