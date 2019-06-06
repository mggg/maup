from itertools import product

import geopandas
import pytest
from shapely.geometry import Point, Polygon

from maup.repair import (
    close_gaps,
    holes,
    holes_of_union,
    absorb_by_shared_perimeter,
    resolve_overlaps,
    adjacencies,
)


def square_at(lower_left_corner, side_length=1):
    x, y = lower_left_corner
    coords = [
        (x, y),
        (x + side_length, y),
        (x + side_length, y + side_length),
        (x, y + side_length),
    ]
    return Polygon(coords)


class TestHoles:
    def test_single_geometry(self):
        hole_coords = [(25, 25), (75, 25), (75, 75), (25, 75)]
        geometry = Polygon(
            [(0, 0), (100, 0), (100, 100), (0, 100)], holes=[hole_coords]
        )
        result = holes_of_union(geopandas.GeoSeries([geometry]))
        assert len(result) == 1
        assert result[0] == Polygon(hole_coords)

    def test_multiple_geometries(self):
        # 000
        # 0 0
        # 000
        geometries = geopandas.GeoSeries(
            [
                square_at(point)
                for point in product([0, 1, 2], [0, 1, 2])
                if point != (1, 1)
            ]
        )
        result = holes_of_union(geometries)
        assert len(result) == 1
        assert result[0].equals(square_at((1, 1)))

    def test_multiple_holes_of_union(self):
        # 00000
        # 0 0 0
        # 00000
        geometries = geopandas.GeoSeries(
            [
                square_at(point)
                for point in product([0, 1, 2, 3, 4], [0, 1, 2])
                if point not in [(1, 1), (3, 1)]
            ]
        )
        result = holes_of_union(geometries)
        assert len(result) == 2
        squares = [square_at((1, 1)), square_at((3, 1))]
        assert (result[0].equals(squares[0]) and result[1].equals(squares[1])) or (
            result[1].equals(squares[0]) and result[0].equals(squares[1])
        )

    def test_multipolygon(self):
        # 000 000
        # 0 0 0 0
        # 000 000

        geometries = geopandas.GeoSeries(
            [
                square_at(point)
                for point in product([0, 1, 2], [0, 1, 2])
                if point != (1, 1)
            ]
            + [
                square_at(point)
                for point in product([4, 5, 6], [0, 1, 2])
                if point != (5, 1)
            ]
        )
        result = holes_of_union(geometries)
        assert len(result) == 2
        squares = [square_at((1, 1)), square_at((5, 1))]
        assert (result[0].equals(squares[0]) and result[1].equals(squares[1])) or (
            result[1].equals(squares[0]) and result[0].equals(squares[1])
        )

    def test_raises_for_non_polygons(self):
        has_a_point = geopandas.GeoSeries([Point((0, 0)), square_at((0, 0))])
        with pytest.raises(TypeError):
            holes_of_union(has_a_point)

    def test_holes_raises_for_non_polygon(self):
        with pytest.raises(TypeError):
            holes(Point(0, 0))


class TestFixGaps:
    def test_closes_gaps(self):
        # 001
        # 0 1
        # 001
        pacman = Polygon(
            [(0, 0), (0, 3), (2, 3), (2, 2), (1, 2), (1, 1), (2, 1), (2, 0)]
        )

        bar = Polygon([(2, 0), (2, 3), (3, 3), (3, 0)])

        geometries = geopandas.GeoSeries([pacman, bar])
        fixed = close_gaps(geometries, relative_threshold=None)
        assert fixed[1].equals(bar)
        assert fixed[0].equals(Polygon([(0, 0), (0, 3), (2, 3), (2, 0)]))

    def test_can_impose_relative_area_threshold(self):
        # 001
        # 0 1
        # 001
        pacman = Polygon(
            [(0, 0), (0, 3), (2, 3), (2, 2), (1, 2), (1, 1), (2, 1), (2, 0)]
        )

        bar = Polygon([(2, 0), (2, 3), (3, 3), (3, 0)])

        geometries = geopandas.GeoSeries([pacman, bar])
        fixed = close_gaps(geometries, relative_threshold=0.01)
        # Since the gap is more than 1% of the area, the gap is not closed
        assert fixed[1].equals(bar)
        assert fixed[0].equals(pacman)

        geometries = geopandas.GeoSeries([pacman, bar])
        fixed = close_gaps(geometries, relative_threshold=0.5)
        # Since the gap is less than 50% of the area, the gap is closed
        assert fixed[1].equals(bar)
        assert fixed[0].equals(Polygon([(0, 0), (0, 3), (2, 3), (2, 0)]))


class TestAbsorbBySharedPerimeters:
    def test_returns_targets_if_sources_empty(self):
        square1 = square_at((0, 0))
        square2 = square_at((1, 0))
        targets = geopandas.GeoSeries([square1, square2])
        sources = geopandas.GeoSeries()

        assert absorb_by_shared_perimeter(sources, targets) is targets

    def test_raises_error_if_targets_empty(self):
        square1 = square_at((0, 0))
        square2 = square_at((1, 0))
        sources = geopandas.GeoSeries([square1, square2])
        targets = geopandas.GeoSeries()

        with pytest.raises(IndexError):
            absorb_by_shared_perimeter(sources, targets)


class TestResolveOverlaps:
    def test_removes_overlaps(self):
        # 00x11
        # 00x11
        # 00x11
        square1 = square_at((0, 0), side_length=3)
        square2 = square_at((2, 0), side_length=3)
        geometries = geopandas.GeoSeries([square1, square2])
        result = resolve_overlaps(geometries, relative_threshold=None)

        inters = adjacencies(result)
        assert not (inters.area > 0).any()

    def test_returns_same_if_no_overlaps(self, four_square_grid):
        assert resolve_overlaps(four_square_grid) is four_square_grid.geometry

    def test_assigns_overlap_by_max_shared_perimeter(self):
        """The overlapping area should be assigned to the polygon that shares
        the most perimeter with the overlap.
        """
        # 000
        # 00x1
        # 00x1
        square1 = square_at((0, 0), side_length=3)
        square2 = square_at((2, 0), side_length=2)
        geometries = geopandas.GeoSeries([square1, square2])
        result = resolve_overlaps(geometries, relative_threshold=None)

        # Expected:
        # 000
        # 0001
        # 0001
        assert result[0].equals(square1)
        assert result[1].equals(Polygon([(3, 0), (3, 2), (4, 2), (4, 0)]))

    def test_threshold(self):
        # 000
        # 00x1
        # 00x1
        square1 = square_at((0, 0), side_length=3)
        square2 = square_at((2, 0), side_length=2)
        geometries = geopandas.GeoSeries([square1, square2])
        # This threshold is low enough that nothing should happen:
        result = resolve_overlaps(geometries, relative_threshold=0.0001)

        # Expected:
        # 000
        # 00x1
        # 00x1
        print(result)
        assert result[0].equals(square1)
        assert result[1].equals(square2)

    def test_threshold_rules_out_one_but_not_both(self):
        # 000
        # 00x1
        # 00x1
        square1 = square_at((0, 0), side_length=3)
        square2 = square_at((2, 0), side_length=2)
        geometries = geopandas.GeoSeries([square1, square2])

        # It's under threshold w.r.t square1 but not square 2
        result = resolve_overlaps(geometries, relative_threshold=0.4)

        # Expected:
        # 000
        # 00x1
        # 00x1
        assert result[0].equals(square1)
        assert result[1].equals(square2)
