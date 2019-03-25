import pytest
from maup import prorate, intersections


@pytest.fixture
def sources(four_square_grid):
    return four_square_grid


@pytest.fixture
def targets(square_mostly_in_top_left):
    return square_mostly_in_top_left


def test_prorate_gives_expected_value(sources, targets):
    pieces = intersections(sources, targets)
    pieces = pieces[pieces.area > 0]
    weight_by = pieces.area / pieces.index.get_level_values("source").map(sources.area)
    prorated = prorate(pieces, sources.area, weight_by)
    assert (prorated == targets.area).all()


def test_prorate_dataframe(sources, targets):
    sources["data1"] = [10, 10, 10, 10]
    sources["data2"] = [10, 10, 10, 10]
    columns = ["data1", "data2"]

    pieces = intersections(sources, targets)

    # Weight by prorated population from blocks
    weight_by = pieces.area / pieces.index.get_level_values("source").map(sources.area)

    # Use blocks to estimate population of each piece
    prorated = prorate(pieces, sources[columns], weight_by)

    assert (prorated["data1"] == 10 * targets.area).all()
    assert (prorated["data2"] == 10 * targets.area).all()


def test_prorate_raises_if_data_is_not_dataframe_or_series(sources, targets):
    pieces = intersections(sources, targets)
    with pytest.raises(TypeError):
        prorate(pieces, "not a series", [])
