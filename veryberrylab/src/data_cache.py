"""
src/data_cache.py
=================
Single module-level data store loaded once at app startup.
All Dash pages import from here instead of re-running ETL.
"""

from __future__ import annotations

import pandas as pd

# Will be populated by initialize()
df_clean: pd.DataFrame = pd.DataFrame()
stats_cache: dict = {}
season_metrics: pd.DataFrame = pd.DataFrame()
completeness: pd.DataFrame = pd.DataFrame()
ingestion_warnings: list[str] = []
_initialized: bool = False


def initialize(verbose: bool = False) -> None:
    """Load data and compute all derived artifacts. Call once before app.run()."""
    global df_clean, stats_cache, season_metrics, completeness, ingestion_warnings, _initialized

    if _initialized:
        return

    from src.etl import run_etl
    from src.stats import compute_all_stats
    from src.aggregate import compute_season_metrics, build_completeness_matrix

    print("VeryBerryLab — loading data...")
    df_clean, ingestion_warnings = run_etl(verbose=verbose)

    print("  Computing statistics (228 trait × date combinations)...")
    stats_cache = compute_all_stats(df_clean)

    print("  Computing season metrics...")
    season_metrics = compute_season_metrics(df_clean, stats_cache)

    print("  Building completeness matrix...")
    completeness = build_completeness_matrix(df_clean)

    _initialized = True
    print(f"  Ready.  {len(df_clean)} observations · {len(stats_cache)} stat results\n")
