import warnings

from geopandas import GeoSeries, GeoDataFrame

from shapely import make_valid

from .indexed_geometries import IndexedGeometries, get_geometries
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


# Added option to output result as GeoDataFrame instead of GeoSeries
def adjacencies(
    geometries,
    output_type="geoseries",
    adjacency_type="rook",
    *,
    warn_for_overlaps=True,
    warn_for_islands=True
):
    """Returns adjacencies between geometries.
    The default return type is a
    `GeoSeries` with a `MultiIndex`, whose (i, j)th entry is the pairwise
    intersection between geometry `i` and geometry `j`. We ensure that
    `i < j` always holds, so that any adjacency is represented just once
    in the series.
    If output_type == "geodataframe", the return type is a range-indexed GeoDataFrame
    with a "neighbors" column containing the pair (i,j) for the geometry consisting
    of the intersection between geometry `i` and geometry `j`.

    """
    if adjacency_type not in ["rook", "queen"]:
        raise ValueError('adjacency_type must be "rook" or "queen"')

    geometries = get_geometries(geometries)
    geometries = make_valid(geometries)

    # Change here suggested by Hazel to handle the case where there are no adjacencies:
    adjs = list(iter_adjacencies(geometries))
    if adjs:
        index, geoms = zip(*adjs)
    else:
        index, geoms = [[], []]

    # Made a change here to add the GeoDataFrame option:
    if output_type == "geodataframe":
        inters = GeoDataFrame(
            {"neighbors": index, "geometry": geoms}, crs=geometries.crs
        )
    else:
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

    # Made a change here to accomodate the GeoDataFrame option:
    if warn_for_islands:
        if output_type == "geodataframe":
            islands = set(geometries.index) - set(
                i for pair in inters["neighbors"] for i in pair
            )
        else:
            islands = set(geometries.index) - set(
                i for pair in inters.index for i in pair
            )
        if len(islands) > 0:
            warnings.warn(
                "Found islands.\n" "Indices of islands: {}".format(islands),
                IslandWarning,
            )

    return inters
