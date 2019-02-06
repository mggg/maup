import geopandas
import numpy
import pytest

from spatial_ops import intersection_matrix


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
