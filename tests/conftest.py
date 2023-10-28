import geopandas as gp
import pytest
from shapely.geometry import Polygon
import pandas as pd
import maup

CRS = "+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs"


@pytest.fixture
def crs():
    return CRS


@pytest.fixture
def four_square_grid():
    """
    b d
    a c
    """
    a = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    b = Polygon([(0, 1), (0, 2), (1, 2), (1, 1)])
    c = Polygon([(1, 0), (1, 1), (2, 1), (2, 0)])
    d = Polygon([(1, 1), (1, 2), (2, 2), (2, 1)])
    df = gp.GeoDataFrame(
        {"ID": ["a", "b", "c", "d"], "geometry": [a, b, c, d]}, crs=CRS
    )
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
        ],
        crs=CRS,
    )


@pytest.fixture
def left_half_of_square_grid(four_square_grid):
    return four_square_grid[four_square_grid["ID"].isin(["a", "b"])]


@pytest.fixture
def squares_df(squares_within_four_square_grid):
    return gp.GeoDataFrame(
        {
            "geometry": squares_within_four_square_grid,
            "data": [1, 1, 1, 1],
            "ID": ["01", "02", "03", "04"],
        },
        crs=CRS,
    )


@pytest.fixture
def square_mostly_in_top_left():
    return gp.GeoSeries([Polygon([(1.5, 0.5), (1.5, 2), (0, 2), (0, 0.5)])], crs=CRS)


@pytest.fixture
def squares_some_neat_some_overlapping(
    square_mostly_in_top_left, squares_within_four_square_grid
):
    result = pd.concat(
        [squares_within_four_square_grid, square_mostly_in_top_left],
        ignore_index=True,
    )
    result.crs = CRS
    return result


@pytest.fixture
def big_square():
    return gp.GeoSeries([Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])], crs=CRS)
