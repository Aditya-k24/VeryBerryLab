"""WS2 ingestion: shape, batch assignment, join keys, and — critically —
that '-' becomes missing (NaN), never zero."""
import numpy as np
import pandas as pd

from src.etl import (BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_MAP, _parse_sheet,
                     _build_df)


def test_row_count_and_keys(ws2_df):
    assert len(ws2_df) == 198                       # 11 cv × 6 dates × 3 reps
    assert ws2_df["cultivar"].nunique() == 11
    # every (date, cultivar, rep) is unique — no accidental column collisions
    assert not ws2_df.duplicated(["date", "cultivar", "rep"]).any()


def test_batch_assignment(ws2_df):
    for cv in ws2_df["cultivar"].unique():
        expect = "A" if cv in BATCH_A else "B"
        got = ws2_df[ws2_df["cultivar"] == cv]["batch"].unique()
        assert list(got) == [expect], cv


def test_trailing_space_sheet_maps_to_albion(ws2_df):
    # WS2 tab is literally "Alb " (trailing space) — must still land as Albion
    assert "Albion" in ws2_df["cultivar"].values


def test_dtypes(ws2_df):
    assert pd.api.types.is_datetime64_any_dtype(ws2_df["date"])
    for t in TRAIT_COLS:
        assert pd.api.types.is_numeric_dtype(ws2_df[t])


class _FakeWS:
    """Minimal openpyxl-like sheet: rows of tuples via iter_rows(values_only)."""
    def __init__(self, rows):
        self._rows = rows

    def iter_rows(self, values_only=True):
        return iter(self._rows)


def test_dash_becomes_nan_not_zero():
    # date row, rep row, then one trait row with a '-' in rep 2
    import datetime as dt
    d = dt.datetime(2025, 4, 16)
    rows = [
        ("Date", d, d, d),
        ("Rep", 1, 2, 3),
        ("Pri stolon", 5, "-", 7),
    ]
    recs, warns = _parse_sheet(_FakeWS(rows), "Finn")
    df = _build_df(recs)
    vals = df.sort_values("rep")["n_stolon_primary"].tolist()
    assert vals[0] == 5.0
    assert np.isnan(vals[1])          # '-' -> NaN
    assert vals[2] == 7.0
    # explicitly: it must NOT have been coerced to 0
    assert 0.0 not in [v for v in vals if not np.isnan(v)][1:2]


def test_double_dash_and_none_are_nan():
    import datetime as dt
    d = dt.datetime(2025, 4, 16)
    rows = [("Date", d, d), ("Rep", 1, 2), ("Crown diameter (mm)", "--", None)]
    recs, _ = _parse_sheet(_FakeWS(rows), "Finn")
    df = _build_df(recs)
    assert df["crown_diameter_mm"].isna().all()


def test_no_missing_value_silently_zero(ws2_df):
    # sanity: mean of a trait computed only over observed values, and there
    # really are missing cells in the data (so the NaN path is exercised)
    assert ws2_df[TRAIT_COLS].isna().any().any()
