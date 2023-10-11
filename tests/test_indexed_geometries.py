import numpy as np
from unittest.mock import patch

from geopandas import GeoSeries
from shapely import wkt

from maup import IndexedGeometries


def test_indexed_can_be_created_from_a_dataframe(four_square_grid):
    indexed = IndexedGeometries(four_square_grid)
    assert indexed


def test_indexed_returns_overlaps_with_the_given_geometries(four_square_grid, square):
    indexed = IndexedGeometries(four_square_grid)
    overlaps = indexed.intersections(square)
    assert len(overlaps) == len(four_square_grid)


def test_indexed_has_a_spatial_index(four_square_grid):
    indexed = IndexedGeometries(four_square_grid)
    assert hasattr(indexed, "spatial_index")


def test_indexed_queries_its_spatial_index_when_intersections_is_called(
    four_square_grid, square
):
    with patch("maup.indexed_geometries.STRtree.query",) as query_fn:
        query_fn.return_value = np.array([])
        IndexedGeometries(four_square_grid).intersections(square)
        query_fn.assert_called()


def test_intersections_correct_when_all_overlapping(four_square_grid, square):
    indexed = IndexedGeometries(four_square_grid)
    overlaps = indexed.intersections(square)

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
        assert any(overlap.intersection(p).area == p.area for overlap in overlaps)

    for p in overlaps:
        assert any(p.intersection(expected).area == expected.area for expected in expected_polygons)


def test_returns_empty_when_no_overlaps(four_square_grid, distant_polygon):
    indexed = IndexedGeometries(four_square_grid)
    assert len(indexed.intersections(distant_polygon)) == 0


def test_returns_empty_when_no_overlaps_but_bounds_overlap(
    diamond, polygon_inside_diamond_bounds
):
    indexed = IndexedGeometries(GeoSeries([diamond]))
    assert len(indexed.intersections(polygon_inside_diamond_bounds)) == 0


def test_can_be_created_from_a_geoseries(four_square_grid):
    indexed = IndexedGeometries(four_square_grid.geometry)
    assert indexed


def test_covered_by_method_returns_empty_when_not_covered_by_any(
    four_square_grid, square
):
    indexed = IndexedGeometries(four_square_grid)
    covered = indexed.covered_by(square)
    assert len(covered) == 0
