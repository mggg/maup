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


@pytest.fixture
def square():
    return Polygon([(0.5, 0.5), (0.5, 1.5), (1.5, 1.5), (1.5, 0.5)])


@pytest.fixture
def distant_polygon():
    return Polygon([(100, 101), (101, 101), (101, 100)])


@pytest.fixture
def diamond():
    return Polygon([(100, 0), (0, 100), (-100, 0), (0, -100)])


@pytest.fixture
def polygon_inside_diamond_bounds():
    return Polygon([(90, 90), (91, 90), (91, 91), (90, 91)])


@pytest.fixture
def squares_within_four_square_grid():
    return gp.GeoSeries(
        [
            # both fit inside a:
            Polygon([(0, 0), (0, 0.5), (0.5, 0.5), (0.5, 0)]),
            Polygon([(0.5, 0.5), (1, 0.5), (1, 1), (0.5, 1)]),
            # is exactly b:
            Polygon([(0, 1), (0, 2), (1, 2), (1, 1)]),
            # fits neatly inside d:
            Polygon([(1.25, 1.25), (1.25, 1.75), (1.75, 1.75), (1.75, 1.25)]),
        ]
    )


@pytest.fixture
def left_half_of_square_grid(four_square_grid):
    return four_square_grid[four_square_grid["ID"].isin(["a", "b"])]


@pytest.fixture
def squares_df(squares_within_four_square_grid):
    return gp.GeoDataFrame(
        {"geometry": squares_within_four_square_grid, "data": [1, 1, 1, 1]}
    )
