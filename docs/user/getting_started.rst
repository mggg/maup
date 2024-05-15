Getting started with MAUP
=========================

Here are some basic situations where you might find ``maup`` helpful.
For these examples, we use test data from Providence, Rhode Island,
which you can find in our `Rhode Island shapefiles
repo <https://github.com/mggg-states/RI-shapefiles>`__, or in the
``examples`` folder of this repo, reprojected to a non-geographic
coordinate reference system (CRS) optimized for Rhode Island.

.. note::

   Many of maup's functions behave badly in geographic projections
   (i.e., lat/long coordinates), which are the default for shapefiles from
   the U.S. Census bureau. In order to find an appropriate CRS for a
   particular shapefile, consult the database at https://epsg.org.

.. code:: python

   >>> import geopandas
   >>> import pandas
   >>>
   >>> blocks = geopandas.read_file("zip://./examples/blocks.zip").to_crs(32030)
   >>> precincts = geopandas.read_file("zip://./examples/precincts.zip").to_crs(32030)
   >>> districts = geopandas.read_file("zip://./examples/districts.zip").to_crs(32030)

.. _assigning-precincts-to-districts:

Assigning precincts to districts
--------------------------------

The ``assign`` function in ``maup`` takes two sets of geometries called
``sources`` and ``targets`` and returns a pandas ``Series``. The Series
maps each geometry in ``sources`` to the geometry in ``targets`` that
covers it. (Here, geometry *A* *covers* geometry *B* if every point of
*A* and its boundary lies in *B* or its boundary.) If a source geometry
is not covered by one single target geometry, it is assigned to the
target geometry that covers the largest portion of its area.

.. code:: python

   >>> import maup
   >>>
   >>> precinct_to_district_assignment = maup.assign(precincts, districts)
   >>> # Add the assigned districts as a column of the `precincts` GeoDataFrame:
   >>> precincts["DISTRICT"] = precinct_to_district_assignment
   >>> precinct_to_district_assignment.head()
   0     7
   1     5
   2    13
   3     6
   4     1
   dtype: int64

As an aside, you can use that ``precinct_to_district_assignment`` object
to create a
`gerrychain <https://gerrychain.readthedocs.io/en/latest/>`__
``Partition`` representing this districting plan.

.. _aggregating-block-data-to-precincts:

Aggregating block data to precincts
-----------------------------------

Precinct shapefiles usually come with election data, but not demographic
data. In order to study their demographics, we need to aggregate
demographic data from census blocks up to the precinct level. We can do
this by assigning blocks to precincts and then aggregating the data with
a Pandas
`groupby <http://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.groupby.html>`_
operation:

.. code:: python

   >>> variables = ["TOTPOP", "NH_BLACK", "NH_WHITE"]
   >>>
   >>> blocks_to_precincts_assignment = maup.assign(blocks, precincts)
   >>> precincts[variables] = blocks[variables].groupby(blocks_to_precincts_assignment).sum()
   >>> precincts[variables].head()
      TOTPOP  NH_BLACK  NH_WHITE
   0    5907       886       380
   1    5636       924      1301
   2    6549       584      4699
   3    6009       435      1053
   4    4962       156      3713

If you want to move data from one set of geometries to another but your
source geometries do not nest cleanly into your target geometries, see
`Prorating data when units do not nest
neatly <#prorating-data-when-units-do-not-nest-neatly>`__.

.. _disaggregating-data-when-units-do-not-nest-neatly:

Disaggregating data from precincts down to blocks
-------------------------------------------------

It's common to have data at a coarser scale that you want to attach to
finer-scale geometries. For instance, this may happen when vote totals
for a certain election are only reported at the county level, and we
want to attach that data to precinct geometries.

Let's say we want to prorate the vote totals in the columns
``"PRES16D"``, ``"PRES16R"`` from our ``precincts`` GeoDataFrame down to
our ``blocks`` GeoDataFrame. The first crucial step is to decide how we
want to distribute a precinct's data to the blocks within it. Since
we're prorating election data, it makes sense to use a block's total
population or voting-age population. Here's how we might prorate by
population (``"TOTPOP"``):

.. code:: python

   >>> election_columns = ["PRES16D", "PRES16R"]
   >>> blocks_to_precincts_assignment = maup.assign(blocks, precincts)
   >>>
   >>> # We prorate the vote totals according to each block's share of the overall
   >>> # precinct population:
   >>> weights = blocks.TOTPOP / blocks_to_precincts_assignment.map(blocks.TOTPOP.groupby(blocks_to_precincts_assignment).sum())
   >>> prorated = maup.prorate(blocks_to_precincts_assignment, precincts[election_columns], weights)
   >>>
   >>> # Add the prorated vote totals as columns on the `blocks` GeoDataFrame:
   >>> blocks[election_columns] = prorated
   >>>
   >>> # We'll call .round(2) to round the values for display purposes, but note that the 
   >>> # actual values should NOT be rounded in order to avoid accumulation of rounding
   >>> # errors.
   >>> blocks[election_columns].round(2).head()
      PRES16D  PRES16R
   0     0.00     0.00
   1    12.26     1.70
   2    15.20     2.62
   3    15.50     2.67
   4     3.28     0.45


.. warning::

   (1) Many states contain Census blocks and precincts that have zero population. In the example above, a zero-population precinct leads to division by zero in the definition of the weights, which results in NaN values for some entries.

   Although it is not strictly necessary to resolve this in the example
   above, sometimes this creates issues down the line. One option is to
   replace NaN values with zeros, using

   .. code:: python

      >>> weights = weights.fillna(0)

   (2) In some cases, zero-population precincts may have a small nonzero number of recorded votes in some elections. The procedure outlined above will lose these votes in the proration process due to the zero (or NaN) values for the weights corresponding to all the blocks in those precincts. If it is crucial to keep vote totals perfectly accurate, these votes will need to be assigned to the new units manually.

Progress bars
-------------

For long-running operations, the user might want to see a progress bar
to estimate how much longer a task will take (and whether to abandon it
altogether).

``maup`` provides an optional progress bar for this purpose. To
temporarily activate a progress bar for a certain operation, use
``with maup.progress():``:

.. code:: python

   with maup.progress():
       assignment = maup.assign(precincts, districts)

To turn on progress bars for all applicable operations (e.g. for an
entire script), set ``maup.progress.enabled = True``:

.. code:: python

   maup.progress.enabled = True
   # Now a progress bar will display while this function runs:
   assignment = maup.assign(precincts, districts)
   # And this one too:
   pieces = maup.intersections(old_precincts, new_precincts, area_cutoff=0)


