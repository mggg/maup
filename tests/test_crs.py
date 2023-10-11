import geopandas as gpd
import pytest
from maup.crs import require_same_crs


def test_require_same_crs(square, four_square_grid):
    square_gdf = gpd.GeoDataFrame([{"geometry": square}])
    square_gdf.crs = "epsg:4269"
    four_square_grid.crs = "epsg:4326"

    @require_same_crs
    def f(sources, targets):
        raise RuntimeError("Something went wrong.")

    with pytest.raises(TypeError):
        f(square_gdf, four_square_grid)
