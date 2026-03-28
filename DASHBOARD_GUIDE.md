# VeryBerryLab Dashboard — Data & Visualisation Guide

This document explains what the data represents biologically, what each page in the dashboard shows, and how to read every chart and table.

---

## The Data

### What is being measured?

This dataset is from **Phenotyping Batch 4**, a strawberry plant phenotyping experiment. We are tracking the vegetative and reproductive architecture of 11 strawberry cultivars across a growing season (April–July 2025). Every measurement is taken on a living plant in the field or greenhouse — not lab-derived.

Each row in the dataset represents **one replicate plant** (`rep 1`, `rep 2`, or `rep 3`) of a cultivar on a specific measurement date. There are **198 total observations**.

### The 11 Cultivars

The cultivars are split into two staggered measurement schedules called **batches**:

| Batch | Cultivars |
|---|---|
| **A** | Albion, Cabrio, Camarosa\*, Chandler, Finn, Sensation |
| **B** | Brilliance, Moxie, Portola, Radiance, Ruby June |

Each cultivar is measured on **6 of the 12 total dates** in the season. Batch A and Batch B don't always share measurement dates — this is intentional scheduling, not missing data.

> \* "Camarosa" is provisional. The Excel tab is labelled `Cam` and the full cultivar name needs team confirmation.

### The 19 Traits

All traits are counts or measurements taken per plant:

#### Stolon Architecture (runner network)
Strawberry plants spread vegetatively through **stolons** (runners). We count how many stolons exist at each branching level:

| Trait | What it means |
|---|---|
| `n_stolon_primary` | Number of primary stolons radiating directly from the crown |
| `n_stolon_secondary` | Number of secondary stolons branching off primaries |
| `n_stolon_tertiary` | Tertiary branches (3rd order) |
| `n_stolon_quaternary` | Quaternary branches (4th order) |
| `stolon_length_primary_cm` | Physical length (cm) of the primary stolons |

A plant with more stolons and longer primaries is building a larger vegetative network — it is runner-prolific, which matters for propagation efficiency.

#### Daughter Plants (DPs)
Daughter plants are new plantlets that root at the **nodes** of stolons. We distinguish two node positions:

- **Alternate nodes (alt)** — every other node along a stolon; this is the typical rooting position
- **Mid nodes (mid)** — the midpoint position along a stolon

| Trait | What it means |
|---|---|
| `n_dp_alt_primary` | DPs at alternate nodes on primary stolons |
| `n_dp_alt_secondary` | DPs at alternate nodes on secondary stolons |
| `n_dp_alt_tertiary` | DPs at alternate nodes on tertiary stolons |
| `n_dp_alt_quaternary` | DPs at alternate nodes on quaternary stolons |
| `n_dp_mid_primary` | DPs at mid nodes on primary stolons |
| `n_dp_mid_secondary` | DPs at mid nodes on secondary stolons |
| `n_dp_mid_tertiary` | DPs at mid nodes on tertiary stolons |
| `n_dp_mid_quaternary` | DPs at mid nodes on quaternary stolons |
| `n_dp_total_alt` | Total DPs across all alternate nodes (all stolon orders combined) |
| `n_dp_total_mid` | Total DPs across all mid nodes (all stolon orders combined) |

More daughter plants = more propagation material. The split between alt and mid positions tells us something about rooting efficiency and node utilisation.

#### Flowering
| Trait | What it means |
|---|---|
| `n_flowers_total` | Total flower count on the whole plant |
| `n_flowers_mp` | Flowers on the **mother plant** (crown) |
| `n_flowers_dp` | Flowers on the **daughter plants** (nodes) |

Flowers signal reproductive investment. A plant flowering heavily while also producing many stolons is doing double duty — this balance varies by cultivar and date.

#### Crown
| Trait | What it means |
|---|---|
| `crown_diameter_mm` | Diameter of the plant crown in millimetres |

The crown is the central growing point of the plant. A larger crown generally indicates a more vigorous, established plant. It also drives stolon output.

### Missing Data

There are three distinct reasons a value can be absent:

- **Observed** — a real number was recorded
- **Not measured** — the date was scheduled for this cultivar but the value was not recorded (marked `-` in the Excel)
- **Not scheduled** — this date simply doesn't exist for this cultivar (different batch)

These are not the same thing. A "not scheduled" cell is expected and normal; "not measured" on a scheduled date is a gap worth investigating.

---

## Page-by-Page Guide

---

### 1. Data Health

**Purpose:** Before doing any analysis, verify that the data loaded correctly and is complete.

#### Summary Cards
Five top-level numbers at a glance:
- **Cultivars** — should be 11
- **Dates** — should be 12 unique dates across the season
- **Traits** — always 19
- **Observations** — 198 (11 cultivars × 6 dates × 3 reps, with some batch stagger)
- **Missing %** — the percentage of trait cells that are NaN across the whole dataset

The missing % is expected to be non-zero because each batch only covers 6 of 12 dates, so half the date × cultivar cells are structurally absent.

#### Measurement Timeline
A scatter plot of **which cultivar was measured on which date**. Each diamond = one measurement date for that cultivar.

- **Blue diamonds** = Batch A cultivars
- **Orange diamonds** = Batch B cultivars
- The two batches have distinct but overlapping date windows — this is how you visually confirm the staggered schedule is correct

If a cultivar is missing dates it should have, or has dates it shouldn't, this chart will reveal it immediately.

#### Completeness Matrix
A heatmap with **cultivars on the Y axis** and **dates on the X axis**.

In "All traits" mode, each cell shows what percentage of the 19 traits were observed for that cultivar–date combination. The colour runs from light (few traits measured) to dark green (fully observed).

When you select a specific trait, the cell colour becomes categorical:
- **Dark green** = observed
- **Yellow** = not measured (scheduled but absent)
- **Light grey** = not scheduled (different batch — expected)

A dotted orange vertical line marks where Batch B dates begin. Batch A cultivars will have grey cells on Batch B dates and vice versa — this is correct.

#### Ingestion Warnings
Any issues encountered while reading the Excel file are listed here — unexpected cell values, unrecognised sheet names, formula results that couldn't be parsed. These are informational notices, not necessarily errors.

---

### 2. Trait Explorer

**Purpose:** See how a single trait evolves over the season and how cultivars compare.

#### Filters
- **Trait** — choose any of the 19 traits
- **Cultivars** — toggle individual cultivars on/off (default: all 11)
- **Show raw replicates** — toggle whether individual rep points are drawn on top of the mean line

#### Time Series (mean ± SE)
A line chart showing each cultivar's **mean trait value over time**, with a shaded ribbon for ±1 standard error.

Key design decisions:
- Lines are drawn **within each batch only** — there is no line crossing the batch gap, because Batch A and Batch B don't share dates and connecting them would imply continuity where there is none
- A dotted grey vertical line separates the two batch windows, labelled "← A | B →"
- Raw replicate dots are jittered slightly left/right so overlapping reps from the same date are visible separately

This is the primary chart for spotting whether a cultivar is trending upward, peaking mid-season, or declining. Crossing lines tell you which cultivar overtakes another as the season progresses.

#### Distribution by Date (small multiples)
A grid of small dot plots — **one panel per measurement date**. Each panel shows all selected cultivars on the Y axis and trait values on the X axis.

- Each dot = one replicate plant
- The **diamond marker** = cultivar mean for that date
- Y positions are shared across panels (same cultivar always at the same height)

This view is better than the time series when you want to see **spread within a cultivar** at a single moment — are the three reps tightly clustered or scattered? Scattered reps suggest high within-cultivar variability on that date.

---

### 3. Date Compare

**Purpose:** Pick one trait and one date and get a rigorous statistical comparison of all cultivars.

#### Filters
- **Trait** — any of the 19 traits
- **Date** — only dates with actual data for the selected trait are offered
- **α** — significance threshold (0.05 default; 0.01 for stricter, 0.10 for exploratory)

#### Cultivar Comparison (dot plot)
Cultivars are sorted on the Y axis by their mean value — **highest mean at the top**. For each cultivar:

- **Filled dots** = the three individual replicate values (vertically offset so they don't overlap)
- **Diamond** = the cultivar mean
- **Horizontal bar** = ±1 standard error around the mean
- **Letter label (left side)** = the CLD letter (see below)
- **Gold star (right side)** = marks the top group (letter "a")

#### What the CLD Letters Mean
CLD stands for **Compact Letter Display**. It is produced by the Piepho (2004) algorithm after Kruskal–Wallis + Conover–Iman post-hoc testing.

The rule is simple: **cultivars that share at least one letter are not statistically different from each other** at the chosen α.

- `a` = the best-performing group (highest mean, for all 19 traits where higher = better)
- `ab` = overlaps with both the top group and a lower group
- `b`, `bc`, `c` = progressively lower-performing groups with no overlap with `a`

If all cultivars show the same letter (e.g. all `a`), there are no significant differences on that date.

#### Statistics Panel
Shows the full output of the statistical test:
- **KW H statistic** — the Kruskal–Wallis test value
- **p-value** — probability of this result under the null hypothesis of no difference
- **Effect size ε²** — how much of the variation in trait values is explained by cultivar identity (0 = none, 1 = complete). An ε² above ~0.3 is considered a strong effect.
- **Groups (k)** — how many cultivars were present on this date
- **Total n** — total replicate observations going into the test
- **Post-hoc** — always Conover–Iman
- **Correction** — Holm step-down (default), which controls family-wise error rate more powerfully than Bonferroni

If KW is not significant, the CLD is shown labelled as exploratory. This is intentional — even when the omnibus test fails, the pairwise patterns are still informative for generating hypotheses.

#### Pairwise Adjusted p-value Table
An expandable matrix showing the Holm-corrected Conover–Iman p-value for every pair of cultivars. Significant pairs are highlighted. This is the full evidence behind the CLD.

---

### 4. Season Summary

**Purpose:** A birds-eye view of which traits showed meaningful cultivar differences across the whole season, and which cultivars performed best.

#### Effect Size Heatmap (ε²)
A heatmap with **traits on the Y axis** and **dates on the X axis**. Each cell is coloured by ε² — the fraction of variance explained by cultivar identity on that trait × date combination.

- **White/pale** = ε² near 0 (cultivars all similar, or too few plants to distinguish)
- **Dark green** = ε² near 0.8 (cultivars strongly differentiated)
- **Significance stars in cells** = `*` p<0.05, `**` p<0.01, `***` p<0.001

Reading this heatmap: if an entire row (trait) is mostly pale, that trait does not discriminate cultivars well this season. If a row is consistently dark with stars, that is a key differentiating trait. Columns that are dark indicate dates when cultivar separation is strongest — often peak season.

A dotted orange vertical line separates Batch A dates from Batch B dates. Comparing colour intensity left vs right tells you whether separation was stronger early or late in the season.

#### Champion & Peak Table
For a selected trait, each cultivar is summarised across the season:

| Column | Meaning |
|---|---|
| **Cultivar** | Name |
| **Trend** | ↑ increasing, ↓ decreasing, → flat (based on linear regression slope over observed dates) |
| **Peak (date)** | The highest mean value recorded for this cultivar and what date it occurred |
| **Champion wins** | `X% (wins/total_sig_dates)` — on what fraction of dates where KW was significant did this cultivar hold CLD letter "a" (top group)? |

A cultivar with 80% champion wins for `n_stolon_primary` was consistently the best stolon producer across most of the season. A cultivar with a single peak win on one date but low overall % might have had one exceptional measurement but was otherwise average.

---

### 5. Plant Animation

**Purpose:** A visual intuition for the plant's architecture at a selected timepoint — not a scientific chart, but a communicative schematic.

#### What the figure shows

The figure draws a stylised top-down view of a strawberry plant using the measured trait values as inputs:

| Visual element | Driven by |
|---|---|
| **Central circle (crown)** | Size ∝ `crown_diameter_mm` |
| **Lines radiating from crown** | Count = `n_stolon_primary`; length ∝ `stolon_length_primary_cm` |
| **Short branches off primaries** | Count = `n_stolon_secondary` |
| **Dark green circles at stolon tips** | = daughter plants at alternate nodes (`n_dp_total_alt`) |
| **Light blue circles at secondary tips** | = daughter plants at mid nodes (`n_dp_total_mid`) |
| **Yellow stars near the crown** | Count = `n_flowers_total` |

The title always reads "Visual summary — values below are exact" to make clear that while positions are evenly distributed for clarity, the counts and sizes are anchored to real measurements.

#### Controls

- **Cultivar dropdown** — switches to a different cultivar; the slider adjusts to show only dates when that cultivar was measured
- **Date slider** — steps through the cultivar's measurement dates chronologically (starts at the first date)
- **▶ Play / ⏸ Pause button** — auto-advances the date slider every 1.5 seconds so you can watch the plant architecture change over the season
- **Show cross-cultivar mean** — replaces the individual cultivar with the average across all cultivars measured on each date; useful for seeing the "typical" plant at each timepoint

#### Values table
The exact numeric means for the key traits are always shown alongside the figure. This prevents the schematic from being misleading — if the visual looks big but the crown is only 18 mm, the table makes that clear.

---

### 6. Export & Methods

**Purpose:** Download the data and document the analytical choices for reproducibility.

#### Downloads

| File | Contents |
|---|---|
| `pheno4_clean.csv` | Tidy wide format — one row per (cultivar × date × rep), 198 rows, 23 columns |
| `pheno4_long.csv` | Long format — one row per (cultivar × date × rep × trait), 3,762 rows |
| `pheno4_stats.csv` | KW H, p, ε² for every (trait × date) combination tested |
| `pheno4_season.csv` | Champion %, peak value, peak date, trend per (cultivar × trait) |

#### Statistical Methods summary

The methods section documents every analytical decision:
- KW test with ε² effect size
- Conover–Iman post-hoc
- Holm correction (default)
- Piepho CLD algorithm
- Trend classification (linear regression with 5% slope threshold)
- How the plant animation schematic is scaled

---

## Common Reading Mistakes to Avoid

**"Not scheduled" ≠ missing data.** Half the cultivar × date grid will be grey in the completeness matrix. That is expected because of the two-batch design.

**The time series lines stop at batch boundaries.** If Batch A cultivars seem to disappear mid-chart, they did — they have no Batch B dates. This is correct.

**CLD letter "a" is always the best group for these traits.** All 19 traits are defined as higher = better, so "a" always means the highest-performing cultivar group.

**ε² near zero on the heatmap does not mean the trait is unimportant.** It means cultivars were similar to each other on that date. The trait may differentiate strongly on a different date.

**The plant animation is schematic, not anatomically accurate.** Stolon angles are evenly distributed for visual clarity. The counts and sizes are real; the geometry is illustrative.
