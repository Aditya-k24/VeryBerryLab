"""
pages/export_methods.py — Page 6: Export & Methods

Download buttons for all CSV outputs + full statistical methods description.
"""

import dash
import pandas as pd
from dash import Input, Output, callback, dcc, html

import src.data_cache as cache
from src.etl import TRAIT_COLS, TRAIT_LABELS

dash.register_page(__name__, path="/export", name="Export & Methods", order=5)

METHODS = [
    ("Data ingestion",
     "Workbook read with openpyxl (data_only=True — cached formula values). "
     "Wide cross-tab (columns = date × replicate, rows = traits) pivoted to tidy "
     "row-per-replicate table. Cells containing '-' recorded as NaN, not zero."),

    ("Batches",
     "Batch A: Albion, Cabrio, Camarosa, Chandler, Finn, Sensation. "
     "Batch B: Brilliance, Moxie, Portola, Radiance, Ruby June. "
     "Comparisons are within-batch; no cross-batch 'same-day' comparisons are made."),

    ("Omnibus test",
     "Kruskal–Wallis H test (scipy.stats.kruskal) per (trait × date). "
     "Default significance threshold α = 0.05."),

    ("Effect size ε²",
     "ε² = max(0, (H − k + 1) / (n − k)), where H = KW statistic, "
     "k = number of groups, n = total observations. Range [0, 1]. "
     "Reference: Tomczak & Tomczak (2014)."),

    ("Post-hoc test",
     "Conover–Iman pairwise test (scikit-posthocs.posthoc_conover). "
     "Computed after a significant omnibus; also shown (labelled exploratory) "
     "when the omnibus is not significant."),

    ("Multiple comparisons correction",
     "Holm step-down correction (default) — controls family-wise error rate, "
     "more powerful than Bonferroni. Bonferroni available as a conservative alternative. "
     "Reference: Holm (1979)."),

    ("Compact Letter Display",
     "Piepho (2004) sweep algorithm. Cultivars sharing at least one letter are "
     "not significantly different at the chosen α. Letter 'a' = best group. "
     "Reference: Piepho H-P (2004) J Comput Graph Stat 13:456–466."),

    ("Season metrics",
     "Trend arrows from linear regression of cultivar mean on date (days). "
     "Slope > 5 % of mean → up; < −5 % → down; otherwise flat. "
     "Champion win % = fraction of significant-KW dates where cultivar held letter 'a'. "
     "Peak value = cultivar max mean across dates (higher-is-better traits)."),

    ("Plant animation",
     "Schematic figure only — crown radius ∝ crown_diameter_mm; "
     "stolon count/length ∝ n_stolon_primary / stolon_length_primary_cm; "
     "secondary stolons, daughter plants, and flowers scaled to their trait values. "
     "Stolon angles evenly distributed for visual clarity."),
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _export_item(title, desc, btn_id, dl_id):
    return html.Div(className="export-card", children=[
        html.H4(title, className="export-title"),
        html.P(desc, className="card-subtitle"),
        html.Button("Download", id=btn_id, className="btn btn-primary"),
    ])


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Export & Methods", className="page-title"),
        html.P("Download processed data and review all statistical choices.",
               className="page-subtitle"),
    ]),
    html.Div(className="content-area", children=[

        html.Div(className="card", children=[
            html.H3("Downloads", className="card-title"),
            html.Div(className="export-grid", children=[
                _export_item("Tidy data (CSV)",
                             "One row per cultivar × date × replicate. 198 rows.",
                             "btn-clean", "dl-clean"),
                _export_item("Long format (CSV)",
                             "One row per cultivar × date × rep × trait. 3762 rows.",
                             "btn-long", "dl-long"),
                _export_item("Statistics summary (CSV)",
                             "KW H, p, ε² for all trait × date combinations.",
                             "btn-stats", "dl-stats"),
                _export_item("Season metrics (CSV)",
                             "Champion %, peak value, trend per cultivar × trait.",
                             "btn-season", "dl-season"),
            ]),
            dcc.Download(id="dl-clean"),
            dcc.Download(id="dl-long"),
            dcc.Download(id="dl-stats"),
            dcc.Download(id="dl-season"),
        ]),

        html.Div(className="card", children=[
            html.H3("Statistical Methods", className="card-title"),
            html.Div(className="methods-list", children=[
                html.Div(className="method-block", children=[
                    html.H4(title, className="method-title"),
                    html.P(body,  className="method-body"),
                ]) for title, body in METHODS
            ]),
        ]),
    ]),
])




# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(Output("dl-clean", "data"), Input("btn-clean", "n_clicks"),
          prevent_initial_call=True)
def dl_clean(_):
    df = cache.df_clean.copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return dcc.send_data_frame(df.to_csv, "pheno4_clean.csv", index=False)


@callback(Output("dl-long", "data"), Input("btn-long", "n_clicks"),
          prevent_initial_call=True)
def dl_long(_):
    df = cache.df_clean.copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    long = df.melt(id_vars=["date", "cultivar", "batch", "rep"],
                   value_vars=TRAIT_COLS, var_name="trait", value_name="value")
    long["trait_label"] = long["trait"].map(TRAIT_LABELS)
    return dcc.send_data_frame(long.to_csv, "pheno4_long.csv", index=False)


@callback(Output("dl-stats", "data"), Input("btn-stats", "n_clicks"),
          prevent_initial_call=True)
def dl_stats(_):
    rows = []
    for (trait, date), r in sorted(cache.stats_cache.items()):
        rows.append({
            "trait": trait, "trait_label": TRAIT_LABELS.get(trait, trait),
            "date": date, "cultivars": ";".join(r.cultivars),
            "n_total": sum(r.n_per_cv.values()),
            "kw_H": round(r.kw_H, 4), "kw_p": round(r.kw_p, 6),
            "epsilon2": round(r.epsilon2, 4), "significant": r.significant,
            "alpha": r.alpha, "correction": r.correction,
        })
    return dcc.send_data_frame(pd.DataFrame(rows).to_csv, "pheno4_stats.csv", index=False)


@callback(Output("dl-season", "data"), Input("btn-season", "n_clicks"),
          prevent_initial_call=True)
def dl_season(_):
    df = cache.season_metrics.copy()
    if "peak_date" in df.columns:
        df["peak_date"] = df["peak_date"].apply(
            lambda d: pd.Timestamp(d).strftime("%Y-%m-%d")
            if pd.notna(d) and d is not None else ""
        )
    df.insert(1, "trait_label", df["trait"].map(TRAIT_LABELS))
    return dcc.send_data_frame(df.to_csv, "pheno4_season.csv", index=False)
