"""
src/stats.py
============
Statistical engine for the VeryBerryLab phenotyping dashboard.

Per (trait × date) computation
--------------------------------
  1. Kruskal–Wallis H test (scipy.stats.kruskal)
  2. Effect size ε²  =  (H − k + 1) / (n − k),  clipped at 0
  3. Conover–Iman post-hoc with Holm correction (scikit-posthocs)
  4. Compact Letter Display (Piepho 2004 sweep algorithm)

Public API
----------
  compute_stats_for(df, trait, date, alpha, correction) -> StatsResult | None
  compute_all_stats(df, alpha, correction) -> dict[(trait, date_str), StatsResult]
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import scipy.stats as scipy_stats
import scikit_posthocs as sp


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class StatsResult:
    trait: str
    date: str                          # ISO date string YYYY-MM-DD
    cultivars: list[str]               # cultivars present on this date
    n_per_cv: dict[str, int]           # n valid observations per cultivar
    means: dict[str, float]
    medians: dict[str, float]
    se: dict[str, float]
    raw_values: dict[str, list[float]] # list of up to 3 rep values

    kw_H: float
    kw_p: float
    epsilon2: float                    # effect size, [0, 1]
    significant: bool

    cld: dict[str, str]                # compact letter display (always computed)
    posthoc: Optional[pd.DataFrame]    # adjusted p-value matrix (None if n_groups < 2)

    alpha: float
    correction: str


# ---------------------------------------------------------------------------
# CLD — Piepho (2004) sweep algorithm
# ---------------------------------------------------------------------------

def _compact_letter_display(
    means: dict[str, float],
    posthoc: pd.DataFrame,
    alpha: float,
) -> dict[str, str]:
    """
    Piepho (2004) sweep algorithm.
    Returns dict: cultivar -> letter string (e.g. 'a', 'ab', 'b').
    Cultivars that share at least one letter are NOT significantly different.
    """
    cultivars = list(means.keys())
    if len(cultivars) == 1:
        return {cultivars[0]: "a"}

    # Sort by mean ascending (Piepho: sweep from left to right)
    sorted_cvs = sorted(cultivars, key=lambda cv: means.get(cv, 0.0))
    idx = {cv: i for i, cv in enumerate(sorted_cvs)}
    n = len(sorted_cvs)

    # Build set of significantly-different index-pairs
    sig_pairs: set[tuple[int, int]] = set()
    for i, cv_i in enumerate(sorted_cvs):
        for j, cv_j in enumerate(sorted_cvs):
            if j <= i:
                continue
            try:
                p = posthoc.loc[cv_i, cv_j]
            except KeyError:
                try:
                    p = posthoc.loc[cv_j, cv_i]
                except KeyError:
                    continue
            if pd.notna(p) and p < alpha:
                sig_pairs.add((i, j))

    # Initialise groups as one set containing all cultivars
    groups: set[frozenset[int]] = {frozenset(range(n))}

    # Sweep: for each significant pair, split any group containing both
    changed = True
    while changed:
        changed = False
        new_groups: set[frozenset[int]] = set()
        for group in groups:
            split_done = False
            for (i, j) in sig_pairs:
                if i in group and j in group:
                    g1 = group - {i}
                    g2 = group - {j}
                    if g1:
                        new_groups.add(g1)
                    if g2:
                        new_groups.add(g2)
                    split_done = True
                    changed = True
                    break
            if not split_done:
                new_groups.add(group)
        groups = new_groups

    # Remove redundant groups (subsets of another group)
    groups_list = list(groups)
    non_redundant = [
        g for g in groups_list
        if not any(g < other for other in groups_list)
    ]

    # Sort groups for deterministic letter assignment (largest first, then by min member)
    non_redundant.sort(key=lambda g: (-len(g), min(g)))

    # Assign letters
    letter_map: dict[str, list[str]] = {cv: [] for cv in sorted_cvs}
    for letter_idx, group in enumerate(non_redundant):
        letter = chr(ord("a") + letter_idx)
        for i in group:
            letter_map[sorted_cvs[i]].append(letter)

    return {cv: "".join(sorted(letters)) for cv, letters in letter_map.items()}


# ---------------------------------------------------------------------------
# Per (trait × date) computation
# ---------------------------------------------------------------------------

def compute_stats_for(
    df: pd.DataFrame,
    trait: str,
    date,
    alpha: float = 0.05,
    correction: str = "holm",
) -> Optional[StatsResult]:
    """
    Compute full stats for one (trait, date) combination.
    Returns None if fewer than 2 cultivars have any data on this date.
    """
    date_ts = pd.Timestamp(date)
    subset = df[df["date"] == date_ts][["cultivar", trait]].dropna(subset=[trait])

    if subset.empty:
        return None

    groups = subset.groupby("cultivar")[trait]
    group_data = {cv: vals.tolist() for cv, vals in groups}
    group_data = {cv: vals for cv, vals in group_data.items() if len(vals) >= 1}

    if len(group_data) < 2:
        return None

    cultivars = sorted(group_data.keys())
    n_per_cv    = {cv: len(group_data[cv]) for cv in cultivars}
    means       = {cv: float(np.mean(group_data[cv])) for cv in cultivars}
    medians     = {cv: float(np.median(group_data[cv])) for cv in cultivars}
    se          = {
        cv: float(np.std(group_data[cv], ddof=1) / math.sqrt(len(group_data[cv])))
        if len(group_data[cv]) > 1 else 0.0
        for cv in cultivars
    }

    # Kruskal–Wallis
    arrays = [group_data[cv] for cv in cultivars]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            kw_H, kw_p = scipy_stats.kruskal(*arrays)
    except ValueError:
        return None

    # Effect size ε²  (Tomczak & Tomczak 2014)
    k = len(cultivars)
    n_total = sum(n_per_cv.values())
    epsilon2 = max(0.0, (kw_H - k + 1) / (n_total - k)) if n_total > k else 0.0
    epsilon2 = min(epsilon2, 1.0)

    significant = bool(kw_p < alpha)

    # Post-hoc (always compute for CLD; grey it in UI if not significant)
    posthoc: Optional[pd.DataFrame] = None
    cld: dict[str, str] = {cv: "a" for cv in cultivars}

    if len(cultivars) >= 2:
        try:
            long_df = subset[subset["cultivar"].isin(cultivars)].copy()
            long_df.columns = ["cultivar", "value"]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                posthoc = sp.posthoc_conover(
                    long_df, val_col="value", group_col="cultivar", p_adjust=correction
                )
            cld = _compact_letter_display(means, posthoc, alpha)
        except Exception:
            posthoc = None

    date_str = date_ts.strftime("%Y-%m-%d")

    return StatsResult(
        trait=trait,
        date=date_str,
        cultivars=cultivars,
        n_per_cv=n_per_cv,
        means=means,
        medians=medians,
        se=se,
        raw_values=group_data,
        kw_H=float(kw_H),
        kw_p=float(kw_p),
        epsilon2=epsilon2,
        significant=significant,
        cld=cld,
        posthoc=posthoc,
        alpha=alpha,
        correction=correction,
    )


# ---------------------------------------------------------------------------
# Full cache
# ---------------------------------------------------------------------------

def compute_all_stats(
    df: pd.DataFrame,
    alpha: float = 0.05,
    correction: str = "holm",
) -> dict[tuple[str, str], StatsResult]:
    """
    Compute stats for every (trait, date) combination in df.
    Returns dict keyed by (trait, 'YYYY-MM-DD').
    """
    from src.etl import TRAIT_COLS

    cache: dict[tuple[str, str], StatsResult] = {}
    all_dates = sorted(df["date"].unique())

    for trait in TRAIT_COLS:
        for date in all_dates:
            result = compute_stats_for(df, trait, date, alpha=alpha, correction=correction)
            if result is not None:
                cache[(trait, result.date)] = result

    return cache


# ---------------------------------------------------------------------------
# Significance label helper
# ---------------------------------------------------------------------------

def sig_label(p: float) -> str:
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"
