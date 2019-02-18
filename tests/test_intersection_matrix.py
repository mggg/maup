import geopandas
import numpy
import pandas
import pytest

from spatial_ops import InterpolationMatrix
from spatial_ops.intersection_matrix import intersection_matrix, intersections


def test_intersection_matrix_returns_expected_matrix(four_square_grid, square):
    result = intersection_matrix(
        four_square_grid, geopandas.GeoSeries([square]), lambda x, i, j: x.area
    )

    assert numpy.asarray(result == numpy.array([[0.25, 0.25, 0.25, 0.25]])).all()


def test_raises_type_error_for_non_integer_indices(four_square_grid, square):
    with pytest.raises(TypeError):
        intersection_matrix(
            four_square_grid.set_index("ID"),
            geopandas.GeoSeries([square]),
            lambda x, i, j: x.area,
        )


def test_returns_a_series_with_same_index_as_targets(
    four_square_grid, square_mostly_in_top_left
):
    four_square_grid["data"] = [1, 1, 1, 1]

    matrix = InterpolationMatrix.from_geometries(
        four_square_grid, square_mostly_in_top_left, lambda x, i, j: x.area
    )
    result = matrix.interpolate(four_square_grid["data"])

    assert result.index == square_mostly_in_top_left.index


def test_works_when_source_indices_are_not_integers(
    four_square_grid, square_mostly_in_top_left
):
    four_square_grid["data"] = [1, 1, 1, 1]
    four_square_grid = four_square_grid.set_index("ID")

    matrix = InterpolationMatrix.from_geometries(
        four_square_grid, square_mostly_in_top_left, lambda x, i, j: x.area
    )
    result = matrix.interpolate(four_square_grid["data"])

    assert result.iloc[0] == 1 + 0.5 + 0.25 + 0.5


def test_works_when_target_indices_are_not_integers(
    four_square_grid, square_mostly_in_top_left
):
    four_square_grid["data"] = [1, 1, 1, 1]
    square_mostly_in_top_left = (
        geopandas.GeoDataFrame({"geometry": square_mostly_in_top_left, "ID": ["a"]})
        .set_index("ID")
        .geometry
    )

    matrix = InterpolationMatrix.from_geometries(
        four_square_grid, square_mostly_in_top_left, lambda x, i, j: x.area
    )
    result = matrix.interpolate(four_square_grid["data"])

    assert result.loc["a"] == 1 + 0.5 + 0.25 + 0.5


def test_has_transpose_method():
    _matrix = numpy.matrix([[1, 1], [1, 0]])
    matrix = InterpolationMatrix(
        _matrix, sources_index=[1, 2], targets_index=["a", "b"]
    )

    transposed = matrix.transpose()

    assert (transposed.matrix == _matrix.transpose()).all()
    assert transposed.targets_index == [1, 2]
    assert transposed.sources_index == ["a", "b"]


def test_raises_value_error_when_instantiated_with_mismatched_indices_and_matrix():
    _matrix = numpy.matrix([[1, 1], [1, 0]])

    with pytest.raises(ValueError):
        InterpolationMatrix(
            _matrix, sources_index=[1, 2, 3], targets_index=["a", "b", "c"]
        )


def test_raises_value_error_when_asked_to_interpolate_something_of_the_wrong_shape():
    _matrix = numpy.matrix([[1, 1], [1, 0]])
    matrix = InterpolationMatrix(
        _matrix, sources_index=[1, 2], targets_index=["a", "b"]
    )

    with pytest.raises(ValueError):
        matrix.interpolate([1, 2, 3])


def test_raises_error_when_interpolating_non_numerical_column():
    _matrix = numpy.matrix([[1, 1], [1, 0]])
    matrix = InterpolationMatrix(
        _matrix, sources_index=[1, 2], targets_index=["a", "b"]
    )

    with pytest.raises(ValueError):
        matrix.interpolate(["x", "y"])


def test_can_tell_whether_it_preserves_mass():
    _matrix = numpy.matrix([[1, 1], [1, 0]])
    matrix = InterpolationMatrix(
        _matrix, sources_index=[1, 2], targets_index=["a", "b"]
    )

    assert not matrix.preserves_mass()

    _matrix = numpy.matrix([[0.5, 0.5], [0.5, 0.5]])
    matrix = InterpolationMatrix(
        _matrix, sources_index=[1, 2], targets_index=["a", "b"]
    )

    assert matrix.preserves_mass()


def test_must_normalize_area_to_preserve_mass(four_square_grid, big_square):
    matrix = InterpolationMatrix.from_geometries(
        four_square_grid, big_square, lambda x, i, j: x.area / big_square.iloc[i].area
    )

    assert matrix.preserves_mass()


def test_can_normalize_so_that_it_preserves_mass():
    _matrix = numpy.matrix([[1, 1], [1, 0]])
    matrix = InterpolationMatrix(
        _matrix, sources_index=[1, 2], targets_index=["a", "b"]
    )

    assert not matrix.preserves_mass()

    normalized = matrix.normalize()

    assert normalized.preserves_mass()


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
