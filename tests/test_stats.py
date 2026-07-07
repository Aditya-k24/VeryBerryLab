"""Statistical engine: KW significance, epsilon2 bounds, and CLD letter
direction (regression guard: 'a' must mark the HIGHEST-mean group)."""
import numpy as np
import pandas as pd

from src.stats import compute_stats_for, sig_label


def _df(groups):
    rows = []
    for cv, vals in groups.items():
        for r, v in enumerate(vals):
            rows.append({"date": pd.Timestamp("2025-01-01"),
                         "cultivar": cv, "x": float(v), "rep": r + 1})
    return pd.DataFrame(rows)


def test_cld_letter_a_is_highest_mean():
    # well-separated, enough reps to reach significance
    g = {"Low": [1, 1.1, 0.9, 1.0, 1.2],
         "Mid": [5, 5.1, 4.9, 5.0, 5.2],
         "High": [20, 20.1, 19.9, 20.0, 20.2]}
    r = compute_stats_for(_df(g), "x", pd.Timestamp("2025-01-01"))
    assert r.significant
    top = max(r.means, key=r.means.get)
    assert top == "High"
    assert "a" in r.cld["High"]           # champion letter on the best group
    assert "a" not in r.cld["Low"]        # not on the worst


def test_cld_letter_order_follows_mean_not_group_size():
    # A dominant top cultivar (small group) plus a larger low cluster: letter
    # 'a' must go to the TOP mean, not to the biggest group.
    g = {"Top": [40, 41, 39, 40, 42],
         "M1": [10, 11, 9, 10, 12], "M2": [10, 9, 11, 10, 11],
         "M3": [9, 10, 11, 10, 9]}
    r = compute_stats_for(_df(g), "x", pd.Timestamp("2025-01-01"))
    top = max(r.means, key=r.means.get)
    assert top == "Top"
    assert "a" in r.cld["Top"]
    assert all("a" not in r.cld[c] for c in ["M1", "M2", "M3"])


def test_epsilon2_bounds():
    g = {"A": [1, 2, 3], "B": [1, 2, 3], "C": [1, 2, 3]}
    r = compute_stats_for(_df(g), "x", pd.Timestamp("2025-01-01"))
    assert 0.0 <= r.epsilon2 <= 1.0


def test_identical_groups_not_significant():
    g = {"A": [2, 2, 2], "B": [2, 2, 2], "C": [2, 2, 2]}
    r = compute_stats_for(_df(g), "x", pd.Timestamp("2025-01-01"))
    assert not r.significant


def test_single_group_returns_none():
    g = {"A": [1, 2, 3]}
    assert compute_stats_for(_df(g), "x", pd.Timestamp("2025-01-01")) is None


def test_shared_letter_when_indistinguishable():
    g = {"A": [10, 10.1, 9.9], "B": [10.2, 9.8, 10.0], "C": [10.1, 9.9, 10.0]}
    r = compute_stats_for(_df(g), "x", pd.Timestamp("2025-01-01"))
    # none separable -> all share letter 'a'
    assert all("a" in v for v in r.cld.values())


def test_missing_dropped_not_zeroed():
    g = {"A": [10, 10, float("nan")], "B": [1, 1, 1]}
    r = compute_stats_for(_df(g), "x", pd.Timestamp("2025-01-01"))
    assert r.n_per_cv["A"] == 2           # NaN row excluded, not counted as 0
    assert r.means["A"] == 10.0


def test_sig_label():
    assert sig_label(0.0005) == "***"
    assert sig_label(0.005) == "**"
    assert sig_label(0.03) == "*"
    assert sig_label(0.5) == "ns"


def test_real_cache_epsilon2_in_range(stats_cache):
    for r in stats_cache.values():
        assert 0.0 <= r.epsilon2 <= 1.0
        assert set(r.means) == set(r.cultivars)
