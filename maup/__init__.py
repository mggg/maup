from importlib.metadata import version as _distribution_version

from .adjacencies import adjacencies
from .assign import assign, AssigmentWarning
from .indexed_geometries import IndexedGeometries
from .intersections import intersections, prorate
from .repair import (
    close_gaps,
    resolve_overlaps,
    quick_repair,
    snap_to_grid,
    crop_to,
    expand_to,
    doctor,
)
from .smart_repair import smart_repair
from .normalize import normalize
from .progress_bar import progress

__version__ = _distribution_version("maup")
__all__ = [
    "adjacencies",
    "AssigmentWarning",
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
    "progress",
]
