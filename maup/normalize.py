from pandas import Series


def normalize(weights, level=0):
    """Takes a series of MultiIndexed weights and normalizes them with
    respect to one level (level 0 by default)."""
    source_assignment = Series(
        weights.index.get_level_values(level), index=weights.index
    )
    denominators = source_assignment.map(weights.groupby(source_assignment).sum())
    return (weights / denominators).fillna(0)
