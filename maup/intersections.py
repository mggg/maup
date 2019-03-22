from geopandas import GeoDataFrame

from .indexed_geometries import IndexedGeometries
from .indices import get_geometries_with_range_index


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
