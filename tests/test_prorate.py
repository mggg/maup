import geopandas
import pandas
import pytest

from maup import assign, intersections, prorate, normalize


@pytest.fixture
def sources(four_square_grid):
    return four_square_grid


@pytest.fixture
def targets(square_mostly_in_top_left):
    return square_mostly_in_top_left


def test_prorate_gives_expected_value(sources, targets):
    pieces = intersections(sources, targets, area_cutoff=0)
    weights = pieces.area / pieces.index.get_level_values("source").to_series(
        index=pieces.index
    ).map(sources.area)
    prorated = prorate(pieces, sources.area, weights)
    assert (prorated == targets.area).all()


def test_prorate_dataframe(sources, targets):
    sources["data1"] = [10, 10, 10, 10]
    sources["data2"] = [10, 10, 10, 10]
    columns = ["data1", "data2"]

    pieces = intersections(sources, targets)

    weight_by = pieces.area / pieces.index.get_level_values("source").map(sources.area)

    # Use blocks to estimate population of each piece
    prorated = prorate(pieces, sources[columns], weight_by)

    assert (prorated["data1"] == 10 * targets.area).all()
    assert (prorated["data2"] == 10 * targets.area).all()


def test_prorate_dataframe_with_assignment(sources, targets):
    sources["data1"] = [10, 10, 10, 10]
    sources["data2"] = [10, 10, 10, 10]
    columns = ["data1", "data2"]

    relationship = pandas.Series({0: 0})
    weight_by = pandas.Series({0: 1})

    # Use blocks to estimate population of each piece
    prorated = prorate(relationship, sources[columns], weight_by)

    assert (prorated["data1"] == 10).all()
    assert (prorated["data2"] == 10).all()
    assert prorated.index == targets.index


def test_prorate_raises_if_data_is_not_dataframe_or_series(sources, targets):
    pieces = intersections(sources, targets)
    with pytest.raises(TypeError):
        prorate(
            pieces,
            "not a series",
            weights=pandas.Series([0] * len(pieces), index=pieces.index),
        )


def test_one_dimensional_intersections_dont_cause_error(sources):
    pieces = intersections(sources, sources.iloc[:2])
    weight_by = pieces.area / pieces.index.get_level_values("source").map(sources.area)
    prorated = prorate(pieces, sources.area, weight_by)
    assert (prorated == sources.iloc[:2].area).all()


def test_example_case():
    blocks = geopandas.read_file("zip://./examples/blocks.zip")
    old_precincts = geopandas.read_file("zip://./examples/precincts.zip")
    new_precincts = geopandas.read_file("zip://./examples/new_precincts.zip")
    columns = ["SEN18D", "SEN18R"]
    # Include area_cutoff=0 to ignore any intersections with no area,
    # like boundary intersections, which we do not want to include in
    # our proration.
    pieces = intersections(old_precincts, new_precincts, area_cutoff=0)
    # Weight by prorated population from blocks
    weights = blocks["TOTPOP"].groupby(assign(blocks, pieces)).sum()
    weights = normalize(weights, level=0)
    # Use blocks to estimate population of each piece
    new_precincts[columns] = prorate(pieces, old_precincts[columns], weights=weights)

    assert (new_precincts[columns] > 0).sum().sum() > len(new_precincts) / 2
    for col in columns:
        assert abs(new_precincts[col].sum() - old_precincts[col].sum()) / old_precincts[col].sum() < 0.1


def test_trivial_case(sources):
    sources["data1"] = [10, 10, 10, 10]
    sources["data2"] = [10, 10, 10, 10]
    columns = ["data1", "data2"]
    pieces = intersections(sources, sources, area_cutoff=0)
    weights = pandas.Series([1] * len(pieces), index=pieces.index)
    prorated = prorate(pieces, sources[columns], weights)
    assert (prorated == sources[columns]).all().all()
