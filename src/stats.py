"""
src/stats.py
============
Statistical engine: Kruskal–Wallis · effect size ε² · Conover–Iman / Holm · CLD.

Public API
----------
  compute_stats_for(df, trait, date, alpha, correction) -> StatsResult | None
  compute_all_stats(df, alpha, correction) -> dict[(trait, 'YYYY-MM-DD'), StatsResult]
  sig_label(p) -> str   e.g. '***', '**', '*', 'ns'
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import scipy.stats as scipy_stats
import scikit_posthocs as sp


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class StatsResult:
    trait:      str
    date:       str          # YYYY-MM-DD
    cultivars:  list[str]    # cultivars present on this date
    n_per_cv:   dict[str, int]
    means:      dict[str, float]
    medians:    dict[str, float]
    se:         dict[str, float]
    raw_values: dict[str, list[float]]

    kw_H:       float
    kw_p:       float
    epsilon2:   float        # [0, 1]
    significant: bool

    cld:        dict[str, str]           # Piepho CLD letters
    posthoc:    Optional[pd.DataFrame]   # adjusted p-value matrix

    alpha:      float
    correction: str          # 'holm' | 'bonferroni'


# ---------------------------------------------------------------------------
# CLD — Piepho (2004) sweep algorithm
# ---------------------------------------------------------------------------

def _cld(means: dict[str, float], posthoc: pd.DataFrame, alpha: float) -> dict[str, str]:
    """
    Returns {cultivar: letter_string} where shared letters = not significantly different.
    """
    cvs = list(means)
    if len(cvs) == 1:
        return {cvs[0]: "a"}

    sorted_cvs = sorted(cvs, key=lambda c: means.get(c, 0.0))
    idx = {c: i for i, c in enumerate(sorted_cvs)}
    n   = len(sorted_cvs)

    sig: set[tuple[int, int]] = set()
    for i, ci in enumerate(sorted_cvs):
        for j, cj in enumerate(sorted_cvs):
            if j <= i:
                continue
            try:
                p = posthoc.loc[ci, cj]
            except KeyError:
                try:
                    p = posthoc.loc[cj, ci]
                except KeyError:
                    continue
            if pd.notna(p) and float(p) < alpha:
                sig.add((i, j))

    groups: set[frozenset[int]] = {frozenset(range(n))}

    changed = True
    while changed:
        changed = False
        next_groups: set[frozenset[int]] = set()
        for grp in groups:
            split = False
            for (i, j) in sig:
                if i in grp and j in grp:
                    g1 = grp - {i}
                    g2 = grp - {j}
                    if g1: next_groups.add(g1)
                    if g2: next_groups.add(g2)
                    split = True
                    changed = True
                    break
            if not split:
                next_groups.add(grp)
        groups = next_groups

    gl = list(groups)
    non_redundant = [g for g in gl if not any(g < other for other in gl)]
    non_redundant.sort(key=lambda g: (-len(g), min(g)))

    letter_map: dict[str, list[str]] = {c: [] for c in sorted_cvs}
    for li, grp in enumerate(non_redundant):
        letter = chr(ord("a") + li)
        for i in grp:
            letter_map[sorted_cvs[i]].append(letter)

    return {c: "".join(sorted(letters)) for c, letters in letter_map.items()}


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_stats_for(
    df: pd.DataFrame,
    trait: str,
    date,
    alpha: float = 0.05,
    correction: str = "holm",
) -> Optional[StatsResult]:
    date_ts = pd.Timestamp(date)
    sub = df[df["date"] == date_ts][["cultivar", trait]].dropna(subset=[trait])
    if sub.empty:
        return None

    gd = {cv: g[trait].tolist() for cv, g in sub.groupby("cultivar") if len(g) >= 1}
    if len(gd) < 2:
        return None

    cvs      = sorted(gd)
    n_per_cv = {cv: len(gd[cv]) for cv in cvs}
    means    = {cv: float(np.mean(gd[cv])) for cv in cvs}
    medians  = {cv: float(np.median(gd[cv])) for cv in cvs}
    se       = {
        cv: float(np.std(gd[cv], ddof=1) / math.sqrt(len(gd[cv]))) if len(gd[cv]) > 1 else 0.0
        for cv in cvs
    }

    arrays = [gd[cv] for cv in cvs]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            kw_H, kw_p = scipy_stats.kruskal(*arrays)
    except ValueError:
        return None

    k       = len(cvs)
    n_total = sum(n_per_cv.values())
    eps2    = max(0.0, min(1.0, (kw_H - k + 1) / (n_total - k))) if n_total > k else 0.0

    posthoc: Optional[pd.DataFrame] = None
    cld_letters: dict[str, str]     = {cv: "a" for cv in cvs}

    if k >= 2:
        try:
            long = sub[sub["cultivar"].isin(cvs)].copy()
            long.columns = ["cultivar", "value"]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                posthoc = sp.posthoc_conover(
                    long, val_col="value", group_col="cultivar", p_adjust=correction
                )
            cld_letters = _cld(means, posthoc, alpha)
        except Exception:
            posthoc = None

    return StatsResult(
        trait=trait,
        date=date_ts.strftime("%Y-%m-%d"),
        cultivars=cvs,
        n_per_cv=n_per_cv,
        means=means,
        medians=medians,
        se=se,
        raw_values=gd,
        kw_H=float(kw_H),
        kw_p=float(kw_p),
        epsilon2=eps2,
        significant=bool(kw_p < alpha),
        cld=cld_letters,
        posthoc=posthoc,
        alpha=alpha,
        correction=correction,
    )


def compute_all_stats(
    df: pd.DataFrame,
    alpha: float = 0.05,
    correction: str = "holm",
) -> dict[tuple[str, str], StatsResult]:
    from src.etl import TRAIT_COLS
    cache: dict[tuple[str, str], StatsResult] = {}
    for trait in TRAIT_COLS:
        for date in sorted(df["date"].unique()):
            r = compute_stats_for(df, trait, date, alpha=alpha, correction=correction)
            if r is not None:
                cache[(trait, r.date)] = r
    return cache


def sig_label(p: float) -> str:
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    return "ns"
