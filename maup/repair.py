import math
import pandas
import functools
import warnings

from geopandas import GeoSeries, GeoDataFrame
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely import make_valid 

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
# The old version of this file used buffer(0) to simplify geometries, but this only
# works properly for polygons.  For 1-D objects such as LineStrings, it kills them off
# completely - and this resulted in some pretty disastrous choices in the 
# absorb_by_shared_perimeter function when ALL the perimeters simplified to zero and
# the choice of which geometry to absorb into was essentially random!
# In this version, buffer(0) has been replaced by Shapely 2.0's make_valid function,
# which is MUCH better behaved - EXCEPT that when applied to a GeoSeries it apparently
# removes the CRS - which then creates problems for functions that use @require_same_crs.
# So here we need to be careful throughout to reassign the correct CRS to a GeoSeries
# after applying the make_valid function.


class AreaCroppingWarning(UserWarning):
    pass


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
        overlaps, with_overlaps_removed, relative_threshold=None
    )

def autorepair(geometries, relative_threshold=0.1):
    """
    Applies all the tricks in `maup.repair` with default args. Should work by default.
    The default `relative_threshold` is `0.1`. This default is chosen to include
    tiny overlaps that can be safely auto-fixed while preserving major overlaps
    that might indicate deeper issues and should be handled on a case-by-case
    basis. Set `relative_threshold=None` to attempt to resolve all overlaps. See
    `resolve_overlaps()` and `close_gaps()` for more.
    """
    orig_crs = geometries.crs
    geometries = get_geometries(geometries)

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
        warnings.warn("Some cropped geometries have zero area, likely due to\n"+
                      "large differences in the union of the geometries in your\n"+
                      "source and target shapefiles. This may become an issue\n"+
                      "when maupping.\n",
                      AreaCroppingWarning
        )

    return cropped_geometries

@require_same_crs
def expand_to(source, target):
    """
    Expands the source geometries to the target geometries.
    """
    geometries = get_geometries(source).make_valid()

    source_union = unary_union(geometries)

    leftover_geometries = get_geometries(target).apply(lambda x: x - source_union)
    leftover_geometries = leftover_geometries[~leftover_geometries.is_empty].explode(index_parts=False)

    geometries = absorb_by_shared_perimeter(
        leftover_geometries, get_geometries(source), relative_threshold=None
    )

    return geometries



def doctor(source, target=None):
    """
    Detects quality issues in a given set of source and target geometries. Quality
    issues include overlaps, gaps, invalid geometries, repeated verticies, non-perfect
    tiling, and not entirely overlapping source and targets. If `maup.doctor()` returns
    `True`, votes should not be lost when prorating or assigning (beyond a few due to
    rounding, etc.). Passing a target to doctor is optional.
    """
    shapefiles = [source]
    source_union = unary_union(get_geometries(source))

    # Adding "health_check" variable to return instead of using assertions.
    health_check = True

    if target is not None:
        shapefiles.append(target)

        target_union = unary_union(get_geometries(target))
        sym_area = target_union.symmetric_difference(source_union).area

        if sym_area != 0:
            print("The unions of target and source differ!")
            health_check = False

    for shp in shapefiles:
        if not shp.geometry.apply(lambda x: isinstance(x, (Polygon, MultiPolygon))).all():
            print("Some rows do not have geometries.")
            health_check = False

        overlaps = count_overlaps(shp)
        holes = len(holes_of_union(shp))

        if overlaps != 0:
            print("There are", overlaps, "overlaps.")
            health_check = False
        if holes != 0:
            print("There are", holes, "holes.")
            health_check = False
        if not shp.is_valid.all():
            print("There are some invalid geometries.")
            health_check = False            

    return health_check


def count_overlaps(shp):
    """
    Counts overlaps. Code is taken directly from the resolve_overlaps function in maup.
    """
    inters = adjacencies(shp.geometry, warn_for_islands=False, warn_for_overlaps=False)
    overlaps = inters[inters.area > 0].make_valid()
    return len(overlaps)
    
    
def count_holes(shp):
    gaps = holes_of_union(shp.geometry)
    return(len(gaps))
            

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
        return Polygon(deduped_vertices_exterior, holes = deduped_vertices_interiors)


def snap_polygon_to_grid(polygon, n=-7):
    if len(polygon.interiors) == 0:
        return Polygon([(round(x, -n), round(y, -n)) for x, y in polygon.exterior.coords])
    else:
        return Polygon([(round(x, -n), round(y, -n)) for x, y in polygon.exterior.coords], holes = [[(round(x, -n), round(y, -n)) for x, y in interior_ring.coords] for interior_ring in polygon.interiors])


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
