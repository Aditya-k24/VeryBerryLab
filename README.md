# Strawberry Trait Dashboard

An interactive research dashboard for strawberry phenotyping data. Tracks the vegetative and reproductive architecture of 11 strawberry cultivars across a full growing season (April–July 2025).

**11 cultivars · 12 measurement dates · 3 replicates · 19 traits · 198 observations**

---

## What This Is

This repository contains a multi-page [Dash](https://dash.plotly.com/) application for exploring, visualising, and statistically analysing **Phenotyping Batch 4** strawberry data. It was built for the VeryBerryLab to support cultivar selection and propagation decisions.

The dashboard answers questions like:
- Which cultivars produce the most stolons (runners) at each point in the season?
- Are there statistically significant differences between cultivars for a given trait on a given date?
- Which cultivar is most consistently the "champion" producer across the season?
- What does a typical plant look like architecturally at a given timepoint?

---

## Quick Start

```bash
cd Analytics
pip install -r requirements.txt
python3 app.py
```

Open **http://localhost:5001**

---

## Repository Layout

```
strawberry-trait-dashboard/         (GitHub: Aditya-k24/strawberry-trait-dashboard)
├── Analytics/                      ← Main Dash application (run this)
│   ├── app.py                      ← Entry point; multi-page Dash 4.x app
│   ├── requirements.txt
│   ├── assets/
│   │   └── style.css               ← Warm-paper editorial theme
│   ├── pages/
│   │   ├── data_health.py          ← Page 1: Summary cards, timeline, completeness
│   │   ├── trait_explorer.py       ← Page 2: Time series + replicate dot plots
│   │   ├── date_compare.py         ← Page 3: Statistical comparison + CLD
│   │   ├── season_summary.py       ← Page 4: ε² heatmap + champion table
│   │   ├── cross_batch.py          ← Page 5: Cross-batch trajectory view
│   │   ├── plant_animation.py      ← Page 6: SVG plant architecture schematic
│   │   └── export_methods.py       ← Page 7: CSV downloads + methods citations
│   ├── src/
│   │   ├── etl.py                  ← Raw Excel → tidy DataFrame + batch_id
│   │   ├── stats.py                ← KW + ε² + Holm + Conover + CLD engine
│   │   ├── aggregate.py            ← Season metrics (trend, peak, champion%)
│   │   ├── plant_arch.py           ← Daughter-plant architecture reconstruction
│   │   ├── ws1_parser.py           ← Worksheet 1 stolon code parser
│   │   └── data_cache.py           ← Singleton data loader (called once at startup)
│   ├── data/
│   │   └── raw/                    ← Offline copy of source workbook
│   └── tests/
│
├── Phenotyping Data with Aditya 1_27_2026/  ← Historical raw data (Batches 1–5)
└── DASHBOARD_GUIDE.md              ← Full guide: what every chart means
```

The field-data-collection PWA that feeds this dashboard is a separate repo,
[`Aditya-k24/veryberry-field`](https://github.com/Aditya-k24/veryberry-field) —
not part of this one.

---

## The Data

### Cultivars

Two staggered measurement batches:

| Batch | Cultivars |
|-------|-----------|
| **A** | Albion, Cabrillo, Camarosa\*, Chandler, Finn, Sensation |
| **B** | Brilliance, Moxie, Portola, Radiance, Ruby June |

Each cultivar is measured on **6 of the 12 total dates** in the season. Batch A and B do not share all dates — this is intentional scheduling, not missing data.

> \* The `Cam` Excel tab is provisionally mapped to **Camarosa**. Confirm with team before publication.

### Traits (19 total)

| Group | Traits |
|-------|--------|
| **Stolon architecture** | `n_stolon_primary`, `n_stolon_secondary`, `n_stolon_tertiary`, `n_stolon_quaternary`, `stolon_length_primary_cm` |
| **Daughter plants — alternate nodes** | `n_dp_alt_primary/secondary/tertiary/quaternary`, `n_dp_total_alt` |
| **Daughter plants — mid nodes** | `n_dp_mid_primary/secondary/tertiary/quaternary`, `n_dp_total_mid` |
| **Flowering** | `n_flowers_total`, `n_flowers_mp`, `n_flowers_dp` |
| **Morphology** | `crown_diameter_mm` |

### Missing Values

There are three distinct reasons a cell can be absent — and they are **not interchangeable**:

| Status | Meaning |
|--------|---------|
| Observed | A real number was recorded |
| Not measured | Date was scheduled but the value was not recorded (`-` in Excel) |
| Not scheduled | This date simply doesn't exist for this cultivar (different batch) |

The ETL layer distinguishes all three and they are displayed separately in the completeness heatmap.

---

## Dashboard Pages

### 1. Data Health
Summary cards (cultivar / date / trait / observation / missing % counts), a scatter plot of the measurement timeline per cultivar, and a completeness heatmap (cultivar × date) with categorical colouring for observed / not measured / not scheduled. Any Excel ingestion warnings are listed here.

### 2. Trait Explorer
Per-trait time series with mean ± SE ribbons and optional raw replicate dots. Lines are drawn within each batch only — no line crosses the batch gap, preventing false continuity. A small-multiples dot plot shows within-cultivar spread at each individual date.

### 3. Date Compare
Select a trait and a date to get a full statistical comparison:
- **Sorted dot plot** — cultivars ranked by mean, with rep dots, SE bars, and CLD letters
- **Kruskal–Wallis** omnibus test with H statistic, p-value, and ε² effect size
- **Pairwise table** — Holm-corrected Conover–Iman adjusted p-values for every cultivar pair

### 4. Season Summary
- **ε² heatmap** (traits × dates) — shows which trait × date combinations had strong cultivar differentiation. Cells annotated with `*`, `**`, `***` for significance.
- **Champion table** — for a selected trait, each cultivar's season trend (↑↓→), peak value and date, and champion win percentage (% of significant dates where CLD letter = "a").

### 5. Plant Animation
A scroll-driven SVG schematic of a strawberry plant drawn from actual trait values. Crown size, stolon count/length, daughter plant positions, and flower count are all anchored to measurements. A play/pause control animates through measurement dates to show how the plant architecture changes over the season.

### 6. Export & Methods
Download four CSV files:
- `pheno4_clean.csv` — tidy wide format (198 rows)
- `pheno4_long.csv` — long format (3,762 rows)
- `pheno4_stats.csv` — KW H, p, ε² per (trait × date)
- `pheno4_season.csv` — champion %, peak, trend per (cultivar × trait)

Full statistical methods documentation with citations is included on this page.

---

## Statistical Engine

| Component | Method |
|-----------|--------|
| Omnibus test | Kruskal–Wallis H (non-parametric one-way) |
| Effect size | ε² = max(0, (H − k + 1) / (n − k)) — Tomczak & Tomczak (2014) |
| Post-hoc | Conover–Iman pairwise test |
| Multiple testing correction | Holm step-down (default); controls family-wise error rate |
| Compact Letter Display | Piepho (2004) sweep algorithm |
| Season trend | OLS slope over observed dates; classified ↑/↓/→ at 5% threshold |
| Colour palette | Okabe–Ito (colorblind-safe, 11 colours) |

---

## Tests

```bash
cd Analytics
pytest tests/
```

35 unit tests covering `src/parse_codes.py` — the Worksheet 1 stolon-path parser for Phase 2 stolon genealogy analysis.

---

## Dependencies

```
dash>=2.14        plotly>=5.18       pandas>=2.0
numpy>=1.24       scipy>=1.11        scikit-posthocs>=0.9
statsmodels>=0.14 openpyxl>=3.1      pytest>=7.4
```

---

## Key References

- Conover, W.J. & Iman, R.L. (1979). On some alternative procedures using ranks for the analysis of experimental designs. *Communications in Statistics — Theory and Methods*, 8(14), 1349–1368.
- Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 6(2), 65–70.
- Piepho, H.P. (2004). An algorithm for a letter-based representation of all-pairwise comparisons. *Journal of Computational and Graphical Statistics*, 13(2), 456–466.
- Tomczak, M. & Tomczak, E. (2014). The need to report effect size estimates revisited. An overview of some recommended measures of effect size. *Trends in Sport Sciences*, 1(21), 19–25.

---

## Notes

- Processed CSV outputs (`data/processed/`) are reproducible by running `src/etl.py` + `src/aggregate.py` and are excluded from git.
- Raw data workbooks are tracked as an offline backup of the canonical source file.
