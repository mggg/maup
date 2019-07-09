import pytest

from shapely.geometry.base import BaseGeometry

from maup.adjacencies import adjacencies, OverlapWarning, IslandWarning


class TestAdjacencies:
    def test_on_four_square_grid(self, four_square_grid):
        adjs = adjacencies(four_square_grid)
        assert set(adjs.index) == {(0, 1), (1, 3), (2, 3), (0, 2)}

    def test_queen_on_four_square_grid(self, four_square_grid):
        adjs = adjacencies(four_square_grid, "queen")
        assert set(adjs.index) == {(0, 1), (1, 3), (2, 3), (0, 2), (1, 2), (0, 3)}

    def test_raises_for_invalid_adj_type(self, four_square_grid):
        with pytest.raises(ValueError):
            adjacencies(four_square_grid, "knight")

    def test_warns_for_overlaps(self, squares_some_neat_some_overlapping):
        with pytest.warns(OverlapWarning):
            adjacencies(squares_some_neat_some_overlapping)

    def test_warns_for_islands(self, four_square_grid):
        with pytest.warns(IslandWarning):
            adjacencies(four_square_grid.loc[[0, 3]])

    def test_returns_geometries(self, four_square_grid):
        adjs = adjacencies(four_square_grid)
        assert len(adjs.length) == 4

        for geom in adjs:
            assert isinstance(geom, BaseGeometry)

    def test_sets_crs(self, four_square_grid):
        assert four_square_grid.crs

        adjs = adjacencies(four_square_grid)
        assert adjs.crs == four_square_grid.crs
