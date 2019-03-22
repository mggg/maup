# maup

[![Build Status](https://travis-ci.com/mggg/maup.svg?branch=master)](https://travis-ci.com/mggg/maup)
[![Code Coverage](https://codecov.io/gh/mggg/maup/branch/master/graph/badge.svg)](https://codecov.io/gh/mggg/maup)
[![PyPI Package](https://badge.fury.io/py/maup.svg)](https://https://pypi.org/project/gerrychain/)

`maup` is the geospatial toolkit for redistricting data. The package streamlines
the basic workflows that arise when working with blocks, precincts, and districts,
such as

-   [Assigning precincts to districts](#assigning-precincts-to-districts),
-   [Aggregating block data to precincts](#aggregating-block-data-to-precincts), and
-   [Disaggregating data from precincts down to blocks](#disaggregating-data-from-precincts-down-to-blocks).

The project's priorities are to be efficient by using spatial
indices whenever possible and to integrate well with the existing ecosystem
around [pandas](https://pandas.pydata.org/), [geopandas](https://geopandas.org)
and [shapely](https://shapely.readthedocs.io/en/latest/). The
package is distributed under the MIT License.

## Installation

To install from PyPI, run `pip install maup` from your terminal.

If you are using Anaconda, we recommend installing geopandas
first by running `conda install -c conda-forge geopandas`
and then running `pip install maup`.

## Examples

Here are some basic situations where you might find `maup` helpful. For
these examples, let's assume that you have some shapefiles with data at
varying scales, and that you've used `geopandas.read_file` to read those
shapefiles into three GeoDataFrames:

-   `blocks`: Census blocks with demographic data.
-   `precincts`: Precinct geometries with election data but no demographic data.
-   `districts`: Legislative district geometries with no data attached.

### Assigning precincts to districts

The `assign` function in `maup` takes two sets of geometries
called `sources` and `targets` and returns a pandas `Series`. The Series maps each
geometry in `sources` to the geometry in `targets` that covers it.
(Here, geometry _A_ _covers_ geometry _B_ if every point of _A_ and its
boundary lies in _B_ or its boundary.) If a source geometry is not covered by
one single target geometry, it is assigned to the target geometry that covers
the largest portion of its area.

```python
from maup import assign

assignment = assign(precincts, districts)

# Add the assigned districts as a column of the `precincts` GeoDataFrame:
precincts["DISTRICT"] = assignment
```

As an aside, you can use that `assignment` object to create a
[gerrychain](https://gerrychain.readthedocs.io/en/latest/) `Partition`
representing the division of the precincts into legislative districts:

```python
from gerrychain import Graph, Partition

graph = Graph.from_geodataframe(precincts)
legislative_districts = Partition(graph, assignment)
```

### Aggregating block data to precincts

If you want to aggregate columns called `"TOTPOP"`, `"NH_BLACK"`, and
`"NH_WHITE"` from `blocks` up to `precincts`, you can run:

```python
from maup import assign

variables = ["TOTPOP", "NH_BLACK", "NH_WHITE"]

assignment = assign(blocks, precincts)
precincts[variables] = blocks[variables].groupby(assignment).sum()
```

### Disaggregating data from precincts down to blocks

It's common to have data at a coarser scale and want to try and
disaggregate or prorate it down to finer-scaled geometries. For example,
let's say we want to prorate some election data in columns `"PRESD16"`,
`"PRESR16"` from our `precincts` GeoDataFrame down to our `blocks`
GeoDataFrame.

The first crucial step is to decide how we want to distribute a precinct's data
to the blocks within it. Since we're prorating election data, it makes sense to
use a block's total population or voting-age population. Here's how we might
prorate by population (`"TOTPOP"`):

```python
from maup import assign

election_columns = ["PRESD16", "PRESR16"]
assignment = assign(blocks, precincts)

# We prorate the vote totals according to each block's share of the overall
# precinct population:
weights = blocks.TOTPOP / assignment.map(precincts.TOTPOP)
prorated = assignment.map(precincts[election_columns]) * weights

# Add the prorated vote totals as columns on the `blocks` GeoDataFrame:
blocks[election_columns] = prorated
```

#### Warning about areal interpolation

**We strongly urge you _not_ to prorate by area!** The area of a census block is **not**
a good predictor of its population. In fact, the correlation goes in the other direction:
larger census blocks are _less_ populous than smaller ones.

## Modifiable areal unit problem

The name of this package comes from the
[modifiable areal unit problem (MAUP)](https://en.wikipedia.org/wiki/Modifiable_areal_unit_problem):
the same spatial data will look different depending on how you divide up the space.
Since `maup` is all about changing the way your data is aggregated and partitioned, we have named it
after the MAUP to encourage that the toolkit be used thoughtfully and responsibly.
