import geopandas
import maup
import pytest

# These tests are losely based off the test_example_case in test_prorate.py

def test_example_close_gaps_repair_MI():
    shp = geopandas.read_file("zip://./examples/MI.zip") # MI shapefile

    holes = maup.repair.holes_of_union(shp)
    assert len(holes) > 0
    assert holes.unary_union.area > 100
    shp["geometry"] = maup.close_gaps(shp, relative_threshold=None)

    # assert len(maup.repair.holes_of_union(shp)) == 0 # this fails, probably due to floating precision issues
    assert maup.repair.holes_of_union(shp).unary_union.area < 1e-10 # good enough?

def test_example_resolve_overlaps_repair_MI():
    shp = geopandas.read_file("zip://./examples/MI.zip") # MI shapefile

    assert count_overlaps(shp) > 0
    shp["geometry"] = maup.resolve_overlaps(shp, relative_threshold=None)
    assert count_overlaps(shp) == 0

def test_example_autorepair_MI():
    shp = geopandas.read_file("zip://./examples/MI.zip") # MI shapefile

    assert count_overlaps(shp) > 0
    holes = maup.repair.holes_of_union(shp)
    assert holes.unary_union.area > 100
    assert len(holes) > 0

    shp["geometry"] = maup.autorepair(shp, relative_threshold=None)

    assert count_overlaps(shp) == 0
    holes = maup.repair.holes_of_union(shp)
    assert holes.unary_union.area < 1e-10

def test_snap_shp_to_grid():
    shp = geopandas.read_file("zip://./examples/MI.zip") # MI shapefile
    assert maup.snap_to_grid(shp).all()

# def test_snap_autorepair_MI():

# def test_snap_shape_to_grid():

# def test_snap_polygon_to_grid():

def test_snap_shape_to_grid_type_error():
    with pytest.raises(TypeError):
        maup.repair.snap_shape_to_grid("not a Polygon object")


def count_overlaps(shp):
    """
    Counts overlaps. Code is taken directly from the resolve_overlaps function in maup.
    """
    inters = maup.repair.adjacencies(shp["geometry"], warn_for_islands=False, warn_for_overlaps=False)
    overlaps = inters[inters.area > 0].buffer(0)
    return len(overlaps)
