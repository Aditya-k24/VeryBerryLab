"""
src/data_cache.py
=================
Module-level singleton loaded once at app startup.
All Dash pages import from here.
"""

from __future__ import annotations

import pandas as pd

df_clean:           pd.DataFrame = pd.DataFrame()
stats_cache:        dict         = {}
season_metrics:     pd.DataFrame = pd.DataFrame()
completeness:       pd.DataFrame = pd.DataFrame()
ingestion_warnings: list[str]    = []
_ready:             bool         = False


def initialize(verbose: bool = False) -> None:
    global df_clean, stats_cache, season_metrics, completeness, ingestion_warnings, _ready
    if _ready:
        return

    from src.etl       import run_etl
    from src.stats     import compute_all_stats
    from src.aggregate import compute_season_metrics, build_completeness_matrix

    print("VeryBerryLab — loading data...")
    df_clean, ingestion_warnings = run_etl(verbose=verbose)

    print("  Computing statistics...")
    stats_cache = compute_all_stats(df_clean)

    print("  Computing season metrics...")
    season_metrics = compute_season_metrics(df_clean, stats_cache)

    print("  Building completeness matrix...")
    completeness = build_completeness_matrix(df_clean)

    _ready = True
    print(f"  Ready — {len(df_clean)} obs · {len(stats_cache)} stat results\n")
