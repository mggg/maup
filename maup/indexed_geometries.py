import pandas
import geopandas
# Added numpy import to handle output of STRtree query
import numpy
import warnings

from shapely.prepared import prep
from shapely.strtree import STRtree
from .progress_bar import progress


def get_geometries(geometries):
    if isinstance(geometries, geopandas.GeoDataFrame):
        return getattr(geometries, "geometry", geometries)
    return geometries


class IndexedGeometries:
    def __init__(self, geometries):
        self.geometries = get_geometries(geometries)
        self.spatial_index = STRtree(self.geometries)
        self.index = self.geometries.index


    def query(self, geometry):  
        # IMPORTANT: When "geometry" is multi-part, this query will return a
        # (2 x n) array instead of a (1 x n) array, so it's safest to flatten the query
        # output before proceeding.
        relevant_index_array = self.spatial_index.query(geometry)
        relevant_indices = [*set(numpy.ndarray.flatten(relevant_index_array))]
        relevant_geometries = self.geometries.iloc[relevant_indices]
        return relevant_geometries

    def intersections(self, geometry):  
        relevant_geometries = self.query(geometry)  
        intersections = relevant_geometries.intersection(geometry)
        return intersections[-(intersections.is_empty | intersections.isna())]

    def covered_by(self, container):   
        relevant_geometries = self.query(container)
        prepared_container = prep(container)

        if len(relevant_geometries) == 0:  # in case nothing is covered
            return relevant_geometries
        else:
            selected_geometries = relevant_geometries.apply(prepared_container.covers)
            return relevant_geometries[selected_geometries]

    def assign(self, targets):  
        target_geometries = get_geometries(targets)
        groups = [
            self.covered_by(container).apply(lambda x: container_index)
            for container_index, container in progress(
                target_geometries.items(), len(target_geometries)
            )
        ]
        if groups:
            groups = [group for group in groups if len(group) > 0]
            groups_concat = pandas.concat(groups)
            # No reindexing allowed with a non-unique Index,
            # so we need to find and remove repetitions.  (This only happens when the
            # targets have overlaps and some source is completely covered by more
            # than one target.)
            # Any that get removed here will be randomly assigned to one of the 
            # covering units at the assign_by_area step by maup.assign.
            groups_concat_index_list = list(groups_concat.index)
            seen = set()
            bad_indices = list(set([x for x in groups_concat_index_list if x in seen or seen.add(x)]))             
            if len(bad_indices)>0:
                groups_concat = groups_concat.drop(bad_indices)
            return groups_concat.reindex(self.index)
        else:
            return geopandas.GeoSeries()


    def enumerate_intersections(self, targets):
        target_geometries = get_geometries(targets)
        for i, target in progress(target_geometries.items(), len(target_geometries)):
            for j, intersection in self.intersections(target).items():
                yield i, j, intersection
