import numpy as np
import pandas
import scipy.sparse
from geopandas import GeoDataFrame

from .indexed_geometries import IndexedGeometries
from .indices import get_geometries_with_range_index


class InterpolationMatrix:
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
        name = getattr(series, "name", None)
        vector = convert_to_array(series)
        interpolated_data = self.matrix * vector
        return pandas.Series(
            data=interpolated_data, name=name, index=self.targets_index
        )

    def transpose(self):
        return self.__class__(
            self.matrix.transpose(), self.targets_index, self.sources_index
        )

    def preserves_mass(self):
        return (np.sum(self.matrix, axis=1) == np.ones(len(self.sources_index))).all()

    def normalize(self):
        normalized_matrix = self.matrix / np.sum(self.matrix, axis=1)
        return self.__class__(normalized_matrix, self.targets_index, self.sources_index)

    @classmethod
    def from_geometries(cls, sources, targets, weight_by):
        reindexed_sources = get_geometries_with_range_index(sources)
        reindexed_targets = get_geometries_with_range_index(targets)
        matrix = intersection_matrix(
            reindexed_sources, reindexed_targets, weight_by
        ).tocsr()
        return cls(matrix, sources.index, targets.index)


def convert_to_array(series):
    if hasattr(series, "to_numpy"):
        return series.to_numpy()
    return np.asarray(series)


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
        matrix[i, j] = weight_by(intersection, i, j)

    return matrix


def intersections(sources, targets):
    reindexed_sources = get_geometries_with_range_index(sources)
    reindexed_targets = get_geometries_with_range_index(targets)
    spatially_indexed_sources = IndexedGeometries(reindexed_sources)

    records = [
        # Flip i, j to j, i so that the index is ["source", "target"]
        (sources.index[j], targets.index[i], geometry)
        for i, j, geometry in spatially_indexed_sources.enumerate_intersections(
            reindexed_targets
        )
    ]
    df = GeoDataFrame.from_records(records, columns=["source", "target", "geometry"])
    geometries = df.set_index(["source", "target"]).geometry
    geometries.sort_index(inplace=True)
    return geometries
