from .indexed_geometries import IndexedGeometries
from .intersections import intersections


def assign(sources, targets):
    """Assign source geometries to targets. A source is assigned to the
    target that covers it, or, if no target covers the entire source, the
    target that covers the most of its area.
    """
    assignment = assign_by_covering(sources, targets)
    unassigned = sources[assignment.isna()]
    assignments_by_area = assign_by_area(unassigned, targets)

    assignment.update(assignments_by_area)
    return assignment


def assign_by_covering(sources, targets):
    indexed_sources = IndexedGeometries(sources)
    return indexed_sources.assign(targets)


def assign_by_area(sources, targets):
    intersection_areas = intersections(sources, targets).area
    assignment = (
        intersection_areas.groupby(level="source").idxmax().apply(drop_source_label)
    )
    return assignment


def drop_source_label(index):
    return index[1]
