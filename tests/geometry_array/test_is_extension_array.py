import pytest
from pandas.tests.extension import base

from spatial_ops.geometry_array import GeometryArray


class TestConstructors(base.BaseConstructorsTests):
    pass


def test_raises_if_passed_non_geometrydtype(data):
    with pytest.raises(TypeError):
        GeometryArray._from_sequence(data, dtype=int)
