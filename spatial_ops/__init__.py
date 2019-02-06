import geopandas
import numpy
import pandas
import scipy.sparse
import shapely.geometry
from shapely.prepared import prep
from shapely.strtree import STRtree


def get_geometries(geometries):
    return getattr(geometries, "geometry", geometries)


class IndexedGeometries:
    def __init__(self, geometries):
        self.geometries = get_geometries(geometries)
        for i, geometry in self.geometries.items():
            geometry.index = i
        self.spatial_index = STRtree(self.geometries)
        self.index = self.geometries.index

    def query(self, geometry):
        relevant_indices = [geom.index for geom in self.spatial_index.query(geometry)]
        relevant_geometries = self.geometries.loc[relevant_indices]
        return relevant_geometries

    def intersections(self, geometry):
        relevant_geometries = self.query(geometry)
        intersections = relevant_geometries.intersection(geometry)
        return intersections[intersections.is_empty == False]

    def covered_by(self, container):
        relevant_geometries = self.query(container)
        prepared_container = prep(container)
        return relevant_geometries[relevant_geometries.apply(prepared_container.covers)]

    def assign(self, target):
        target_geometries = get_geometries(target)
        groups = [
            self.covered_by(container).apply(lambda x: container_index)
            for container_index, container in target_geometries.items()
        ]
        assignment = pandas.concat(groups).reindex(self.index)
        return assignment

    def iter_intersections(self, targets):
        target_geometries = get_geometries(targets)
        for j, target in target_geometries.items():
            for i, intersection in self.intersections(target).items():
                yield i, j, intersection


def assign(sources, targets):
    indexed_sources = IndexedGeometries(sources)
    return indexed_sources.assign(targets)


def intersection_matrix(sources, targets, weight_by):
    if not (sources.index.is_numeric() and targets.index.is_numeric()):
        raise TypeError(
            "Sources and targets must have integer indices "
            "(see http://pandas.pydata.org/pandas-docs/stable/"
            "getting_started/basics.html#basics-reindexing for more information)"
        )
    indexed_sources = IndexedGeometries(sources)
    matrix = scipy.sparse.dok_matrix((len(sources), len(targets)))

    for (i, j, intersection) in indexed_sources.iter_intersections(targets):
        matrix[i, j] = weight_by(intersection)
    return matrix


def assign_by_area(sources, targets):
    if not (sources.index.is_numeric() and targets.index.is_numeric()):
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
