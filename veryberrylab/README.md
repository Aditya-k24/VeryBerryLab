# VeryBerryLab — Pheno 4 Analysis

Statistical analysis and interactive visualization of strawberry phenotyping data (Batch 4).
Measures stolon and daughter-plant dynamics across 11 cultivars over 12 measurement dates
(April – July 2025), with 3 replicate plants per cultivar per date.

---

## Data Source

**Single canonical source — do not use any other file:**

```
Phenotyping Data with Aditya 1_27_2026/
  Pheno Batch 4/
    Phenotyping 4 Worksheet 2.xlsx      ← 11 sheets, one per cultivar
```

The workbook is a wide cross-tab: columns = (date × rep), rows = traits.
A identical offline copy is kept at `data/raw/Phenotyping 4 Worksheet 2.xlsx`
and is used automatically if the canonical path is unavailable.

---

## What We Are Measuring

| Group | Traits |
|---|---|
| Stolons (counts) | Primary, Secondary, Tertiary, Quaternary |
| Daughter plants — alternate nodes | on Primary / Secondary / Tertiary / Quaternary stolon |
| Daughter plants — mid nodes | on Primary / Secondary / Tertiary / Quaternary stolon |
| Daughter plant totals | Total (alt nodes), Total (mid nodes) |
| Flowers | Total, on Mother Plant, on Daughter Plants |
| Morphology | Primary Stolon Length (cm), Crown Diameter (mm) |

**11 cultivars** in two staggered batches measured every ~2 weeks:

| Batch A (6 cvs) | Batch B (5 cvs) |
|---|---|
| Albion, Cabrio, Camarosa\*, Chandler, Finn, Sensation | Brilliance, Moxie, Portola, Radiance, Ruby June |

> \* `Cam` tab → **Camarosa** is provisional. Confirm full name with team before any publication.

---

## Setup

```bash
pip install -r requirements.txt
```

Key dependencies: `pandas`, `openpyxl`, `plotly`, `scipy`, `scikit-posthocs`, `numpy`.

---

## Pipeline

Run each step from the **`veryberrylab/`** directory.

### Step 1 — ETL (raw Excel → tidy CSV)

```bash
python3 src/etl.py
```

Reads `Phenotyping 4 Worksheet 2.xlsx`, pivots the wide cross-tab into one row
per (cultivar × date × rep), validates, and writes:

- `data/processed/pheno4_clean.csv` — **198 rows × 22 columns**

### Step 2 — Aggregate (tidy CSV → summary stats)

```bash
python3 src/aggregate.py
```

Groups by (date, cultivar), computes mean, SE, and n for all 19 traits. Writes:

- `data/processed/pheno4_aggregated.csv` — wide format (66 rows)
- `data/processed/pheno4_long.csv` — long format (1 254 rows)
- `data/processed/pheno4_viz.json` — nested JSON for client-side use
- `data/processed/missingness_report.csv` — missing-value audit

### Step 3a — Prototype charts (Viz A & B)

```bash
python3 viz/prototype.py
```

Reads `pheno4_aggregated.csv`. Produces:

- `viz/chart_A.html` — interactive multi-cultivar time-series (trait dropdown)
- `viz/chart_B.html` — 3 × 4 small-multiples grid per cultivar (stolon orders)

### Step 3b — Statistical chart (Viz C)

```bash
python3 viz/pheno4_stats_viz.py
```

Reads `pheno4_clean.csv` directly (needs the raw replicates for Kruskal-Wallis).
Runs **228 (trait × date)** statistical comparisons and produces:

- `viz/chart_C.html` — full-viewport interactive chart

#### What chart_C.html shows

**Bar Chart mode** (default)
- One bar per cultivar on the selected date, sorted by mean descending
- SE error bars with caps
- CLD letters (compact letter display) above every bar — shared letters = no
  significant difference after Dunn / Bonferroni post-hoc
- ★ stars on best-group (letter "a") bars when KW is significant
- Bottom stats bar: current trait · date · KW χ² · p-value · significance label

**Line Chart mode** (toggle in header)
- All cultivars as mean ± SE time-series across their 6 measurement dates
- Cultivar legend on the right
- Bottom stats bar: trait name · "all measurement dates"

---

## Tests

```bash
pytest tests/
```

Covers `src/parse_codes.py` (35 test cases for the Worksheet 1 stolon-path parser).
The parser is implemented and tested but not yet integrated into the main pipeline
(Phase 2 — stolon genealogy analysis — is pending).

---

## File Layout

```
veryberrylab/
├── README.md                   ← you are here
├── requirements.txt
├── ASSUMPTIONS.md              ← data-layout notes and open questions
├── organise_pheno4.py          ← standalone Excel formatter (manual review use)
├── data/
│   ├── raw/
│   │   ├── Phenotyping 4 Worksheet 1.xlsx   (stolon path codes — Phase 2)
│   │   └── Phenotyping 4 Worksheet 2.xlsx   (offline copy of canonical source)
│   └── processed/
│       ├── pheno4_clean.csv
│       ├── pheno4_aggregated.csv
│       ├── pheno4_long.csv
│       ├── pheno4_viz.json
│       └── missingness_report.csv
├── src/
│   ├── etl.py                  ← Step 1: raw Excel → tidy CSV
│   ├── aggregate.py            ← Step 2: tidy CSV → summary stats
│   └── parse_codes.py          ← Phase 2 (not yet integrated): Worksheet 1 parser
├── viz/
│   ├── prototype.py            ← Step 3a: Viz A & B
│   ├── pheno4_stats_viz.py     ← Step 3b: Viz C (statistical)
│   ├── chart_A.html            ← generated output
│   ├── chart_B.html            ← generated output
│   └── chart_C.html            ← generated output
└── tests/
    └── test_parser.py          ← unit tests for parse_codes.py
```
