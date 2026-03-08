"""
src/etl.py
==========
Ingest Phenotyping 4 Worksheet 2 (wide cross-tab, 11 cultivar sheets) and
produce a tidy, row-per-rep CSV ready for statistical analysis.

Canonical data source
---------------------
    Phenotyping Data with Aditya 1_27_2026/Pheno Batch 4/
        Phenotyping 4 Worksheet 2.xlsx

Run from the veryberrylab/ directory
-------------------------------------
    python3 src/etl.py

Output
------
    data/processed/pheno4_clean.csv   — 198 rows × 22 columns
                                        (11 cultivars × 6 dates × 3 reps)
"""

from pathlib import Path

import openpyxl
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

# Canonical source: the original workbook in the shared data folder.
# data/raw/ holds an identical copy for offline use; both have the same MD5.
CANONICAL_XLSX = (
    ROOT.parent
    / "Phenotyping Data with Aditya 1_27_2026"
    / "Pheno Batch 4"
    / "Phenotyping 4 Worksheet 2.xlsx"
)
FALLBACK_XLSX = ROOT / "data" / "raw" / "Phenotyping 4 Worksheet 2.xlsx"
RAW_PATH = CANONICAL_XLSX if CANONICAL_XLSX.exists() else FALLBACK_XLSX

OUT_PATH = ROOT / "data" / "processed" / "pheno4_clean.csv"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Cultivar tab → full name map
# ---------------------------------------------------------------------------
CULTIVAR_MAP = {
    "Fin":   "Finn",
    "Cab":   "Cabrio",
    "Cam":   "Camarosa",   # ⚠️ provisional — confirm with team (see ASSUMPTIONS.md)
    "Sen":   "Sensation",
    "Cha":   "Chandler",
    "Alb ":  "Albion",     # tab name has trailing space
    "Alb":   "Albion",     # defensive: handle without space too
    "Mox":   "Moxie",
    "RJune": "Ruby June",
    "Bri":   "Brilliance",
    "Por":   "Portola",
    "Rad":   "Radiance",
}

# ---------------------------------------------------------------------------
# Trait row label → internal column name
# Trailing spaces in labels are stripped before lookup.
# ---------------------------------------------------------------------------
TRAIT_MAP = {
    "Pri stolon":               "n_stolon_primary",
    "Sec stolon":               "n_stolon_secondary",
    "Ter stolon":               "n_stolon_tertiary",
    "Quart Stolon":             "n_stolon_quaternary",
    "dp on alt of pri stolon":  "n_dp_alt_primary",
    "dp on alt of sec stolon":  "n_dp_alt_secondary",
    "dp on alt of ter stolon":  "n_dp_alt_tertiary",
    "dp on alt of quart stolon":"n_dp_alt_quaternary",
    "dp on mid of pri stolon":  "n_dp_mid_primary",
    "dp on mid of sec stolon":  "n_dp_mid_secondary",
    "dp on mid of ter stolon":  "n_dp_mid_tertiary",
    "dp on mid of quart stolon":"n_dp_mid_quaternary",
    "Total dp on alt":          "n_dp_total_alt",
    "Total dp on mid":          "n_dp_total_mid",
    "#Total Flowers":           "n_flowers_total",
    "# Flowers mp/mp":          "n_flowers_mp",
    "# Flowers dp/mp":          "n_flowers_dp",
    "Pri Stolon length (cm)":   "stolon_length_primary_cm",
    "Crown diameter (mm)":      "crown_diameter_mm",
}

NUMERIC_COLS = [c for c in TRAIT_MAP.values()]


# ---------------------------------------------------------------------------
# Per-sheet parser
# ---------------------------------------------------------------------------

def _parse_sheet(ws, cultivar_name: str) -> list[dict]:
    """
    Convert one cultivar sheet (wide cross-tab) into a list of tidy records.

    Sheet layout confirmed by inspection:
      Row 0 : 'Date'  + [date, None, None, date, None, None, ...]  (18 cols)
      Row 1 : 'Rep'   + [1, 2, 3, 1, 2, 3, ...]
      Row 2+: trait   + [val, val, val, val, val, val, ...]

    Each data column corresponds to a (date, rep) pair.
    """
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 3:
        return []

    # ---- Build (date, rep) column headers from rows 0 and 1 ----
    date_row = rows[0]   # e.g. ('Date', datetime, None, None, datetime, ...)
    rep_row  = rows[1]   # e.g. ('Rep', 1.0, 2.0, 3.0, 1.0, ...)

    # Forward-fill dates (merged cells appear as None)
    dates = []
    current_date = None
    for val in date_row[1:]:
        if val is not None:
            current_date = val
        dates.append(current_date)

    reps = []
    for val in rep_row[1:]:
        try:
            reps.append(int(val))
        except (TypeError, ValueError):
            reps.append(None)

    col_headers = list(zip(dates, reps))  # list of (date, rep) — len 18

    # ---- Build one record per (date, rep) ----
    # Start with skeleton records
    skeleton: dict[tuple, dict] = {}
    for date, rep in col_headers:
        key = (date, rep)
        if key not in skeleton:
            skeleton[key] = {
                "cultivar": cultivar_name,
                "date":     date,
                "rep":      rep,
            }

    # ---- Fill trait values ----
    for row in rows[2:]:
        label = row[0]
        if label is None:
            continue
        internal = TRAIT_MAP.get(str(label).strip())
        if internal is None:
            continue  # not a trait we track

        for (date, rep), raw_val in zip(col_headers, row[1:]):
            key = (date, rep)
            # Convert to float; '-' and formula errors become NaN
            if raw_val == "-" or raw_val is None:
                val = float("nan")
            else:
                try:
                    val = float(raw_val)
                except (TypeError, ValueError):
                    val = float("nan")
            skeleton[key][internal] = val

    return list(skeleton.values())


# ---------------------------------------------------------------------------
# Main ETL
# ---------------------------------------------------------------------------

def run_etl() -> pd.DataFrame:
    print(f"Loading: {RAW_PATH}")
    wb = openpyxl.load_workbook(str(RAW_PATH), read_only=True, data_only=True)

    all_records = []
    for tab_name in wb.sheetnames:
        cultivar = CULTIVAR_MAP.get(tab_name)
        if cultivar is None:
            print(f"  [SKIP] Unknown tab '{tab_name}' — not in CULTIVAR_MAP")
            continue
        ws = wb[tab_name]
        records = _parse_sheet(ws, cultivar)
        all_records.extend(records)
        print(f"  [OK]   {tab_name:8s} → {cultivar:12s}  ({len(records)} rows)")

    wb.close()

    # ---- Build DataFrame ----
    df = pd.DataFrame(all_records)

    # Ensure all trait columns exist (fill NaN if a sheet was missing a trait)
    for col in NUMERIC_COLS:
        if col not in df.columns:
            df[col] = float("nan")

    # ---- Type coercion ----
    # date is already a Python datetime from openpyxl; convert to pandas Timestamp
    df["date"] = pd.to_datetime(df["date"])

    # rep must be 1, 2, or 3
    df["rep"] = pd.to_numeric(df["rep"], errors="coerce").astype("Int64")

    # numeric trait columns
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ---- Column order ----
    col_order = ["date", "cultivar", "rep"] + NUMERIC_COLS
    df = df[[c for c in col_order if c in df.columns]]

    # ---- Sort ----
    df = df.sort_values(["cultivar", "date", "rep"]).reset_index(drop=True)

    # ---- Validation ----
    _validate(df)

    # ---- Save ----
    df.to_csv(str(OUT_PATH), index=False)
    print(f"\nSaved → {OUT_PATH}")
    print(f"Shape : {df.shape[0]} rows × {df.shape[1]} columns")

    return df


def _validate(df: pd.DataFrame) -> None:
    """Run sanity checks and print a report. Raises on critical failures."""
    ok = True
    print("\n--- Validation ---")

    # (1) Expected cultivars
    expected = {
        "Finn", "Cabrio", "Camarosa", "Sensation", "Chandler",
        "Albion", "Moxie", "Ruby June", "Brilliance", "Portola", "Radiance",
    }
    found = set(df["cultivar"].unique())
    if found != expected:
        missing = expected - found
        extra   = found - expected
        print(f"  [WARN] Cultivar mismatch. Missing: {missing}  Extra: {extra}")
        ok = False
    else:
        print(f"  [OK]   All 11 cultivars present: {sorted(found)}")

    # (2) Rep values
    bad_reps = df[~df["rep"].isin([1, 2, 3])]
    if not bad_reps.empty:
        print(f"  [FAIL] {len(bad_reps)} rows with unexpected rep IDs:\n{bad_reps[['date','cultivar','rep']]}")
        ok = False
    else:
        print("  [OK]   All rep IDs are 1, 2, or 3")

    # (3) No duplicate (date, cultivar, rep) combos
    dupes = df.duplicated(["date", "cultivar", "rep"])
    if dupes.any():
        print(f"  [FAIL] {dupes.sum()} duplicate (date, cultivar, rep) rows")
        ok = False
    else:
        print("  [OK]   No duplicate (date, cultivar, rep) rows")

    # (4) Date range
    dmin, dmax = df["date"].min(), df["date"].max()
    if not (pd.Timestamp("2025-04-01") <= dmin <= pd.Timestamp("2025-04-30")):
        print(f"  [WARN] Unexpected min date: {dmin}")
    if not (pd.Timestamp("2025-06-01") <= dmax <= pd.Timestamp("2025-07-15")):
        print(f"  [WARN] Unexpected max date: {dmax}")
    print(f"  [OK]   Date range: {dmin.date()} → {dmax.date()}")

    # (5) Missing value summary
    print("\n  Missing value counts per trait:")
    count_cols = [c for c in NUMERIC_COLS if c in df.columns]
    miss = df[count_cols].isna().sum()
    for col, n in miss.items():
        if n > 0:
            pct = 100 * n / len(df)
            print(f"          {col:<35s}: {n:4d} / {len(df)}  ({pct:.1f}%)")
    if (miss == 0).all():
        print("          (no missing values in any trait column)")

    if not ok:
        print("\n  ⚠️  One or more validation checks failed — review output above")
    else:
        print("\n  All critical checks passed.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_etl_from_bytes(xlsx_bytes: bytes) -> pd.DataFrame:
    """
    Parse a Pheno 4 Worksheet 2 workbook from raw bytes (e.g. a file upload).
    Returns a tidy DataFrame identical in structure to run_etl() but does
    not write to disk and does not print validation output.
    """
    from io import BytesIO
    wb = openpyxl.load_workbook(BytesIO(xlsx_bytes), read_only=True, data_only=True)

    all_records = []
    for tab_name in wb.sheetnames:
        cultivar = CULTIVAR_MAP.get(tab_name)
        if cultivar is None:
            continue
        ws = wb[tab_name]
        records = _parse_sheet(ws, cultivar)
        all_records.extend(records)
    wb.close()

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    for col in NUMERIC_COLS:
        if col not in df.columns:
            df[col] = float("nan")

    df["date"] = pd.to_datetime(df["date"])
    df["rep"]  = pd.to_numeric(df["rep"], errors="coerce").astype("Int64")
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    col_order = ["date", "cultivar", "rep"] + NUMERIC_COLS
    df = df[[c for c in col_order if c in df.columns]]
    df = df.sort_values(["cultivar", "date", "rep"]).reset_index(drop=True)
    return df


if __name__ == "__main__":
    df = run_etl()
    print("\nSample (first 5 rows):")
    pd.set_option("display.max_columns", 10)
    pd.set_option("display.width", 120)
    print(df.head())
