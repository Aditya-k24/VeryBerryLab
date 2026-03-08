# ASSUMPTIONS — Phenotyping 4 Analysis

## Confirmed by File Inspection (2026-02-17)

### File Structure
- **Worksheet 2** (`Phenotyping 4 Worksheet 2.xlsx`) contains **11 sheets**, one per cultivar.
- Sheet tab abbreviations → full cultivar names:
  | Tab    | Full Name      | Notes |
  |--------|---------------|-------|
  | Fin    | Finn          | Confirmed |
  | Cab    | Cabrio        | Confirmed |
  | Cam    | **Unknown**   | ⚠️ 11th cultivar — see open question below |
  | Sen    | Sensation     | Confirmed |
  | Cha    | Chandler      | Confirmed |
  | Alb    | Albion        | Tab has trailing space `'Alb '` — stripped in ETL |
  | Mox    | Moxie         | Confirmed |
  | RJune  | Ruby June     | Confirmed |
  | Bri    | Brilliance    | Confirmed |
  | Por    | Portola       | Confirmed |
  | Rad    | Radiance      | Confirmed |

- **Open question #1:** What is the full name of the `Cam` cultivar?
  Provisional mapping: `Cam → "Camarosa"` (used in processed outputs until confirmed).
  Team must confirm before any publication use.

### Data Layout (per sheet)
- **Row 0:** `Date` header + date values. Dates only appear in columns 1, 4, 7, 10, 13, 16
  (i.e., the first of every 3-column group for each date). Cols 2–3, 5–6, etc. are `None`
  (merged cells in Excel). The ETL forward-fills these.
- **Row 1:** `Rep` header + rep values `[1, 2, 3]` repeating across all 18 data columns.
- **Rows 2+:** Trait label in col 0, then one value per (date × rep) combination = 18 values.
- Total columns: 1 (label) + 6 dates × 3 reps = **19 columns**.

### Dates
- All measurement dates are in **2025** (NOT 2024 as originally assumed in the plan template).
- Year is embedded in the Excel datetime objects (not inferred).
- Different cultivars were measured on different date subsets (staggered scheduling).
  The **12 unique dates** across all cultivars are:
  `2025-04-16`, `2025-04-23`, `2025-04-30`, `2025-05-07`, `2025-05-14`, `2025-05-21`,
  `2025-05-28`, `2025-06-04`, `2025-06-11`, `2025-06-18`, `2025-06-25`, `2025-07-02`
- Each cultivar has exactly **6 measurement dates** from the set above.
- Example: Finn was measured Apr 16, Apr 30, May 14, May 28, Jun 11, Jun 25.
  Brilliance/Moxie/Portola/Radiance/Ruby June include Jul 2 in their 6 dates.

### Traits Present
| Row label (exact, after strip) | Internal name | Level |
|---|---|---|
| `Pri stolon` | `n_stolon_primary` | 1 |
| `Sec stolon` | `n_stolon_secondary` | 1 |
| `Ter stolon` | `n_stolon_tertiary` | 1 |
| `Quart Stolon` | `n_stolon_quaternary` | 1 |
| `dp on alt of pri stolon` | `n_dp_alt_primary` | 2 |
| `dp on alt of sec stolon` | `n_dp_alt_secondary` | 2 |
| `dp on alt of ter stolon` | `n_dp_alt_tertiary` | 2 |
| `dp on alt of quart stolon` | `n_dp_alt_quaternary` | 2 |
| `dp on mid of pri stolon` | `n_dp_mid_primary` | 2 |
| `dp on mid of sec stolon` | `n_dp_mid_secondary` | 2 |
| `dp on mid of ter stolon` | `n_dp_mid_tertiary` | 2 |
| `dp on mid of quart stolon` | `n_dp_mid_quaternary` | 2 |
| `Total dp on alt` | `n_dp_total_alt` | 2 |
| `Total dp on mid` | `n_dp_total_mid` | 2 |
| `#Total Flowers` | `n_flowers_total` | 3 |
| `# Flowers mp/mp` | `n_flowers_mp` | 3 |
| `# Flowers dp/mp` | `n_flowers_dp` | 3 |
| `Pri Stolon length (cm)` | `stolon_length_primary_cm` | 3 |
| `Crown diameter (mm)` | `crown_diameter_mm` | 3 |

- Additional rows exist (secondary stolon position breakdown, truss counts, internode lengths,
  dry matter) but are not included in the primary analysis scope.

### Missing Values
- Cells containing `'-'` (dash string) = trait not yet measured on that date.
  These are treated as `NaN`, NOT as zero.
- Excel formula cells (e.g. `=sum(...)`) are resolved by reading with `data_only=True`.
  Early dates (first 2 date columns) have raw numeric values; later dates use formulas.
  Both are correctly read as numeric with `data_only=True`.

### Replication
- Each row represents one observation from one mother plant (rep).
- 3 reps per (date, cultivar): rep IDs are 1, 2, 3.
- The dataset has `11 cultivars × 6 dates (per cultivar) × 3 reps = 198 rows` in the cleaned CSV.

### Worksheet 1 Code Format
- Worksheet 1 uses **dot-separated** codes, NOT hyphen-separated as described in the plan BNF.
  - Format: `mother_id.stolon_id.node_id.daughter_id`
  - Secondary branches use slash: `mother_id.stolon_id.node_id/sec_stolon_id.node_id.daughter_id`
  - Tertiary: `m.s.n/s2.n2/s3.n3.d`
- Examples seen: `1.1.2.1`, `1.1.2/1.2.1`, `3.1.2/1.2/1.2.1`
- The plan's BNF grammar remains valid conceptually; separator is `.` not `-`.

---

## Open Questions (for team confirmation)

| # | Question | Current assumption | Impact |
|---|---|---|---|
| 1 | Full name of `Cam` cultivar? | `"Camarosa"` (provisional) | All processed outputs will use this name until corrected |
| 2 | Are all dates in 2025? | Yes — confirmed from Excel datetime objects | N/A, confirmed |
| 3 | Can a single stolon node have both a daughter plant AND a branching stolon? | No (assumed exclusive) | Parser logic |
| 4 | Are total stolon counts in Worksheet 2 inclusive of stolons with daughters? | Yes | Reconciliation report |
| 5 | Does Worksheet 3 contain harvest data for all 11 cultivars? | Yes (11 sheets confirmed) | Phase 3 analysis scope |
| 6 | What is `Pheno 4 Data book for analysis 8 cvs.xlsx`? | Subset for publication | Out of scope for now |

---

## Missingness Notes (to be updated after ETL run)
See `data/processed/missingness_report.csv` after running `src/etl.py` + `src/aggregate.py`.

Key observation: `Crown diameter (mm)`, internode lengths, and dry matter data are only
populated for the **final date (2025-06-25)** in the Finn sheet. Other dates show `'-'`.
This is expected — morphology measurements are typically end-of-season harvests.
