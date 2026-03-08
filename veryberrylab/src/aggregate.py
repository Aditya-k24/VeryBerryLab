"""
src/aggregate.py
================
Aggregate pheno4_clean.csv by (date, cultivar): compute mean, standard error,
and n (valid replicates) for every numeric trait.  Also generates a missingness
report and a long-format CSV for the visualization layer.

Run from the veryberrylab/ directory:
    python src/aggregate.py

Inputs:
    data/processed/pheno4_clean.csv

Outputs:
    data/processed/pheno4_aggregated.csv   — wide format (one row per date × cultivar)
    data/processed/pheno4_long.csv         — long format (one row per date × cultivar × trait)
    data/processed/missingness_report.csv  — per (date, cultivar, trait) missing-rep counts
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT       = Path(__file__).resolve().parent.parent
CLEAN_CSV  = ROOT / "data" / "processed" / "pheno4_clean.csv"
AGG_CSV    = ROOT / "data" / "processed" / "pheno4_aggregated.csv"
LONG_CSV   = ROOT / "data" / "processed" / "pheno4_long.csv"
MISS_CSV   = ROOT / "data" / "processed" / "missingness_report.csv"
VIZ_JSON   = ROOT / "data" / "processed" / "pheno4_viz.json"

# ---------------------------------------------------------------------------
# Trait columns (these must exist in pheno4_clean.csv)
# ---------------------------------------------------------------------------
STOLON_COLS = [
    "n_stolon_primary",
    "n_stolon_secondary",
    "n_stolon_tertiary",
    "n_stolon_quaternary",
]

DAUGHTER_COLS = [
    "n_dp_alt_primary",
    "n_dp_alt_secondary",
    "n_dp_alt_tertiary",
    "n_dp_alt_quaternary",
    "n_dp_mid_primary",
    "n_dp_mid_secondary",
    "n_dp_mid_tertiary",
    "n_dp_mid_quaternary",
    "n_dp_total_alt",
    "n_dp_total_mid",
]

FLOWER_COLS = [
    "n_flowers_total",
    "n_flowers_mp",
    "n_flowers_dp",
]

MORPH_COLS = [
    "stolon_length_primary_cm",
    "crown_diameter_mm",
]

ALL_TRAIT_COLS = STOLON_COLS + DAUGHTER_COLS + FLOWER_COLS + MORPH_COLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sem(x: pd.Series) -> float:
    """Standard error of the mean, ignoring NaN. Returns NaN if < 2 valid obs."""
    valid = x.dropna()
    if len(valid) < 2:
        return float("nan")
    return float(valid.std(ddof=1) / np.sqrt(len(valid)))


# ---------------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------------

def run_aggregate() -> tuple[pd.DataFrame, pd.DataFrame]:
    print(f"Loading: {CLEAN_CSV}")
    df = pd.read_csv(str(CLEAN_CSV), parse_dates=["date"])

    # Restrict to traits actually present
    trait_cols = [c for c in ALL_TRAIT_COLS if c in df.columns]
    print(f"Trait columns found: {len(trait_cols)}")

    # ---- Aggregation: mean, SE, n per (date, cultivar) ----
    grp = df.groupby(["date", "cultivar"])

    agg_mean = grp[trait_cols].mean().add_suffix("_mean")
    agg_se   = grp[trait_cols].agg(_sem).add_suffix("_se")
    agg_n    = grp[trait_cols].count().add_suffix("_n")

    agg_df = pd.concat([agg_mean, agg_se, agg_n], axis=1).reset_index()

    # ---- Validate: n_reps should never exceed 3 ----
    n_cols = [c for c in agg_df.columns if c.endswith("_n")]
    max_n  = agg_df[n_cols].max().max()
    if max_n > 3:
        print(f"  [WARN] Some n values exceed 3 (max={max_n}) — check for duplicate reps")
    else:
        print(f"  [OK]   Max reps per group = {max_n}")

    # ---- Missingness report ----
    def _miss_counts(g):
        return g[trait_cols].isna().sum()

    miss = (
        df.groupby(["date", "cultivar"])
        .apply(_miss_counts, include_groups=False)
        .reset_index()
    )
    miss.to_csv(str(MISS_CSV), index=False)
    print(f"Saved → {MISS_CSV}")

    # ---- Save aggregated CSV ----
    agg_df.to_csv(str(AGG_CSV), index=False)
    print(f"Saved → {AGG_CSV}  ({agg_df.shape[0]} rows)")

    # ---- Long format for visualization ----
    long_df = _make_long(agg_df, trait_cols)
    long_df.to_csv(str(LONG_CSV), index=False)
    print(f"Saved → {LONG_CSV}  ({long_df.shape[0]} rows)")

    # ---- Nested JSON for D3 / Plotly.js ----
    _make_json(agg_df, trait_cols)
    print(f"Saved → {VIZ_JSON}")

    return agg_df, long_df


def _make_long(agg_df: pd.DataFrame, trait_cols: list[str]) -> pd.DataFrame:
    """
    Melt aggregated wide DataFrame to long format:
        date, cultivar, trait, mean_value, se_value, n_reps
    """
    mean_df = agg_df.melt(
        id_vars=["date", "cultivar"],
        value_vars=[f"{t}_mean" for t in trait_cols if f"{t}_mean" in agg_df.columns],
        var_name="trait_mean",
        value_name="mean_value",
    )
    mean_df["trait"] = mean_df["trait_mean"].str.replace("_mean$", "", regex=True)

    se_df = agg_df.melt(
        id_vars=["date", "cultivar"],
        value_vars=[f"{t}_se" for t in trait_cols if f"{t}_se" in agg_df.columns],
        var_name="trait_se",
        value_name="se_value",
    )
    se_df["trait"] = se_df["trait_se"].str.replace("_se$", "", regex=True)

    n_df = agg_df.melt(
        id_vars=["date", "cultivar"],
        value_vars=[f"{t}_n" for t in trait_cols if f"{t}_n" in agg_df.columns],
        var_name="trait_n",
        value_name="n_reps",
    )
    n_df["trait"] = n_df["trait_n"].str.replace("_n$", "", regex=True)

    long_df = (
        mean_df[["date", "cultivar", "trait", "mean_value"]]
        .merge(se_df[["date", "cultivar", "trait", "se_value"]], on=["date", "cultivar", "trait"])
        .merge(n_df[["date", "cultivar", "trait", "n_reps"]],   on=["date", "cultivar", "trait"])
    )
    long_df = long_df.sort_values(["cultivar", "trait", "date"]).reset_index(drop=True)
    return long_df


def _make_json(agg_df: pd.DataFrame, trait_cols: list[str]) -> None:
    """Generate nested JSON suitable for D3.js or Plotly.js client-side rendering."""
    cultivars = sorted(agg_df["cultivar"].unique())
    dates_all = sorted(agg_df["date"].dt.strftime("%Y-%m-%d").unique().tolist())

    output = {
        "metadata": {
            "experiment":  "Phenotyping 4",
            "year":        2025,
            "date_range":  [dates_all[0], dates_all[-1]],
            "traits":      trait_cols,
            "trait_levels": {
                "level1_stolons":   ["n_stolon_primary", "n_stolon_secondary",
                                     "n_stolon_tertiary", "n_stolon_quaternary"],
                "level2_daughters": [c for c in trait_cols if c.startswith("n_dp")],
                "level3_flowers":   ["n_flowers_total", "n_flowers_mp", "n_flowers_dp"],
                "level3_morphology":["stolon_length_primary_cm", "crown_diameter_mm"],
            },
        },
        "cultivars": {},
    }

    for cultivar in cultivars:
        sub = agg_df[agg_df["cultivar"] == cultivar].sort_values("date")
        dates = sub["date"].dt.strftime("%Y-%m-%d").tolist()
        traits_data: dict = {}
        for t in trait_cols:
            mean_col = f"{t}_mean"
            se_col   = f"{t}_se"
            n_col    = f"{t}_n"
            if mean_col not in sub.columns:
                continue
            traits_data[t] = {
                "mean": [None if pd.isna(v) else round(float(v), 4) for v in sub[mean_col]],
                "se":   [None if pd.isna(v) else round(float(v), 4) for v in sub[se_col]],
                "n":    [None if pd.isna(v) else int(v)             for v in sub[n_col]],
            }
        output["cultivars"][cultivar] = {
            "dates":  dates,
            "traits": traits_data,
        }

    with open(str(VIZ_JSON), "w") as f:
        json.dump(output, f, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    agg_df, long_df = run_aggregate()
    print("\nAggregated sample (first 5 rows, stolon columns):")
    pd.set_option("display.max_columns", 12)
    pd.set_option("display.width", 140)
    stolon_cols = ["date", "cultivar"] + [
        c for c in agg_df.columns if "stolon_primary" in c or "stolon_secondary" in c
    ]
    print(agg_df[stolon_cols].head())
