
Fixing topological issues, overlaps, and gaps
---------------------------------------------

Precinct shapefiles are often created by stitching together collections
of precinct geometries sourced from different counties or different
years. As a result, the shapefile often has gaps or overlaps between
precincts where the different sources disagree about the boundaries.
(And by “often,” we mean “for almost every shapefile that isn't produced
by the U.S. Census Burueau.”) As we saw in the examples above, these
issues can pose problems when moving data between shapefiles.

Even when working with a single shapefile, gaps and overlaps may cause
problems if you are interested in working with the adjacency graph of
the precincts. This adjacency information is especially important when
studying redistricting, because districts are almost always expected to
be contiguous.

Before doing anything else, it is wise to understand the current status
of a shapefile with regard to topological issues. ``maup`` provides a
``doctor`` function to diagnose gaps, overlaps, and invalid geometries.
If a shapefile has none of these issues, ``maup.doctor`` returns a value
of ``True``; otherwise it returns ``False`` along with a brief summary
of the problems that it found.

The blocks shapefile, like most shapefiles from the Census Bureau, is
clean:

.. code:: python

   >>> maup.doctor(blocks)
   True

The old precincts shapefile, however, has some minor issues:

.. code:: python

   >>> maup.doctor(old_precincts)
   There are 2 overlaps.
   There are 3 holes.
   False

As of version 2.0.0, ``maup`` provides two repair functions with a
variety of options for fixing these issues:

1. ``quick_repair`` is the new name for the ``autorepair`` function from
   version 1.x (and ``autorepair`` still works as a synonym). This
   function makes fairly simplistic repairs to gaps and overlaps:

   -  Any polygon :math:`Q` created by the overlapping intersection of
      two geometries :math:`P_1` and :math:`P_2` is removed from both
      polygons and reassigned to the one with which it shares the
      greatest perimeter.
   -  Any polygon :math:`Q` representing a gap between geometries
      :math:`P_1,\ldots, P_n` is assigned to the one with which it
      shares the greatest perimeter.

   This function is probably sufficient when gaps and overlaps are all
   very small in area relative to the areas of the geometries, **AND**
   when the repaired file will only be used for operations like
   aggregating and prorating data. But it should **NOT** be relied upon
   when it is important for the repaired file to accurately represent
   adjacency relations between neighboring geometries, such as when a
   precinct shapefile is used as a basis for creating districting plans
   with contiguous districts.

   For instance, when a gap adjoins many geometries (which happens
   frequently along county boundaries in precinct shapefiles!),
   whichever geometry the gap is adjoined to becomes “adjacent” to
   **all** the other geometries adjoining the gap, which can lead to the
   creation of discontiguous districts in plans based on the repaired
   shapefile.

2. ``smart_repair`` is a more sophisticated repair function designed to
   reproduce the “true” adjacency relations between geometries as
   accurately as possible. In the case of gaps that adjoin several
   geometries, this is accomplished by an algorithm that divides the gap
   into pieces to be assigned to different geometries instead of
   assigning the entire gap to a single geometry.

   In addition to repairing gaps and overlaps, ``smart_repair`` includes
   two optional features:

   -  In many cases, the shapefile geometries are intended to nest
      cleanly into some larger units; e.g., in many states, precincts
      should nest cleanly into counties. ``smart_repair`` allows the
      user to optionally specify a second shapefile—e.g., a shapefile of
      county boundaries within a state—and then performs the repair
      process so that the repaired geometries nest cleanly into the
      units in the second shapefile.
   -  Whether as a result of inaccurate boundaries in the original map
      or as an artifact of the repair algorithm, it may happen that some
      units share boundaries with very short perimeter but should
      actually be considered “queen adjacent”—i.e., intersecting at only
      a single point—rather than “rook adjacent”—i.e., intersecting
      along a boundary of positive length. ``smart_repair`` includes an
      optional step in which all rook adjacencies of length below a
      user-specified parameter are converted to queen adjacencies.

``smart_repair`` can accept either a GeoSeries or GeoDataFrame as input,
and the output type will be the same as the input type. The input must
be projected to a non-geographic coordinate reference system (CRS)—i.e.,
**not** lat/long coordinates—in order to have sufficient precision for
the repair. One option is to reproject a GeoDataFrame called ``gdf`` to
a suitable UTM (Universal Transverse Mercator) projection via

.. code:: python

   gdf = gdf.to_crs(gdf.estimate_utm_crs())

At a minimum, all overlaps will be repaired in the output. Optional
arguments include: \* ``snapped`` (default value ``True``): If ``True``,
all polygon vertices are snapped to a grid of size no more than
:math:`10^{-10}` times the maximum of width/height of the entire
shapefile extent. **HIGHLY RECOMMENDED** to avoid topological exceptions
due to rounding errors. \* ``fill_gaps`` (default value ``True``): If
``True``, all simply connected gaps with area less than
``fill_gaps_threshold`` times the largest area of all geometries
adjoining the gap are filled. Default threshold is :math:`0.1`; setting
``fill_gaps_threshold = None`` will fill all simply connected gaps. \*
``nest_within_regions`` (default value ``None``): If
``nest_within_regions`` is a secondary GeoSeries or GeoDataFrame of
region boundaries (e.g., counties within a state) then the repair will
be performed so that repaired geometries nest cleanly into the region
boundaries; specifically, each repaired geometry will be contained in
the region with which the original geometry has the largest area of
intersection. Note that the CRS for the region GeoSeries/GeoDataFrame
must be the same as that for the primary input. \* ``min_rook_length``
(default value ``None``): If ``min_rook_length`` is given a numerical
value, all rook adjacencies with length below this value will be
replaced with queen adjacencies. Note that this is an absolute value and
not a relative value, so make sure that the value provided is in the
correct units with respect to the input GeoSeries/GeoDataFrame's CRS.
