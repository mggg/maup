from numpy import nan
from pandas import MultiIndex

from spatial_ops import assign


def test_assign_assigns_geometries_when_they_nest_neatly(
    four_square_grid, squares_within_four_square_grid
):
    result = assign(squares_within_four_square_grid, four_square_grid)
    assert len(list(result)) == len(squares_within_four_square_grid)


def test_assign_returns_iterable(four_square_grid, squares_within_four_square_grid):
    result = assign(squares_within_four_square_grid, four_square_grid)
    assert iter(result)


def test_assignment_has_dtype_of_target_geom_index(
    four_square_grid, squares_within_four_square_grid
):
    target = four_square_grid.set_index("ID")

    result = assign(squares_within_four_square_grid, target)

    assert result.dtype == target.index.dtype


def test_assign_gives_expected_answer_when_geoms_nest_neatly(
    four_square_grid, squares_within_four_square_grid
):
    result = set(
        assign(
            squares_within_four_square_grid, four_square_grid.set_index("ID")
        ).items()
    )

    assert result == {(0, "a"), (1, "a"), (2, "b"), (3, "d")}


def test_assigns_na_to_geometries_not_fitting_into_any_others(
    left_half_of_square_grid, squares_within_four_square_grid
):
    result = set(
        assign(
            squares_within_four_square_grid, left_half_of_square_grid.set_index("ID")
        ).items()
    )

    assert result == {(0, "a"), (1, "a"), (2, "b"), (3, nan)}
