from maup.crs import require_same_crs
import pytest


def test_require_same_crs(square, four_square_grid):
    square.crs = "foo"
    four_square_grid.crs = "bar"

    @require_same_crs
    def f(sources, targets):
        raise RuntimeError("Something went wrong.")

    with pytest.raises(TypeError):
        f(square, four_square_grid)
