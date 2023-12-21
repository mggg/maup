import math
import warnings
from collections import deque

import numpy
import pandas
import shapely

from geopandas import GeoSeries, GeoDataFrame
from shapely import make_valid, extract_unique_points
from shapely.strtree import STRtree
from shapely.ops import unary_union, polygonize, linemerge, nearest_points
from shapely.geometry import Polygon, MultiPolygon, Point, MultiPoint, LineString, MultiLineString
from shapely.geometry.polygon import orient
from tqdm import tqdm, TqdmWarning

from .adjacencies import adjacencies
from .assign import assign
from .indexed_geometries import get_geometries
from .intersections import intersections
from .progress_bar import progress
from .repair import doctor, snap_to_grid

warnings.filterwarnings('ignore', 'GeoSeries.isna', UserWarning)
warnings.filterwarnings("ignore", category=TqdmWarning)

pandas.options.mode.chained_assignment = None


"""
Some of these functions are based on the functions in Mary Barker's
check_shapefile_connectivity.py script in @gerrymandr/Preprocessing.

Updated functions for maup 2.0.0 were written by Jeanne Clelland.
"""

#########
# MAIN REPAIR FUNCTION
#########


def smart_repair(geometries_df, snapped=True, snap_precision=10, fill_gaps=True,
                 fill_gaps_threshold=0.1, disconnection_threshold=0.0001,
                 nest_within_regions=None, min_rook_length=None):
    """
    Repairs topology issues (overlaps, gaps, invalid polygons) in a geopandas
    GeoDataFrame or GeoSeries, with an emphasis on preserving intended adjacency
    relations between geometries as closely as possible.

    Specifically, the algorithm
    (1) Applies shapely.make_valid to all polygon geometries.
    (2) If snapped = True (default), snaps all polygon vertices to a grid of size no
        more than 10^(-snap_precision) times the max of width/height of the entire
        extent of the input. HIGHLY RECOMMENDED to avoid topological exceptions due to
        rounding errors.  Default value for snap_precision is 10; if topological
        exceptions still occur, try reducing snap_precision (which must be integer-
        valued) to 9 or 8.
    (3) Resolves all overlaps.
    (4) If fill_gaps = True (default), closes all simply connected gaps with area
        less than fill_gaps_threshold times the largest area of all geometries adjoining
        the gap.  Default threshold is 10%; if fill_gaps_threshold = None then all
        simply connected gaps will be filled.
    (5) If nest_within_regions is a secondary GeoDataFrame/GeoSeries of region boundaries
        (e.g., counties in a state) then all of the above will be performed so that
        repaired geometries nest cleanly into the region boundaries; each repaired
        geometrywill be contained in the region with which the original geometry has the
        largest area of intersection.  Default value is None.
    (6) If min_rook_length is given a numerical value, replaces all rook adjacencies
        with length below this value with queen adjacencies.  Note that this is an
        absolute value and not a relative value, so make sure that the value provided
        is in the correct units with respect to the input's CRS.
        Default value is None.
    (7) Sometimes the repair process creates tiny fragments that are disconnected from
        the district that they are assigned to.  A final cleanup step assigns any such
        fragments to a neighboring geometry if their area is less than
        disconnection_threshold times the area of the largest connected component of
        their assigned geometry. Default threshold is 0.01%, and this seems to work
        well in practice.
    """

    # Keep a copy of the original input for comparisons later!
    if isinstance(geometries_df, GeoSeries):
        orig_input_type = "geoseries"
        geometries_df = GeoDataFrame(geometry=geometries_df)
        geometries0_df = geometries_df.copy()
    elif isinstance(geometries_df, GeoDataFrame):
        orig_input_type = "geodataframe"
        geometries_df = geometries_df.copy()
        geometries0_df = geometries_df.copy()
    else:
        raise TypeError("Input geometries must be in the form of a geopandas GeoSeries or GeoDataFrame.")

    # Ensure that geometries are 2-D and not 3-D:
    for i in geometries_df.index:
        geometries_df["geometry"][i] = shapely.wkb.loads(
            shapely.wkb.dumps(geometries_df["geometry"][i], output_dimension=2))

    # Ensure that crs is not geographic:
    if geometries_df.crs is not None:
        if geometries_df.crs.is_geographic:
            raise Exception("Input geometries must be in a projected, non-geographic CRS. To project a GeoDataFrame 'gdf' to UTM, use 'gdf = gdf.to_crs(gdf.estimate_utm_crs())' ")

    # If nest_within_regions is not None, require it to have the same CRS as the main shapefile
    # and set regions_df equal to a GeoDataFrame version.
    # nest_within_regions is None, set regions_df equal to None so we can use it as a parameter later.
    if nest_within_regions is None:
        regions_df = None
    else:
        if isinstance(nest_within_regions, GeoSeries):
            regions_df = GeoDataFrame(geometry=nest_within_regions)
        elif isinstance(nest_within_regions, GeoDataFrame):
            regions_df = nest_within_regions.copy()
        else:
            raise TypeError("nest_within_regions must be a geopandas GeoSeries or GeoDataFrame.")

        if nest_within_regions.crs != geometries_df.crs:
            raise Exception("nest_within_regions must be in the same CRS as the geometries being repaired.")
        if doctor(nest_within_regions, silent=True, accept_holes=True) is False:
            raise Exception("nest_within_regions must be topologically clean---i.e., all geometries must be valid and there must be no overlaps between geometries. Generally the best source for region shapefiles is the U.S. Census Burueau.")

    # Before doing anything else, make sure all polygons are valid, convert any empty
    # geometries to empty Polygons to avoid type errors, and remove any LineStrings and
    # MultiLineStrings.
    for i in geometries_df.index:
        geometries_df["geometry"][i] = make_valid(geometries_df["geometry"][i])
        if geometries_df["geometry"][i] is None:
            geometries_df["geometry"][i] = Polygon()
        if geometries_df["geometry"][i].geom_type == "GeometryCollection":
            geometries_df["geometry"][i] = unary_union([x for x in geometries_df["geometry"][i].geoms if x.geom_type in ("Polygon", "MultiPolygon")])

    # If snapped is True, snap all polygon vertices to a grid of size no more than
    # 10^(-10) times the max of width/height of the entire extent of the input.
    # (For instance, in Texas this would be less than 1/100th of an inch.)
    # This avoids a rare "non-noded intersection" error due to a GEOS bug and leaves
    # several orders of magnitude for additional intersection operations before hitting
    # python's precision limit of about 10^(-15).
    if snapped:
        # These bounds are in the form (xmin, ymin, xmax, ymax)
        geometries_total_bounds = geometries_df.total_bounds
        largest_bound = max(geometries_total_bounds[2] - geometries_total_bounds[0], geometries_total_bounds[3] - geometries_total_bounds[1])
        snap_magnitude = int(math.log10(largest_bound)) - snap_precision
        geometries_df["geometry"] = snap_to_grid(geometries_df["geometry"], n=snap_magnitude)
        if nest_within_regions is not None:
            regions_df["geometry"] = snap_to_grid(regions_df["geometry"], n=snap_magnitude)

        # Snapping could possibly have created some invalid polygons, so do another round
        # of validity checks - and do a validity check for regions as well, if applicable.
        for i in geometries_df.index:
            geometries_df["geometry"][i] = make_valid(geometries_df["geometry"][i])
            if geometries_df["geometry"][i].geom_type == "GeometryCollection":
                geometries_df["geometry"][i] = unary_union([x for x in geometries_df["geometry"][i].geoms if x.geom_type in ("Polygon", "MultiPolygon")])
        if nest_within_regions is not None:
            for i in regions_df.index:
                regions_df["geometry"][i] = make_valid(regions_df["geometry"][i])
                if regions_df["geometry"][i].geom_type == "GeometryCollection":
                    regions_df["geometry"][i] = unary_union([x for x in regions_df["geometry"][i].geoms if x.geom_type in ("Polygon", "MultiPolygon")])
        print("Snapping all geometries to a grid with precision 10^(", snap_magnitude, ") to avoid GEOS errors.")

    # Construct data about overlaps of all orders, plus holes.
    overlap_tower, holes_df = building_blocks(geometries_df, nest_within_regions=regions_df)

    # Use data from the overlap tower to rebuild geometries with no overlaps.
    # If nest_within_regions is not None, resolve overlaps and fill holes (if applicable)
    # for each region separately.

    if nest_within_regions is None:
        print("Resolving overlaps...")
        reconstructed_df = reconstruct_from_overlap_tower(geometries_df, overlap_tower)

        # Use data about the holes to fill holes if applicable.
        if fill_gaps:
            # First remove any holes above the relative area threshold (if any).
            # Also remove any non-simply connected holes since our algorithm breaks
            # down in that case, regardless of whether or not a relative area
            # threshold has been set.
            holes_df, num_holes_dropped = drop_bad_holes(reconstructed_df, holes_df, fill_gaps_threshold=fill_gaps_threshold)
            if num_holes_dropped > 0:
                print(num_holes_dropped, "gaps will remain unfilled, because they either are not simply connected or exceed the area threshold.")

            print("Filling gaps...")
            reconstructed_df = smart_close_gaps(reconstructed_df, holes_df)

    else:
        if fill_gaps:
            print("Resolving overlaps and filling gaps...")
        else:
            print("Resolving overlaps...")

        reconstructed_df = geometries_df.copy()
        geometries_to_regions_assignment = assign(geometries_df.geometry, regions_df.geometry)

        for r_ind in nest_within_regions.index:
            geometries_this_region_indices = [g_ind for g_ind in geometries_df.index if geometries_to_regions_assignment[g_ind] == r_ind]
            geometries_this_region_df = geometries_df.loc[geometries_this_region_indices]

            overlap_tower_this_region = []
            for i in range(len(overlap_tower)):
                overlap_tower_this_region.append(overlap_tower[i][overlap_tower[i]["region"] == r_ind])

            reconstructed_this_region_df = reconstruct_from_overlap_tower(geometries_this_region_df, overlap_tower_this_region, nested=True)

            if fill_gaps:
                holes_this_region_df = holes_df[holes_df["region"] == r_ind]
                # First remove any holes above the relative area threshold (if any).
                # Also remove any non-simply connected holes since our algorithm breaks
                # down in that case, regardless of whether or not a relative area
                # threshold has been set.
                holes_this_region_df, num_holes_dropped_this_region = drop_bad_holes(reconstructed_this_region_df, holes_this_region_df, fill_gaps_threshold=fill_gaps_threshold)
                if num_holes_dropped_this_region > 0:
                    print(num_holes_dropped_this_region, "gaps in region", r_ind, "will remain unfilled, because they either are not simply connected or exceed the area threshold.")

                reconstructed_this_region_df = smart_close_gaps(reconstructed_this_region_df, holes_this_region_df)

            reconstructed_df["geometry"].loc[list(reconstructed_this_region_df.index)] = reconstructed_this_region_df["geometry"]

    # Check for geometries that have become (more) disconnected, generally with an extra
    # component of negligible area.  If any are found and the area is negligible,
    # reassign to an adjacent geometry by shared perimeter.
    # If the area is not negligible, leave it alone and report it so that the user
    # can decide what to do about it.

    disconnected_df = reconstructed_df[reconstructed_df["geometry"].apply(lambda x: x.geom_type != "Polygon")]

    # This will include geometries that were disconnected in the original; need to
    # filter by whether they got worse.

    if len(disconnected_df) > 0:
        disconnected_poly_indices = []
        for ind in disconnected_df.index:
            if num_components(reconstructed_df["geometry"][ind]) > num_components(geometries0_df["geometry"][ind]):
                disconnected_poly_indices.append(ind)

        if len(disconnected_poly_indices) > 0:
            # These are the ones (if any) that got worse.
            geometries = get_geometries(reconstructed_df)
            spatial_index = STRtree(geometries)
            index_by_iloc = dict((i, list(geometries.index)[i]) for i in range(len(geometries.index)))

            for g_ind in disconnected_poly_indices:
                excess = num_components(reconstructed_df["geometry"][g_ind]) - num_components(geometries0_df["geometry"][g_ind])
                component_num_list = list(range(len(reconstructed_df["geometry"][g_ind].geoms)))
                component_areas = []

                for c_ind in range(len(reconstructed_df["geometry"][g_ind].geoms)):
                    component_areas.append((c_ind, reconstructed_df["geometry"][g_ind].geoms[c_ind].area))

                component_areas_sorted = sorted(component_areas, key=lambda tup: tup[1])
                big_area = max([reconstructed_df["geometry"][g_ind].area, geometries0_df["geometry"][g_ind].area])

                for i in range(excess):
                    # Check whether the ith smallest component has small enough area, and if
                    # so find a better polygon to add it to.
                    c_ind = component_areas_sorted[i][0]
                    this_fragment = reconstructed_df["geometry"][g_ind].geoms[c_ind]
                    if component_areas_sorted[i][1] < disconnection_threshold*big_area:
                        possible_intersect_integer_indices = [*set(numpy.ndarray.flatten(spatial_index.query(this_fragment)))]
                        possible_intersect_indices = [(index_by_iloc[k]) for k in possible_intersect_integer_indices]

                        if nest_within_regions is not None:
                            # Restrict to geometries in the same region as this geometry
                            possible_intersect_indices = [ind for ind in possible_intersect_indices if geometries_to_regions_assignment[ind] == geometries_to_regions_assignment[g_ind]]

                        shared_perimeters = []
                        for g_ind2 in possible_intersect_indices:
                            if g_ind2 != g_ind and not (this_fragment.boundary).intersection(reconstructed_df["geometry"][g_ind2].boundary).is_empty:
                                shared_perimeters.append((g_ind2, (this_fragment.boundary).intersection(reconstructed_df["geometry"][g_ind2].boundary).length))

                        # If this is an isolated fragment and doesn't touch any other
                        # geometries, leave it alone; otherwise, choose a geometry to
                        # adjoin it to by largest shared perimeter.
                        if len(shared_perimeters) > 0:
                            component_num_list.remove(c_ind)  # Tells us to take out this component later
                            max_shared_perim = sorted(shared_perimeters, key=lambda tup: tup[1])[-1]
                            poly_to_add_to = max_shared_perim[0]
                            reconstructed_df["geometry"][poly_to_add_to] = unary_union(
                                [reconstructed_df["geometry"][poly_to_add_to], this_fragment])

                if len(component_num_list) == 1:
                    reconstructed_df["geometry"][g_ind] = reconstructed_df["geometry"][g_ind].geoms[component_num_list[0]]
                elif len(component_num_list) > 1:
                    reconstructed_df["geometry"][g_ind] = MultiPolygon(
                        [reconstructed_df["geometry"][g_ind].geoms[c_ind] for c_ind in component_num_list])
                else:
                    print("WARNING: A component of the geometry at index", g_ind, "was badly disconnected and redistributed to other geometries!")

    # We should usually now be back to the correct number of components everywhere, but
    # there may occasionally be exceptions, so check again and alert the user if not.

    disconnected_df_2 = reconstructed_df[reconstructed_df["geometry"].apply(lambda x: x.geom_type != "Polygon")]
    if len(disconnected_df_2) > 0:
        for ind in disconnected_df_2.index:
            if num_components(reconstructed_df["geometry"][ind]) > num_components(geometries0_df["geometry"][ind]):
                print("WARNING: A component of the geometry at index", ind, "may have been disconnected!")

    if min_rook_length is not None:
        # Find all inter-polygon boundaries shorter than min_rook_length and replace them
        # with queen adjacencies by manipulating coordinates of all surrounding polygon.
        print("Converting small rook adjacencies to queen...")
        reconstructed_df = small_rook_to_queen(reconstructed_df, min_rook_length)

    if orig_input_type == "geoseries":
        return reconstructed_df.geometry
    else:
        return reconstructed_df


#########
# SUPPORTING FUNCTIONS
#########

def num_components(geom):
    """Counts the number of connected components of a shapely object."""
    if geom.is_empty:
        return 0
    elif geom.geom_type in ("Polygon",  "Point", "LineString"):
        return 1
    elif geom.geom_type in ("MultiPolygon", "MultiLineString", "GeometryCollection"):
        return len(geom.geoms)


def segments(curve):
    """Extracts a list of the individual line segments from a LineString"""
    return list(map(LineString, zip(curve.coords[:-1], curve.coords[1:])))


def building_blocks(geometries_df, nest_within_regions=None):
    """
    Partitions the extent of the input via all boundaries of all geometries
    (and regions, if nest_within_regions is a GeoDataFrame/GeoSeries of region
    boundaries); associates to each polygon in the partition the set of polygons in the
    original shapefile whose intersection created it, and organizes this data according
    to order of the overlaps. (Order zero = hole)
    """
    if isinstance(geometries_df, GeoDataFrame) is False:
        raise TypeError("Primary input to building_blocks must be a GeoDataFrame.")

    geometries_df = geometries_df.copy()
    if nest_within_regions is not None:
        if isinstance(nest_within_regions, GeoDataFrame) is False:
            raise TypeError("nest_within_regions must be either None or a GeoDataFrame.")
        else:
            regions_df = nest_within_regions.copy()

    # Make a list of all the boundaries of all the polygons.
    # This won't work properly with MultiPolygons, so explode first:
    boundaries = []
    geometries_exploded_df = geometries_df.explode(index_parts=False).reset_index(drop=True)
    for i in geometries_exploded_df.index:
        boundaries.append(shapely.boundary(geometries_exploded_df["geometry"][i]))

    # Include region boundaries if applicable:
    if nest_within_regions is not None:
        regions_exploded_df = regions_df.explode(index_parts=False).reset_index(drop=True)
        for i in regions_exploded_df.index:
            boundaries.append(shapely.boundary(regions_exploded_df["geometry"][i]))

    boundaries_exploded = []
    for geom in boundaries:
        if geom.geom_type == "LineString":
            boundaries_exploded.append(geom)
        elif geom.geom_type == "MultiLineString":
            boundaries_exploded += list(geom.geoms)
    boundaries_union = shapely.node(MultiLineString(boundaries_exploded))

    # Create a geodataframe with all the pieces created by overlaps of all orders,
    # together with a set for each piece consisting of the polygons that created the overlap.
    pieces_df = GeoDataFrame(columns=["polygon indices"],
                             geometry=GeoSeries(list(polygonize(boundaries_union))),
                             crs=geometries_df.crs)

    for i in pieces_df.index:
        pieces_df["polygon indices"][i] = set()

    # Add a column to indicate the region for each piece; if there are no regions the
    # entries will remain as None.
    pieces_df["region"] = None

    g_spatial_index = STRtree(geometries_df["geometry"])
    g_index_by_iloc = dict((i, list(geometries_df.index)[i]) for i in range(len(geometries_df)))

    # If region boundaries are included, also create an STRtree for the regions
    # and assign the main geometries to regions by largest area overlap.
    if nest_within_regions is not None:
        r_spatial_index = STRtree(regions_df["geometry"])
        r_index_by_iloc = dict((i, list(regions_df.index)[i]) for i in range(len(regions_df)))
        geometries_to_regions_assignment = assign(geometries_df.geometry, regions_df.geometry)

    print("Identifying overlaps...")
    for i in progress(pieces_df.index, len(pieces_df.index)):
        # If region boundaries are included, identify the region for each piece.
        # Note that "None" is a possibility, and that each piece will belong to a unique
        # region because the regions GeoDataFrame/GeoSeries MUST be clean.
        if nest_within_regions is not None:
            possible_region_integer_indices = [*set(numpy.ndarray.flatten(r_spatial_index.query(pieces_df["geometry"][i])))]
            possible_region_indices = [r_index_by_iloc[k] for k in possible_region_integer_indices]

            for j in possible_region_indices:
                if pieces_df["geometry"][i].representative_point().intersects(regions_df["geometry"][j]):
                    pieces_df["region"][i] = j

        # Now identify the set of geometries in the main geometry that each piece is
        # contained in. If region boundaries are included, then while determining which
        # geometries each piece is contained in, omit any geometries that are
        # assigned to a region other than the one the piece is contained in.
        possible_geom_integer_indices = [*set(numpy.ndarray.flatten(g_spatial_index.query(pieces_df["geometry"][i])))]
        possible_geom_indices = [g_index_by_iloc[k] for k in possible_geom_integer_indices]

        for j in possible_geom_indices:
            if nest_within_regions is not None:
                if pieces_df["geometry"][i].representative_point().intersects(geometries_df["geometry"][j]):
                    if geometries_to_regions_assignment[j] == pieces_df["region"][i]:
                        pieces_df["polygon indices"][i] = pieces_df["polygon indices"][i].union({j})
            else:
                if pieces_df["geometry"][i].representative_point().intersects(geometries_df["geometry"][j]):
                    pieces_df["polygon indices"][i] = pieces_df["polygon indices"][i].union({j})

    # Organize this info into separate GeoDataFrames for overlaps of all orders - including
    # order zero, which corresponds to gaps.
    # This will be easier if we temporarily add a column for overlap degree.
    overlap_degree_list = [len(x) for x in pieces_df["polygon indices"]]
    pieces_df["overlap degree"] = overlap_degree_list

    # Here are the gaps:
    holes_df = (pieces_df[pieces_df["overlap degree"] == 0]).reset_index(drop=True)

    # If region boundaries are included, drop all the polygons that didn't fall into any
    # region, and also take the (exploded) unary unions of all the gaps in each region,
    # since some pieces of geometries from other regions may now be gaps that are adjacent
    # to other gaps.
    if nest_within_regions is not None:
        pieces_df = pieces_df[~pieces_df["region"].isna()].reset_index(drop=True)
        holes_df = holes_df[~holes_df["region"].isna()].reset_index(drop=True)

        consolidated_holes_df = GeoDataFrame(columns=["polygon indices", "geometry", "region", "overlap degree"],
                                             geometry="geometry", crs=holes_df.crs)
        for r_ind in regions_df.index:
            this_region_holes_df = holes_df[holes_df["region"] == r_ind]
            this_region_consolidated_holes = GeoSeries([unary_union(this_region_holes_df["geometry"])]).explode(index_parts=False).reset_index(drop=True)
            this_region_consolidated_holes_df = GeoDataFrame(geometry=this_region_consolidated_holes, crs=holes_df.crs)

            this_region_consolidated_holes_df.insert(0, "polygon indices", None)
            for i in this_region_consolidated_holes_df.index:
                this_region_consolidated_holes_df["polygon indices"][i] = set()
            this_region_consolidated_holes_df.insert(2, "region", r_ind)
            this_region_consolidated_holes_df.insert(2, "overlap degree", 0)

            consolidated_holes_df = pandas.concat([consolidated_holes_df, this_region_consolidated_holes_df]).reset_index(drop=True)

        holes_df = consolidated_holes_df

    # Here is a list of GeoDataFrames, one consisting of all overlaps of each order:
    overlap_tower = []

    for i in range(max(pieces_df["overlap degree"])):
        overlap_tower.append(pieces_df[pieces_df["overlap degree"] == i+1])

    # Drop unnecessary "overlap degree" column and reindex each GeoDataFrame:
    for i in range(len(overlap_tower)):
        del overlap_tower[i]["overlap degree"]
        overlap_tower[i] = overlap_tower[i].reset_index(drop=True)
    del holes_df["overlap degree"]

    # Drop the "polygon indices" column in the holes GeoDataFrame:
    del holes_df["polygon indices"]

    return overlap_tower, holes_df


def reconstruct_from_overlap_tower(geometries_df, overlap_tower, nested=False):
    """
    Rebuild the polygons in geometries_df with overlaps removed.
    """
    # Keep a copy of the original input for comparisons later!
    geometries0_df = geometries_df.copy()

    geometries_df = geometries_df.copy()
    overlap_tower = [df.copy() for df in overlap_tower]

    geometries_df["geometry"] = Polygon()

    max_overlap_level = len(overlap_tower)

    # Start by assigning all order 1 pieces to the polygon they came from:
    for ind in overlap_tower[0].index:
        this_poly_ind = list(overlap_tower[0]["polygon indices"][ind])[0]
        this_piece = overlap_tower[0]["geometry"][ind]
        geometries_df["geometry"][this_poly_ind] = unary_union([geometries_df["geometry"][this_poly_ind], this_piece])

    # We will need to know which geometries were disconnected by removing
    # overlaps, so add columns for numbers of components in the original and refined
    # geometries to each dataframe for future use.
    geometries_df["num components orig"] = 0
    geometries_df["num components refined"] = 0

    for ind in geometries_df.index:
        geometries_df["num components orig"][ind] = num_components(geometries0_df["geometry"][ind])
        geometries_df["num components refined"][ind] = num_components(geometries_df["geometry"][ind])

    # Now, start with the order 2 overlaps and gradually add overlaps at successively
    # higher orders until done.

    # First look for geometries at the top level that were disconnected
    # by the refinement process, and give them first dibs at grabbing overlaps
    # until they are reconnected or run out of overlaps to grab.
    # Note that this doesn't always completely work; in rare cases a single overlap
    # can disconnect more than one polygon, and only one of them gets to grab it back.
    # This will be addressed at the end of the reconstruction process.

    geometries_disconnected_df = geometries_df[geometries_df["num components refined"] > geometries_df["num components orig"]]

    for i in range(1, max_overlap_level):
        overlaps_df = overlap_tower[i]
        overlaps_df_unused_indices = overlaps_df.index.tolist()

        o_spatial_index = STRtree(overlaps_df["geometry"])
        o_index_by_iloc = dict((i, list(overlaps_df.index)[i]) for i in range(len(overlaps_df)))

        for g_ind in geometries_disconnected_df.index:
            possible_overlap_integer_indices = [*set(numpy.ndarray.flatten(o_spatial_index.query(geometries_disconnected_df["geometry"][g_ind])))]
            possible_overlap_indices_0 = [o_index_by_iloc[k] for k in possible_overlap_integer_indices]
            possible_overlap_indices = list(set(possible_overlap_indices_0) & set(overlaps_df_unused_indices))

            geom_finished = False

            for o_ind in possible_overlap_indices:
                # If the corresponding overlap intersects this geometry (and was
                # contained in it originally!), grab it.
                if (geom_finished is False) and (g_ind in list(overlaps_df["polygon indices"][o_ind])) and (not geometries_disconnected_df["geometry"][g_ind].intersection(overlaps_df["geometry"][o_ind]).is_empty):

                    if (geometries_disconnected_df["geometry"][g_ind].intersection(overlaps_df["geometry"][o_ind])).length > 0:
                        geometries_disconnected_df["geometry"][g_ind] = unary_union([
                            geometries_disconnected_df["geometry"][g_ind], overlaps_df["geometry"][o_ind]
                            ])
                        overlaps_df_unused_indices.remove(o_ind)
                        if num_components(geometries_disconnected_df["geometry"][g_ind]) == geometries_df["num components orig"][g_ind]:
                            geom_finished = True

            geometries_df["geometry"][g_ind] = geometries_disconnected_df["geometry"][g_ind]

            if geom_finished:
                geometries_disconnected_df = geometries_disconnected_df.drop(g_ind)

        # That's all we can do for the disconnected geometries at this level.
        # Go on to filling in the rest of the overlaps by greatest perimeter.
        g_spatial_index = STRtree(geometries_df["geometry"])
        g_index_by_iloc = dict((i, list(geometries_df.index)[i]) for i in range(len(geometries_df)))

        if nested is False:
            print("Assigning order", i+1, "pieces...")
        for o_ind in overlaps_df_unused_indices:
            this_overlap = overlaps_df["geometry"][o_ind]
            shared_perimeters = []
            possible_geom_integer_indices = [*set(numpy.ndarray.flatten(g_spatial_index.query(overlaps_df["geometry"][o_ind])))]
            possible_geom_indices = [g_index_by_iloc[k] for k in possible_geom_integer_indices]

            for g_ind in possible_geom_indices:
                if (g_ind in list(overlaps_df["polygon indices"][o_ind])) and not (this_overlap.boundary).intersection(geometries_df["geometry"][g_ind].boundary).is_empty:
                    shared_perimeters.append((g_ind, (this_overlap.boundary).intersection(geometries_df["geometry"][g_ind].boundary).length))

            if len(shared_perimeters) > 0:
                max_shared_perim = sorted(shared_perimeters, key=lambda tup: tup[1])[-1]
                poly_to_add_to = max_shared_perim[0]
                geometries_df["geometry"][poly_to_add_to] = unary_union(
                    [geometries_df["geometry"][poly_to_add_to], this_overlap])
            else:
                # It seems like this should never happen, but it still seems to on
                # very rare occasions.
                if nested is False:
                    print("Couldn't find a polygon to glue a component in the intersection of geometries", overlaps_df["polygon indices"][o_ind], "to")

    reconstructed_df = geometries_df
    del reconstructed_df["num components orig"]
    del reconstructed_df["num components refined"]

    return reconstructed_df


def drop_bad_holes(reconstructed_df, holes_df, fill_gaps_threshold):
    """ Identify holes that won't be filled and drop them from holes_df """

    holes_df = holes_df.copy()

    if fill_gaps_threshold is not None:
        spatial_index = STRtree(reconstructed_df.geometry)
        index_by_iloc = dict((i, list(reconstructed_df.index)[i]) for i in range(len(reconstructed_df.index)))
        hole_indices_to_drop = []
        for h_ind in holes_df.index:
            this_hole = holes_df["geometry"][h_ind]
            if shapely.get_num_interior_rings(holes_df["geometry"][h_ind]) > 0:
                hole_indices_to_drop.append(h_ind)
            else:
                possible_intersect_integer_indices = [*set(numpy.ndarray.flatten(spatial_index.query(this_hole)))]
                possible_intersect_indices = [(index_by_iloc[k]) for k in possible_intersect_integer_indices]
                actual_intersect_indices = [g_ind for g_ind in possible_intersect_indices if not this_hole.intersection(reconstructed_df["geometry"][g_ind]).is_empty]
                if len(actual_intersect_indices) > 0:
                    max_geom_area = max(reconstructed_df["geometry"][g_ind].area for g_ind in actual_intersect_indices)
                    hole_area_ratio = this_hole.area/max_geom_area
                    if hole_area_ratio > fill_gaps_threshold:
                        hole_indices_to_drop.append(h_ind)

    else:
        hole_indices_to_drop = []
        for h_ind in holes_df.index:
            if shapely.get_num_interior_rings(holes_df["geometry"][h_ind]) > 0:
                hole_indices_to_drop.append(h_ind)

    if len(hole_indices_to_drop) > 0:
        holes_df = holes_df.drop(hole_indices_to_drop).reset_index(drop=True)

    return holes_df, len(hole_indices_to_drop)


def smart_close_gaps(geometries_df, holes_df):
    """
    Fill simply connected gaps; general procedure is roughly as follows:
    (1) Fill in gaps that only intersect one non-exterior geometry in the
        obvious way.
    (2) For remaining gaps, partially fill by "convexifying" boundaries with each
        non-exterior geometry.  This will have the effect of completely filling
        gaps that only intersect 2 geometries and no exterior boundaries.
    (3) For any gap that intersects 4 or more geometries nontrivially (including
        exterior boundaries), find the non-adjacent pair with the shortest distance
        between them and try to connect the pair by adding a "triangle" to each of the
        non-exterior geometries in the pair. (Keep trying until this succeeds for
        some pair.) This reduces the gap to 1 or 2 smaller gaps, each intersecting
        strictly fewer geometries than the original. Put the smaller gaps back in the
        queue for the next round.
    (4) For any gap that intersects exactly 3 geometries (including exterior boundaries)
        nontrivially, fill by a process that gives a portion of the gap to each of
        the non-exterior geometries that it intersects.
    """
    geometries_df = geometries_df.copy()
    holes_df = holes_df.copy()

    # First step is to simplify gaps by convexifying the geometry boundaries:
    geometries_df, holes_df = convexify_hole_boundaries(geometries_df, holes_df)

    # Now proceed with filling simplified gaps.
    if len(holes_df) > 0:
        holes_to_process = deque(list(holes_df["geometry"]))
        this_region = list(holes_df["region"])[0]  # All holes in this dataframe should be from the same region
        if this_region is None:
            pbar = tqdm(desc="Gaps to fill", total=len(holes_to_process))
        else:
            pbar = tqdm(desc=f"Gaps to fill in region {this_region}", total=len(holes_to_process))
    else:
        holes_to_process = deque([])
        pbar = tqdm(desc="Gaps to fill", total=len(holes_to_process))

    while len(holes_to_process) > 0:
        pbar_increment = 1
        this_hole = holes_to_process.popleft()
        this_hole_df = GeoDataFrame(geometry=GeoSeries([this_hole]), crs=holes_df.crs)
        this_hole_boundaries_df = construct_hole_boundaries(geometries_df, this_hole_df)

        # Break into cases depending on how many target geometries intersect this gap
        # and how many line segments the gap boundary consists of.
        # After convexification, all gaps must have at least 3 boundaries (possibly
        # including an exterior boundary).

        if len(set(this_hole_boundaries_df["target"]).difference({-1})) == 1:
            # Attach the gap to the unique non-exterior geometry that it intersects:
            poly_to_add_to = list(set(this_hole_boundaries_df["target"]).difference({-1}))[0]
            geometries_df["geometry"][poly_to_add_to] = unary_union([geometries_df["geometry"][poly_to_add_to], this_hole])

        elif len(segments(this_hole.boundary)) == 3:  # If the hole is a simple triangle
            if len(set(this_hole_boundaries_df["target"]).difference({-1})) == 3:
                # Find the incenter of the triangle and use it to divide the triangle into
                # 3 smaller triangles.  (The incenter is more natural for this purpose than
                # the centroid, especially for long skinny triangles.)
                this_hole_incenter = incenter(this_hole)
                for thb_ind in this_hole_boundaries_df.index:
                    g_ind = this_hole_boundaries_df["target"][thb_ind]
                    this_segment = this_hole_boundaries_df["geometry"][thb_ind]
                    this_segment_poly_to_add = make_valid(Polygon([this_segment.boundary.geoms[0], this_segment.boundary.geoms[1], this_hole_incenter]))
                    geometries_df["geometry"][g_ind] = unary_union([geometries_df["geometry"][g_ind], this_segment_poly_to_add])

            else:
                # There are either 2 sides intersecting a common geometry or 1
                # side intersecting an exterior boundary. In this case join the entire
                # triangle to the geometry that it shares the largest perimeter with.
                touching_geoms = list(set(this_hole_boundaries_df["target"]).difference({-1}))
                perim_1 = this_hole.intersection(geometries_df["geometry"][touching_geoms[0]]).length
                perim_2 = this_hole.intersection(geometries_df["geometry"][touching_geoms[1]]).length
                if perim_1 > perim_2:
                    poly_to_add_to = touching_geoms[0]
                else:
                    poly_to_add_to = touching_geoms[1]
                geometries_df["geometry"][poly_to_add_to] = unary_union([geometries_df["geometry"][poly_to_add_to], this_hole])

        else:
            this_hole_df = GeoDataFrame(geometry=GeoSeries([this_hole]), crs=holes_df.crs)
            this_hole_boundaries_df = construct_hole_boundaries(geometries_df, this_hole_df)

            # If this_hole falls into one of the simple cases above, put it back
            # in the queue.  (Note that after convexification,
            # this_hole_boundaries_df can only have length 2 if one of the
            # boundaries is exterior and didn't get convexified.)
            if len(this_hole_boundaries_df) == 3:
                # Put the gap boundaries and target geometries into oriented order:
                this_hole_boundaries = [this_hole_boundaries_df["geometry"][0]]
                target_geometries = [this_hole_boundaries_df["target"][0]]

                if this_hole_boundaries_df["geometry"][1].coords[0] == this_hole_boundaries_df["geometry"][0].coords[-1]:
                    this_hole_boundaries.append(this_hole_boundaries_df["geometry"][1])
                    target_geometries.append(this_hole_boundaries_df["target"][1])
                    this_hole_boundaries.append(this_hole_boundaries_df["geometry"][2])
                    target_geometries.append(this_hole_boundaries_df["target"][2])
                elif this_hole_boundaries_df["geometry"][2].coords[0] == this_hole_boundaries_df["geometry"][0].coords[-1]:
                    this_hole_boundaries.append(this_hole_boundaries_df["geometry"][2])
                    target_geometries.append(this_hole_boundaries_df["target"][2])
                    this_hole_boundaries.append(this_hole_boundaries_df["geometry"][1])
                    target_geometries.append(this_hole_boundaries_df["target"][1])

                # If one of the boundaries is an exterior region boundary, find
                # the shortest path between the vertex that isn't one of its
                # endpoints and the nearest point in this boundary, and divide
                # the hole between the other two adjacent geometries along this path.
                # Otherwise, for each of the three boundary endpoints, construct
                # the angle bisector of the two adjacent line segments and extend
                # this line beyond the extent of the hole.  Intersections of these
                # 3 line segments will determine the endpoints of the new boundaries.

                if -1 in target_geometries:
                    ext_boundary_position = target_geometries.index(-1)
                    # Cyclically permute so that the exterior boundary is in the
                    # 1st position:
                    this_hole_boundaries = this_hole_boundaries[ext_boundary_position:] + this_hole_boundaries[0:ext_boundary_position]
                    target_geometries = target_geometries[ext_boundary_position:] + target_geometries[0:ext_boundary_position]

                    main_vertex = Point(this_hole_boundaries[2].coords[0])
                    nearest_ext_boundary_point = nearest_points(main_vertex, extract_unique_points(this_hole_boundaries[0]))[1]

                    ext_boundary_points = list(extract_unique_points(this_hole_boundaries[0]).geoms)
                    nearest_point_position = ext_boundary_points.index(nearest_ext_boundary_point)

                    if nearest_point_position == 0:
                        # Add the entire hole to target_geometries[1].
                        geometries_df["geometry"][target_geometries[1]] = unary_union([geometries_df["geometry"][target_geometries[1]], this_hole])

                    elif nearest_point_position == len(ext_boundary_points) - 1:
                        # Add the entire hole to target_geometries[2].
                        geometries_df["geometry"][target_geometries[2]] = unary_union([geometries_df["geometry"][target_geometries[2]], this_hole])

                    else:
                        this_hole_triangulation = triangulate_polygon(this_hole)
                        sp = LineString(shortest_path_in_polygon(this_hole, main_vertex, nearest_ext_boundary_point, full_triangulation=this_hole_triangulation))

                        poly1_to_add_boundary = unary_union([this_hole_boundaries[1], sp, LineString(ext_boundary_points[nearest_point_position:])])
                        poly1_to_add = polygonize(poly1_to_add_boundary)[0]
                        geometries_df["geometry"][target_geometries[1]] = unary_union([geometries_df["geometry"][target_geometries[1]], poly1_to_add])

                        poly2_to_add_boundary = unary_union([this_hole_boundaries[2], sp, LineString(ext_boundary_points[0:nearest_point_position+1])])
                        poly2_to_add = polygonize(poly2_to_add_boundary)[0]
                        geometries_df["geometry"][target_geometries[2]] = unary_union([geometries_df["geometry"][target_geometries[2]], poly2_to_add])

                else:
                    max_line_length = this_hole.boundary.length/2
                    vertices = []
                    bisectors = []

                    for i in range(3):
                        this_vertex = numpy.array(this_hole_boundaries[i].coords[0])
                        vertices.append(Point(this_hole_boundaries[i].coords[0]))
                        this_vec_1_raw = numpy.array(this_hole_boundaries[i].coords[1]) - this_vertex
                        this_vec_2_raw = numpy.array(this_hole_boundaries[i-1].coords[-2]) - this_vertex
                        this_unit_vec_1 = this_vec_1_raw/math.sqrt(this_vec_1_raw[0]**2 + this_vec_1_raw[1]**2)
                        this_unit_vec_2 = this_vec_2_raw/math.sqrt(this_vec_2_raw[0]**2 + this_vec_2_raw[1]**2)
                        this_bisector_vec_raw = this_unit_vec_1 + this_unit_vec_2
                        this_bisector_unit_vec = this_bisector_vec_raw/math.sqrt(this_bisector_vec_raw[0]**2 + this_bisector_vec_raw[1]**2)
                        this_bisector = LineString([tuple(this_vertex), tuple(this_vertex + max_line_length*this_bisector_unit_vec)])
                        bisectors.append(this_bisector)

                    # Points of intersection of the bisectors:
                    i_points = [bisectors[0].intersection(bisectors[1]), bisectors[1].intersection(bisectors[2]), bisectors[2].intersection(bisectors[0])]

                    # Note that these points could coincide - e.g., if the convexified
                    # hole is a triangle - and the rest of the construction would be very
                    # simple.
                    # Also - even though this is geometrically impossible(!),
                    # rounding errors can create a situation in which two
                    # of these points are equal but different from the 3rd.
                    # In this case, assume that the one that appears twice
                    # is actually the common value for all three.

                    if i_points[0] == i_points[1] or i_points[0] == i_points[2]:
                        # Construct pieces to append to geometries and append them.
                        middle_point = i_points[0]
                        for i in range(3):
                            poly_to_add_boundary = unary_union([this_hole_boundaries[i], LineString([this_hole_boundaries[i].coords[-1], middle_point, this_hole_boundaries[i].coords[0]])])
                            poly_to_add = polygonize(poly_to_add_boundary)[0]
                            geometries_df["geometry"][target_geometries[i]] = unary_union([geometries_df["geometry"][target_geometries[i]], poly_to_add])

                    elif i_points[1] == i_points[2]:
                        # Construct pieces to append to geometries and append them.
                        middle_point = i_points[1]
                        for i in range(3):
                            poly_to_add_boundary = unary_union([this_hole_boundaries[i], LineString([this_hole_boundaries[i].coords[-1], middle_point, this_hole_boundaries[i].coords[0]])])
                            poly_to_add = polygonize(poly_to_add_boundary)[0]
                            geometries_df["geometry"][target_geometries[i]] = unary_union([geometries_df["geometry"][target_geometries[i]], poly_to_add])

                    else:
                        # In general, each bisector intersects the other two
                        # bisectors in distinct points.  To accurately construct
                        # the path to the more distant one, we need to include
                        # the nearer one as an intermediate point.
                        # And we might as well go ahead and find the incenter of the
                        # triangle formed by the intersection points, and include it
                        # on the path to the more distant one so we can completely
                        # fill the hole without a separate step.
                        middle_point = incenter(Polygon(i_points))

                        # The first bisector contains the 1st and 3rd intersection points.
                        if vertices[0].distance(i_points[0]) > vertices[0].distance(i_points[2]):
                            v0_to_i01_path = LineString([vertices[0], i_points[2], middle_point, i_points[0]])
                            v0_to_i02_path = LineString([vertices[0], i_points[2]])
                        else:
                            v0_to_i01_path = LineString([vertices[0], i_points[0]])
                            v0_to_i02_path = LineString([vertices[0], i_points[0], middle_point, i_points[2]])

                        # The second bisector contains the 1st and 2nd intersection points.
                        if vertices[1].distance(i_points[0]) > vertices[1].distance(i_points[1]):
                            v1_to_i01_path = LineString([vertices[1], i_points[1], middle_point, i_points[0]])
                            v1_to_i12_path = LineString([vertices[1], i_points[1]])
                        else:
                            v1_to_i01_path = LineString([vertices[1], i_points[0]])
                            v1_to_i12_path = LineString([vertices[1], i_points[0], middle_point, i_points[1]])

                        # The third bisector contains the 2nd and 3rd intersection points.
                        if vertices[2].distance(i_points[1]) > vertices[2].distance(i_points[2]):
                            v2_to_i12_path = LineString([vertices[2], i_points[2], middle_point, i_points[1]])
                            v2_to_i02_path = LineString([vertices[2], i_points[2]])
                        else:
                            v2_to_i12_path = LineString([vertices[2], i_points[1]])
                            v2_to_i02_path = LineString([vertices[2], i_points[1], middle_point, i_points[2]])

                        # Construct and adjoin new polygon pieces one at a time.
                        poly0_to_add_boundary = unary_union([this_hole_boundaries[0], v0_to_i01_path, v1_to_i01_path])
                        poly0_to_add = polygonize(poly0_to_add_boundary)[0]
                        geometries_df["geometry"][target_geometries[0]] = unary_union([geometries_df["geometry"][target_geometries[0]], poly0_to_add])

                        poly1_to_add_boundary = unary_union([this_hole_boundaries[1], v1_to_i12_path, v2_to_i12_path])
                        poly1_to_add = polygonize(poly1_to_add_boundary)[0]
                        geometries_df["geometry"][target_geometries[1]] = unary_union([geometries_df["geometry"][target_geometries[1]], poly1_to_add])

                        poly2_to_add_boundary = unary_union([this_hole_boundaries[2], v2_to_i02_path, v0_to_i02_path])
                        poly2_to_add = polygonize(poly2_to_add_boundary)[0]
                        geometries_df["geometry"][target_geometries[2]] = unary_union([geometries_df["geometry"][target_geometries[2]], poly2_to_add])

            else:  # If len(this_hole_boundaries_df) >= 4
                this_hole_triangulation = triangulate_polygon(this_hole)
                thb_distances = []

                for i in this_hole_boundaries_df.index:
                    for j in this_hole_boundaries_df.index:
                        if j > i:
                            this_distance = this_hole_boundaries_df["geometry"][i].distance(this_hole_boundaries_df["geometry"][j])
                            if this_distance != 0:
                                thb_distances.append((i, j, this_distance))

                thb_distance_data_sorted = deque(sorted(thb_distances, key=lambda tup: tup[2]))

                found_triangles = False
                while found_triangles is False and len(thb_distance_data_sorted) > 0:
                    boundary_distance_data = thb_distance_data_sorted.popleft()
                    boundaries_to_connect = (boundary_distance_data[0], boundary_distance_data[1])

                    nhb1 = this_hole_boundaries_df["geometry"][boundaries_to_connect[0]]
                    nhb2 = this_hole_boundaries_df["geometry"][boundaries_to_connect[1]]
                    geom1 = this_hole_boundaries_df["target"][boundaries_to_connect[0]]
                    geom2 = this_hole_boundaries_df["target"][boundaries_to_connect[1]]

                    # Construct the shortest paths between
                    # (1) initial points of both boundaries;
                    # (2) terminal points of both boundaries.
                    # These paths will intersect, possibly at a vertex or along entire
                    # hole boundary segments, but generically---and provably for at
                    # at leat one non-adjacent pair---at a single interior point of
                    # the hole.
                    # In the generic case, these paths together with the two
                    # hole boundaries will form a pair of "triangles" that each share a
                    # boundary of positive length with one of the two hole boundaries.
                    # Find the closest pair that satisfy this generic intersection
                    # condition and adjoin each of the triangles formed in this way
                    # to its adjacent geometry.  This will create
                    # two smaller holes - which already have convexified geometry
                    # boundaries by construction! - and we put these back on the queue
                    # for the next round.

                    if not (geom1 == -1 and geom2 == -1):
                        # If one of the boundaries is exterior (and in the rare case that BOTH
                        # boundaries are exterior, skip this pair and go on to the next one):
                        # Find the closest point on the exterior boundary to the non-exterior
                        # geometry, construct a "triangle" by taking the shortest paths from
                        # the endpoints of the non-exterior geometry to this point, and
                        # (assuming it has positive area) adjoining it to the non-exterior
                        # geometry.
                        if geom1 == -1 or geom2 == -1:
                            if geom1 == -1:
                                nhb_ext = nhb1
                                nhb_int = nhb2
                                geom_int = geom2
                            elif geom2 == -1:
                                nhb_ext = nhb2
                                nhb_int = nhb1
                                geom_int = geom1
                            point1 = nhb_int.boundary.geoms[0]
                            point2 = nhb_int.boundary.geoms[1]
                            nearest_ext_boundary_point = nearest_points(nhb_int, extract_unique_points(nhb_ext))[1]
                            path1 = LineString(shortest_path_in_polygon(this_hole, point1, nearest_ext_boundary_point, full_triangulation=this_hole_triangulation))
                            path2 = LineString(shortest_path_in_polygon(this_hole, point2, nearest_ext_boundary_point, full_triangulation=this_hole_triangulation))
                            polys_to_add_boundary = shapely.node(MultiLineString([nhb_int, path1, path2]))
                            polys_to_add = polygonize(polys_to_add_boundary)
                            if len(polys_to_add) > 0:
                                for poly_to_add in polys_to_add:
                                    if poly_to_add.area > 0:
                                        found_triangles = True
                                        geometries_df["geometry"][geom_int] = unary_union([geometries_df["geometry"][geom_int], poly_to_add])
                                        this_hole = this_hole.difference(poly_to_add)

                        else:
                            # Start by constructing the shortest paths between the initial point
                            # of each boundary and the terminal point of the other.  If these
                            # paths are disjoint, then this pair of boundaries is strongly
                            # mutually visible and we want to connect them.  Otherwise,
                            # skip this pair and move on to the next one.
                            point11 = nhb1.boundary.geoms[0]
                            point12 = nhb1.boundary.geoms[1]
                            point21 = nhb2.boundary.geoms[0]
                            point22 = nhb2.boundary.geoms[1]

                            test_path1_vertices = shortest_path_in_polygon(this_hole, point11, point22, full_triangulation=this_hole_triangulation)
                            test_path2_vertices = shortest_path_in_polygon(this_hole, point12, point21, full_triangulation=this_hole_triangulation)
                            if len(set(test_path1_vertices).intersection(set(test_path2_vertices))) == 0:
                                # In this case we should be good to add triangles formed
                                # by crossing paths between the initial and terminal
                                # points between the two boundaries!
                                # A minor exception is when both boundaries target the same
                                # geometry, in which case we want the paths to NOT cross in
                                # order to preserve convexity of the geometry boundaries in the
                                # new holes, and we'll add a single polygon instead of a
                                # pair of triangles.

                                found_triangles = True

                                if geom1 == geom2:
                                    path1 = LineString(shortest_path_in_polygon(this_hole, point11, point22, full_triangulation=this_hole_triangulation))
                                    path2 = LineString(shortest_path_in_polygon(this_hole, point12, point21, full_triangulation=this_hole_triangulation))
                                else:
                                    path1 = LineString(shortest_path_in_polygon(this_hole, point11, point21, full_triangulation=this_hole_triangulation))
                                    path2 = LineString(shortest_path_in_polygon(this_hole, point12, point22, full_triangulation=this_hole_triangulation))

                                polys_to_add_boundary = shapely.node(MultiLineString([nhb1, nhb2, path1, path2]))
                                polys_to_add = polygonize(polys_to_add_boundary)
                                # polys_to_add will consist of either 1 or 2 polygons,
                                # each sharing a positive-length boundary witha unique geometry.
                                # Add each polygon to the geometry that it shares a boundary with.
                                nhb1_segments = segments(nhb1)
                                nhb2_segments = segments(nhb2)
                                for poly_to_add in polys_to_add:
                                    poly_to_add = orient(poly_to_add)
                                    # Cover all bases with both possible orientations for
                                    # boundary segments, even though the proper orientation
                                    # SHOULD always be correct.
                                    poly_segments_oriented = segments(poly_to_add.boundary)
                                    poly_segments_reverse = [shapely.reverse(segment) for segment in poly_segments_oriented]
                                    poly_segments_all = set(poly_segments_oriented + poly_segments_reverse)
                                    if (len(set(nhb1_segments).intersection(poly_segments_all)) > 0) and (len(set(nhb2_segments).intersection(poly_segments_all)) == 0):
                                        geometries_df["geometry"][geom1] = unary_union([geometries_df["geometry"][geom1], poly_to_add])
                                        this_hole = this_hole.difference(poly_to_add)

                                    elif (len(set(nhb1_segments).intersection(poly_segments_all)) == 0) and (len(set(nhb2_segments).intersection(poly_segments_all)) > 0):
                                        geometries_df["geometry"][geom2] = unary_union([geometries_df["geometry"][geom2], poly_to_add])
                                        this_hole = this_hole.difference(poly_to_add)

                                    elif geom1 == geom2:
                                        geometries_df["geometry"][geom1] = unary_union([geometries_df["geometry"][geom1], poly_to_add])
                                        this_hole = this_hole.difference(poly_to_add)

                                    else:
                                        print("Internal triangle construction went weird!")
                                        print("Hole boundaries:")
                                        for i in this_hole_boundaries_df.index:
                                            print("Target:", this_hole_boundaries_df["target"][i])
                                            print(list(this_hole_boundaries_df["geometry"][i].coords))
                                        print("poly_to_add boundaries:")
                                        print(list(poly_to_add.boundary.coords))

                # Now put the new hole(s) created by removing triangles back in the queue:
                if found_triangles and not this_hole.is_empty:
                    if this_hole.geom_type == "MultiPolygon":  # 2 holes to add
                        holes_to_add = [orient(geom) for geom in this_hole.geoms]
                    elif this_hole.geom_type == "Polygon":  # 1 hole to add
                        holes_to_add = [orient(this_hole)]
                    holes_to_process.extend(holes_to_add)
                    pbar_increment -= len(holes_to_add)

                elif found_triangles is False:
                    # This is rare, but it does happen occasionally in the scenario where
                    # there's a large external boundary that, if it weren't external,
                    # would grab most (or maybe even all) of the hole in the
                    # convexification process.
                    # In this case, just assign the entire hole to the geometry with which
                    # it shares the largest perimeter.  (This is fairly close to what
                    # tends to happen with large, non-convexified external boundaries
                    # anyway!)
                    shared_perimeters = []
                    for i in this_hole_boundaries_df.index:
                        if this_hole_boundaries_df["target"][i] != -1:
                            shared_perimeters.append((this_hole_boundaries_df["target"][i], this_hole_boundaries_df["geometry"][i].length))
                    if len(shared_perimeters) > 0:
                        max_shared_perim = sorted(shared_perimeters, key=lambda tup: tup[1])[-1]
                        poly_to_add_to = max_shared_perim[0]
                        geometries_df["geometry"][poly_to_add_to] = unary_union(
                            [geometries_df["geometry"][poly_to_add_to], this_hole])

        pbar.update(pbar_increment)

    pbar.close()

    return geometries_df


def small_rook_to_queen(geometries_df, min_rook_length):
    """
    Convert all rook adjacencies between geometries with total adjacency length less
    than min_rook_length to queen adjacencies.
    """

    geometries_df = geometries_df.copy()

    # The input should be clean, so these should all be 1-D or less:
    adj_df = adjacencies(geometries_df, output_type="geodataframe")
    adj_df.crs = geometries_df.crs

    # Identify the adjacencies whose TOTAL length is less than the threshold;
    # since this is all about adjacency relations, there's no need to fix
    # a small component when there's also a large component that will create
    # an adjacency regardless.
    # Add column for boundary length and select the small ones:
    adj_df["boundary length"] = adj_df["geometry"].length
    small_adj_df = adj_df[adj_df["boundary length"] < min_rook_length]

    # Get rid of point geometries, linemerge the MultiLineStrings, and then
    # explode into components. (Then get rid of points again.)
    for ind in small_adj_df.index:
        if small_adj_df["geometry"][ind].geom_type == "GeometryCollection":
            small_adj_list = list(small_adj_df["geometry"][ind].geoms)
            small_adj_list_no_point = [x for x in small_adj_list if x.geom_type != "Point"]
            small_adj_df["geometry"][ind] = MultiLineString(small_adj_list_no_point)

        if small_adj_df["geometry"][ind].geom_type == "MultiLineString":
            small_adj_df["geometry"][ind] = linemerge(small_adj_df["geometry"][ind])

    small_adj_df = small_adj_df.explode(index_parts=False).reset_index(drop=True)

    small_adj_df_indices_to_drop = []
    for ind in small_adj_df.index:
        if small_adj_df["geometry"][ind].geom_type == "Point":
            small_adj_df_indices_to_drop.append(ind)

    if len(small_adj_df_indices_to_drop) > 0:
        small_adj_df = small_adj_df.drop(small_adj_df_indices_to_drop)

    # Next, construct small disks around each adjacency, and add them to a list.
    # We'll take their unary union later in case any of them overlap.
    disks_to_remove_list = []
    for a_ind in small_adj_df.index:
        this_adj = small_adj_df["geometry"][a_ind]
        adj_diam = this_adj.length
        fat_point_radius = 0.6*adj_diam  # slightly more than the radius from the midpoint to the endpoints
        endpoint1 = this_adj.coords[0]
        endpoint2 = this_adj.coords[-1]
        midpoint = LineString([endpoint1, endpoint2]).centroid
        disk_to_remove = midpoint.buffer(fat_point_radius)
        disks_to_remove_list.append(disk_to_remove)

    if len(disks_to_remove_list) > 0:
        # Make a list of the convex hulls of all the components of the unary union,
        # and make sure none of THOSE intersect.  (Note that is is only necessary if there
        # is more than 1 disk to remove.)
        polys_to_remove_list = disks_to_remove_list
        polys_to_remove_complete = False
        while polys_to_remove_complete is False:
            all_polys_to_remove = unary_union(polys_to_remove_list)
            if all_polys_to_remove.geom_type == "Polygon":  # if it's all one big polygon now
                merged_polys_to_remove_list = [all_polys_to_remove]
            else:
                merged_polys_to_remove_list = list(all_polys_to_remove.geoms)

            convex_polys_to_remove_list = [shapely.convex_hull(x) for x in merged_polys_to_remove_list]

            if len(convex_polys_to_remove_list) == 1:
                polys_to_remove_complete = True
            elif unary_union(convex_polys_to_remove_list).geom_type == "MultiPolygon":
                # Note that if the unary union is a Polygon, then this next condition
                # below can't hold anyway and we want polys_to_remove_complete to remain
                # False.
                if len(unary_union(convex_polys_to_remove_list).geoms) == len(convex_polys_to_remove_list):
                    polys_to_remove_complete = True

            polys_to_remove_list = convex_polys_to_remove_list

        # Build an STRtree to use for finding intersecting geometries.
        g_spatial_index = STRtree(geometries_df["geometry"])
        g_index_by_iloc = dict((i, list(geometries_df.index)[i]) for i in range(len(geometries_df)))

        for a_ind in range(len(polys_to_remove_list)):
            poly_to_remove = polys_to_remove_list[a_ind]

            # Identify geometries that might intersect this polygon.
            possible_geom_integer_indices = [*set(numpy.ndarray.flatten(g_spatial_index.query(poly_to_remove)))]
            possible_geom_indices = [g_index_by_iloc[k] for k in possible_geom_integer_indices]

            # Use the boundaries of these geometries together with the boundary of the disk to
            # polygonize and divide geometries into pieces inside and outside the disk.
            boundaries = [geometries_df["geometry"][i].boundary for i in possible_geom_indices]
            boundaries.append(LineString(list(poly_to_remove.exterior.coords)))

            boundaries_exploded = []
            for geom in boundaries:
                if geom.geom_type == "LineString":
                    boundaries_exploded.append(geom)
                elif geom.geom_type == "MultiLineString":
                    boundaries_exploded += list(geom.geoms)
            boundaries_union = shapely.node(MultiLineString(boundaries_exploded))

            pieces_df = GeoDataFrame(columns=["polygon indices"],
                                     geometry=GeoSeries(list(polygonize(boundaries_union))),
                                     crs=geometries_df.crs)

            # Associate the pieces to the main geometries.  (Note that if there are
            # gaps, some pieces may be unassigned.)
            for i in pieces_df.index:
                pieces_df["polygon indices"][i] = set()

            for i in pieces_df.index:
                temp_possible_geom_integer_indices = [*set(numpy.ndarray.flatten(g_spatial_index.query(pieces_df["geometry"][i])))]
                temp_possible_geom_indices = [g_index_by_iloc[k] for k in temp_possible_geom_integer_indices]

                for j in temp_possible_geom_indices:
                    if pieces_df["geometry"][i].representative_point().intersects(geometries_df["geometry"][j]):
                        pieces_df["polygon indices"][i] = pieces_df["polygon indices"][i].union({j})

            # Now rebuild the disk from the pieces that are inside the circle, and drop them from
            # pieces_df.  Then we'll give the pieces outside the circle back to the geometries that they came from.

            poly_to_remove_refined = Polygon()

            pieces_df_indices_to_drop = []
            for p_ind in pieces_df.index:
                if pieces_df["geometry"][p_ind].representative_point().intersects(poly_to_remove):
                    poly_to_remove_refined = unary_union([poly_to_remove_refined, pieces_df["geometry"][p_ind]])
                    pieces_df_indices_to_drop.append(p_ind)
            if len(pieces_df_indices_to_drop) > 0:
                pieces_df = pieces_df.drop(pieces_df_indices_to_drop)

            for g_ind in possible_geom_indices:
                geometries_df["geometry"][g_ind] = Polygon()

            for p_ind in pieces_df.index:
                if len(pieces_df["polygon indices"][p_ind]) == 1:  # Note that it won't be >1 if the file is clean!
                    this_poly_ind = list(pieces_df["polygon indices"][p_ind])[0]
                    this_piece = pieces_df["geometry"][p_ind]
                    if this_poly_ind in possible_geom_indices:
                        # This check is needed because the geometries in possible_geom_incides can form a
                        # non-simply-connected region, in which case the interior holes - which may consist
                        # of multiple geometries each - may be assigned someplace they shouldn't be!
                        geometries_df["geometry"][this_poly_ind] = unary_union([geometries_df["geometry"][this_poly_ind], this_piece])

            # Find the boundary arcs between geometries and poly_to_remove_refined (and make sure each arc is a connected piece):
            possible_geoms = geometries_df.loc[possible_geom_indices]
            poly_to_remove_boundaries_df = intersections(GeoDataFrame(geometry=GeoSeries([poly_to_remove_refined], crs=geometries_df.crs)), possible_geoms, output_type="geodataframe")

            for b_ind in poly_to_remove_boundaries_df.index:
                if poly_to_remove_boundaries_df["geometry"][b_ind].geom_type == "MultiLineString":
                    poly_to_remove_boundaries_df["geometry"][b_ind] = linemerge(poly_to_remove_boundaries_df["geometry"][b_ind])

            poly_to_remove_boundaries_df = poly_to_remove_boundaries_df.explode(index_parts=False).reset_index(drop=True)
            poly_to_remove_centroid_coords = poly_to_remove_refined.centroid.coords[0]

            # For each boundary arc, create a "pie wedge" from the center of poly_to_remove_refined
            # subtending this arc.  (Since the polygon is convex, these are guaranteed to piece
            # together nicely.)
            for b_ind in poly_to_remove_boundaries_df.index:
                boundary_arc_coords = list(poly_to_remove_boundaries_df["geometry"][b_ind].coords)
                boundary_wedge_coords = boundary_arc_coords + [poly_to_remove_centroid_coords]

                g_ind = poly_to_remove_boundaries_df["target"][b_ind]

                geometries_df["geometry"][g_ind] = unary_union([geometries_df["geometry"][g_ind], Polygon(boundary_wedge_coords)])

    return geometries_df


def construct_hole_boundaries(geometries_df, holes_df):
    """
    Construct a GeoDataFrame with all positive-length intersections between hole
    and geometry boundaries, including intersections between hole boundaries and
    exterior boundaries, if applicable.
    """
    geometries_df = geometries_df.copy()
    holes_df = holes_df.copy()

    # Be sure gaps are correctly oriented:
    for h_ind in holes_df.index:
        holes_df.geometry[h_ind] = orient(holes_df.geometry[h_ind])

    # Do this WITHOUT using geometric intersection operations, which seem to be prone to
    # inexplicable rounding errors (GEOS bugs?)
    # Start by constructing an STRtree to find geometries that may intersect gaps.

    g_spatial_index = STRtree(geometries_df["geometry"])
    g_index_by_iloc = dict((i, list(geometries_df.index)[i]) for i in range(len(geometries_df)))

    # Initialize the geodataframe for the gap boundaries
    hole_boundaries_df = GeoDataFrame(columns=["source", "target"], geometry=GeoSeries([]), crs=geometries_df.crs)

    # For each gap and each geometry that it might possibly intersect, find all
    # common LineStrings in their boundaries (if any) and take their unary union to
    # construct the appropriate boundary between them.  (Note that this requires paying
    # VERY careful attention to orientations!)
    for h_ind in holes_df.index:
        this_hole = holes_df["geometry"][h_ind]
        this_hole_segments = segments(this_hole.boundary)
        this_hole_segments_used = []

        possible_geom_integer_indices = [*set(numpy.ndarray.flatten(g_spatial_index.query(holes_df["geometry"][h_ind])))]
        possible_geom_indices = [g_index_by_iloc[k] for k in possible_geom_integer_indices]

        for g_ind in possible_geom_indices:

            this_geom = geometries_df["geometry"][g_ind]
            if this_geom.geom_type == "Polygon":
                this_geom_geoms = [orient(this_geom)]
            elif this_geom.geom_type == "MultiPolygon":
                this_geom_geoms = [orient(geom) for geom in this_geom.geoms]

            this_geom_boundary_components = []
            for geom in this_geom_geoms:
                this_geom_boundary = geom.boundary
                if this_geom_boundary.geom_type == "LineString":
                    this_geom_boundary_components += [this_geom_boundary]
                elif this_geom_boundary.geom_type == "MultiLineString":
                    this_geom_boundary_components += list(this_geom_boundary.geoms)

            this_geom_segments = set()
            for component in this_geom_boundary_components:
                this_geom_segments = this_geom_segments.union(set(segments(component)))

            this_hole_this_geom_segments = [segment for segment in this_hole_segments if (segment in this_geom_segments or shapely.reverse(segment) in this_geom_segments)]

            if len(this_hole_this_geom_segments) > 0:

                this_hole_segments_used += this_hole_this_geom_segments
                this_hole_boundary_df = GeoDataFrame(geometry=GeoSeries([linemerge(this_hole_this_geom_segments)]), crs=geometries_df.crs)
                this_hole_boundary_df.insert(0, "source", h_ind)
                this_hole_boundary_df.insert(1, "target", g_ind)

                hole_boundaries_df = pandas.concat([hole_boundaries_df, this_hole_boundary_df]).reset_index(drop=True)

        # Finally, check for any exterior boundary:
        if len(this_hole_segments) > len(this_hole_segments_used):
            exterior_segments = [segment for segment in this_hole_segments if segment not in this_hole_segments_used]
            this_hole_exterior_boundary_df = GeoDataFrame(geometry=GeoSeries([linemerge(exterior_segments)]), crs=geometries_df.crs)
            this_hole_exterior_boundary_df.insert(0, "source", h_ind)
            this_hole_exterior_boundary_df.insert(1, "target", -1)
            hole_boundaries_df = pandas.concat([hole_boundaries_df, this_hole_exterior_boundary_df]).reset_index(drop=True)

    hole_boundaries_df = hole_boundaries_df.explode(index_parts=False).reset_index(drop=True)

    return hole_boundaries_df


def incenter(triangle):
    """
    Find the incenter (intersection point of the angle bisectors) of a triangle.
    """
    triangle_vertices = triangle.boundary.coords
    triangle_segments = segments(triangle.boundary)

    if len(triangle_segments) != 3:
        raise TypeError("Input must be a triangle!")

    x_a = triangle_vertices[0][0]
    y_a = triangle_vertices[0][1]
    x_b = triangle_vertices[1][0]
    y_b = triangle_vertices[1][1]
    x_c = triangle_vertices[2][0]
    y_c = triangle_vertices[2][1]
    a = triangle_segments[1].length
    b = triangle_segments[2].length
    c = triangle_segments[0].length

    # The incenter will be a weighted average of the coordinates of the vertices,
    # with coefficients proportional to a,b,c.

    alpha = a/(a + b + c)
    beta = b/(a + b + c)
    gamma = c/(a + b + c)

    x_i = alpha*x_a + beta*x_b + gamma*x_c
    y_i = alpha*y_a + beta*y_b + gamma*y_c

    # Occasionally for very tiny triangles, rounding errors produce a point not
    # contained in the triangle.  In this case, replace the computed point with
    # the nearest vertex of the triangle.
    if not triangle.contains(Point(x_i, y_i)):
        point_to_return = nearest_points(Point(x_i, y_i), MultiPoint([Point(x_a, y_a), Point(x_b, y_b), Point(x_c, y_c)]))[1]
    else:
        point_to_return = Point(x_i, y_i)

    return point_to_return


def triangulate_polygon(polygon):
    """
    Triangulate a not-necessarily-convex simple polygon, based on the ear clipping
    method.
    """

    triangles = []
    poly = polygon

    while len(segments(poly.boundary)) > 3:
        poly_vertices = list(extract_unique_points(poly).geoms)

        # Find an ear to cut from the polygon and add it to the list of triangles.
        for i in range(len(poly_vertices)):
            triangle_to_check = Polygon([poly_vertices[i-1], poly_vertices[i], poly_vertices[i+1]])
            if poly.contains(triangle_to_check) and LineString([poly_vertices[i-1], poly_vertices[i+1]]).intersection(poly.boundary).difference(MultiPoint([poly_vertices[i-1], poly_vertices[i+1]])).is_empty:
                triangles.append(triangle_to_check)
                poly = poly.difference(triangle_to_check)
                break

    # Remaining polygon is now a triangle, so add it to the list.
    triangles.append(poly)

    return triangles


def shortest_path_in_polygon(polygon, start, end, full_triangulation=None):
    """
    Finds the shortest path between any two vertices in a not-necessarily-convex
    simple polygon.  The polygon must be valid and simply connected,
    and "start" and "end" must be vertices of the polygon.

    Optional input full_triangulation allows triangulation to be computed in
    advance to avoid repetition when multiple paths need to be computed within
    the same polygon.
    """
    if not (polygon.is_valid and polygon.geom_type == "Polygon"):
        raise TypeError("shortest_path_in_polygon: Input polygon must be a valid Polygon.")
    if not extract_unique_points(polygon).contains(MultiPoint([start, end])):
        raise TypeError("shortest_path_in_polygon: Start and end points must be vertices of the polygon.")

    # First check for the easy case: If the line segment between the start and end points is
    # contained in the polygon, then that's the shortest path.  (And the rest of the algorithm
    # won't work correctly because the simplified polygon will degenerate.)

    if polygon.contains(LineString([start, end])) or polygon.boundary.contains(LineString([start, end])):
        return [start, end]

    else:
        # First make sure the polygon is oriented so that we're clear on what
        # "left" and "right" mean.
        polygon = orient(polygon)

        # Create two paths around polygon.boundary to the start and end points, oriented
        # appropriately.
        boundary_points = list(extract_unique_points(polygon.boundary).geoms)
        start_index = boundary_points.index(start)
        end_index = boundary_points.index(end)
        if start_index < end_index:
            path_1 = LineString(boundary_points[start_index:end_index+1])
            path_2 = LineString(boundary_points[end_index:] + boundary_points[0:start_index+1])
        else:
            path_1 = LineString(boundary_points[start_index:] + boundary_points[0:end_index+1])
            path_2 = LineString(boundary_points[end_index:start_index+1])

        if (extract_unique_points(path_1).geoms[0] == start) and (extract_unique_points(path_2).geoms[0] == end):
            right_path = path_1
            left_path = shapely.reverse(path_2)

        elif (extract_unique_points(path_2).geoms[0] == start) and (extract_unique_points(path_1).geoms[0] == end):
            right_path = path_2
            left_path = shapely.reverse(path_1)

        right_path_points = list(extract_unique_points(right_path).geoms)
        left_path_points = list(extract_unique_points(left_path).geoms)

        # Now triangulate the polygon, but only keep the triangles that have one vertex
        # in each of the right and left paths (not counting the starting and ending points)
        # in order to create a "sleeve" for the shortest path.
        if full_triangulation is None:
            full_triangulation = triangulate_polygon(polygon)

        triangulation = []
        for triangle in full_triangulation:
            if not triangle.boundary.intersection(MultiPoint(right_path_points[1:-1])).is_empty and not triangle.boundary.intersection(MultiPoint(left_path_points[1:-1])).is_empty:
                triangulation.append(triangle)

        # Put the triangles for the sleeve in the correct order:
        initial_triangle = [triangle for triangle in triangulation if start in extract_unique_points(triangle.boundary).geoms][0]

        ordered_triangulation = [initial_triangle]
        triangulation.remove(initial_triangle)

        while len(triangulation) > 0:
            leading_triangle = ordered_triangulation[-1]
            next_triangle = [triangle for triangle in triangulation if leading_triangle.intersection(triangle).geom_type == "LineString"][0]
            ordered_triangulation.append(next_triangle)
            triangulation.remove(next_triangle)

        # Regard the sleeve given by the union of these triangles as the "simplified"
        # polygon; the shortest path must be contained in this simplfied polygon.
        polygon_simplified = unary_union(ordered_triangulation)

        # Now use the ordered triangulation to order the vertices of the simplified polygon,
        # as well as the left and right paths restricted to the simplified polygon.
        ordered_path_vertices = [start]
        right_path_simplified_points = [start]
        left_path_simplified_points = [start]

        for triangle in ordered_triangulation:
            this_triangle_vertices = set(extract_unique_points(triangle.boundary).geoms)
            this_triangle_new_vertices = this_triangle_vertices.difference(set(ordered_path_vertices))
            ordered_path_vertices = ordered_path_vertices + list(this_triangle_new_vertices)
            for vertex in this_triangle_new_vertices:
                if vertex in right_path_points:
                    right_path_simplified_points.append(vertex)
                if vertex in left_path_points:
                    left_path_simplified_points.append(vertex)

        # Initialize the found_shortest_path and the left and right funnel edges:
        found_shortest_path = [start]

        left_funnel = [left_path_simplified_points[0], left_path_simplified_points[1]]
        right_funnel = [right_path_simplified_points[0], right_path_simplified_points[1]]

        # We've already used the first 3 points on this list, so take them out.
        ordered_path_vertices = ordered_path_vertices[3:]

        # Now find the shortest path!
        for point in ordered_path_vertices:
            apex = found_shortest_path[-1]

            if point in left_path_simplified_points:
                this_funnel = left_funnel
                other_funnel = right_funnel
                reflex_sign = 1
            elif point in right_path_simplified_points:
                this_funnel = right_funnel
                other_funnel = left_funnel
                reflex_sign = -1

            # Start by checking whether this point can see the apex, and if so, the
            # apex becomes the new predecessor on this funnel.
            # Otherwise, find the first point on this funnel that can see point,
            # and check whether this is a *reflex* vertex.  If so, cut off the rest
            # of this funnel and add point to it.  If not, find the first seen
            # vertex on the *other* funnel; it's guaranteed to be reflex.  Make it
            # the new apex, and add the other funnel up to this point to
            # found_shortest_path.
            if polygon_simplified.contains(LineString([apex, point])) or polygon_simplified.boundary.contains(LineString([apex, point])):
                this_funnel = [apex, point]

            else:
                for i in range(1, len(this_funnel)):
                    if polygon_simplified.contains(LineString([this_funnel[i], point])) or polygon_simplified.boundary.contains(LineString([this_funnel[i], point])):
                        first_seen = i
                        break

                seg1 = list(LineString([this_funnel[first_seen-1], this_funnel[first_seen]]).coords)
                seg2 = list(LineString([this_funnel[first_seen], point]).coords)

                vec1 = (seg1[1][0] - seg1[0][0], seg1[1][1] - seg1[0][1])
                vec2 = (seg2[1][0] - seg2[0][0], seg2[1][1] - seg2[0][1])

                cross_prod = vec1[0]*vec2[1] - vec1[1]*vec2[0]

                if cross_prod*reflex_sign >= 0:
                    # If this vertex is reflex:
                    this_funnel = this_funnel[0:first_seen+1] + [point]
                else:
                    first_seen = min(i for i in range(1, len(other_funnel)) if polygon_simplified.contains(LineString([other_funnel[i], point])) or polygon_simplified.boundary.contains(LineString([other_funnel[i], point])))
                    found_shortest_path += other_funnel[1: first_seen+1]
                    apex = other_funnel[first_seen]
                    this_funnel = [apex, point]
                    other_funnel = other_funnel[first_seen:]

            # Reassign this_funnel and other_funnel to left_funnel and right_funnel:
            if point in left_path_simplified_points:
                left_funnel = this_funnel
                right_funnel = other_funnel
            elif point in right_path_simplified_points:
                right_funnel = this_funnel
                left_funnel = other_funnel

        # Still need to complete the path by adding the portion from the current apex to
        # the endpoint:
        found_shortest_path += left_funnel[1:]

        return found_shortest_path


def convexify_hole_boundaries(geometries_df, holes_df):
    """
    Partially fill gaps as follows:
    (1) Assign any gap that only adjoins 1 geometry to that geometry.
    (2) For each gap that adjoins at least 2 geometries, "convexify" the geometries
        surrounding the gap by replacing the gap's boundary with each geometry by the
        shortest path within the gap between its endpoints and "filling in" the
        geometry up to the new boundary. (Exterior boundaries, if any, are left alone.)
    If there are only 2 non-exterior (and no exterior) geometries intersecting
    the gap, this will fill the gap completely; otherwise it will usually leave one or
    more smaller gaps remaining.  The convexity of the geometry boundaries will simplify
    the process of filling the remaining gap(s).
    """
    geometries_df = geometries_df.copy()
    holes_df = holes_df.copy()

    completed_holes_df = GeoDataFrame(columns=["region"], geometry=GeoSeries([]), crs=holes_df.crs)

    if len(holes_df) > 0:
        holes_to_process = deque(list(holes_df["geometry"]))
        this_region = list(holes_df["region"])[0]  # All holes in this dataframe should be from the same region
        if this_region is None:
            pbar = tqdm(desc="Gaps to simplify", total=len(holes_to_process))
        else:
            pbar = tqdm(desc=f"Gaps to simplify in region {this_region}", total=len(holes_to_process))
    else:
        holes_to_process = deque([])
        pbar = tqdm(desc="Gaps to simplify", total=len(holes_to_process))

    while len(holes_to_process) > 0:
        pbar_increment = 1
        this_hole = holes_to_process.popleft()
        this_hole_df = GeoDataFrame(geometry=GeoSeries([this_hole]), crs=holes_df.crs)
        this_hole_boundaries_df = construct_hole_boundaries(geometries_df, this_hole_df)

        # Take care of some trivial cases:
        if len(set(this_hole_boundaries_df["target"]).difference({-1})) == 0:
            # This is probably a small component of a region that isn't assigned to
            # any geometry in that region. Just leave it alone and let it be a hole.
            if this_region is not None:
                print("Found a component of the region at index", this_region, "that does not intersect any geometry assigned to that region.")

        elif len(set(this_hole_boundaries_df["target"]).difference({-1})) == 1:
            # Attach the hole to the unique non-exterior geometry that it intersects:
            poly_to_add_to = list(set(this_hole_boundaries_df["target"]).difference({-1}))[0]
            geometries_df["geometry"][poly_to_add_to] = unary_union([geometries_df["geometry"][poly_to_add_to], this_hole])

        else:
            # Each remaining hole intersects at least 2 geometries nontrivially.
            # "Convexify" the geometries surrounding this hole by replacing the
            # boundary with each geometry by the shortest path within the hole
            # between its endpoints and "filling in" the geometry up to the
            # new boundary. (Exterior boundaries, if any, should be left alone.)

            # In cases where there are 2 or more boundaries with the same target
            # geometry, we'll need to check to see whether they end up adjacent
            # after convexifying.  If they do, their UNION isn't guaranteed to be
            # convexified at the end, so we'll put that hole back in the queue for
            # another round of processing.
            if len(set(this_hole_boundaries_df["target"])) == len(this_hole_boundaries_df):
                target_repetition = False
            else:
                target_repetition = True
                repeated_targets = []
                for target in set(this_hole_boundaries_df["target"]):
                    boundaries_this_target = this_hole_boundaries_df[this_hole_boundaries_df["target"] == target]
                    if len(boundaries_this_target) > 1:
                        repeated_targets.append((target, len(boundaries_this_target)))

            new_hole_in_progress = this_hole
            this_hole_triangulation = triangulate_polygon(new_hole_in_progress)

            for thb_ind in this_hole_boundaries_df.index:
                thb = this_hole_boundaries_df["geometry"][thb_ind]
                this_geom = this_hole_boundaries_df["target"][thb_ind]

                if this_geom != -1:
                    start = list(extract_unique_points(thb).geoms)[0]
                    end = list(extract_unique_points(thb).geoms)[-1]

                    sp = LineString(shortest_path_in_polygon(this_hole, start, end, full_triangulation=this_hole_triangulation))

                    piece_to_add_boundary = unary_union([thb, sp])
                    if piece_to_add_boundary.geom_type == "MultiLineString":
                        piece_to_add_boundary = linemerge(piece_to_add_boundary)

                    piece_to_add = unary_union(polygonize(piece_to_add_boundary))
                    geometries_df["geometry"][this_geom] = unary_union([geometries_df["geometry"][this_geom], piece_to_add])
                    new_hole_in_progress = new_hole_in_progress.difference(piece_to_add)

            if not new_hole_in_progress.is_empty:
                if new_hole_in_progress.geom_type == "Polygon":
                    new_holes = [new_hole_in_progress]
                elif new_hole_in_progress.geom_type == "MultiPolygon":
                    new_holes = list(new_hole_in_progress.geoms)

                for new_hole in new_holes:
                    new_hole = orient(new_hole)
                    new_hole_df = GeoDataFrame(geometry=GeoSeries([new_hole]), crs=holes_df.crs)
                    new_hole_df.insert(0, "region", this_region)

                    if target_repetition:
                        # Check to see whether the target that was repeated in the original
                        # hole boundaries has fewer (but not zero!) hole boundaries
                        # associated to it in this hole.  If so, some distinct boundaries
                        # may have been concatenated after convexifying, resulting in a
                        # non-convex boundary - so put the hole back in the queue for
                        # another round of processing.
                        new_hole_boundaries_df = construct_hole_boundaries(geometries_df, new_hole_df)
                        reprocess_hole = False
                        for target in repeated_targets:
                            new_boundaries_this_target = new_hole_boundaries_df[new_hole_boundaries_df["target"] == target[0]]
                            if len(new_boundaries_this_target) > 0 and len(new_boundaries_this_target) < target[1]:
                                reprocess_hole = True
                                break
                        if reprocess_hole:
                            holes_to_process.append(new_hole)
                        else:
                            completed_holes_df = pandas.concat([completed_holes_df, new_hole_df]).reset_index(drop=True)
                    else:
                        completed_holes_df = pandas.concat([completed_holes_df, new_hole_df]).reset_index(drop=True)

        pbar.update(pbar_increment)

    pbar.close()

    return geometries_df, completed_holes_df
