import functools
import warnings

import pandas

from geopandas import GeoSeries
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection
from shapely.ops import unary_union

from .adjacencies import adjacencies
from .assign import assign_to_max
from .crs import require_same_crs
from .indexed_geometries import get_geometries
from .intersections import intersections


"""
Some of these functions are based on the functions in Mary Barker's
check_shapefile_connectivity.py script in @gerrymandr/Preprocessing.
"""

# IMPORTANT TO BE AWARE OF FOR FUTURE UPDATES:
# A previous version of this file used buffer(0) to simplify geometries, but this only
# works properly for polygons.  For 1-D objects such as LineStrings, it kills them off
# completely - and this resulted in some pretty disastrous choices in the
# absorb_by_shared_perimeter function when ALL the perimeters simplified to zero and
# the choice of which geometry to absorb into was essentially random!
# In this version, buffer(0) has been replaced by Shapely 2.0's make_valid function,
# which is MUCH better behaved - EXCEPT that when applied to a GeoSeries via
# geoseries = make_valid(geoseries)
# it apparently removes the CRS - which then creates problems for functions that use
# @require_same_crs.
# Note that it appears to work correctly if we use the format
# geoseries = geoseries.make_valid()


class AreaCroppingWarning(UserWarning):
    pass


def make_valid_polygons(geometries, force_polygons=True):
    """Extended make valid function with optional filter for non polygonal
    data from the output."""
    geometries = geometries.make_valid()
    if force_polygons:
        # Map function causes CRS information to be dropped.
        crs = geometries.crs
        geometries = geometries.map(trim_valid)
        if crs is not None:
            geometries = geometries.set_crs(crs)
    return geometries


def trim_valid(value):
    """Ensures that the results from the "make_valid_polygons" method won't be
    geometry collections with mixed types by filtering out non-polygons.
    """
    if isinstance(value, GeometryCollection):
        # List comprehension excluding non-Polygons
        value = [item for item in value.geoms
                 if isinstance(item, (Polygon, MultiPolygon))]
        # Re-aggregegating multiple Polygons into single MultiPolygon object.
        value = value[0] if len(value) == 1 else MultiPolygon(value)
    return value


def holes_of_union(geometries):
    """Returns any holes in the union of the given geometries."""
    geometries = get_geometries(geometries)
    if not all(
        isinstance(geometry, (Polygon, MultiPolygon)) for geometry in geometries
    ):
        raise TypeError(f"Must be a Polygon or MultiPolygon (got types {set([x.geom_type for x in geometries])})!")

    union = unary_union(geometries)
    series = holes(union)
    series.crs = geometries.crs
    return series


def holes(geometry):
    """Returns any holes in a Polygon or MultiPolygon."""
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


def close_gaps(geometries, relative_threshold=0.1, force_polygons=False):
    """Closes gaps between geometries by assigning the hole to the polygon
    that shares the greatest perimeter with the hole.

    If the area of the gap is greater than `relative_threshold` times the
    area of the polygon, then the gap is left alone. The default value
    of `relative_threshold` is 0.1. This is intended to preserve intentional
    gaps while closing the tiny gaps that can occur as artifacts of
    geospatial operations. Set `relative_threshold=None` to attempt close all
    gaps. Due to floating point precision issues, all gaps may not be closed.

    Optional "force_polygons" argument included to apply an automatic filter
    non-polygonal fragments during operation.
    """
    geometries = get_geometries(geometries)
    gaps = holes_of_union(geometries)
    return absorb_by_shared_perimeter(
        gaps, geometries, relative_threshold=relative_threshold, force_polygons=force_polygons
    )


def resolve_overlaps(geometries, relative_threshold=0.1, force_polygons=False):
    """For any pair of overlapping geometries, assigns the overlapping area to the
    geometry that shares the greatest perimeter with the overlap. Returns the GeoSeries
    of geometries, which will have no overlaps.

    If the ratio of the overlap's area to either of the overlapping geometries'
    areas is greater than `relative_threshold`, then the overlap is ignored.
    The default `relative_threshold` is `0.1`. This default is chosen to include
    tiny overlaps that can be safely auto-fixed while preserving major overlaps
    that might indicate deeper issues and should be handled on a case-by-case
    basis. Set `relative_threshold=None` to attempt to resolve all overlaps. Due
    to floating point precision issues, all overlaps may not be resolved.

    Optional "force_polygons" argument included to apply an automatic filter
    non-polygonal fragments during operation.
    """
    geometries = get_geometries(geometries)
    inters = adjacencies(geometries, warn_for_islands=False, warn_for_overlaps=False)
    if force_polygons:
        overlaps = make_valid_polygons(inters[inters.area > 0])
    else:
        overlaps = inters[inters.area > 0].make_valid()

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
        overlaps, with_overlaps_removed, relative_threshold=None, force_polygons=force_polygons
    )


def quick_repair(geometries, relative_threshold=0.1, force_polygons=False):
    """
    New name for autorepair function from Maup 1.x.
    Uses simplistic algorithms to repair most gaps and overlaps.

    The default `relative_threshold` is `0.1`. This default is chosen to include
    tiny overlaps that can be safely auto-fixed while preserving major overlaps
    that might indicate deeper issues and should be handled on a case-by-case
    basis. Set `relative_threshold=None` to attempt to resolve all overlaps. See
    `resolve_overlaps()` and `close_gaps()` for more.

    For a more careful repair that takes adjacencies and higher-order overlaps
    between geometries into account, consider using smart_repair instead.
    """
    return autorepair(geometries, relative_threshold=relative_threshold, force_polygons=force_polygons)


def autorepair(geometries, relative_threshold=0.1, force_polygons=False):
    """
    Uses simplistic algorithms to repair most gaps and overlaps. Additional
    optional argument provided that can drop any fragmented line segments that
    may occur while using shapely's make valid function. Should work by default.

    The default `relative_threshold` is `0.1`. This default is chosen to include
    tiny overlaps that can be safely auto-fixed while preserving major overlaps
    that might indicate deeper issues and should be handled on a case-by-case
    basis. Set `relative_threshold=None` to attempt to resolve all overlaps. See
    `resolve_overlaps()` and `close_gaps()` for more.

    For a more careful repair that takes adjacencies and higher-order overlaps
    between geometries into account, consider using smart_repair instead.
    """
    geometries = get_geometries(geometries)

    if force_polygons:
        geometries = make_valid_polygons(remove_repeated_vertices(geometries))
        geometries = make_valid_polygons(resolve_overlaps(geometries,
                                                          relative_threshold=relative_threshold,
                                                          force_polygons=force_polygons))
        geometries = make_valid_polygons(close_gaps(geometries,
                                                    relative_threshold=relative_threshold,
                                                    force_polygons=force_polygons))
    else:
        geometries = remove_repeated_vertices(geometries).make_valid()
        geometries = resolve_overlaps(geometries, relative_threshold=relative_threshold).make_valid()
        geometries = close_gaps(geometries, relative_threshold=relative_threshold).make_valid()

    return geometries


def remove_repeated_vertices(geometries):
    """
    Removes repeated vertices. Vertices are considered to be repeated if they
    appear consecutively, excluding the start and end points.
    """
    return geometries.geometry.apply(lambda x: apply_func_to_polygon_parts(x, dedup_vertices))


def snap_to_grid(geometries, n=-7):
    """
    Snap the geometries to a grid by rounding to the nearest 10^n. Helps to
    resolve floating point precision issues in shapefiles.
    """
    func = functools.partial(snap_polygon_to_grid, n=n)
    return geometries.geometry.apply(lambda x: apply_func_to_polygon_parts(x, func))


@require_same_crs
def crop_to(source, target):
    """
    Crops the source geometries to the target geometries.
    """
    target_union = unary_union(get_geometries(target))
    cropped_geometries = get_geometries(source).apply(lambda x: x.intersection(target_union))

    if (cropped_geometries.area == 0).any():
        warnings.warn("Some cropped geometries have zero area, likely due to\n" +
                      "large differences in the union of the geometries in your\n" +
                      "source and target shapefiles. This may become an issue\n" +
                      "when maupping.\n",
                      AreaCroppingWarning
                      )

    return cropped_geometries


@require_same_crs
def expand_to(source, target, force_polygons=False):
    """
    Expands the source geometries to the target geometries.
    """

    if force_polygons:
        geometries = make_valid_polygons(get_geometries(source))
    else:
        geometries = get_geometries(source).make_valid()

    source_union = unary_union(geometries)

    leftover_geometries = get_geometries(target).apply(lambda x: x - source_union)
    leftover_geometries = leftover_geometries[~leftover_geometries.is_empty].explode(index_parts=False)

    geometries = absorb_by_shared_perimeter(
        leftover_geometries, get_geometries(source), relative_threshold=None, force_polygons=force_polygons
    )

    return geometries


def doctor(source, target=None, silent=False, accept_holes=False):
    """
    Detects quality issues in a given set of source and target geometries. Quality
    issues include overlaps, gaps, invalid geometries, non-perfect
    tiling, and not entirely overlapping source and targets. If `maup.doctor()` returns
    `True`, votes should not be lost when prorating or assigning (beyond a few due to
    rounding, etc.). Passing a target to doctor is optional.

    If silent is True, then print outputs are suppressed. (Default is silent = False.)

    If accept_holes is True, then holes alone do not cause doctor to return a value of
    False. (Default is accept_holes = False.)
    """
    shapefiles = [source]
    source_union = unary_union(get_geometries(source))

    health_check = True

    if target is not None:
        shapefiles.append(target)

        target_union = unary_union(get_geometries(target))
        sym_area = target_union.symmetric_difference(source_union).area

        if sym_area != 0:
            if silent is False:
                print("The unions of target and source differ!")
            health_check = False

    for shp in shapefiles:
        if not shp.geometry.apply(lambda x: isinstance(x, (Polygon, MultiPolygon))).all():
            if silent is False:
                print("Some rows do not have geometries.")
            health_check = False

        overlaps = count_overlaps(shp)
        num_holes = len(holes_of_union(shp))

        if overlaps != 0:
            if silent is False:
                print("There are", overlaps, "overlaps.")
            health_check = False
        if num_holes != 0:
            if silent is False:
                print("There are", num_holes, "holes.")
            if accept_holes is False:
                health_check = False
        if not shp.is_valid.all():
            if silent is False:
                print("There are some invalid geometries.")
            health_check = False

    return health_check


def count_overlaps(shp):
    """
    Counts overlaps between geometries.
    Code is taken directly from the resolve_overlaps function in maup.
    """
    inters = adjacencies(shp.geometry, warn_for_islands=False, warn_for_overlaps=False)
    overlaps = inters[inters.area > 0].make_valid()
    return len(overlaps)


def count_holes(shp):
    """
    Counts gaps between geometries.
    """
    gaps = holes_of_union(shp.geometry)
    return len(gaps)


def apply_func_to_polygon_parts(shape, func):
    if isinstance(shape, Polygon):
        return func(shape)
    elif isinstance(shape, MultiPolygon):
        return MultiPolygon([func(poly) for poly in shape.geoms])
    else:
        raise TypeError(f"Can only apply {func} to a Polygon or MultiPolygon (got {shape} with type {type(shape)})!")


def dedup_vertices(polygon):
    if len(polygon.interiors) == 0:
        deduped_vertices = []
        for c, p in enumerate(list(polygon.exterior.coords)):
            if c == 0:
                deduped_vertices.append(p)
            elif p != deduped_vertices[-1]:
                deduped_vertices.append(p)
        return Polygon(deduped_vertices)

    else:
        deduped_vertices_exterior = []
        for c, p in enumerate(list(polygon.exterior.coords)):
            if c == 0:
                deduped_vertices_exterior.append(p)
            elif p != deduped_vertices_exterior[-1]:
                deduped_vertices_exterior.append(p)

        deduped_vertices_interiors = []
        for interior_ring in polygon.interiors:
            deduped_vertices_this_ring = []
            for c, p in enumerate(list(interior_ring.coords)):
                if c == 0:
                    deduped_vertices_this_ring.append(p)
                elif p != deduped_vertices_this_ring[-1]:
                    deduped_vertices_this_ring.append(p)
            deduped_vertices_interiors.append(deduped_vertices_this_ring)
        return Polygon(deduped_vertices_exterior, holes=deduped_vertices_interiors)


def snap_polygon_to_grid(polygon, n=-7):
    if len(polygon.interiors) == 0:
        return Polygon([(round(x, -n), round(y, -n)) for x, y in polygon.exterior.coords])
    else:
        return Polygon([(round(x, -n), round(y, -n)) for x, y in polygon.exterior.coords], holes=[[(round(x, -n), round(y, -n)) for x, y in interior_ring.coords] for interior_ring in polygon.interiors])


def snap_multilinestring_to_grid(multilinestring, n=-7):
    if multilinestring.geom_type == "LineString":
        return LineString([(round(x, -n), round(y, -n)) for x, y in multilinestring.coords])
    elif multilinestring.geom_type == "MultiLineString":
        return MultiLineString([LineString([(round(x, -n), round(y, -n)) for x, y in linestring.coords]) for linestring in multilinestring.geoms])


def split_by_level(series, multiindex):
    return tuple(
        multiindex.get_level_values(i).to_series(index=multiindex).map(series)
        for i in range(multiindex.nlevels)
    )


@require_same_crs
def absorb_by_shared_perimeter(sources, targets, relative_threshold=None, force_polygons=False):
    if len(sources) == 0:
        return targets

    if len(targets) == 0:
        raise IndexError("targets must be nonempty")

    if force_polygons:
        inters = make_valid_polygons(intersections(sources, targets, area_cutoff=None))
    else:
        inters = intersections(sources, targets, area_cutoff=None).make_valid()

    assignment = assign_to_max(inters.length)

    if relative_threshold is not None:
        under_threshold = (
            sources.area / assignment.map(targets.area)
        ) < relative_threshold
        assignment = assignment[under_threshold]

    sources_to_absorb = GeoSeries(
        sources.groupby(assignment).apply(unary_union), crs=sources.crs,
    )

    # Note that the following line produces a warning message when sources_to_absorb
    # and targets have different indices:

    # "lib/python3.11/site-packages/geopandas/base.py:31: UserWarning: The indices of
    # the two GeoSeries are different.
    # warn("The indices of the two GeoSeries are different.")

    # This difference in indices is expected since not all target geometries may have sources
    # to absorb, so it would be nice to remove this warning.
    result = targets.union(sources_to_absorb)

    # The .union call only returns the targets who had a corresponding
    # source to absorb. Now we fill in all of the unchanged targets.
    result = result.reindex(targets.index)
    did_not_absorb = result.isna() | result.is_empty
    result.loc[did_not_absorb] = targets[did_not_absorb]

    return result
