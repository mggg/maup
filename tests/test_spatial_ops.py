from unittest.mock import patch

from geopandas import GeoSeries
from shapely import wkt

from spatial_ops import Refinement


def test_refinement_can_be_created_from_a_dataframe(four_square_grid):
    refinement = Refinement(four_square_grid)
    assert refinement


def test_refinement_is_callable(four_square_grid, square):
    refinement = Refinement(four_square_grid)
    assert callable(refinement)


def test_refinement_returns_overlaps_with_the_given_geometries(
    four_square_grid, square
):
    refinement = Refinement(four_square_grid)
    overlaps = refinement(square)
    assert len(overlaps) == len(four_square_grid)


def test_refinement_has_a_spatial_index(four_square_grid):
    refinement = Refinement(four_square_grid)
    assert hasattr(refinement, "spatial_index")


def test_refinement_queries_its_spatial_index_when_called(four_square_grid, square):
    with patch("spatial_ops.STRtree") as SpatialIndex:
        spatial_index = SpatialIndex.return_value
        refinement = Refinement(four_square_grid)
        overlaps = refinement(square)
        spatial_index.query.assert_called()


def test_refinement_correct_when_all_overlapping(four_square_grid, square):
    refinement = Refinement(four_square_grid)
    overlaps = refinement(square)

    expected_polygons = [
        wkt.loads(p)
        for p in [
            "POLYGON ((0.5 1, 1 1, 1 0.5, 0.5 0.5, 0.5 1))",
            "POLYGON ((1 1.5, 1 1, 0.5 1, 0.5 1.5, 1 1.5))",
            "POLYGON ((1 0.5, 1 1, 1.5 1, 1.5 0.5, 1 0.5))",
            "POLYGON ((1 1, 1 1.5, 1.5 1.5, 1.5 1, 1 1))",
        ]
    ]

    for p in expected_polygons:
        assert any(overlap == p for overlap in overlaps)

    for p in overlaps:
        assert any(p == expected for expected in expected_polygons)


def test_returns_empty_when_no_overlaps(four_square_grid, distant_polygon):
    refinement = Refinement(four_square_grid)
    assert len(refinement(distant_polygon)) == 0


def test_returns_empty_when_no_overlaps_but_bounds_overlap(
    diamond, polygon_inside_diamond_bounds
):
    refinement = Refinement(GeoSeries([diamond]))
    assert len(refinement(polygon_inside_diamond_bounds)) == 0
