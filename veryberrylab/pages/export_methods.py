"""
pages/export_methods.py
========================
Page 6 — Export & Methods

  • Download tidy CSV (pheno4_clean.csv)
  • Download long-format CSV
  • Download stats summary CSV
  • Methods description: statistical choices, alpha, correction, formula citations
"""

import io

import dash
import pandas as pd
from dash import Input, Output, callback, dcc, html

import src.data_cache as cache
from src.etl import TRAIT_COLS, TRAIT_LABELS

dash.register_page(__name__, path="/export", name="Export & Methods", order=5)


# ---------------------------------------------------------------------------
# Methods text
# ---------------------------------------------------------------------------

METHODS_CONTENT = [
    ("Data ingestion",
     "Raw data are read from the Phenotyping 4 Worksheet 2 Excel workbook using openpyxl "
     "with data_only=True (cached formula values). The wide cross-tab format (columns = "
     "date × replicate, rows = traits) is pivoted to a tidy row-per-replicate table. "
     "Missing cells ('-') are recorded as NaN — not zero."),

    ("Batches",
     "11 cultivars are divided into two staggered measurement schedules: "
     "Batch A (Albion, Cabrio, Camarosa, Chandler, Finn, Sensation) and "
     "Batch B (Brilliance, Moxie, Portola, Radiance, Ruby June). "
     "Statistical comparisons are performed within each batch's date set. "
     "Cross-batch 'same day' comparisons are not made."),

    ("Omnibus test",
     "Kruskal–Wallis H test (scipy.stats.kruskal) is applied per (trait × date) "
     "combination, comparing cultivar groups. Significance threshold α = 0.05 by default."),

    ("Effect size",
     "Epsilon-squared (ε²) is computed as: ε² = max(0, (H − k + 1) / (n − k)), "
     "where H is the KW statistic, k is the number of groups, n is the total "
     "number of observations. ε² ranges from 0 (no effect) to 1 (maximum discrimination). "
     "Reference: Tomczak & Tomczak (2014)."),

    ("Post-hoc test",
     "Conover–Iman pairwise post-hoc test (scikit-posthocs.posthoc_conover) "
     "is performed after a significant omnibus result. The post-hoc is also computed "
     "for non-significant omnibus results and shown as exploratory (labelled)."),

    ("Multiple comparisons correction",
     "Holm step-down correction is applied by default (controls family-wise error rate, "
     "more powerful than Bonferroni). Bonferroni is available as a conservative alternative. "
     "Reference: Holm (1979)."),

    ("Compact Letter Display (CLD)",
     "CLD is generated using the Piepho (2004) sweep algorithm. Cultivars sharing "
     "at least one letter are not significantly different at the chosen α. "
     "Letter 'a' designates the best-performing group (highest mean for higher-is-better traits). "
     "Reference: Piepho H-P (2004) An algorithm for a letter-based representation "
     "of all-pairwise comparisons. J Comput Graph Stat 13:456–466."),

    ("Season metrics",
     "Trend arrows (↑↓→) are derived from linear regression of cultivar mean against "
     "date (in days) over observed dates. A slope exceeding 5% of the trait mean is "
     "classified as up or down; otherwise flat. "
     "Champion win % = fraction of dates with significant KW where the cultivar "
     "held letter 'a'. Peak value = maximum cultivar mean across dates."),

    ("Plant animation",
     "The plant figure is a schematic summary scaled to mean trait values. "
     "Crown circle diameter ∝ crown_diameter_mm. "
     "Primary stolon count and length ∝ n_stolon_primary and stolon_length_primary_cm. "
     "Secondary stolons, daughter plants, and flowers are scaled to n_stolon_secondary, "
     "n_dp_total_alt, n_dp_total_mid, and n_flowers_total respectively. "
     "Stolon positions are evenly distributed for visual clarity only."),

    ("Reproducibility",
     "All outputs are deterministic given the same input workbook and software versions. "
     "Key package versions: pandas ≥ 2.0, scipy ≥ 1.11, scikit-posthocs ≥ 0.9, "
     "dash ≥ 2.14. Analysis date and software versions are included in CSV exports."),
]


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Export & Methods", className="page-title"),
        html.P("Download data and review the statistical methods used in this dashboard.",
               className="page-subtitle"),
    ]),
    html.Div(className="content-area", children=[

        # Downloads
        html.Div(className="card", children=[
            html.H3("Downloads", className="card-title"),
            html.Div(className="export-row", children=[
                html.Div(className="export-item", children=[
                    html.H4("Tidy Data (CSV)", className="export-title"),
                    html.P("One row per (cultivar × date × replicate). "
                           "198 rows × 23 columns.", className="card-subtitle"),
                    html.Button("Download pheno4_clean.csv", id="btn-dl-clean",
                                className="btn btn-primary"),
                    dcc.Download(id="dl-clean"),
                ]),
                html.Div(className="export-item", children=[
                    html.H4("Long Format (CSV)", className="export-title"),
                    html.P("One row per (cultivar × date × rep × trait). "
                           "All 19 traits × 198 obs = 3762 rows.", className="card-subtitle"),
                    html.Button("Download pheno4_long.csv", id="btn-dl-long",
                                className="btn btn-primary"),
                    dcc.Download(id="dl-long"),
                ]),
                html.Div(className="export-item", children=[
                    html.H4("Statistics Summary (CSV)", className="export-title"),
                    html.P("KW H, p, ε² for all (trait × date) combinations.",
                           className="card-subtitle"),
                    html.Button("Download pheno4_stats.csv", id="btn-dl-stats",
                                className="btn btn-primary"),
                    dcc.Download(id="dl-stats"),
                ]),
                html.Div(className="export-item", children=[
                    html.H4("Season Metrics (CSV)", className="export-title"),
                    html.P("Champion %, peak value, trend per (cultivar × trait).",
                           className="card-subtitle"),
                    html.Button("Download pheno4_season.csv", id="btn-dl-season",
                                className="btn btn-primary"),
                    dcc.Download(id="dl-season"),
                ]),
            ]),
        ]),

        # Methods
        html.Div(className="card", children=[
            html.H3("Statistical Methods", className="card-title"),
            html.Div(className="methods-content", children=[
                html.Div(className="method-section", children=[
                    html.H4(title, className="method-title"),
                    html.P(body, className="method-body"),
                ])
                for title, body in METHODS_CONTENT
            ]),
        ]),
    ]),
])


# ---------------------------------------------------------------------------
# Callbacks — downloads
# ---------------------------------------------------------------------------

@callback(Output("dl-clean", "data"), Input("btn-dl-clean", "n_clicks"),
          prevent_initial_call=True)
def dl_clean(_):
    df = cache.df_clean.copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return dcc.send_data_frame(df.to_csv, "pheno4_clean.csv", index=False)


@callback(Output("dl-long", "data"), Input("btn-dl-long", "n_clicks"),
          prevent_initial_call=True)
def dl_long(_):
    df = cache.df_clean.copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    long_df = df.melt(
        id_vars=["date", "cultivar", "batch", "rep"],
        value_vars=TRAIT_COLS,
        var_name="trait",
        value_name="value",
    )
    long_df["trait_label"] = long_df["trait"].map(TRAIT_LABELS)
    return dcc.send_data_frame(long_df.to_csv, "pheno4_long.csv", index=False)


@callback(Output("dl-stats", "data"), Input("btn-dl-stats", "n_clicks"),
          prevent_initial_call=True)
def dl_stats(_):
    rows = []
    for (trait, date), res in sorted(cache.stats_cache.items()):
        rows.append({
            "trait":       trait,
            "trait_label": TRAIT_LABELS.get(trait, trait),
            "date":        date,
            "cultivars":   ";".join(res.cultivars),
            "n_total":     sum(res.n_per_cv.values()),
            "kw_H":        round(res.kw_H, 4),
            "kw_p":        round(res.kw_p, 6),
            "epsilon2":    round(res.epsilon2, 4),
            "significant": res.significant,
            "alpha":       res.alpha,
            "correction":  res.correction,
        })
    df = pd.DataFrame(rows)
    return dcc.send_data_frame(df.to_csv, "pheno4_stats.csv", index=False)


@callback(Output("dl-season", "data"), Input("btn-dl-season", "n_clicks"),
          prevent_initial_call=True)
def dl_season(_):
    df = cache.season_metrics.copy()
    if "peak_date" in df.columns:
        df["peak_date"] = df["peak_date"].apply(
            lambda d: pd.Timestamp(d).strftime("%Y-%m-%d") if pd.notna(d) and d is not None else ""
        )
    df.insert(1, "trait_label", df["trait"].map(TRAIT_LABELS))
    return dcc.send_data_frame(df.to_csv, "pheno4_season.csv", index=False)
