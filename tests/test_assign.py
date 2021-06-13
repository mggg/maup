import geopandas
import pandas
from numpy import nan

from maup import assign
from maup.assign import assign_by_area, assign_by_covering


def test_assign_assigns_geometries_when_they_nest_neatly(
    four_square_grid, squares_within_four_square_grid
):

    result = assign_by_covering(squares_within_four_square_grid, four_square_grid)
    assert len(list(result)) == len(squares_within_four_square_grid)


def test_assign_returns_iterable(four_square_grid, squares_within_four_square_grid):
    result = assign_by_covering(squares_within_four_square_grid, four_square_grid)
    assert iter(result)


def test_assignment_has_dtype_of_target_geom_index(
    four_square_grid, squares_within_four_square_grid
):
    target = four_square_grid.set_index("ID")

    result = assign_by_covering(squares_within_four_square_grid, target)

    assert result.dtype == target.index.dtype


def test_assign_gives_expected_answer_when_geoms_nest_neatly(
    four_square_grid, squares_within_four_square_grid
):
    result = set(
        assign_by_covering(
            squares_within_four_square_grid, four_square_grid.set_index("ID")
        ).items()
    )

    assert result == {(0, "a"), (1, "a"), (2, "b"), (3, "d")}


def test_assigns_na_to_geometries_not_fitting_into_any_others(
    left_half_of_square_grid, squares_within_four_square_grid
):
    result = set(
        assign_by_covering(
            squares_within_four_square_grid, left_half_of_square_grid.set_index("ID")
        ).items()
    )

    assert result == {(0, "a"), (1, "a"), (2, "b"), (3, nan)}


def test_assign_can_be_used_with_groupby(four_square_grid, squares_df):
    assignment = assign_by_covering(squares_df, four_square_grid.set_index("ID"))

    result = squares_df.groupby(assignment)

    assert set(result.groups.keys()) == {"a", "b", "d"}
    assert set(result.indices["a"]) == {0, 1}
    assert set(result.indices["b"]) == {2}
    assert set(result.indices["d"]) == {3}


def test_assign_can_be_used_with_groupby_and_aggregate(four_square_grid, squares_df):
    assignment = assign_by_covering(squares_df, four_square_grid.set_index("ID"))

    result = squares_df.groupby(assignment)["data"].sum()

    expected = pandas.Series([2, 1, 1], index=["a", "b", "d"])
    assert (expected == result).all()


class TestAssignByArea:
    def test_gives_same_answer_for_integer_indices(self, four_square_grid, squares_df):
        assignment = assign_by_area(squares_df, four_square_grid)
        expected = assign_by_covering(squares_df, four_square_grid)
        assert (expected == assignment).all()

    def test_gives_same_answer_for_targets_with_non_integer_index(
        self, four_square_grid, squares_df
    ):
        targets = four_square_grid.set_index("ID")
        # targets = four_square_grid
        # sources = squares_df.set_index("ID")
        sources = squares_df
        assignment = assign_by_area(sources, targets)
        expected = assign_by_covering(sources, targets)
        assert (expected == assignment).all()

    def test_gives_same_answer_for_sources_with_non_integer_index(
        self, four_square_grid, squares_df
    ):
        targets = four_square_grid
        sources = squares_df.set_index("ID")
        assignment = assign_by_area(sources, targets)
        expected = assign_by_covering(sources, targets)
        assert (expected == assignment).all()

    def test_gives_same_answer_when_both_have_non_integer_indices(
        self, four_square_grid, squares_df
    ):
        targets = four_square_grid.set_index("ID")
        sources = squares_df.set_index("ID")
        assignment = assign_by_area(sources, targets)
        expected = assign_by_covering(sources, targets)
        assert (expected == assignment).all()

    def test_gives_expected_answer_when_sources_not_neatly_nested(
        self, four_square_grid, square_mostly_in_top_left
    ):
        assignment = assign_by_area(square_mostly_in_top_left, four_square_grid)
        expected = pandas.Series([1], index=[0])

        assert (expected == assignment).all()

    def test_assign_by_area_dispatches_to_non_integer_version(
        self, four_square_grid, squares_df
    ):
        targets = four_square_grid.set_index("ID")
        sources = squares_df.set_index("ID")
        assignment = assign_by_area(sources, targets)
        expected = assign_by_covering(sources, targets)
        assert (expected == assignment).all()


def test_assign_dispatches_to_without_area_and_with_area(
    four_square_grid, squares_some_neat_some_overlapping, crs
):
    other = four_square_grid.set_index("ID")
    other.crs = crs
    print(squares_some_neat_some_overlapping.crs, other.crs)
    assignment = assign(squares_some_neat_some_overlapping, other)
    expected = pandas.Series(
        ["a", "a", "b", "d", "b"], index=squares_some_neat_some_overlapping.index
    )

    assert (expected == assignment).all()

def test_example_case():
    # Losely based off test_example_case function in test_prorate.py
    blocks = geopandas.read_file("zip://./examples/blocks.zip")
    precincts = geopandas.read_file("zip://./examples/new_precincts.zip")
    columns = ["TOTPOP", "BVAP", "WVAP", "HISP"]
    assignment = assign(blocks, precincts)
    precincts[columns] = blocks[columns].groupby(assignment).sum()
    assert (precincts[columns] > 0).sum().sum() > len(precincts)
    for col in columns: # fails because it does not neatly cover
        assert abs(precincts[col].sum() - blocks[col].sum()) / blocks[col].sum() < 0.5
