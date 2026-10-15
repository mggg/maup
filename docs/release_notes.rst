Release notes
=============

2.1.1
-----

* Fixed the import failure with GeoPandas 1.2 by removing maup's obsolete
  ``use_pygeos`` check.
* Added a ``legacy`` extra that pins GerryChain 0.3.2 and gerrytools 1.2.1 with
  pandas below 3 and GeoPandas below 1.2. Both older packages access the removed
  PyGEOS option. Pinning GerryChain also prevents gerrytools 1.2.1 from selecting
  GerryChain 1.x, whose graph API has changed. Base dependency bounds are unchanged.
* Added integration tests for the legacy extra and for GerryChain 1.x with
  gerrytools 2.x, pandas 3, and GeoPandas 1.2 or newer. CI resolves dependencies
  independently of the lockfile to catch incompatibilities introduced by updates.

Gerrytools 1.2.0 requires ``maup<=1.1.0`` and ``pandas<2``, so it cannot be used
with modern maup. Upgrade to gerrytools 1.2.1 to use the legacy extra. Maup 2.0.3
requires pandas below 3 and cannot be combined with GerryChain 1.x.

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
