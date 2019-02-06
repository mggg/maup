import geopandas
import numpy
import pandas

from .indexed_geometries import IndexedGeometries, get_geometries
from .intersection_matrix import intersection_matrix


def assign_without_area(sources, targets):
    indexed_sources = IndexedGeometries(sources)
    return indexed_sources.assign(targets)


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


def assign_by_area(sources, targets):
    if not (
        isinstance(sources.index, pandas.RangeIndex)
        and isinstance(targets.index, pandas.RangeIndex)
    ):
        return assign_by_area_with_non_integer_indices(sources, targets)

    matrix = intersection_matrix(sources, targets, lambda geom: geom.area).tocsr()
    assignment = pandas.Series(numpy.ravel(matrix.argmax(axis=1)), index=sources.index)
    return assignment


def get_geometries_with_range_index(geometries):
    gdf = geopandas.GeoDataFrame({"geometry": get_geometries(geometries)}).set_index(
        pandas.RangeIndex(len(geometries))
    )
    return gdf.geometry


def map_from_range_index(iterable):
    return dict(zip(pandas.RangeIndex(len(iterable)), iterable))


def assign_by_area_with_non_integer_indices(sources, targets):
    reindexed_sources = get_geometries_with_range_index(sources)
    reindexed_targets = get_geometries_with_range_index(targets)

    assignment = assign_by_area(reindexed_sources, reindexed_targets)

    return assignment.map(map_from_range_index(targets.index)).rename(
        map_from_range_index(sources.index)
    )
