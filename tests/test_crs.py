import geopandas as gpd
import pytest
from maup.crs import require_same_crs


def test_require_same_crs(square, four_square_grid):
    square_gdf = gpd.GeoDataFrame([{"geometry": square}], crs=4432)
    four_square_grid = four_square_grid.set_crs(4433, allow_override=True)

    @require_same_crs
    def f(sources, targets):
        raise RuntimeError("Something went wrong.")

    with pytest.raises(TypeError):
        f(square_gdf, four_square_grid)
