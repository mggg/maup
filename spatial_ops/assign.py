import numpy
import pandas

from .indexed_geometries import IndexedGeometries
from .indices import map_from_range_index
from .intersection_matrix import IntersectionMatrix


def assign(sources, targets):
    """Assign source geometries to targets. A source is assigned to the
    target that covers it, or, if no target covers the entire source, the
    target that covers the most of its area.
    """
    assignment = assign_without_area(sources, targets)
    unassigned = sources[assignment.isna()]
    assignments_by_area = assign_by_area(unassigned, targets)

    assignment.update(assignments_by_area)
    return assignment


def assign_without_area(sources, targets):
    indexed_sources = IndexedGeometries(sources)
    return indexed_sources.assign(targets)


def assign_by_area(sources, targets):
    matrix = IntersectionMatrix.from_geometries(sources, targets, lambda g: g.area)
    assignment = pandas.Series(
        numpy.ravel(matrix.matrix.argmax(axis=0)), index=sources.index
    )
    return assignment.map(map_from_range_index(targets.index)).rename(
        map_from_range_index(sources.index)
    )
