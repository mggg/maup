import warnings

from geopandas import GeoSeries

from .indexed_geometries import IndexedGeometries


class OverlapWarning(UserWarning):
    pass


def iter_adjacencies(geometries):
    indexed = IndexedGeometries(geometries)
    for i, geometry in indexed.geometries.items():
        possible = indexed.query(geometry)
        possible = possible[possible.index > i]
        inters = possible.intersection(geometry)
        inters = inters[-inters.is_empty]
        for j, inter in inters.items():
            yield (i, j), inter


def adjacencies(geometries, adjacency_type="rook", warn_for_overlaps=True):
    if adjacency_type not in ["rook", "queen"]:
        raise ValueError('adjacency_type must be "rook" or "queen"')

    index, geoms = zip(*iter_adjacencies(geometries))
    inters = GeoSeries(geoms, index=index)

    if adjacency_type == "rook":
        inters = inters[inters.length > 0]

    overlaps = inters[inters.area > 0]
    if warn_for_overlaps and len(overlaps) > 0:
        warnings.warn(
            "Found overlapping polygons while computing adjacencies.\n"
            "This could be evidence of topological problems.\n"
            "Indices of overlaps: {}".format(set(overlaps.index)),
            OverlapWarning,
        )

    return inters
