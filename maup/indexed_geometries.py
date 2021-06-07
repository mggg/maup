import pandas
from shapely.prepared import prep
from shapely.strtree import STRtree
from .progress_bar import progress


def get_geometries(geometries):
    return getattr(geometries, "geometry", geometries)


class IndexedGeometries:
    def __init__(self, geometries):
        self.geometries = get_geometries(geometries)
        geoms = list(self.geometries)
        for i, geometry in enumerate(geoms):
            geometry.index = i
        self.spatial_index = STRtree(geoms)
        self.index = self.geometries.index

    def query(self, geometry):
        relevant_indices = [geom.index for geom in self.spatial_index.query(geometry)]
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

