"""
src/ws1_parser.py
=================
Parse Phenotyping 4 Worksheet 1.xlsx — repeated stolon/daughter measurements
collected 6-7 times per cultivar between April and July 2025.

Each sheet = one cultivar.
Each date block = measurements for all tracked plants on that date.

Output structure per cultivar:
{
    "cultivar": str,
    "dates":    [sorted ISO date strings, e.g. "2025-04-23"],
    "plants": {
        plant_code: {
            date_str: {
                "sec_stolon":    int,
                "sec_daughters": int,
                "ter_stolon":    int,
                "ter_daughters": int,
                "quart_stolon":  int,
                "quart_daughters": int,
                "stolon_length": float | None,
                "measured":      True    # this row had real measurements
            }
        }
    },
    "codes_by_date": {date_str: [all plant codes listed on that date]}
}
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd

# ── File discovery ─────────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent          # Analytics/src/
_ROOT = _HERE.parent                             # Analytics/

WS1_CANDIDATES: list[Path] = [
    _ROOT / "data" / "Phenotyping 4 Worksheet 1.xlsx",
    _ROOT.parent / "Phenotyping Data with Aditya 1_27_2026" / "Pheno Batch 4" / "Phenotyping 4 Worksheet 1.xlsx",
]

WS1_SHEET_MAP: dict[str, str] = {
    "Fin":   "Finn",
    "Cab":   "Cabrio",
    "Cam":   "Camarosa",
    "Sen":   "Sensation",
    "Cha":   "Chandler",
    "Alb":   "Albion",
    "Mox":   "Moxie",
    "RJune": "Ruby June",
    "Bri":   "Brilliance",
    "Por":   "Portola",
    "Rad":   "Radiance",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

_CODE_RE = re.compile(r"^\d+\.\d+[\d./]*$")

def _is_code(s: str) -> bool:
    """True if the string looks like a plant code (e.g. '1.1.2.1', '1.1.2/1.4.2')."""
    s = s.strip().replace(" ", "")
    return bool(_CODE_RE.match(s)) and len(s) >= 5

def _to_int(v) -> int:
    try:
        f = float(str(v))
        return int(f) if not pd.isna(f) else 0
    except (ValueError, TypeError):
        return 0

def _to_float(v) -> Optional[float]:
    try:
        f = float(str(v))
        return f if not pd.isna(f) else None
    except (ValueError, TypeError):
        return None


# ── Per-sheet parser ───────────────────────────────────────────────────────────

def _parse_sheet(df_raw: pd.DataFrame, cultivar: str) -> dict:
    """
    Parse one raw sheet (no header set — header is in row index 2).
    Returns the per-cultivar data dict.
    """
    # Detect column layout from header row (row index 2)
    hdr = [str(v).strip().lower() for v in df_raw.iloc[2].tolist()]

    # Find key column indices
    def _col(keywords):
        for i, h in enumerate(hdr):
            if all(k in h for k in keywords):
                return i
        return None

    col_sec_st  = _col(["sec", "stolon"]) or 1
    col_sec_dp  = _col(["sec", "daughter"]) or 2
    col_ter_st  = _col(["ter", "stolon"]) or 3
    col_ter_dp  = _col(["ter", "daughter"]) or 4

    # Quart columns only in Cam & Rad
    col_qrt_st  = _col(["quart", "stolon"])
    col_qrt_dp  = _col(["quart", "daughter"])

    # Stolon Length — last column named "stolon length" or "length"
    col_length  = None
    for i, h in enumerate(hdr):
        if "stolon" in h and "length" in h:
            col_length = i
    if col_length is None:
        col_length = _col(["length"]) or (8 if col_qrt_st else 6)

    n_cols = len(df_raw.columns)

    def safe_get(row, idx):
        if idx is None or idx >= n_cols:
            return None
        v = row.iloc[idx]
        return None if (isinstance(v, float) and pd.isna(v)) else v

    # Walk all rows
    current_date: Optional[str] = None
    plants: dict = {}
    codes_by_date: dict = {}

    for _, row in df_raw.iterrows():
        cell0 = str(safe_get(row, 0) or "").strip()
        cell1 = str(safe_get(row, 1) or "").strip()

        # ── Date marker ────────────────────────────────────────────────────
        if cell0.lower() == "date" and cell1:
            try:
                ts = pd.Timestamp(cell1)
                current_date = ts.strftime("%Y-%m-%d")
                codes_by_date.setdefault(current_date, [])
            except Exception:
                pass
            continue

        # ── Plant-code row ─────────────────────────────────────────────────
        if current_date and _is_code(cell0):
            code = cell0.replace(" ", "").replace("//", "/")
            codes_by_date[current_date].append(code)

            # Check for measurements in numeric columns
            raw_sec_st  = safe_get(row, col_sec_st)
            raw_sec_dp  = safe_get(row, col_sec_dp)
            raw_ter_st  = safe_get(row, col_ter_st)
            raw_ter_dp  = safe_get(row, col_ter_dp)
            raw_len     = safe_get(row, col_length)

            has_data = any(v is not None for v in [raw_sec_st, raw_sec_dp, raw_ter_st, raw_ter_dp, raw_len])

            if has_data:
                rec: dict = {
                    "sec_stolon":      _to_int(raw_sec_st),
                    "sec_daughters":   _to_int(raw_sec_dp),
                    "ter_stolon":      _to_int(raw_ter_st),
                    "ter_daughters":   _to_int(raw_ter_dp),
                    "quart_stolon":    _to_int(safe_get(row, col_qrt_st)),
                    "quart_daughters": _to_int(safe_get(row, col_qrt_dp)),
                    "stolon_length":   _to_float(raw_len),
                    "measured":        True,
                }
                plants.setdefault(code, {})[current_date] = rec

    dates = sorted(codes_by_date.keys())
    return {
        "cultivar":      cultivar,
        "dates":         dates,
        "plants":        plants,
        "codes_by_date": codes_by_date,
    }


# ── Public loader ──────────────────────────────────────────────────────────────

def load_ws1(path: Optional[Path] = None, verbose: bool = False) -> dict[str, dict]:
    """
    Load all cultivar sheets from Worksheet 1.
    Returns {cultivar_name: data_dict}.  Empty dict if file not found.
    """
    candidates = [path] if path else WS1_CANDIDATES
    xl_path = next((p for p in candidates if p and Path(p).exists()), None)

    if xl_path is None:
        if verbose:
            print("  ws1_parser: Worksheet 1 not found — searched:", candidates)
        return {}

    xl = pd.ExcelFile(xl_path)
    result: dict[str, dict] = {}

    for sheet in xl.sheet_names:
        cultivar = WS1_SHEET_MAP.get(sheet.strip())
        if cultivar is None:
            continue
        try:
            df_raw = xl.parse(sheet, header=None)
            data   = _parse_sheet(df_raw, cultivar)
            if data["dates"]:
                result[cultivar] = data
                if verbose:
                    n_plants = len(data["plants"])
                    print(f"    {cultivar}: {len(data['dates'])} dates, {n_plants} measured plants")
        except Exception as e:
            if verbose:
                print(f"  Skipped {sheet}: {e}")

    return result
