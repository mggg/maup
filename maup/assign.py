import pandas

from .indexed_geometries import IndexedGeometries
from .intersections import intersections
from .crs import require_same_crs


@require_same_crs
def assign(sources, targets):
    """Assign source geometries to targets. A source is assigned to the
    target that covers it, or, if no target covers the entire source, the
    target that covers the most of its area.
    """
    assignment = pandas.Series(
        assign_by_covering(sources, targets),
        dtype="float"
    )
    assignment.name = None
    unassigned = sources[assignment.isna()]

    if len(unassigned):  # skip if done
        assignments_by_area = pandas.Series(
            assign_by_area(unassigned, targets),
            dtype="float"
        )
        assignment.update(assignments_by_area)

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
