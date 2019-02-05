from shapely.strtree import STRtree


class Refinement:
    def __init__(self, geometries):
        """
        :geometries: GeoSeries or GeoDataFrame of Polygons
        """
        self.geometries = getattr(geometries, "geometry", geometries)
        for i, geometry in zip(geometries.index, self.geometries):
            geometry.index = i
        self.spatial_index = STRtree(self.geometries)

    def query(self, geometry):
        relevant_indices = [geom.index for geom in self.spatial_index.query(geometry)]
        relevant_geometries = self.geometries.iloc[relevant_indices]
        return relevant_geometries

    def __call__(self, geometry):
        relevant_geometries = self.query(geometry)
        intersections = relevant_geometries.intersection(geometry)
        return intersections[intersections.area > 0]

    def contained_in(self, container):
        relevant_geometries = self.query(container)
        return relevant_geometries[relevant_geometries.apply(container.contains)]
