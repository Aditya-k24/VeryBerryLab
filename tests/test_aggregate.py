"""Completeness matrix and season metrics: missing-value semantics and the
staggered-batch invariant (Batch A and B never share a measurement date)."""
import pandas as pd

from src.aggregate import build_completeness_matrix, compute_season_metrics
from src.etl import BATCH_A, BATCH_B


def test_staggered_batches_never_share_a_date(ws2_df):
    a = set(ws2_df[ws2_df["batch"] == "A"]["date"])
    b = set(ws2_df[ws2_df["batch"] == "B"]["date"])
    assert a and b
    assert a.isdisjoint(b)          # no cross-batch same-day comparison possible


def test_completeness_statuses(ws2_df):
    comp = build_completeness_matrix(ws2_df)
    assert set(comp["status"].unique()) <= {"observed", "not_measured", "not_scheduled"}
    # a Batch A cultivar on a Batch B date must be 'not_scheduled', never 'not_measured'
    b_date = min(ws2_df[ws2_df["batch"] == "B"]["date"])
    a_cv = next(iter(BATCH_A))
    row = comp[(comp["cultivar"] == a_cv) & (comp["date"] == b_date)]
    assert (row["status"] == "not_scheduled").all()


def test_observed_matches_non_null(ws2_df):
    comp = build_completeness_matrix(ws2_df)
    obs = comp[comp["status"] == "observed"]
    # spot check: an 'observed' cell has at least one non-null replicate
    r = obs.iloc[0]
    sub = ws2_df[(ws2_df["cultivar"] == r["cultivar"]) & (ws2_df["date"] == r["date"])]
    assert sub[r["trait"]].notna().any()


def test_season_metrics_columns_and_champion_bounds(ws2_df, stats_cache):
    sm = compute_season_metrics(ws2_df, stats_cache)
    assert {"cultivar", "trait", "trend", "champion_pct",
            "peak_value", "peak_date"} <= set(sm.columns)
    pct = sm["champion_pct"].dropna()
    assert ((pct >= 0) & (pct <= 100)).all()
    assert set(sm["trend"].unique()) <= {"up", "down", "flat"}
