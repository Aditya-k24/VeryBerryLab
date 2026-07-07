"""Merged (multi-batch) ingestion: join keys, missing-value handling, extra
cultivars, and that undated sheets are reported rather than silently dropped."""
import numpy as np
import pandas as pd


def test_returns_df_and_warnings(merged):
    df, warns = merged
    assert isinstance(df, pd.DataFrame)
    assert isinstance(warns, list)


def test_join_keys_present(merged):
    df, _ = merged
    assert {"date", "cultivar", "pheno_batch", "rep"} <= set(df.columns)
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert (df["rep"] >= 1).all()


def test_extra_cultivars_included(merged):
    df, _ = merged
    assert {"Monterey", "Fronteras"} <= set(df["cultivar"].unique())


def test_undated_moxie_reported_not_dropped_silently(merged):
    df, warns = merged
    # Moxie's sheet has no dates -> excluded, but a warning must say so
    assert "Moxie" not in df["cultivar"].unique()
    assert any("Moxie" in w for w in warns)


def test_missing_values_are_nan(merged):
    df, _ = merged
    # merged data contains '-' cells -> at least some NaNs, never silent zeros
    trait_cols = [c for c in df.columns
                  if c not in ("date", "cultivar", "pheno_batch", "rep")]
    assert df[trait_cols].isna().any().any()
