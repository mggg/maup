import pandas
import scipy.sparse

from .indexed_geometries import IndexedGeometries
from .indices import get_geometries_with_range_index


class IntersectionMatrix:
    def __init__(self, matrix, sources_index, targets_index):
        expected_shape = (len(targets_index), len(sources_index))
        if matrix.shape != expected_shape:
            raise ValueError(
                "The source and target indices do not match the shape of "
                "the provided matrix"
            )
        self.matrix = matrix
        self.sources_index = sources_index
        self.targets_index = targets_index

    def interpolate(self, series):
        if len(series) != len(self.sources_index):
            raise ValueError(
                "The provided data is not the same shape as the "
                "source geometries. Maybe you meant to interpolate "
                "in the opposite direction?"
            )
        interpolated_data = self.matrix.dot(series.to_numpy())
        return pandas.Series(
            data=interpolated_data, name=series.name, index=self.targets_index
        )

    def transpose(self):
        return self.__class__(
            self.matrix.transpose(), self.targets_index, self.sources_index
        )

    @classmethod
    def from_geometries(cls, sources, targets, weight_by):
        reindexed_sources = get_geometries_with_range_index(sources)
        reindexed_targets = get_geometries_with_range_index(targets)
        matrix = intersection_matrix(
            reindexed_sources, reindexed_targets, weight_by
        ).tocsr()
        return cls(matrix, sources.index, targets.index)


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
    matrix = scipy.sparse.dok_matrix((len(targets), len(sources)))

    for (i, j, intersection) in indexed_sources.enumerate_intersections(targets):
        matrix[i, j] = weight_by(intersection)

    return matrix
