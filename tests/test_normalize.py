import maup
import pandas


def test_normalize():
    index = pandas.MultiIndex.from_tuples(
        [(0, 1), (0, 2), (1, 2), (1, 3), (1, 4), (2, 4)]
    )
    weights = pandas.Series([10, 20, 25, 15, 0, 30], index=index)
    expected = pandas.Series([1 / 3, 2 / 3, 25 / 40, 15 / 40, 0, 1], index=index)
    assert (maup.normalize(weights) == expected).all(0)
