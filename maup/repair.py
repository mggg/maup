from geopandas import GeoSeries
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from .assign import assign_to_max
from .crs import require_same_crs
from .indexed_geometries import get_geometries
from .intersections import intersections


def holes_of_union(geometries):
    """Returns any holes in the union of the given geometries.

    This is adapted from `check_for_holes` in Mary Barker's
    check_shapefile_connectivity.py script in @gerrymandr/Preprocessing.
    """
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
    geometries = get_geometries(geometries)
    gaps = holes_of_union(geometries)
    return absorb_by_shared_perimeter(
        gaps, geometries, relative_threshold=relative_threshold
    )


@require_same_crs
def absorb_by_shared_perimeter(sources, targets, relative_threshold=None):
    if len(sources) == 0:
        return targets

    if len(targets) == 0:
        raise IndexError("targets must be nonempty")

    assignment = assign_to_max(intersections(sources, targets, area_cutoff=None).length)

    if relative_threshold is not None:
        under_threshold = (
            sources.area / GeoSeries(assignment.map(targets)).area
        ) < relative_threshold
        assignment = assignment[under_threshold]

    sources_to_absorb = GeoSeries(
        sources.groupby(assignment).apply(unary_union), crs=sources.crs
    )
    return targets.union(sources_to_absorb)
