import pandas
from shapely.prepared import prep
from shapely.strtree import STRtree
from shapely.geometry import mapping
from .progress_bar import progress


def get_geometries(geometries):
    return getattr(geometries, "geometry", geometries)

def hash_geom(geom):
    return hash(tuple(mapping(geom)['coordinates']))


class IndexedGeometries:
    def __init__(self, geometries):
        self.geometries = get_geometries(geometries)
        self._index = {}
        for i, geometry in self.geometries.items():
            self._index[hash_geom(geometry)] = i
        self.spatial_index = STRtree(self.geometries)
        self.index = self.geometries.index

    def query(self, geometry):
        relevant_indices = [self._index[hash_geom(geom)] for geom in self.spatial_index.query(geometry)]
        relevant_geometries = self.geometries.loc[relevant_indices]
        return relevant_geometries

    def intersections(self, geometry):
        relevant_geometries = self.query(geometry)
        intersections = relevant_geometries.intersection(geometry)
        return intersections[-(intersections.is_empty | intersections.isna())]

    def covered_by(self, container):
        relevant_geometries = self.query(container)
        prepared_container = prep(container)
        return relevant_geometries[relevant_geometries.apply(prepared_container.covers)]

    def assign(self, targets):
        target_geometries = get_geometries(targets)
        groups = [
            self.covered_by(container).apply(lambda x: container_index)
            for container_index, container in progress(
                target_geometries.items(), len(target_geometries)
            )
        ]
        assignment = pandas.concat(groups).reindex(self.index)
        return assignment

    def enumerate_intersections(self, targets):
        target_geometries = get_geometries(targets)
        for i, target in progress(target_geometries.items(), len(target_geometries)):
            for j, intersection in self.intersections(target).items():
                yield i, j, intersection

