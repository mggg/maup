import geopandas as gp
import pytest
from shapely.geometry import Polygon


@pytest.fixture
def four_square_grid():
    a = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    b = Polygon([(0, 1), (0, 2), (1, 2), (1, 1)])
    c = Polygon([(1, 0), (1, 1), (2, 1), (2, 0)])
    d = Polygon([(1, 1), (1, 2), (2, 2), (2, 1)])
    df = gp.GeoDataFrame({"ID": ["a", "b", "c", "d"], "geometry": [a, b, c, d]})
    df.crs = "+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs"
    return df
