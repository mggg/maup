import geopandas
import pandas

from .indexed_geometries import get_geometries


def get_geometries_with_range_index(geometries):
    gdf = geopandas.GeoDataFrame({"geometry": get_geometries(geometries)}).set_index(
        pandas.RangeIndex(len(geometries))
    )
    return gdf.geometry
