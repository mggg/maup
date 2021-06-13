import warnings

from geopandas import GeoSeries

from .indexed_geometries import IndexedGeometries
from .progress_bar import progress


class OverlapWarning(UserWarning):
    pass


class IslandWarning(UserWarning):
    pass


def iter_adjacencies(geometries):
    indexed = IndexedGeometries(geometries)
    for i, geometry in progress(indexed.geometries.items(), len(indexed.geometries)):
        possible = indexed.query(geometry)
        possible = possible[possible.index > i]
        inters = possible.intersection(geometry)
        inters = inters[-(inters.is_empty | inters.isna())]
        for j, inter in inters.items():
            yield (i, j), inter


def adjacencies(
    geometries, adjacency_type="rook", *, warn_for_overlaps=True, warn_for_islands=True
):
    """Returns adjacencies between geometries. The return type is a
    `GeoSeries` with a `MultiIndex`, whose (i, j)th entry is the pairwise
    intersection between geometry `i` and geometry `j`. We ensure that
    `i < j` always holds, so that any adjacency is represented just once
    in the series.
    """
    if adjacency_type not in ["rook", "queen"]:
        raise ValueError('adjacency_type must be "rook" or "queen"')

    index, geoms = zip(*iter_adjacencies(geometries))
    inters = GeoSeries(geoms, index=index, crs=geometries.crs)

    if adjacency_type == "rook":
        inters = inters[inters.length > 0]

    if warn_for_overlaps:
        overlaps = inters[inters.area > 0]
        if len(overlaps) > 0:
            warnings.warn(
                "Found overlapping polygons while computing adjacencies.\n"
                "This could be evidence of topological problems.\n"
                "Indices of overlaps: {}".format(set(overlaps.index)),
                OverlapWarning,
            )

    if warn_for_islands:
        islands = set(geometries.index) - set(i for pair in inters.index for i in pair)
        if len(islands) > 0:
            warnings.warn(
                "Found islands.\n" "Indices of islands: {}".format(islands),
                IslandWarning,
            )

    return inters
