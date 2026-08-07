"""Shared fixtures. Loads the real workbooks once; skips data-dependent tests
if the Excel files aren't present."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"


@pytest.fixture(scope="session")
def ws2_df():
    if not (DATA / "Phenotyping 4 Worksheet 2.xlsx").exists():
        pytest.skip("WS2 workbook not present")
    from src.etl import run_etl
    df, warns = run_etl(verbose=False)
    return df


@pytest.fixture(scope="session")
def stats_cache(ws2_df):
    from src.stats import compute_all_stats
    return compute_all_stats(ws2_df)


@pytest.fixture(scope="session")
def merged():
    if not (DATA / "Pheno Merged Data.xlsx").exists():
        pytest.skip("merged workbook not present")
    from src.merged_etl import load_merged
    return load_merged()
