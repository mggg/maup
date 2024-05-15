.. maup documentation master file, created by
   sphinx-quickstart on Wed Jun 16 16:05:45 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to MAUP's documentation!
====================================


.. quick tip on reamaking the readme
.. pandoc --from=markdown --to=rst --output=introduction.rst ../README.md

.. include:: introduction.rst


.. toctree::
   :maxdepth: 2
   :caption: Tutorials

   user/getting_started
   user/prorating
   user/topological
   user/simple_example

.. toctree::
   :maxdepth: 2
   :caption: Working with GerryChain

   with_gerrychain/real-life_plan
   with_gerrychain/islands

.. Installation
.. ------------

.. Install ``maup`` by running

..     pip install maup


.. Contribute
.. ----------

.. All contributions are welcome! `maup` is licensed under the MIT license.

.. - Issue Tracker: https://github.com/mggg/maup/issues
.. - Source Code: https://github.com/mggg/maup

.. Indices and tables
.. ==================

.. * :ref:`genindex`
.. * :ref:`modindex`
.. * :ref:`search`


.. toctree::
    :caption: Index
    :maxdepth: 4

    full_ref