from shapely.strtree import STRtree


class Refinement:
    def __init__(self, geometries):
        self.geometries = getattr(geometries, "geometry", geometries)
        for i, geometry in zip(geometries.index, self.geometries):
            geometry.index = i
        self.spatial_index = STRtree(self.geometries)

    def __call__(self, geometry):
        relevant_indices = [geom.index for geom in self.spatial_index.query(geometry)]
        relevant_geometries = self.geometries.iloc[relevant_indices]
        intersections = relevant_geometries.intersection(geometry)
        return intersections[intersections.area > 0]
