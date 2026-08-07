"""
src/merged_etl.py
=================
Parse Pheno Merged Data.xlsx — multi-batch longitudinal snapshots.

Each sheet = one cultivar across Pheno batches 1-5 (2024–2026+).
Each batch group = one measurement date, 2-3 replicates.
Output: tidy DataFrame with columns date, cultivar, pheno_batch, rep, <traits>.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

MERGED_PATH = _ROOT / "data" / "Pheno Merged Data.xlsx"

MERGED_CV_MAP: dict[str, str] = {
    "Mont":   "Monterey",
    "Fron":   "Fronteras",
    "Cam":    "Camarosa",
    "Finn":   "Finn",
    "Por":    "Portola",
    "Cha":    "Chandler",
    "Sen":    "Sensation",
    "Bri":    "Brilliance",
    "Alb":    "Albion",
    "R June": "Ruby June",
    "Mox":    "Moxie",
    "Cab":    "Cabrio",
    "Rad":    "Radiance",
}

# Maps raw Excel label → canonical trait name (strip before lookup)
MERGED_TRAIT_MAP: dict[str, str] = {
    "Pri stolon":                    "n_stolon_primary",
    "Sec stolon":                    "n_stolon_secondary",
    "Ter stolon":                    "n_stolon_tertiary",
    "Quart Stolon":                  "n_stolon_quaternary",
    "dp on alt of pri stolon":       "n_dp_alt_primary",
    "dp on alt of sec stolon":       "n_dp_alt_secondary",
    "dp on alt of ter stolon":       "n_dp_alt_tertiary",
    "dp on alt of quart stolon":     "n_dp_alt_quaternary",
    "dp on mid of pri stolon":       "n_dp_mid_primary",
    "dp on mid of sec stolon":       "n_dp_mid_secondary",
    "dp on mid of ter stolon":       "n_dp_mid_tertiary",
    "dp on mid of quart stolon":     "n_dp_mid_quaternary",
    "Total dp on alt":               "n_dp_total_alt",
    "Total dp on mid":               "n_dp_total_mid",
    "#Total Flowers":                "n_flowers_total",
    "# Flowers mp/mp":               "n_flowers_mp",
    "# Flowers dp/mp":               "n_flowers_dp",
    "Pri Stolon length (cm)":        "stolon_length_primary_cm",
    "Crown diameter (mm)":           "crown_diameter_mm",
    "Dry matter g/dp":               "dry_matter_g_per_dp",
    "Leaf Area g/dp":                "leaf_area_g_per_dp",
}

MERGED_TRAIT_COLS: list[str] = list(dict.fromkeys(MERGED_TRAIT_MAP.values()))

MERGED_TRAIT_LABELS: dict[str, str] = {
    "n_stolon_primary":         "Primary Stolons",
    "n_stolon_secondary":       "Secondary Stolons",
    "n_stolon_tertiary":        "Tertiary Stolons",
    "n_stolon_quaternary":      "Quaternary Stolons",
    "n_dp_alt_primary":         "Daughter Plants (Alt) — Primary",
    "n_dp_alt_secondary":       "Daughter Plants (Alt) — Secondary",
    "n_dp_alt_tertiary":        "Daughter Plants (Alt) — Tertiary",
    "n_dp_alt_quaternary":      "Daughter Plants (Alt) — Quaternary",
    "n_dp_mid_primary":         "Daughter Plants (Mid) — Primary",
    "n_dp_mid_secondary":       "Daughter Plants (Mid) — Secondary",
    "n_dp_mid_tertiary":        "Daughter Plants (Mid) — Tertiary",
    "n_dp_mid_quaternary":      "Daughter Plants (Mid) — Quaternary",
    "n_dp_total_alt":           "Total DPs — Alternate Nodes",
    "n_dp_total_mid":           "Total DPs — Mid Nodes",
    "n_flowers_total":          "Total Flowers",
    "n_flowers_mp":             "Flowers on Mother Plant",
    "n_flowers_dp":             "Flowers on Daughter Plants",
    "stolon_length_primary_cm": "Primary Stolon Length (cm)",
    "crown_diameter_mm":        "Crown Diameter (mm)",
    "dry_matter_g_per_dp":      "Dry Matter (g / DP)",
    "leaf_area_g_per_dp":       "Leaf Area (g / DP)",
}

_MISSING_STRS = {"-", " -", "- ", "--", " - ", " -  ", "—"}
_R_BATCH, _R_DATE, _R_REP, _R_DATA = 1, 2, 3, 4


def _safe_float(v) -> Optional[float]:
    s = str(v).strip()
    if s in _MISSING_STRS or s.lower() in ("nan", "none", ""):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _col_is_numeric(df: pd.DataFrame, col: int, bcol: int, n_rows: int) -> bool:
    """Return True if the data column has at least one numeric value in a mapped-trait row."""
    for ri in range(_R_DATA, min(_R_DATA + 12, n_rows)):
        label = str(df.iloc[ri, bcol]).strip() if bcol < df.shape[1] else ""
        if label in MERGED_TRAIT_MAP:
            v = _safe_float(df.iloc[ri, col]) if col < df.shape[1] else None
            if v is not None:
                return True
    return False


def _parse_sheet(df: pd.DataFrame, cultivar: str) -> list[dict]:
    n_rows, n_cols = df.shape
    if n_rows <= _R_DATA:
        return []

    row_batch = df.iloc[_R_BATCH].tolist()
    row_date  = df.iloc[_R_DATE].tolist()
    row_rep   = df.iloc[_R_REP].tolist()

    # Find batch column start positions
    batch_pos: list[tuple[int, str]] = [
        (col, str(v).strip())
        for col, v in enumerate(row_batch)
        if str(v).strip().startswith("Pheno")
    ]
    if not batch_pos:
        return []

    records: list[dict] = []

    for bi, (bcol, bname) in enumerate(batch_pos):
        next_bcol = batch_pos[bi + 1][0] if bi + 1 < len(batch_pos) else n_cols

        # Date: first parseable timestamp in row_date within [bcol+1, next_bcol)
        date_str: Optional[str] = None
        for c in range(bcol + 1, next_bcol):
            raw = str(row_date[c]).strip() if c < n_cols else "nan"
            if raw in ("nan", "Date", ""):
                continue
            try:
                date_str = pd.Timestamp(raw).strftime("%Y-%m-%d")
                break
            except Exception:
                pass
        if not date_str:
            continue

        # Rep columns: integer-valued cells in row_rep within [bcol+1, next_bcol)
        rep_cols: list[int] = []
        for c in range(bcol + 1, next_bcol):
            raw = str(row_rep[c]).strip() if c < n_cols else "nan"
            try:
                v = int(float(raw))
                if v >= 1:
                    rep_cols.append(c)
            except (ValueError, TypeError):
                pass

        # Filter to only columns that contain actual numeric data in trait rows
        rep_cols = [c for c in rep_cols if _col_is_numeric(df, c, bcol, n_rows)]
        if not rep_cols:
            continue

        # Extract trait → [val_rep1, val_rep2, ...]
        trait_vals: dict[str, list[Optional[float]]] = {}
        for ri in range(_R_DATA, n_rows):
            raw_label = str(df.iloc[ri, bcol]).strip() if bcol < n_cols else ""
            canonical = MERGED_TRAIT_MAP.get(raw_label)
            if canonical is None:
                continue
            if canonical in trait_vals:
                continue
            vals = [
                (_safe_float(df.iloc[ri, c]) if c < n_cols else None)
                for c in rep_cols
            ]
            trait_vals[canonical] = vals

        # Skip batch if no valid trait data at all
        all_vals = [v for vals in trait_vals.values() for v in vals if v is not None]
        if not all_vals:
            continue

        for rep_idx, _col in enumerate(rep_cols):
            row: dict = {
                "date":        pd.Timestamp(date_str),
                "cultivar":    cultivar,
                "pheno_batch": bname,
                "rep":         rep_idx + 1,
            }
            for trait, vals in trait_vals.items():
                v = vals[rep_idx] if rep_idx < len(vals) else None
                row[trait] = v if v is not None else float("nan")
            records.append(row)

    return records


def load_merged(path: Optional[Path] = None) -> tuple[pd.DataFrame, list[str]]:
    """Load Pheno Merged Data.xlsx → (tidy DataFrame, warnings).

    Empty DataFrame if file not found. Sheets that parse to zero rows (e.g. a
    cultivar whose batches carry no measurement date) are reported in warnings
    rather than dropped silently.
    """
    xl_path = Path(path) if path else MERGED_PATH
    if not xl_path.exists():
        return pd.DataFrame(), [f"Merged workbook not found at {xl_path}"]

    xl = pd.ExcelFile(xl_path)
    all_records: list[dict] = []
    warnings: list[str] = []

    for sheet in xl.sheet_names:
        cultivar = MERGED_CV_MAP.get(sheet.strip())
        if cultivar is None:
            warnings.append(f"Merged: unmapped sheet '{sheet}' — skipped")
            continue
        try:
            df_raw = xl.parse(sheet, header=None)
            recs   = _parse_sheet(df_raw, cultivar)
            if not recs:
                warnings.append(
                    f"Merged: {cultivar} produced no rows — likely missing "
                    f"measurement dates in the workbook; excluded from cross-batch view"
                )
            all_records.extend(recs)
        except Exception as e:
            warnings.append(f"Merged: {cultivar} failed to parse ({e}) — skipped")

    if not all_records:
        return pd.DataFrame(), warnings

    df = pd.DataFrame(all_records)
    df["date"] = pd.to_datetime(df["date"])
    df["rep"]  = pd.to_numeric(df["rep"], errors="coerce").astype("Int64")
    for col in MERGED_TRAIT_COLS:
        if col not in df.columns:
            df[col] = float("nan")
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values(["cultivar", "pheno_batch", "date", "rep"]).reset_index(drop=True)
    return df, warnings
