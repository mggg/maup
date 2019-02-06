import geopandas
import numpy
import pytest

from spatial_ops import IntersectionMatrix, intersection_matrix
from spatial_ops.intersection_matrix import IntersectionMatrix


def test_intersection_matrix_returns_expected_matrix(four_square_grid, square):
    result = intersection_matrix(
        four_square_grid, geopandas.GeoSeries([square]), lambda x: x.area
    )

    assert numpy.asarray(result == numpy.array([[0.25, 0.25, 0.25, 0.25]])).all()


def test_raises_type_error_for_non_integer_indices(four_square_grid, square):
    with pytest.raises(TypeError):
        result = intersection_matrix(
            four_square_grid.set_index("ID"),
            geopandas.GeoSeries([square]),
            lambda x: x.area,
        )


def test_returns_a_series_with_same_index_as_targets(
    four_square_grid, square_mostly_in_top_left
):
    four_square_grid["data"] = [1, 1, 1, 1]

    matrix = IntersectionMatrix.from_geometries(
        four_square_grid, square_mostly_in_top_left, lambda x: x.area
    )
    result = matrix.interpolate(four_square_grid["data"])

    assert result.iloc[0] == 1 + 0.5 + 0.25 + 0.5


def test_works_when_indices_are_not_integers(
    four_square_grid, square_mostly_in_top_left
):
    four_square_grid["data"] = [1, 1, 1, 1]
    four_square_grid = four_square_grid.set_index("ID")

    matrix = IntersectionMatrix.from_geometries(
        four_square_grid, square_mostly_in_top_left, lambda x: x.area
    )
    result = matrix.interpolate(four_square_grid["data"])

    assert result.iloc[0] == 1 + 0.5 + 0.25 + 0.5


def test_returns_a_series_with_same_index_as_targets(
    four_square_grid, square_mostly_in_top_left
):
    four_square_grid["data"] = [1, 1, 1, 1]

    matrix = IntersectionMatrix.from_geometries(
        four_square_grid, square_mostly_in_top_left, lambda x: x.area
    )
    result = matrix.interpolate(four_square_grid["data"])

    assert result.iloc[0] == 1 + 0.5 + 0.25 + 0.5


def test_works_when_indices_are_not_integers(
    four_square_grid, square_mostly_in_top_left
):
    four_square_grid["data"] = [1, 1, 1, 1]
    four_square_grid = four_square_grid.set_index("ID")

    matrix = IntersectionMatrix.from_geometries(
        four_square_grid, square_mostly_in_top_left, lambda x: x.area
    )
    result = matrix.interpolate(four_square_grid["data"])

    assert result.iloc[0] == 1 + 0.5 + 0.25 + 0.5


def test_has_transpose_method():
    _matrix = numpy.matrix([[1, 1], [1, 0]])
    matrix = IntersectionMatrix(_matrix, sources_index=[1, 2], targets_index=["a", "b"])

    transposed = matrix.transpose()

    assert (transposed.matrix == _matrix.transpose()).all()
    assert transposed.targets_index == [1, 2]
    assert transposed.sources_index == ["a", "b"]


def test_raises_value_error_when_instantiated_with_mismatched_indices_and_matrix():
    _matrix = numpy.matrix([[1, 1], [1, 0]])

    with pytest.raises(ValueError):
        matrix = IntersectionMatrix(
            _matrix, sources_index=[1, 2, 3], targets_index=["a", "b", "c"]
        )


def test_raises_value_error_when_asked_to_interpolate_something_of_the_wrong_shape():
    _matrix = numpy.matrix([[1, 1], [1, 0]])
    matrix = IntersectionMatrix(_matrix, sources_index=[1, 2], targets_index=["a", "b"])

    with pytest.raises(ValueError):
        matrix.interpolate([1, 2, 3])
