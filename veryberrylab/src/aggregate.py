"""
src/aggregate.py
================
Season-level summary metrics derived from the clean DataFrame and stats cache.

Per (trait, cultivar):
  - trend:          'up', 'down', 'flat'  (linear regression slope over observed dates)
  - slope:          float (trait units per day)
  - peak_value:     max cultivar mean across dates
  - peak_date:      date of peak_value
  - champion_wins:  number of dates where this cultivar is in the 'a' CLD group
                    (only counted when the omnibus test is significant)
  - champion_pct:   champion_wins / dates_with_significant_kw

Also exposes build_completeness_matrix() for the Data Health page.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.etl import TRAIT_COLS, TRAIT_DIRECTION


def compute_season_metrics(
    df: pd.DataFrame,
    stats_cache: dict,
) -> pd.DataFrame:
    """
    Returns a DataFrame with columns:
        cultivar, trait, trend, slope, peak_value, peak_date,
        champion_wins, total_sig_dates, champion_pct
    """
    rows = []

    cultivars = sorted(df["cultivar"].unique())
    all_dates  = sorted(df["date"].unique())

    for trait in TRAIT_COLS:
        higher_is_better = TRAIT_DIRECTION.get(trait, True)

        for cv in cultivars:
            cv_df = df[df["cultivar"] == cv][["date", trait]].dropna(subset=[trait])
            if cv_df.empty:
                continue

            # Mean per date
            means_by_date = cv_df.groupby("date")[trait].mean()
            dates = means_by_date.index.tolist()
            vals  = means_by_date.values.tolist()

            # Trend (linear regression on date ordinal)
            slope = 0.0
            trend = "flat"
            if len(dates) >= 2:
                x = np.array([(d - dates[0]).days for d in dates], dtype=float)
                y = np.array(vals, dtype=float)
                mask = np.isfinite(y)
                if mask.sum() >= 2:
                    coeffs = np.polyfit(x[mask], y[mask], 1)
                    slope = float(coeffs[0])
                    # Use 5% of mean as threshold for "flat"
                    mean_val = float(np.nanmean(y))
                    threshold = abs(mean_val) * 0.05 if mean_val != 0 else 0.01
                    if slope > threshold:
                        trend = "up"
                    elif slope < -threshold:
                        trend = "down"

            # Peak
            valid_vals = [(d, v) for d, v in zip(dates, vals) if np.isfinite(v)]
            if valid_vals:
                if higher_is_better:
                    peak_date, peak_value = max(valid_vals, key=lambda x: x[1])
                else:
                    peak_date, peak_value = min(valid_vals, key=lambda x: x[1])
            else:
                peak_date, peak_value = None, float("nan")

            # Champion wins
            champion_wins = 0
            total_sig_dates = 0

            for date in all_dates:
                date_str = pd.Timestamp(date).strftime("%Y-%m-%d")
                result = stats_cache.get((trait, date_str))
                if result is None:
                    continue
                if cv not in result.cultivars:
                    continue
                if not result.significant:
                    continue
                total_sig_dates += 1
                cld_letter = result.cld.get(cv, "")
                if "a" in cld_letter:
                    champion_wins += 1

            champion_pct = (
                100.0 * champion_wins / total_sig_dates
                if total_sig_dates > 0
                else float("nan")
            )

            rows.append({
                "cultivar":       cv,
                "trait":          trait,
                "trend":          trend,
                "slope":          slope,
                "peak_value":     peak_value,
                "peak_date":      peak_date,
                "champion_wins":  champion_wins,
                "total_sig_dates": total_sig_dates,
                "champion_pct":   champion_pct,
            })

    return pd.DataFrame(rows)


def build_completeness_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a long DataFrame with columns:
        cultivar, date, trait, status

    status values:
        'observed'      — at least one non-NaN rep exists
        'not_measured'  — date is in this cultivar's schedule but all reps are NaN
        'not_scheduled' — date is not in this cultivar's schedule
    """
    all_dates = sorted(df["date"].unique())

    # Each cultivar's scheduled dates
    cv_dates: dict[str, set] = {}
    for cv in df["cultivar"].unique():
        cv_dates[cv] = set(df[df["cultivar"] == cv]["date"].unique())

    rows = []
    for cv in sorted(df["cultivar"].unique()):
        for date in all_dates:
            for trait in TRAIT_COLS:
                if date not in cv_dates[cv]:
                    status = "not_scheduled"
                else:
                    subset = df[(df["cultivar"] == cv) & (df["date"] == date)][trait]
                    if subset.notna().any():
                        status = "observed"
                    else:
                        status = "not_measured"

                rows.append({
                    "cultivar": cv,
                    "date":     date,
                    "trait":    trait,
                    "status":   status,
                })

    return pd.DataFrame(rows)
