import pandas
import shapely.geometry
from shapely.prepared import prep
from shapely.strtree import STRtree


def get_geometries(geometries):
    return getattr(geometries, "geometry", geometries)


class Refinement:
    def __init__(self, geometries):
        self.geometries = get_geometries(geometries)
        for i, geometry in self.geometries.items():
            geometry.index = i
        self.spatial_index = STRtree(self.geometries)

    def query(self, geometry):
        relevant_indices = [geom.index for geom in self.spatial_index.query(geometry)]
        relevant_geometries = self.geometries.loc[relevant_indices]
        return relevant_geometries

    def __call__(self, geometry):
        relevant_geometries = self.query(geometry)
        intersections = relevant_geometries.intersection(geometry)
        return intersections[intersections.area > 0]

    def covered_by(self, container):
        relevant_geometries = self.query(container)
        prepared_container = prep(container)
        return relevant_geometries[relevant_geometries.apply(prepared_container.covers)]


def assign(source, target):
    source_geometries = get_geometries(source)
    target_geometries = get_geometries(target)
    refinement = Refinement(source_geometries)

    groups = [
        refinement.covered_by(container).apply(lambda x: target_index)
        for target_index, container in target_geometries.items()
    ]
    assignment = pandas.concat(groups).reindex(source_geometries.index)
    return assignment
