"""Sphinx configuration for the netleak report.

Build with `make report`, which regenerates the result tables from results/summary.csv
first. Notebooks are rendered from their saved outputs; nothing is executed here.
"""

project = "netleak"
author = "Winston Li and Chris Furlong"
copyright = "2026, Winston Li and Chris Furlong"

extensions = ["myst_nb"]
nb_execution_mode = "off"
myst_enable_extensions = ["dollarmath", "colon_fence", "attrs_inline"]

html_theme = "furo"
html_title = "Does the classifier know the service, or the machine?"
html_static_path = []
html_copy_source = False   # the 10 MB notebook source would otherwise ship with the site
html_show_sourcelink = False
html_baseurl = "https://chrisfurlong03.github.io/netleak/"
exclude_patterns = ["_build", "**.ipynb_checkpoints", "make_tables.py"]
suppress_warnings = ["mystnb.unknown_mime_type", "myst.xref_missing"]
