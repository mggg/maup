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
