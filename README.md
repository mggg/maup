# maup

[![Build Status](https://travis-ci.com/mggg/maup.svg?branch=master)](https://travis-ci.com/mggg/maup)
[![Code Coverage](https://codecov.io/gh/mggg/maup/branch/master/graph/badge.svg)](https://codecov.io/gh/mggg/maup)
[![PyPI Package](https://badge.fury.io/py/maup.svg)](https://pypi.org/project/maup/)

`maup` is the geospatial toolkit for redistricting data. The package streamlines
the basic workflows that arise when working with blocks, precincts, and
districts, such as

-   [Assigning precincts to districts](#assigning-precincts-to-districts),
-   [Aggregating block data to precincts](#aggregating-block-data-to-precincts),
-   [Disaggregating data from precincts down to blocks](#disaggregating-data-from-precincts-down-to-blocks),
    and
-   [Prorating data when units do not nest neatly](#prorating-data-when-units-do-not-nest-neatly).

The project's priorities are to be efficient by using spatial indices whenever
possible and to integrate well with the existing ecosystem around
[pandas](https://pandas.pydata.org/), [geopandas](https://geopandas.org) and
[shapely](https://shapely.readthedocs.io/en/latest/). The package is distributed
under the MIT License.

## Installation

To install from PyPI, run `pip install maup` from your terminal.

If you are using Anaconda, we recommend installing geopandas first by running
`conda install -c conda-forge geopandas` and then running `pip install maup`.

## Examples

Here are some basic situations where you might find `maup` helpful. For these
examples, we use test data from Providence, Rhode Island, which you can find in
our
[Rhode Island shapefiles repo](https://github.com/mggg-states/RI-shapefiles), or
in the `examples` folder of this repo.

```python
>>> import geopandas
>>> import pandas
>>>
>>> blocks = geopandas.read_file("zip://./examples/blocks.zip")
>>> precincts = geopandas.read_file("zip://./examples/precincts.zip")
>>> districts = geopandas.read_file("zip://./examples/districts.zip")

```

### Assigning precincts to districts

The `assign` function in `maup` takes two sets of geometries called `sources`
and `targets` and returns a pandas `Series`. The Series maps each geometry in
`sources` to the geometry in `targets` that covers it. (Here, geometry _A_
_covers_ geometry _B_ if every point of _A_ and its boundary lies in _B_ or its
boundary.) If a source geometry is not covered by one single target geometry, it
is assigned to the target geometry that covers the largest portion of its area.

```python
>>> import maup
>>>
>>> assignment = maup.assign(precincts, districts)
>>> # Add the assigned districts as a column of the `precincts` GeoDataFrame:
>>> precincts["DISTRICT"] = assignment
>>> assignment.head()
0     7
1     5
2    13
3     6
4     1
dtype: int64

```

As an aside, you can use that `assignment` object to create a
[gerrychain](https://gerrychain.readthedocs.io/en/latest/) `Partition`
representing this districting plan.

### Aggregating block data to precincts

Precinct shapefiles usually come with election data, but not demographic data.
In order to study their demographics, we need to aggregate demographic data from
census blocks up to the precinct level. We can do this by assigning blocks to
precincts and then aggregating the data with a Pandas
[`groupby`](http://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.groupby.html)
operation:

```python
>>> variables = ["TOTPOP", "NH_BLACK", "NH_WHITE"]
>>>
>>> assignment = maup.assign(blocks, precincts)
>>> precincts[variables] = blocks[variables].groupby(assignment).sum()
>>> precincts[variables].head()
   TOTPOP  NH_BLACK  NH_WHITE
0    5907       886       380
1    5636       924      1301
2    6549       584      4699
3    6009       435      1053
4    4962       156      3713

```

If you want to move data from one set of geometries to another but your source
and target geometries do not nest neatly (i.e. have overlaps), see
[Prorating data when units do not nest neatly](#prorating-data-when-units-do-not-nest-neatly).

### Disaggregating data from precincts down to blocks

It's common to have data at a coarser scale that you want to attach to
finer-scaled geometries. Usually this happens when vote totals for a certain
election are only reported at the county level, and we want to attach that data
to precinct geometries.

Let's say we want to prorate the vote totals in the columns `"PRES16D"`,
`"PRES16R"` from our `precincts` GeoDataFrame down to our `blocks` GeoDataFrame.
The first crucial step is to decide how we want to distribute a precinct's data
to the blocks within it. Since we're prorating election data, it makes sense to
use a block's total population or voting-age population. Here's how we might
prorate by population (`"TOTPOP"`):

```python
>>> election_columns = ["PRES16D", "PRES16R"]
>>> assignment = maup.assign(blocks, precincts)
>>>
>>> # We prorate the vote totals according to each block's share of the overall
>>> # precinct population:
>>> weights = blocks.TOTPOP / assignment.map(precincts.TOTPOP)
>>> prorated = maup.prorate(assignment, precincts[election_columns], weights)
>>>
>>> # Add the prorated vote totals as columns on the `blocks` GeoDataFrame:
>>> blocks[election_columns] = prorated
>>> # We'll call .round(2) to round the values for display purposes.
>>> blocks[election_columns].round(2).head()
   PRES16D  PRES16R
0     0.00     0.00
1    12.26     1.70
2    15.20     2.62
3    15.50     2.67
4     3.28     0.45

```

#### Warning about areal interpolation

**We strongly urge you _not_ to prorate by area!** The area of a census block is
**not** a good predictor of its population. In fact, the correlation goes in the
other direction: larger census blocks are _less_ populous than smaller ones.

### Prorating data when units do not nest neatly

Suppose you have a shapefile of precincts with some election results data and
you want to join that data onto a different, more recent precincts shapefile.
The two sets of precincts will have overlaps, and will not nest neatly like the
blocks and precincts did in the above examples. (Not that blocks and precincts
always nest neatly...)

We can use `maup.intersections` to break the two sets of precincts into pieces
that nest neatly into both sets. Then we can disaggregate from the old precincts
onto these pieces, and aggregate up from the pieces to the new precincts. This
move is a bit complicated, so `maup` provides a function called `prorate` that
does just that.

We'll use our same `blocks` GeoDataFrame to estimate the populations of the
pieces for the purposes of proration.

For our "new precincts" shapefile, we'll use the VTD shapefile for Rhode Island
that the U.S. Census Bureau produced as part of their 2018 test run of for the
2020 Census.

```python
>>> old_precincts = precincts
>>> new_precincts = geopandas.read_file("zip://./examples/new_precincts.zip")
>>>
>>> columns = ["SEN18D", "SEN18R"]
>>>
>>> # Include area_cutoff=0 to ignore any intersections with no area,
>>> # like boundary intersections, which we do not want to include in
>>> # our proration.
>>> pieces = maup.intersections(old_precincts, new_precincts, area_cutoff=0)
>>>
>>> # Weight by prorated population from blocks
>>> weights = blocks["TOTPOP"].groupby(maup.assign(blocks, pieces)).sum()
>>>
>>> # Use blocks to estimate population of each piece
>>> new_precincts[columns] = maup.prorate(
...     pieces,
...     old_precincts[columns],
...     weights=weights
... )
>>> new_precincts[columns].head()
      SEN18D    SEN18R
0  3033568.0  205734.0
1  1171050.0   66465.0
2    35502.0    6222.0
3   120950.0    9896.0
4   307008.0   24960.0

```

## Modifiable areal unit problem

The name of this package comes from the
[modifiable areal unit problem (MAUP)](https://en.wikipedia.org/wiki/Modifiable_areal_unit_problem):
the same spatial data will look different depending on how you divide up the
space. Since `maup` is all about changing the way your data is aggregated and
partitioned, we have named it after the MAUP to encourage that the toolkit be
used thoughtfully and responsibly.
