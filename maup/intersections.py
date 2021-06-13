import pandas
from geopandas import GeoDataFrame

from .crs import require_same_crs
from .indexed_geometries import IndexedGeometries
from .indices import get_geometries_with_range_index


@require_same_crs
def intersections(sources, targets, area_cutoff=None):
    """Computes all of the nonempty intersections between two sets of geometries.
    The returned `~geopandas.GeoSeries` will have a MultiIndex, where the geometry
    at index *(i, j)* is the intersection of ``sources[i]`` and ``targets[j]``
    (if it is not empty).

    :param sources: geometries
    :type sources: :class:`~geopandas.GeoSeries` or :class:`~geopandas.GeoDataFrame`
    :param targets: geometries
    :type targets: :class:`~geopandas.GeoSeries` or :class:`~geopandas.GeoDataFrame`
    :rtype: :class:`~geopandas.GeoSeries`
    :param area_cutoff: (optional) if provided, only return intersections with
        area greater than ``area_cutoff``
    :type area_cutoff: Number or None
    """
    reindexed_sources = get_geometries_with_range_index(sources)
    reindexed_targets = get_geometries_with_range_index(targets)
    spatially_indexed_sources = IndexedGeometries(reindexed_sources)

    records = [
        # Flip i, j to j, i so that the index is ["source", "target"]
        (sources.index[j], targets.index[i], geometry)
        for i, j, geometry in spatially_indexed_sources.enumerate_intersections(
            reindexed_targets
        )
    ]
    df = GeoDataFrame.from_records(records, columns=["source", "target", "geometry"])
    geometries = df.set_index(["source", "target"]).geometry
    geometries.sort_index(inplace=True)
    geometries.crs = sources.crs

    if area_cutoff is not None:
        geometries = geometries[geometries.area > area_cutoff]

    return geometries


def prorate(relationship, data, weights, aggregate_by="sum"):
    """
    Prorate data from one set of geometries to another, using their
    `~maup.intersections` or an assignment.

    :param relationship: the :func:`~maup.intersections` of the geometries you are
        getting data from (sources) and the geometries you are moving the data
        to; or, a series assigning sources to targets
    :type inters: :class:`geopandas.GeoSeries`
    :param data: the data you want to move (must be indexed the same as
        the source geometries)
    :type data: :class:`pandas.Series` or :class:`pandas.DataFrame`
    :param weights: the weights to use when prorating from ``sources`` to
        ``inters``
    :type weights: :class:`pandas.Series`
    :param function aggregate_by: (optional) the function to use for aggregating from
        ``inters`` to ``targets``. The default is ``"sum"``.
    """
    if relationship.index.nlevels > 1:
        source_assignment = relationship.index.get_level_values("source").to_series(
            index=relationship.index
        )
    else:
        source_assignment = relationship

    weights = weights.reindex_like(relationship)

    if isinstance(data, pandas.DataFrame):
        disagreggated = pandas.DataFrame(
            {
                column: source_assignment.map(data[column]) * weights
                for column in data.columns
            }
        )
    elif isinstance(data, pandas.Series):
        disagreggated = source_assignment.map(data) * weights
    else:
        raise TypeError("Data must be a Series or DataFrame")

    if isinstance(disagreggated.index, pandas.MultiIndex):
        aggregated = disagreggated.groupby(level="target").agg(aggregate_by)
    else:
        aggregated = disagreggated

    return aggregated
