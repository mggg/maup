import pandas
import scipy.sparse

from .indexed_geometries import IndexedGeometries


def raise_exception_if_not_range_indexed(*datasets):
    for series in datasets:
        if not isinstance(series.index, pandas.RangeIndex):
            raise TypeError(
                "The sources and targets must have a RangeIndex indices to "
                "construct their intersection_matrix"
            )


def intersection_matrix(sources, targets, weight_by):
    raise_exception_if_not_range_indexed(sources, targets)
    indexed_sources = IndexedGeometries(sources)
    matrix = scipy.sparse.dok_matrix((len(sources), len(targets)))

    for (i, j, intersection) in indexed_sources.iter_intersections(targets):
        matrix[i, j] = weight_by(intersection)
    return matrix
