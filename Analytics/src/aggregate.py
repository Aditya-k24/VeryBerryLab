"""
src/aggregate.py
================
Season-level metrics and completeness matrix.

compute_season_metrics(df, stats_cache) -> DataFrame
  columns: cultivar, trait, trend, slope, peak_value, peak_date,
           champion_wins, total_sig_dates, champion_pct

build_completeness_matrix(df) -> DataFrame
  columns: cultivar, date, trait, status
  status: 'observed' | 'not_measured' | 'not_scheduled'
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.etl import TRAIT_COLS, TRAIT_DIRECTION


def compute_season_metrics(df: pd.DataFrame, stats_cache: dict) -> pd.DataFrame:
    rows = []
    all_dates = sorted(df["date"].unique())

    for trait in TRAIT_COLS:
        higher_is_better = TRAIT_DIRECTION.get(trait, True)

        for cv in sorted(df["cultivar"].unique()):
            sub = df[df["cultivar"] == cv][["date", trait]].dropna(subset=[trait])
            if sub.empty:
                continue

            means_by_date = sub.groupby("date")[trait].mean()
            dates = means_by_date.index.tolist()
            vals  = means_by_date.values.tolist()

            # Trend
            slope = 0.0
            trend = "flat"
            if len(dates) >= 2:
                x = np.array([(d - dates[0]).days for d in dates], dtype=float)
                y = np.array(vals, dtype=float)
                mask = np.isfinite(y)
                if mask.sum() >= 2:
                    slope = float(np.polyfit(x[mask], y[mask], 1)[0])
                    threshold = abs(float(np.nanmean(y))) * 0.05 if np.nanmean(y) != 0 else 0.01
                    trend = "up" if slope > threshold else ("down" if slope < -threshold else "flat")

            # Peak
            valid = [(d, v) for d, v in zip(dates, vals) if np.isfinite(v)]
            if valid:
                peak_date, peak_value = (max if higher_is_better else min)(valid, key=lambda x: x[1])
            else:
                peak_date, peak_value = None, float("nan")

            # Champion wins
            wins = 0
            sig_dates = 0
            for date in all_dates:
                ds = pd.Timestamp(date).strftime("%Y-%m-%d")
                r  = stats_cache.get((trait, ds))
                if r is None or cv not in r.cultivars or not r.significant:
                    continue
                sig_dates += 1
                if "a" in r.cld.get(cv, ""):
                    wins += 1

            rows.append({
                "cultivar":        cv,
                "trait":           trait,
                "trend":           trend,
                "slope":           slope,
                "peak_value":      peak_value,
                "peak_date":       peak_date,
                "champion_wins":   wins,
                "total_sig_dates": sig_dates,
                "champion_pct":    100.0 * wins / sig_dates if sig_dates > 0 else float("nan"),
            })

    return pd.DataFrame(rows)


def build_completeness_matrix(df: pd.DataFrame) -> pd.DataFrame:
    all_dates = sorted(df["date"].unique())
    cv_dates  = {cv: set(df[df["cultivar"] == cv]["date"].unique()) for cv in df["cultivar"].unique()}
    rows = []
    for cv in sorted(df["cultivar"].unique()):
        for date in all_dates:
            for trait in TRAIT_COLS:
                if date not in cv_dates[cv]:
                    status = "not_scheduled"
                elif df[(df["cultivar"] == cv) & (df["date"] == date)][trait].notna().any():
                    status = "observed"
                else:
                    status = "not_measured"
                rows.append({"cultivar": cv, "date": date, "trait": trait, "status": status})
    return pd.DataFrame(rows)
