import pandas

from geopandas import GeoSeries
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from .adjacencies import adjacencies
from .assign import assign_to_max
from .crs import require_same_crs
from .indexed_geometries import get_geometries
from .intersections import intersections


"""
These functions are based on the functions in Mary Barker's
check_shapefile_connectivity.py script in @gerrymandr/Preprocessing.
"""


def holes_of_union(geometries):
    """Returns any holes in the union of the given geometries."""
    geometries = get_geometries(geometries)
    if not all(
        isinstance(geometry, (Polygon, MultiPolygon)) for geometry in geometries
    ):
        raise TypeError("all geometries must be Polygons or MultiPolygons")

    union = unary_union(geometries)
    series = holes(union)
    series.crs = geometries.crs
    return series


def holes(geometry):
    if isinstance(geometry, MultiPolygon):
        return GeoSeries(
            [
                Polygon(list(hole.coords))
                for polygon in geometry.geoms
                for hole in polygon.interiors
            ]
        )
    elif isinstance(geometry, Polygon):
        return GeoSeries([Polygon(list(hole.coords)) for hole in geometry.interiors])
    else:
        raise TypeError("geometry must be a Polygon or MultiPolygon to have holes")


def close_gaps(geometries, relative_threshold=0.1):
    """Closes gaps between geometries by assigning the hole to the polygon
    that shares the most perimeter with the hole.

    If the area of the gap is greater than `relative_threshold` times the
    area of the polygon, then the gap is left alone. The default value
    of `relative_threshold` is 0.1. This is intended to preserve intentional
    gaps while closing the tiny gaps that can occur as artifacts of
    geospatial operations. Set `relative_threshold=None` to attempt close all
    gaps. Due to floating point precision issues, all gaps may not be closed.
    """
    geometries = get_geometries(geometries)
    gaps = holes_of_union(geometries)
    return absorb_by_shared_perimeter(
        gaps, geometries, relative_threshold=relative_threshold
    )


def resolve_overlaps(geometries, relative_threshold=0.1):
    """For any pair of overlapping geometries, assigns the overlapping area to the
    geometry that shares the most perimeter with the overlap. Returns the GeoSeries
    of geometries, which will have no overlaps.

    If the ratio of the overlap's area to either of the overlapping geometries'
    areas is greater than `relative_threshold`, then the overlap is ignored.
    The default `relative_threshold` is `0.1`. This default is chosen to include
    tiny overlaps that can be safely auto-fixed while preserving major overlaps
    that might indicate deeper issues and should be handled on a case-by-case
    basis. Set `relative_threshold=None` to attempt to resolve all overlaps. Due
    to floating point precision issues, all overlaps may not be resolved.
    """
    geometries = get_geometries(geometries)
    inters = adjacencies(geometries, warn_for_islands=False, warn_for_overlaps=False)
    overlaps = inters[inters.area > 0].buffer(0)

    if relative_threshold is not None:
        left_areas, right_areas = split_by_level(geometries.area, overlaps.index)
        under_threshold = ((overlaps.area / left_areas) < relative_threshold) & (
            (overlaps.area / right_areas) < relative_threshold
        )
        overlaps = overlaps[under_threshold]

    if len(overlaps) == 0:
        return geometries

    to_remove = GeoSeries(
        pandas.concat([overlaps.droplevel(1), overlaps.droplevel(0)]), crs=overlaps.crs
    )
    with_overlaps_removed = geometries.apply(lambda x: x.difference(unary_union(to_remove)))

    return absorb_by_shared_perimeter(
        overlaps, with_overlaps_removed, relative_threshold=None
    )


def split_by_level(series, multiindex):
    return tuple(
        multiindex.get_level_values(i).to_series(index=multiindex).map(series)
        for i in range(multiindex.nlevels)
    )


@require_same_crs
def absorb_by_shared_perimeter(sources, targets, relative_threshold=None):
    if len(sources) == 0:
        return targets

    if len(targets) == 0:
        raise IndexError("targets must be nonempty")

    inters = intersections(sources, targets, area_cutoff=None).buffer(0)
    assignment = assign_to_max(inters.length)

    if relative_threshold is not None:
        under_threshold = (
            sources.area / assignment.map(targets.area)
        ) < relative_threshold
        assignment = assignment[under_threshold]

    sources_to_absorb = GeoSeries(
        sources.groupby(assignment).apply(unary_union), crs=sources.crs,
    )

    result = targets.union(sources_to_absorb)

    # The .union call only returns the targets who had a corresponding
    # source to absorb. Now we fill in all of the unchanged targets.
    result = result.reindex(targets.index)
    did_not_absorb = result.isna() | result.is_empty
    result.loc[did_not_absorb] = targets[did_not_absorb]

    return result
