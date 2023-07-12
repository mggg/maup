import math
import pandas
import geopandas
from geopandas import GeoSeries, GeoDataFrame

import functools

import numpy

import shapely 
from shapely import make_valid 
from shapely.ops import unary_union, split, polygonize, linemerge
from shapely.geometry import Polygon, MultiPolygon, Point, MultiPoint, LineString, MultiLineString
from shapely.strtree import STRtree

from .adjacencies import adjacencies
from .assign import assign_to_max
from .crs import require_same_crs
from .indexed_geometries import get_geometries
from .intersections import intersections
from .progress_bar import progress

from itertools import combinations
from math import sqrt

import warnings; warnings.filterwarnings('ignore', 'GeoSeries.isna', UserWarning)

pandas.options.mode.chained_assignment = None



"""
Here we define a function "autorepair" that takes a GeoDataFrame and:

(1) Resolves all overlaps.

(2) (optionally) Closes all gaps; default is fill_holes = True.

(3) (optionally) Replaces all rook adjacencies with length below a 
    user-specified threshold with queen adjacencies. Default is 
    min_rook_length = None; this step will be skipped unless a
    length threshold is provided.

Note that (2) and (3) are optional but (1) is not!  The procedure for (1)
produces a clean tiling of the region that is necessary for the procedures
in (2) and (3) to work properly.  (If the region is already free of overlaps,
Step (1) won't change anything.)

The algorithm differs significantly from that the original maup version and 
avoids the small floating point errors that tend to occur there.  
(HOW, I HEAR YOU ASK???)

Here's what happens in the original maup version (or really in shapely): 
When two line segments L1, L2 intersect, their point of intersection P is a 
rational function of the coordinates of their endpoints.  In general, these 
coordinates don't have an exact floating point expression and so must be 
approximated.  (In this case, if you ask shapely whether P is contained in
either L1 or L2, it will tell you no!) So P becomes a new vertex on the 
polygon that defines the overlap/hole, but it is not (quite) contained in the 
boundaries of the polygons whose intersection created it.  This discrepancy 
is what ends up leaving behind small overlaps even when they have all 
theoretically been removed.

Additionally, shapely has a rare (but not rare enough!) bug where computing 
the difference between a large polygon and a very small one completely (or
almost completely) obliterates the large one.  THIS IS NOT OKAY!
(Edit: I don't know whether this bug has been resolved in shapely 2.)

In order to avoid both of these issues, these procedures have been completely
redesigned so that no intersections or differences between polygons are ever
used during the construction process. (They are, however, used to identify 
adjacencies; I don't think there's any way around that.)  
1-dimensional intersections between polygon *boundaries* ARE used, but not 
transverse intersections, and not in any way that looks for any interior 
intersection points between the endpoints of line segments, so
the floating point approximation issue doesn't come up.

The result is a completely clean GeoDataFrame with NO overlaps, gaps, or rook
adjacencies below the length threshold!  If unusual topology interferes with
any of this, warning messages will alert the user to specific places that 
should be looked at with human eyes.

Brief sketch of the new overlap-resolution algorithm:

(1) Take the unary union of all the polygon boundaries.  This produces a 
    huge MultiLineString, and the unary_union function does the VERY slick 
    trick of adding those (approximate) points of intersection to the
    LineStrings that should contain them.  (THIS IS HOW THE MAGIC HAPPENS!)

(2) Polygonize this structure. This will produce a set of polygons ("pieces") 
    that give a clean geometric partition of the region, with no gaps or 
    overlaps between them.  Every polygon in this set is the intersection of 
    zero or more polygons from the original GeoDataFrame, with very small
    adjustments resulting from the addition of intersection points to the
    polygon boundaries.  (Pieces where zero polygons "intersect" correspond 
    to holes in the original geometry.)

(3) Choose a representative point in the interior of each piece and identify 
    all the original polygons that contain it.  (Using a representative point
    rather than checking for full containment avoids errors that would result 
    from the polygons having changed slightly!)  This will allow us to identify 
    exactly which polygons from the original geometry intersected to produce 
    that piece.

(4) Re-organize the info in (3) into separate GeoDataFrames according to the 
    degree of the overlap.  This will produce a list of GeoDataFrames, one for 
    intersections of each degree that occurs (including degree 1), plus another 
    GeoDataFrame consisting of all the holes.

(5) Rebuild the polygons from the pieces, using the data in (4). Overlaps are
    assigned to parent polygons, first to resolve any connectivity issues, and 
    then by largest shared perimeter.


Brief sketch of the new gap-closing algorithm:

(1) For any hole whose boundary touches 3 or fewer polygons, attach it to the
    polygon with which it shares the greatest perimeter.  (Doesn't really matter;
    in practice holes have very small area, and adjacency relationships won't be
    affected regardless of where we attach it.)

(2) For a hole whose boundary touches 4 or more polygons, find the pair of 
    non-adjacent polygons with the shortest distance between them.  Cut out a
    piece of the hole and use it to attach these two polygons with a boundary
    segment of positive length.  (This is a "best guess" for when two polygons
    on opposite sides of a long, thin gap should really be adjacent.)
    This leaves behind two new holes, each with strictly fewer boundary
    polygons than the original.

(3) Repeat until all holes are filled.


Brief sketch of the new rook-to-queen algorithm:

Let L be a linestring with length below the specified threshold.

(1) Construct a small disk D that contains the linestring within its interior.
    Find all polygons P_1, ..., P_k that intersect D.  

(2) Take the unary_union of all the boundaries of P_1, ..., P_k, and D, and
    polygonize this structure.  Assign all pieces outside of D to the polygons
    that they came from, and assign the pieces inside D to D.  (This is 
    equivalent to taking the difference of each polygon minus D, except that
    it works cleanly and reliably!)

(3) For each of the polygons whose boundary (now) contains an arc of D's boundary
    circle, create a "pie wedge" inside D subtending this arc, and join it to    
    the polygon that it shares a boundary with.
    
"""





# Some useful short functions:

# Count the number of connected components of a shapely object:
def num_components(geom):  
    if geom.is_empty:
        return 0
    elif (geom.geom_type == "Polygon") or (geom.geom_type == "Point") or (geom.geom_type == "LineString"):
        return 1
    elif (geom.geom_type == "MultiPolygon") or (geom.geom_type == "MultiLineString") or (geom.geom_type == "GeometryCollection"):
        return len(geom.geoms) 




"""
MAIN FUNCTION
"""

def autorepair(geometries0_df, fill_gaps = True, min_rook_length = None, 
                  holes_to_keep = None):
    
    if isinstance(geometries0_df, geopandas.GeoDataFrame) == False:
        raise TypeError(f"Input must be a GeoDataFrame!")
        
    geometries_df = geometries0_df.copy()
    
    # Ensure that geometries are 2-D and not 3-D!
    for i in geometries_df.index:
        geometries_df["geometry"][i] = shapely.wkb.loads(
            shapely.wkb.dumps(geometries_df["geometry"][i], output_dimension=2))
            
    # Warn if crs is geographic:
    if geometries_df.crs is not None:
        if geometries_df.crs.is_geographic:
            warnings.warn("Geometry is in a geographic CRS. Results from 'length' are likely incorrect. Use 'GeoSeries.to_crs()' to re-project geometries to a projected CRS before this operation.")

    # If holes_to_keep and/or overlaps_to_keep are present, require them to have the
    # same CRS as the main shapefile.
    if holes_to_keep is not None: 
        if holes_to_keep.crs != geometries_df.crs:
            raise Exception("holes_to_keep must be in the same CRS as the shapefile being repaired.")


    
    # Construct data about overlaps of all orders, plus holes.
    overlap_tower, holes_df = building_blocks(geometries_df)

    # Use data from the overlap tower to rebuild precincts with no overlaps.
    print("Resolving overlaps...")
    reconstructed_df = reconstruct_from_overlap_tower(geometries_df, overlap_tower)

    # Use data about the holes to fill holes if desired.
    if fill_gaps == True:
        print("Closing gaps...")
        reconstructed_df = close_gaps(reconstructed_df, holes_df)
        
    
    # Check for precincts that have become (more) disconnected, generally with an extra 
    # component of negligible area.  If any are found and the area is negligible,
    # reassign to an adjacent precinct by shared perimeter.  
    # If the area is not negligible, leave it alone and report it so that a human
    # can decide what to do about it!
    
    disconnected_df = reconstructed_df[reconstructed_df["geometry"].apply(lambda x: x.geom_type != "Polygon")] 
    # This will include precincts that were disconnected in the original; need to 
    # filter by whether they got worse.
    
    if len(disconnected_df) > 0:
        disconnected_poly_indices = []
        for ind in disconnected_df.index:
            if num_components(reconstructed_df["geometry"][ind]) > num_components(geometries0_df["geometry"][ind]):
                disconnected_poly_indices.append(ind)
                
        if len(disconnected_poly_indices) > 0: # These are the ones (if any) that got worse.
            geometries = get_geometries(reconstructed_df)
            spatial_index = STRtree(geometries)
            index_by_iloc = dict((i, list(geometries.index)[i]) for i in range(len(geometries.index))) # Build indexing dictionary 
            
            for g_ind in disconnected_poly_indices:
                excess = num_components(reconstructed_df["geometry"][g_ind]) - num_components(geometries0_df["geometry"][g_ind])
                
                component_num_list = [x for x in range(len(reconstructed_df["geometry"][g_ind].geoms))] 
                component_areas = []                                                                                    
                
                for c_ind in range(len(reconstructed_df["geometry"][g_ind].geoms)): 
                    component_areas.append((c_ind, reconstructed_df["geometry"][g_ind].geoms[c_ind].area)) 
                
                component_areas_sorted = sorted(component_areas, key=lambda tup: tup[1])
                
                big_area = max([reconstructed_df["geometry"][g_ind].area, geometries0_df["geometry"][g_ind].area])
                
                for i in range(excess): # Check that the ith smallest component has small enough area find a better polygon to add it to.
                    c_ind = component_areas_sorted[i][0]
                    this_fragment = reconstructed_df["geometry"][g_ind].geoms[c_ind]  
                    if component_areas_sorted[i][1] < 0.0001*big_area:  # Less than 0.01%
                        component_num_list.remove(c_ind) # Tells us to take out this component later
                        possible_intersect_integer_indices = [*set(numpy.ndarray.flatten(spatial_index.query(this_fragment)))]
                        possible_intersect_indices = [(index_by_iloc[k]) for k in possible_intersect_integer_indices] 
                        
                        shared_perimeters = []
                        for g_ind2 in possible_intersect_indices:
                            if g_ind2 != g_ind and not (this_fragment.boundary).intersection(reconstructed_df["geometry"][g_ind2].boundary).is_empty:
                                shared_perimeters.append((g_ind2, (this_fragment.boundary).intersection(reconstructed_df["geometry"][g_ind2].boundary).length))

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
                    print("WARNING: A component of the geometry at index ", g_ind, " was badly disconnected and redistributed to other polygons!")
                
    # We SHOULD be back to the correct number of components everywhere, but check again just to make sure!                

    disconnected_df_2 = reconstructed_df[reconstructed_df["geometry"].apply(lambda x: x.geom_type != "Polygon")] 
    
    if len(disconnected_df_2) > 0:
        for ind in disconnected_df_2.index:
            if num_components(reconstructed_df["geometry"][ind]) > num_components(geometries0_df["geometry"][ind]):
                print("WARNING: A component of the geometry at index ", ind, " may have been disconnected!")

    if min_rook_length is not None:
        # Find all inter-polygon boundaries shorter than min_rook_length and replace them
        # with queen adjacencies by manipulating coordinates of all surrounding polygon.
        print("Converting small rook adjacencies to queen...")
        reconstructed_df = small_rook_to_queen(reconstructed_df, min_rook_length)
        
    if holes_to_keep is not None:    
        holes_to_keep = get_geometries(holes_to_keep)
        
        reconstructed_spatial_index = STRtree(reconstructed_df["geometry"]) # Build STRtree for all the reconstructed geometries
        reconstructed_index_by_iloc = dict((i, list(reconstructed_df.index)[i]) for i in range(len(reconstructed_df)))  # Build indexing dictionary

        for keeper in holes_to_keep:
            possible_geom_integer_indices = [*set(numpy.ndarray.flatten(reconstructed_spatial_index.query(keeper)))]
            possible_geom_indices = [reconstructed_index_by_iloc[k] for k in possible_geom_integer_indices] 
            for g_ind in possible_geom_indices:
                reconstructed_df['geometry'][g_ind] = reconstructed_df['geometry'][g_ind].difference(keeper)
    
    return reconstructed_df
   

# SUPPORTING FUNCTIONS:

# Partition the region via ALL precinct boundaries, identify each polygon in the 
# partition according to which polygons in the original intersected to create it,
# and organize this data according to order of the overlaps.  (Order zero = hole)

def building_blocks(geometries0_df):
    if isinstance(geometries0_df, geopandas.GeoDataFrame) == False:
        raise TypeError(f"Input must be a GeoDataFrame!")

    geometries_df = geometries0_df.copy()
    
    # Make a list of all the boundaries of all the polygons. 
    # This won't work properly with multi-polygons, so explode first:
    
    boundaries = []
    geometries_exploded_df = geometries_df.explode(index_parts=False).reset_index(drop=True) 
    for i in geometries_exploded_df.index:
    
        boundaries.append(shapely.boundary(geometries_exploded_df["geometry"][i]))
    
    boundaries_union = unary_union(boundaries)
    
    # Create geodataframe with all the pieces created by overlaps of all orders, 
    # together with a set for each piece consisting of the polygons that created the overlap.

    pieces_df = geopandas.GeoDataFrame(columns = ["polygon indices"], 
                                geometry = geopandas.GeoSeries([geom for geom in polygonize(boundaries_union)]),
                                crs = geometries_df.crs)

    for i in pieces_df.index:
        pieces_df["polygon indices"][i] = set()
        
        
    g_spatial_index = STRtree(geometries_df["geometry"]) # Build STRtree for the main geometries
    g_index_by_iloc = dict((i, list(geometries_df.index)[i]) for i in range(len(geometries_df)))  # Build indexing dictionary

    print("Identifying overlaps...")
    for i in progress(pieces_df.index, len(pieces_df.index)): 
        possible_geom_integer_indices = [*set(numpy.ndarray.flatten(g_spatial_index.query(pieces_df["geometry"][i])))]
        possible_geom_indices = [g_index_by_iloc[k] for k in possible_geom_integer_indices]  
        
        for j in possible_geom_indices:
            if pieces_df["geometry"][i].representative_point().distance(geometries_df["geometry"][j]) == 0:
                pieces_df["polygon indices"][i] = pieces_df["polygon indices"][i].union({j})

    
    
    # Organize this info into separate gdf's for overlaps of all orders - including 
    # order zero, which corresponds to holes.
    # This will be easier if we temporarily add a column for overlap degree.
    
    overlap_degree_list = [len(x) for x in pieces_df["polygon indices"]] 
    pieces_df["overlap degree"] = overlap_degree_list
    
    # Here are the holes:
    
    holes_df = (pieces_df[pieces_df["overlap degree"] == 0]).reset_index(drop=True)
        
    # And here is a list of GeoDataFrames, one consisting of all overlaps of each order:
    
    overlap_tower = []  

    for i in range(max(pieces_df["overlap degree"])):
        overlap_tower.append(pieces_df[pieces_df["overlap degree"] == i+1])
    
    
    # Get rid of unnecessary column and reindex each GeoDataFrame:
    
    for i in range(len(overlap_tower)):
        del overlap_tower[i]["overlap degree"]
        overlap_tower[i] = overlap_tower[i].reset_index(drop=True)
        
    del holes_df["overlap degree"] 

    return overlap_tower, holes_df
        
    
# Rebuild the polygons with overlaps removed:

def reconstruct_from_overlap_tower(geometries0_df, overlap_tower0): 

    # We want to preserve all the shapefile columns from the original, but 
    # we're going to completely rebuild the geometry from scratch.
    
    geometries_df = geometries0_df.copy()
    overlap_tower = [df.copy() for df in overlap_tower0]
    
    geometries_df["geometry"] = Polygon()
    
    max_overlap_level = len(overlap_tower)

    # Start by assigning all order-1 pieces to the polygon they came from:
    
    for ind in overlap_tower[0].index:
        this_poly_ind = list(overlap_tower[0]["polygon indices"][ind])[0]
        this_piece = overlap_tower[0]["geometry"][ind]
        geometries_df["geometry"][this_poly_ind] = unary_union([geometries_df["geometry"][this_poly_ind], this_piece])

    # IMPORTANT: We need to know which geometries were disconnected by removing  
    # overlaps! Add columns for numbers of components in the original and refined 
    # geometries to each dataframe for future use.

    geometries_df["num components orig"] = 0
    geometries_df["num components refined"] = 0
        
    for ind in geometries_df.index:
        geometries_df["num components orig"][ind] = num_components(geometries0_df["geometry"][ind])
        geometries_df["num components refined"][ind] = num_components(geometries_df["geometry"][ind])

    # Now, start with the order-2 and gradually add overlaps at higher order until done.
    
    # IMPORTANT: First look for geometries at the top level that were disconnected 
    # by the refinement process, and give them first dibs at grabbing overlaps 
    # (regardless of perimeter!) until they are reconnected or run out of overlaps
    # to grab.  
    # (This doesn't always completely work; in rare cases a single overlap
    # can disconnect two polygons, and only one of them gets to grab it back.
    # This will be addressed at the end, within the main function.)

    geometries_disconnected_df = geometries_df[geometries_df["num components refined"] > geometries_df["num components orig"]]

    for i in range(1, max_overlap_level):
        overlaps_df = overlap_tower[i]  
        overlaps_df_unused_indices = overlaps_df.index.tolist() 
            # Need to make sure each overlap only gets used once!
        
        o_spatial_index = STRtree(overlaps_df["geometry"]) # Build STRtree for the overlaps
        o_index_by_iloc = dict((i, list(overlaps_df.index)[i]) for i in range(len(overlaps_df))) # Build indexing dictionary
        
        for g_ind in geometries_disconnected_df.index:
            possible_overlap_integer_indices = [*set(numpy.ndarray.flatten(o_spatial_index.query(geometries_disconnected_df["geometry"][g_ind])))]
            possible_overlap_indices_0 = [o_index_by_iloc[k] for k in possible_overlap_integer_indices]            
            possible_overlap_indices = list(set(possible_overlap_indices_0) & set(overlaps_df_unused_indices))

            
            geom_finished = False  # Only keep adding things until it gets connected again
            
            for o_ind in possible_overlap_indices: 
                # If the corresponding overlap intersects this geometry (and was 
                # contained in it originally!), grab it.
                
                if (geom_finished == False) and (g_ind in list(overlaps_df["polygon indices"][o_ind])) and (not geometries_disconnected_df["geometry"][g_ind].intersection(overlaps_df["geometry"][o_ind]).is_empty):
                    
                    if (geometries_disconnected_df["geometry"][g_ind].intersection(overlaps_df["geometry"][o_ind])).length > 0:
                        geometries_disconnected_df["geometry"][g_ind] = unary_union([
                            geometries_disconnected_df["geometry"][g_ind], overlaps_df["geometry"][o_ind]
                            ])
                        overlaps_df_unused_indices.remove(o_ind)
                        if num_components(geometries_disconnected_df["geometry"][g_ind]) == geometries_df["num components orig"][g_ind]:
                             geom_finished = True
        
            geometries_df["geometry"][g_ind] = geometries_disconnected_df["geometry"][g_ind]
                
            if geom_finished == True:
                geometries_disconnected_df = geometries_disconnected_df.drop(g_ind)
        
            # Okay, that's all we can do for the disconnected geometries at this level.
            # Go on to filling in the rest of the overlaps by greatest perimeter.


        g_spatial_index = STRtree(geometries_df["geometry"]) # Build STRtree for the main geometries
        g_index_by_iloc = dict((i, list(geometries_df.index)[i]) for i in range(len(geometries_df)))  # Build indexing dictionary

        print("Assigning order", i+1, "pieces...")
        for o_ind in progress(overlaps_df_unused_indices, len(overlaps_df_unused_indices)):
            this_overlap = overlaps_df["geometry"][o_ind]
            
            shared_perimeters = []
            
            possible_geom_integer_indices = [*set(numpy.ndarray.flatten(g_spatial_index.query(overlaps_df["geometry"][o_ind])))]
            possible_geom_indices = [g_index_by_iloc[k] for k in possible_geom_integer_indices]  

            
            for g_ind in possible_geom_indices:
                if (g_ind in list(overlaps_df["polygon indices"][o_ind])) and not (this_overlap.boundary).intersection(geometries_df["geometry"][g_ind].boundary).is_empty:
                    shared_perimeters.append((g_ind, (this_overlap.boundary).intersection(geometries_df["geometry"][g_ind].boundary).length))

            # This possibility came up in a previous version, but I hope it will be 
            # obsolete in this version!       
            if len(shared_perimeters) > 0:
                max_shared_perim = sorted(shared_perimeters, key=lambda tup: tup[1])[-1]
                poly_to_add_to = max_shared_perim[0]
                geometries_df["geometry"][poly_to_add_to] = unary_union(
                    [geometries_df["geometry"][poly_to_add_to], this_overlap])
            else:
                print("Couldn't find a polygon to glue a component of intersection ", o_ind, " to")
    

    reconstructed_df = geometries_df.copy()   
    
    del reconstructed_df["num components orig"] 
    del reconstructed_df["num components refined"]
        
    return reconstructed_df
    

    
    
# Close the gaps:

def close_gaps(geometries0_df, holes0_df):
    
    geometries_df = geometries0_df.copy()
    holes_df = holes0_df.copy()
    
    # Check whether there are any holes to fill:   
    if len(holes_df) == 0:
        fill_complete = True
    else:
        fill_complete = False
        
        
    
    while fill_complete == False:

        hole_boundaries_df = intersections(holes_df, geometries_df, output_type = "geodataframe") 
        # Note: all geometries here will (stupidly!) be MultiLineStrings; 
        # convert to LineStrings before exploding.
        
        for ind in hole_boundaries_df.index:
            if hole_boundaries_df["geometry"][ind].geom_type == "MultiLineString":
                hole_boundaries_df["geometry"][ind] = linemerge(hole_boundaries_df["geometry"][ind])

        hole_boundaries_df = hole_boundaries_df.explode(index_parts=False).reset_index(drop=True) 
        # All geometries here should be LineStrings, or occasionally Points.

        activity_this_round = False      # Keep track of whether there's still anything 
                                         # left to do

        new_holes = []                   # Holes that will be created by partial fills 
                                         # to add before next round
                                         
        for h_ind in progress(holes_df.index, len(holes_df.index)):
             
            this_hole = holes_df["geometry"][h_ind]
            this_hole_boundaries_df = hole_boundaries_df[hole_boundaries_df["source"] == h_ind]
            
            if len(set(this_hole_boundaries_df["target"])) <= 3:  # Fill the hole!
                
                shared_perimeters = []
                
                for b_ind in this_hole_boundaries_df.index:
                    g_ind = this_hole_boundaries_df["target"][b_ind]
                    shared_perimeters.append((b_ind, (this_hole.boundary).intersection(geometries_df["geometry"][g_ind].boundary).length))
                
                max_shared_perim = sorted(shared_perimeters, key=lambda tup: tup[1])[-1]
                poly_to_add_to = this_hole_boundaries_df["target"][max_shared_perim[0]]
                
                geometries_df["geometry"][poly_to_add_to] = unary_union(
                    [geometries_df["geometry"][poly_to_add_to], this_hole])
                holes_df = holes_df.drop(h_ind)

                activity_this_round = True
                
            else:  # Partially fill the hole!  
                
                poly_to_add_to, piece_to_connect, new_holes_this_time = partial_fill_data(this_hole, this_hole_boundaries_df)
                                    
                if poly_to_add_to is not None:
                    # If a relative threshold is set, check that the piece to connect is 
                    # under the threshold relative to poly_to_add_to before adjoining it 
                    # to the polygon.  
                    geometries_df["geometry"][poly_to_add_to] = unary_union(
                        [geometries_df["geometry"][poly_to_add_to], piece_to_connect])
                    holes_df = holes_df.drop(h_ind)
                    
                  
                for k in range(len(new_holes_this_time)):
                    new_holes.append(new_holes_this_time[k])
                
                    activity_this_round = True
                    
        if activity_this_round == True: # Add any new holes for the next round!
            for k in range(len(new_holes)):
            
                hole_to_append_df = geopandas.GeoDataFrame(columns = ["polygon indices"], 
                                geometry = geopandas.GeoSeries([new_holes[k]]),
                                crs = geometries_df.crs)
                hole_to_append_df["polygon indices"][0] = set()
                
                holes_df = pandas.concat([holes_df, hole_to_append_df], ignore_index=True)
                holes_df.reset_index(drop=True)

            
                            
        else:  # All done!          
            fill_complete = True


    return geometries_df            
                    


# Partially fill a hole with 4 or more boundary components by attaching two 
# non-adjacent boundary components, leaving behind two new holes, each with strictly
# fewer boundary components than the original.

def partial_fill_data(hole0, hole_boundaries_df0):
    
    # Compute all distances between pairs of non-adjacent polygons along the 
    # boundary of the hole.

    hole = hole0
    hole_boundaries_df = hole_boundaries_df0.copy()
    
    poly_distances = []

    for i in hole_boundaries_df.index:
        for j in hole_boundaries_df.index:
            if j > i:
                this_distance = hole_boundaries_df["geometry"][i].distance(hole_boundaries_df["geometry"][j])
                if this_distance != 0: #maybe use not is_close?
                    poly_distances.append((i, j, this_distance))

                     
    # Choose the shortest-distance non-adjacent pair to connect by gluing a piece 
    # of the hole to one of them.
    
    
    distance_data_sorted = sorted(poly_distances, key=lambda tup: tup[2])
    
    poly_pair_found = False
    
    while poly_pair_found == False and len(distance_data_sorted) > 0:

        min_distance_data = distance_data_sorted[0]
        polys_to_connect = (min_distance_data[0], min_distance_data[1])
    
    # For each of the two polygons that we want to connect, identify the two 
    # vertices at the ends of their boundary segment.
    # For each vertex, find the nearest point in the OTHER of the two polygons, 
    # along with the corresponding distances.
    
    # Add a check to make sure that the geometry works as expected; if not, we'll 
    # drop this polygon pair and move on to the next-closest one.

    
        boundary_point_coords = []

        vertices = [[], []]
        vertices_nearest_point_pairs = [[], []]
        vertices_distances = [[], []]

        for i in range(2):
            boundary_point_coords.append([x for x in hole_boundaries_df["geometry"][polys_to_connect[i]].coords])
            vertices[i].append(Point(boundary_point_coords[i][0][0], boundary_point_coords[i][0][1]))
            vertices[i].append(Point(boundary_point_coords[i][-1][0], boundary_point_coords[i][-1][1]))

        for i in range(2):
            for j in range(2):
                vertices_nearest_point_pairs[i].append(shapely.ops.nearest_points(vertices[i][j], MultiPoint(boundary_point_coords[1-i])))
                vertices_distances[i].append(vertices_nearest_point_pairs[i][j][0].distance(vertices_nearest_point_pairs[i][j][1]))
                    
                    
    # Identify the list positions of the two shortest of these four distances, and 
    # split the hole with the two corresponding line segments.  (Unfortunately this 
    # requires two steps, because the split operation doesn't support splitting 
    # with MultiLineStrings.)
    
    # IT CAN HAPPEN THAT THE TWO SHORTEST LINES DON'T PROVIDE TWO TRUE SPLITS!  
    # If that happens, try the 3rd and 4th lines.  And if THAT doesn't work, go 
    # back to the distance data and pick a different pair of polygons to connect!
 
        sorted_distances = sorted([(0,0,vertices_distances[0][0]), (0,1,vertices_distances[0][1]), 
                                   (1,0,vertices_distances[1][0]), (1,1,vertices_distances[1][1])], 
                                 key = lambda tup: tup[2])
        sorted_line_segments_0 = []
        for k in range(4):
            i = sorted_distances[k][0]
            j = sorted_distances[k][1]
            sorted_line_segments_0.append(LineString(list(vertices_nearest_point_pairs[i][j])))    

    # Ignore any of the line segments that aren't contained within the hole (but 
    # contained within the boundary is okay - and happens!):
    
        sorted_line_segments = []
        for k in range(4):
            if hole.contains(sorted_line_segments_0[k]) or hole.boundary.contains(sorted_line_segments_0[k]):
                sorted_line_segments.append(sorted_line_segments_0[k])


        line_pair_found = False
        
        if len(sorted_line_segments) > 1:
            for j in range(1, len(sorted_line_segments)):
                for i in range(j):
                    if sorted_line_segments[i].disjoint(sorted_line_segments[j]) and line_pair_found == False:
                        line_pair = [i,j]
                        line_pair_found = True
                        
        
        if line_pair_found==True:
 
            new_holes = []
            
            first_split = shapely.ops.split(hole, sorted_line_segments[line_pair[0]])
    
    # First_split should contain two pieces, one of which also intersects the second line.  
    # Find that piece, and split it with the second line. 
    
            for k in range(len(first_split.geoms)): 
                if first_split.geoms[k].intersects(sorted_line_segments[line_pair[1]]): 
                    second_split = shapely.ops.split(first_split.geoms[k], sorted_line_segments[line_pair[1]]) 
                else: 
                    new_holes.append(first_split.geoms[k]) 
                 
    # Find the piece in second_split that also touches the first line.  
    # THIS WILL BE OUR PIECE TO ADJOIN TO ONE OF THE TWO POLYGONS!

    
            for k in range(len(second_split.geoms)): 
                if second_split.geoms[k].intersects(sorted_line_segments[line_pair[0]]): 
                    piece_to_connect = second_split.geoms[k] 
                    poly_pair_found = True  # SUCCESS!!
                else:
                    new_holes.append(second_split.geoms[k]) 
                
        if poly_pair_found == True:
            if piece_to_connect.intersection(hole_boundaries_df["geometry"][polys_to_connect[0]]).length > piece_to_connect.intersection(hole_boundaries_df["geometry"][polys_to_connect[1]]).length:
                poly_to_add_to = hole_boundaries_df["target"][polys_to_connect[0]]
            elif piece_to_connect.intersection(hole_boundaries_df["geometry"][polys_to_connect[0]]).length < piece_to_connect.intersection(hole_boundaries_df["geometry"][polys_to_connect[1]]).length:              
                poly_to_add_to = hole_boundaries_df["target"][polys_to_connect[1]]
   
        else: #Try again with a different polygon pair
            distance_data_sorted.remove(distance_data_sorted[0]) 
                
        

        
    if poly_pair_found == False:  # Not much to do at this point except join by shared 
                                  # perimeter and hope for the best!  (Usually these will
                                  # be small enough that they'll get converted to queen
                                  # adjacencies eventually anyway.)
        shared_perimeters = []
                
        for b_ind in hole_boundaries_df.index:
            g_ind = hole_boundaries_df["target"][b_ind]
            shared_perimeters.append((b_ind, hole_boundaries_df["geometry"][b_ind].length))
                
        max_shared_perim = sorted(shared_perimeters, key=lambda tup: tup[1])[-1]

        poly_to_add_to = hole_boundaries_df["target"][max_shared_perim[0]]
        piece_to_connect = hole
        new_holes = []
        
    return poly_to_add_to, piece_to_connect, new_holes
 

# Convert all rook adjacencies with boundary length less than min_rook_length to queen adjacencies

def small_rook_to_queen(geometries0_df, min_rook_length):
    
    geometries_df = geometries0_df.copy()
    
    adj_df = adjacencies(geometries_df, output_type = "geodataframe")  # We're assuming the input is clean, so these should all be 1-D or less


    for ind in adj_df.index:
        if adj_df["geometry"][ind].geom_type == "GeometryCollection":
            adj_list = list(adj_df["geometry"][ind].geoms)
            adj_list_no_point = [x for x in adj_list if x.geom_type != "Point"]
            adj_df["geometry"][ind] = MultiLineString(adj_list_no_point)
                    
        if adj_df["geometry"][ind].geom_type == "MultiLineString":
            adj_df["geometry"][ind] = linemerge(adj_df["geometry"][ind])

    adj_df = adj_df.explode(index_parts=False).reset_index(drop=True) 

    for ind in adj_df.index:
        if adj_df["geometry"][ind].geom_type == "Point":
            adj_df = adj_df.drop(ind)
    
    
    # Add column for boundary length and pick off the small ones:
    
    adj_df["boundary length"] = adj_df["geometry"].length
    
    small_adj_df = adj_df[adj_df["boundary length"] < min_rook_length]
    
    
    for a_ind in small_adj_df.index: # Don't put a progress bar here; it gets out of control!
                
        # Make sure we haven't inadvertently killed off this adjacency while we were fixing others!
        
        geoms_for_this_adj = list(small_adj_df["neighbors"][a_ind])
        adj_len = geometries_df["geometry"][geoms_for_this_adj[0]].intersection(geometries_df["geometry"][geoms_for_this_adj[1]]).length
        
        if adj_len > 0 and adj_len < min_rook_length:
        
            # Rebuild the STRtree every time because the geometries will change every time.
            g_spatial_index = STRtree(geometries_df["geometry"]) # Build STRtree for the main geometries
            g_index_by_iloc = dict((i, list(geometries_df.index)[i]) for i in range(len(geometries_df)))  # Build indexing dictionary

            # Build a disk enclosing this adjacency; the idea will be to cut it out and replace it 
            # with a "pie chart" so that all polygons touching this disk meet at a queen adjacency 
            # point at the center of the disk.
            adj_diam = small_adj_df["geometry"][a_ind].length
            fat_point_radius = 0.6*adj_diam # slightly more than the radius from the midpoint to the endpoints

            adjacency_points = [x for x in small_adj_df["geometry"][a_ind].coords]
            endpoint1 = adjacency_points[0]
            endpoint2 = adjacency_points[-1]
            midpoint = LineString([endpoint1, endpoint2]).centroid
            midpoint_coords = midpoint.coords[0]
                    
            disk_to_remove = midpoint.buffer(fat_point_radius)
 
            # Identify geometries that might intersect this disk.
            possible_geom_integer_indices = [*set(numpy.ndarray.flatten(g_spatial_index.query(small_adj_df["geometry"][a_ind].buffer(2*fat_point_radius))))]
            possible_geom_indices = [g_index_by_iloc[k] for k in possible_geom_integer_indices] 
       
            # Use the boundaries of these geometries together with the boundary of the disk to 
            # polygonize and divide geometries into pieces inside and outside the disk
            boundaries = [geometries_df["geometry"][i].boundary for i in possible_geom_indices]
            boundaries.append(LineString(list(disk_to_remove.exterior.coords)))
        
            boundaries_union = unary_union(boundaries) 

            pieces_df = geopandas.GeoDataFrame(columns = ["polygon indices"], 
                                     geometry = geopandas.GeoSeries([geom for geom in polygonize(boundaries_union)]),
                                     crs = geometries_df.crs)

            # Associate the pieces to the main geometries.  (Note that if there are holes, some pieces may
            # be unassigned.)
            for i in pieces_df.index:
                pieces_df["polygon indices"][i] = set()
        
            for i in pieces_df.index: 
                temp_possible_geom_integer_indices = [*set(numpy.ndarray.flatten(g_spatial_index.query(pieces_df["geometry"][i])))]
                temp_possible_geom_indices = [g_index_by_iloc[k] for k in temp_possible_geom_integer_indices] 
                
                for j in temp_possible_geom_indices:
                    if pieces_df["geometry"][i].representative_point().distance(geometries_df["geometry"][j]) == 0:
                        pieces_df["polygon indices"][i] = pieces_df["polygon indices"][i].union({j})
        
        
            # Now rebuild the disk from the pieces that are inside the circle, and drop them from 
            # pieces_df.  Then we'll give the pieces outside the circle back to the geometries that they came from.
        
            disk_to_remove = Polygon()

            for p_ind in pieces_df.index:
                if pieces_df["geometry"][p_ind].representative_point().distance(midpoint) < fat_point_radius:
                    disk_to_remove = unary_union([disk_to_remove, pieces_df["geometry"][p_ind]])
                    pieces_df = pieces_df.drop(p_ind)
        
            for g_ind in possible_geom_indices:
                geometries_df["geometry"][g_ind] = Polygon()
    
            for p_ind in pieces_df.index:
                if len(pieces_df["polygon indices"][p_ind]) == 1:  #Note that it won't be >1 if the file is clean!
                    this_poly_ind = list(pieces_df["polygon indices"][p_ind])[0]
                    this_piece = pieces_df["geometry"][p_ind]
                    if this_poly_ind in possible_geom_indices: 
                    # This check is needed because the geometries in possible_geom_incides can form a 
                    # non-simply-connected region, in which case the interior holes - which may consist
                    # of multiple precincts each - may be assigned someplace they shouldn't be!
                        geometries_df["geometry"][this_poly_ind] = unary_union([geometries_df["geometry"][this_poly_ind], this_piece])

            # Find the boundary arcs between geometries and the disk (and make sure each arc is a connected piece):
            possible_geoms = geometries_df.loc[possible_geom_indices]
            circle_boundaries_df = intersections(geopandas.GeoDataFrame(geometry = geopandas.GeoSeries([disk_to_remove], crs = geometries_df.crs)), possible_geoms, output_type = "geodataframe") 
        
            for b_ind in circle_boundaries_df.index:
                if circle_boundaries_df["geometry"][b_ind].geom_type == "MultiLineString":
                    circle_boundaries_df["geometry"][b_ind] = linemerge(circle_boundaries_df["geometry"][b_ind])

            circle_boundaries_df = circle_boundaries_df.explode(index_parts=False).reset_index(drop=True)  
        
            # For each boundary arc, create a "pie wedge" from the center of the disk subtending this arc:
        
            for b_ind in circle_boundaries_df.index:
                boundary_arc_coords = [x for x in circle_boundaries_df["geometry"][b_ind].coords]
                boundary_wedge_coords = boundary_arc_coords + [midpoint_coords]
    
                g_ind = circle_boundaries_df["target"][b_ind]

                geometries_df["geometry"][g_ind] = unary_union([geometries_df["geometry"][g_ind], Polygon(boundary_wedge_coords)])
        
                
    return geometries_df
    





"""
Functions that are unchanged from repair_old
"""


def holes_of_union(geometries):
    """Returns any holes in the union of the given geometries."""
    geometries = get_geometries(geometries)
    if not all(
        isinstance(geometry, (Polygon, MultiPolygon)) for geometry in geometries
    ):
# Changed "type(x) to "x.geom_type"
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





def split_by_level(series, multiindex):
    return tuple(
        multiindex.get_level_values(i).to_series(index=multiindex).map(series)
        for i in range(multiindex.nlevels)
    )


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


# Changing assertions to truth checks so doctor can give a complete report instead of 
# stopping at the first problem.
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
#        assert sym_area == 0, "The unions of target and source differ!"

    for shp in shapefiles:
# Changing "shp["geometry"]" to "shp.geometry" so it will work for both GeoSeries and
# GeoDataFrames,and also changing the assertion behavior.
        if not shp.geometry.apply(lambda x: isinstance(x, (Polygon, MultiPolygon))).all():
            print("Some rows do not have geometries.")
            health_check = False
#        assert shp["geometry"].apply(lambda x: isinstance(x, (Polygon, MultiPolygon))).all(), "Some rows do not have geometries"

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
            

#        assert overlaps == 0, f"There are {overlaps} overlaps!"
#        assert holes == 0, f"There are {holes} holes!"
#        assert shp.is_valid.all(), "There are some invalid geometries!"

    return health_check
#    return True


def count_overlaps(shp):
    """
    Counts overlaps. Code is taken directly from the resolve_overlaps function in maup.
    """
# Changing "shp["geometry"]" to "shp.geometry" so it will work for both GeoSeries and
# GeoDataFrames:
    inters = adjacencies(shp.geometry, warn_for_islands=False, warn_for_overlaps=False)
#    inters = adjacencies(shp["geometry"], warn_for_islands=False, warn_for_overlaps=False)
# Changing buffer(0) to make_valid:
    overlaps = make_valid(inters[inters.area > 0])
#    overlaps = inters[inters.area > 0].buffer(0)
    return len(overlaps)
    
    
# Adding an analogous function "count_holes" that can be used for reporting in an
# expanded version of doctor.
def count_holes(shp):
    gaps = holes_of_union(shp.geometry)
    return(len(gaps))
    

def snap_to_grid(geometries, n=-7):
    """
    Snap the geometries to a grid by rounding to the nearest 10^n. Helps to
    resolve floating point precision issues in shapefiles.
    """
    func = functools.partial(snap_polygon_to_grid, n=n)
# Changing "geometries["geometry"]" to "geometries.geometry" so it will work for both 
# GeoSeries and GeoDataFrames:
    return geometries.geometry.apply(lambda x: apply_func_to_polygon_parts(x, func))
#    return geometries["geometry"].apply(lambda x: apply_func_to_polygon_parts(x, func))


def snap_polygon_to_grid(polygon, n=-7):
    return Polygon([(round(x, -n), round(y, -n)) for x, y in polygon.exterior.coords])


def apply_func_to_polygon_parts(shape, func):
    if isinstance(shape, Polygon):
        return func(shape)
    elif isinstance(shape, MultiPolygon):
        return MultiPolygon([func(poly) for poly in shape.geoms])
    else:
        raise TypeError(f"Can only apply {func} to a Polygon or MultiPolygon (got {shape} with type {type(shape)})!")


