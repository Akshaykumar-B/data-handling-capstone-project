"""Phase 4 exploratory data analysis (EDA) package.

A reproducible, deterministic EDA over the Phase 3 processed datasets. Analysis
functions are pure (DataFrame in -> JSON-safe dict out); all Parquet reads and
report/figure writes are confined to :mod:`src.analysis.io_utils`,
:mod:`src.analysis.figures` and :mod:`src.analysis.run_eda`.

The pipeline never modifies ``data/raw`` or the Phase 3 processed inputs, never
downloads anything, and never parses the 2.3 GB ``routes_clean.geojson`` (its
metadata is sourced from ``processing_report.json``).
"""
