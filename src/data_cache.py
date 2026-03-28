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
ws3_plants:         dict         = {}   # cultivar → Plant (from Worksheet 3)
ws1_data:           dict         = {}   # cultivar → {dates, plants, codes_by_date}
_ready:             bool         = False


def initialize(verbose: bool = False) -> None:
    global df_clean, stats_cache, season_metrics, completeness
    global ingestion_warnings, ws3_plants, ws1_data, _ready
    if _ready:
        return

    from src.etl        import run_etl
    from src.stats      import compute_all_stats
    from src.aggregate  import compute_season_metrics, build_completeness_matrix
    from src.plant_arch import load_all_plants
    from src.ws1_parser import load_ws1

    print("VeryBerryLab — loading data...")
    df_clean, ingestion_warnings = run_etl(verbose=verbose)

    print("  Computing statistics...")
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
        print("    Worksheet 3 not found — plant animation will be limited.")

    print("  Loading Worksheet 1 time-series...")
    ws1_data = load_ws1(verbose=verbose)
    if ws1_data:
        n_dates = sum(len(v["dates"]) for v in ws1_data.values())
        print(f"    {len(ws1_data)} cultivars · {n_dates} date records loaded from Worksheet 1.")
    else:
        print("    Worksheet 1 not found — temporal animation unavailable.")

    _ready = True
    print(f"  Ready — {len(df_clean)} obs · {len(stats_cache)} stat results\n")
