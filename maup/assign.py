import pandas
import warnings

from .indexed_geometries import IndexedGeometries
from .intersections import intersections
from .crs import require_same_crs


class AssigmentWarning(UserWarning):
    """Warning raised when some source geometries are not assigned to any target."""


@require_same_crs
def assign(sources, targets):
    """Assign source geometries to targets. A source is assigned to the
    target that covers it, or, if no target covers the entire source, the
    target that covers the most of its area.

    Returns a pandas Series indexed like sources, with labels from targets.index. Labels may be
    numeric, strings, or tuples. Unassigned sources have missing values and trigger an
    AssigmentWarning; use Series.isna() to find them. The result uses the target index's dtype when
    conversion is possible, otherwise it retains object dtype to accommodate labels and missing
    values.
    """
    # Target labels may be strings or tuples; object also accommodates missing assignments.
    assignment = pandas.Series(assign_by_covering(sources, targets), dtype=object)
    assignment.name = None
    unassigned = sources[assignment.isna()]

    if len(unassigned):  # skip if done
        assignments_by_area = pandas.Series(
            assign_by_area(unassigned, targets), dtype=object
        )
        assignment.update(assignments_by_area)

    # Warn here if there are still unassigned source geometries.
    unassigned = sources[assignment.isna()]
    if len(unassigned):  # skip if done
        warnings.warn(
            "Warning: Some units in the source geometry were unassigned.",
            AssigmentWarning,
        )

    return assignment.astype(targets.index.dtype, errors="ignore")


def assign_by_covering(sources, targets):
    indexed_sources = IndexedGeometries(sources)
    return indexed_sources.assign(targets)


def assign_by_area(sources, targets):
    return assign_to_max(intersections(sources, targets, area_cutoff=0).area)


def assign_to_max(weights):
    return weights.groupby(level="source").idxmax().apply(drop_source_label)


def drop_source_label(index):
    return index[1]
