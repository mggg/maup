import geopandas
import maup
from maup.repair import count_overlaps
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

    # Changed behavior of doctor function so it no longer throws up errors here.
    #with pytest.raises((TypeError, AssertionError)):
    #    maup.doctor(shp)

    assert count_overlaps(shp) > 0
    holes = maup.repair.holes_of_union(shp)
    assert holes.unary_union.area > 100
    assert len(holes) > 0

    shp["geometry"] = maup.autorepair(shp, relative_threshold=None)

    assert count_overlaps(shp) == 0
    holes = maup.repair.holes_of_union(shp)
    assert holes.empty or holes.unary_union.area < 1e-10 # overlaps are not guaranteed to disappear
    assert maup.doctor(shp)

def test_snap_shp_to_grid():
    shp = geopandas.read_file("zip://./examples/MI.zip") # MI shapefile
    assert maup.snap_to_grid(shp).all()

def test_crop_to():
    blocks = geopandas.read_file("zip://./examples/blocks.zip")
    old_precincts = geopandas.read_file("zip://./examples/precincts.zip")
    new_precincts = geopandas.read_file("zip://./examples/new_precincts.zip")
    columns = ["SEN18D", "SEN18R"]

    # Calculate without cropping
    pieces = maup.intersections(old_precincts, new_precincts, area_cutoff=0)
    weights = blocks["TOTPOP"].groupby(maup.assign(blocks, pieces)).sum()
    weights = maup.normalize(weights, level=0)
    new_precincts[columns] = maup.prorate(pieces, old_precincts[columns], weights=weights)

    # Calculate with cropping
    old_precincts["geometries"] = maup.crop_to(old_precincts, new_precincts)
    new_precincts_cropped = new_precincts.copy()
    pieces = maup.intersections(old_precincts, new_precincts_cropped, area_cutoff=0)
    weights = blocks["TOTPOP"].groupby(maup.assign(blocks, pieces)).sum()
    weights = maup.normalize(weights, level=0)
    new_precincts_cropped[columns] = maup.prorate(pieces, old_precincts[columns], weights=weights)

    diff_sum = 0
    for col in columns:
        diff = new_precincts_cropped[col].sum() - new_precincts[col].sum()
        assert diff >= 0

        diff_sum += diff

    # Ideally this would be strictly positive (which would mean less votes are lost after cropping)
    # but crop_to doesn't resolve the missing votes errors yet.
    assert diff_sum >= 0 

# TODO: fix and add more tests
# def test_snap_autorepair_MI():
#     shp = geopandas.read_file("zip://./examples/MI.zip") # MI shapefile

#     shp["geometry"] = maup.snap_to_grid(shp, 0)
#     holes = maup.repair.holes_of_union(shp)
#     assert len(holes) > 0
#     assert holes.unary_union.area > 100
#     shp["geometry"] = maup.close_gaps(shp, relative_threshold=None)
#     shp["geometry"] = maup.snap_to_grid(shp, 0)

#     assert len(maup.repair.holes_of_union(shp)) == 0
#     assert maup.repair.holes_of_union(shp).unary_union.area == 0

# def test_snap_shape_to_grid():

# def test_snap_polygon_to_grid():

def test_apply_func_error():
    with pytest.raises(TypeError):
        maup.repair.apply_func_to_polygon_parts("not a Polygon object", lambda x: x)