Release notes
=============

2.1.0
-----

Dependencies and Python compatibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The minimum runtime dependency versions are:

.. list-table::
   :header-rows: 1

   * - Package
     - Python 3.11
     - Python 3.12 and newer
   * - NumPy
     - 2.4.6
     - 2.5.3
   * - pandas
     - 2.3.3
     - 2.3.3
   * - GeoPandas
     - 1.1.4
     - 1.1.4
   * - Shapely
     - 2.1.2
     - 2.1.2
   * - pyproj
     - 3.7.2
     - 3.8.0
   * - Pyogrio
     - 0.13.0
     - 0.13.0
   * - tqdm
     - 4.70.1
     - 4.70.1


Assignment labels with pandas 3
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``maup.assign()`` preserves string and tuple target labels when combining covering assignments with
the greatest-area fallback. Previously, its attempt to store these labels as floats raised an error
with pandas 3, including when assigning to the MultiIndex returned by ``maup.intersections()``.

The result remains a Series indexed like the source geometries. It uses the target index's dtype
when conversion is possible; otherwise, it retains ``object`` dtype. In particular, integer target
labels combined with missing assignments can produce an ``object`` Series. Use ``assignment.isna()``
to find unassigned sources instead of relying on a floating-point dtype or a specific missing-value
sentinel. The covering and greatest-area selection rules have not changed.
