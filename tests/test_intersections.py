import geopandas
import pandas
import pytest

from maup.intersections import intersections


@pytest.fixture
def sources(squares_within_four_square_grid):
    return squares_within_four_square_grid


@pytest.fixture
def targets(four_square_grid):
    return four_square_grid


@pytest.fixture
def targets_with_str_index(targets):
    return targets.set_index("ID")


class TestIntersections:
    def test_returns_geoseries_with_multiindex(self, sources, targets):
        result = intersections(sources, targets)

        assert isinstance(result, geopandas.GeoSeries)
        assert isinstance(result.index, pandas.MultiIndex)

    def test_works_with_non_range_index(self, sources, targets_with_str_index):
        result = intersections(sources, targets_with_str_index)
        assert isinstance(result, geopandas.GeoSeries)
        assert isinstance(result.index, pandas.MultiIndex)

    def test_indexed_by_source_then_target(self, sources, targets_with_str_index):
        result = intersections(sources, targets_with_str_index)
        assert (result.index.levels[0] == sources.index).all()
        assert (result.index.levels[1] == targets_with_str_index.index).all()

    def test_expected_intersections(self, sources, targets_with_str_index):
        expected = manually_compute_intersections(sources, targets_with_str_index)
        result = intersections(sources, targets_with_str_index)
        assert (result == expected).all()

    def test_gives_expected_index(self, sources, targets_with_str_index):
        expected = manually_compute_intersections(sources, targets_with_str_index)
        result = intersections(sources, targets_with_str_index)
        they_match = result.index == expected.index
        assert they_match.all()

    def test_is_a_top_level_import(self):
        from maup import intersections

        assert intersections

    def test_can_use_area_cutoff(self, sources, targets):
        result = intersections(sources, targets, area_cutoff=0)
        assert (result.area > 0).all()

    def test_sets_crs(self, sources, targets):
        crs = sources.crs
        assert crs
        inters = intersections(sources, targets)
        assert inters.crs == crs


def manually_compute_intersections(sources, targets):
    records = []
    for i, source in sources.geometry.items():
        for j, target in targets.geometry.items():
            intersection = source.intersection(target)
            if not intersection.is_empty:
                records.append((i, j, intersection))

    expected = (
        geopandas.GeoDataFrame.from_records(
            records, columns=["source", "target", "geometry"]
        )
        .set_index(["source", "target"])
        .geometry
    )
    return expected
