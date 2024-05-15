|maup tests| |codecov| |PyPI|

``maup`` is the geospatial toolkit for redistricting data. The package
streamlines the basic workflows that arise when working with blocks,
precincts, and districts, such as

-  `Assigning precincts to
   districts <user/getting_started.html#assigning-precincts-to-districts>`_,
-  `Aggregating block data to
   precincts <user/getting_started.html#aggregating-block-data-to-precincts>`__,
-  `Disaggregating data from precincts down to
   blocks <user/getting_started.html#disaggregating-data-from-precincts-down-to-blocks>`__,
-  `Prorating data when units do not nest
   neatly <user/prorating.html>`__, and
-  `Fixing topological issues, overlaps, and
   gaps <user/topological.html>`__

The project's priorities are to be efficient by using spatial indices
whenever possible and to integrate well with the existing ecosystem
around `pandas <https://pandas.pydata.org/>`__,
`geopandas <https://geopandas.org>`__ and
`shapely <https://shapely.readthedocs.io/en/latest/>`__. The package is
distributed under the MIT License.

Installation
------------

To install ``maup`` from PyPI, run 

.. code:: console

   pip install maup

from the terminal.


Modifiable areal unit problem
-----------------------------

The name of this package comes from the `modifiable areal unit problem
(MAUP) <https://en.wikipedia.org/wiki/Modifiable_areal_unit_problem>`__:
the same spatial data will look different depending on how you divide up
the space. Since ``maup`` is all about changing the way your data is
aggregated and partitioned, we have named it after the MAUP to encourage
users to use the toolkit thoughtfully and responsibly.

.. |maup tests| image:: https://github.com/mggg/maup/actions/workflows/tests.yaml/badge.svg
   :target: https://github.com/mggg/maup/actions/workflows/tests.yaml
.. |codecov| image:: https://codecov.io/gh/mggg/maup/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/mggg/maup
.. |PyPI| image:: https://img.shields.io/pypi/v/maup.svg?color=%23
   :target: https://pypi.org/project/maup/




