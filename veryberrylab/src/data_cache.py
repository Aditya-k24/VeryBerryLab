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
ws3_plants: dict = {}    # cultivar → Plant (from Worksheet 3; loaded by plant_arch)
_initialized: bool = False


def initialize(verbose: bool = False) -> None:
    """Load data and compute all derived artifacts. Call once before app.run()."""
    global df_clean, stats_cache, season_metrics, completeness, ingestion_warnings, ws3_plants, _initialized

    if _initialized:
        return

    from src.etl import run_etl
    from src.stats import compute_all_stats
    from src.aggregate import compute_season_metrics, build_completeness_matrix
    from src.plant_arch import load_all_plants

    print("VeryBerryLab — loading data...")
    df_clean, ingestion_warnings = run_etl(verbose=verbose)

    print("  Computing statistics (228 trait × date combinations)...")
    stats_cache = compute_all_stats(df_clean)

    print("  Computing season metrics...")
    season_metrics = compute_season_metrics(df_clean, stats_cache)

    print("  Building completeness matrix...")
    completeness = build_completeness_matrix(df_clean)

    print("  Loading Worksheet 3 plant architecture...")
    ws3_plants = load_all_plants()
    if ws3_plants:
        print(f"    {len(ws3_plants)} cultivars loaded from Worksheet 3.")
    else:
        print("    Worksheet 3 not found — plant architecture page will be unavailable.")

    _initialized = True
    print(f"  Ready.  {len(df_clean)} observations · {len(stats_cache)} stat results\n")
