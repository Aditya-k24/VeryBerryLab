"""
pages/season_summary.py — Page 4: Season Summary

A) ε² heatmap: traits × dates coloured by effect size, annotated with sig stars.
B) Champion & peak table: per cultivar for a selected trait.
"""

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

import src.data_cache as cache
from src.etl import BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_LABELS
from src.stats import sig_label

dash.register_page(__name__, path="/season-summary", name="Season Summary", order=3)


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

def _heatmap(stats_cache, df):
    all_dates  = sorted(df["date"].unique())
    date_strs  = [str(d)[:10] for d in all_dates]
    date_lbls  = [pd.Timestamp(d).strftime("%d %b") for d in all_dates]

    z     = np.full((len(TRAIT_COLS), len(all_dates)), np.nan)
    annot = [[""] * len(all_dates) for _ in TRAIT_COLS]
    hover = [["No data"] * len(all_dates) for _ in TRAIT_COLS]

    for ti, trait in enumerate(TRAIT_COLS):
        for di, ds in enumerate(date_strs):
            r = stats_cache.get((trait, ds))
            if r is None:
                continue
            z[ti, di]     = r.epsilon2
            lbl = sig_label(r.kw_p)
            annot[ti][di] = lbl if lbl != "ns" else ""
            hover[ti][di] = (
                f"<b>{TRAIT_LABELS.get(trait, trait)}</b><br>"
                f"{pd.Timestamp(ds).strftime('%d %b %Y')}<br>"
                f"ε² = {r.epsilon2:.3f}<br>p = {r.kw_p:.4f} ({lbl})"
            )

    b_dates = sorted(df[df["batch"] == "B"]["date"].unique())
    sep_idx = None
    if b_dates:
        first_b = min(b_dates)
        if first_b in all_dates:
            sep_idx = list(all_dates).index(first_b) - 0.5

    ylabels = [TRAIT_LABELS.get(t, t) for t in TRAIT_COLS]

    fig = go.Figure(go.Heatmap(
        z=z.tolist(), x=date_lbls, y=ylabels,
        text=annot, texttemplate="%{text}", textfont=dict(size=10),
        colorscale=[[0, "#f5faf6"], [0.1, "#c8e6c9"], [0.35, "#66bb6a"],
                    [0.65, "#2e7d32"], [1, "#1b5e20"]],
        zmin=0, zmax=0.8,
        colorbar=dict(title=dict(text="ε²", side="right"), thickness=14, len=0.55),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover, xgap=2, ygap=1,
    ))

    if sep_idx is not None:
        fig.add_shape(type="line", x0=sep_idx, x1=sep_idx,
                      y0=-0.5, y1=len(TRAIT_COLS) - 0.5,
                      line=dict(color="#E69F00", width=2, dash="dot"))
        fig.add_annotation(x=sep_idx, y=len(TRAIT_COLS) - 0.2,
                           text="B →", showarrow=False,
                           font=dict(size=10, color="#E69F00"))

    fig.update_layout(
        height=max(400, len(TRAIT_COLS) * 28 + 80),
        margin=dict(l=240, r=90, t=40, b=70),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(tickangle=-45),
        yaxis=dict(autorange="reversed"),
        font=dict(family="Inter, sans-serif", size=11),
    )
    return fig


# ---------------------------------------------------------------------------
# Champion table
# ---------------------------------------------------------------------------

def _champ_table(season_metrics, trait):
    if season_metrics.empty:
        return html.Div("No metrics available.", className="stats-empty")
    df_t = season_metrics[season_metrics["trait"] == trait].sort_values(
        "champion_pct", ascending=False, na_position="last"
    )
    if df_t.empty:
        return html.Div("No data for selected trait.", className="stats-empty")

    icon  = {"up": "↑", "down": "↓", "flat": "→"}
    color = {"up": "#2d7a45", "down": "#c62828", "flat": "#666"}

    rows = []
    for _, row in df_t.iterrows():
        peak_str = (
            f"{row['peak_value']:.2f} ({pd.Timestamp(row['peak_date']).strftime('%d %b')})"
            if pd.notna(row["peak_value"]) and row["peak_date"] is not None else "—"
        )
        champ_str = (
            f"{row['champion_pct']:.0f}% ({int(row['champion_wins'])}/{int(row['total_sig_dates'])})"
            if pd.notna(row["champion_pct"]) else "—"
        )
        rows.append(html.Tr([
            html.Td(row["cultivar"], className="champ-cv"),
            html.Td(html.Span(icon.get(row["trend"], "→"),
                              style={"color": color.get(row["trend"], "#666"),
                                     "fontSize": "18px", "fontWeight": "700"})),
            html.Td(peak_str,  className="champ-peak"),
            html.Td(champ_str, className="champ-pct"),
        ]))

    return html.Div([
        html.P("Champion = CLD letter 'a' on a date with significant KW (α=0.05). "
               "Trend = linear slope over observed dates.",
               className="card-subtitle"),
        html.Table(className="champ-table", children=[
            html.Thead(html.Tr([html.Th("Cultivar"), html.Th("Trend"),
                                html.Th("Peak (date)"), html.Th("Champion wins")])),
            html.Tbody(rows),
        ]),
    ])


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Season Summary", className="page-title"),
        html.P("Effect-size heatmap across all traits and dates, "
               "plus champion and peak-value ranking per trait.",
               className="page-subtitle"),
    ]),
    html.Div(className="content-area", children=[

        html.Div(className="card", children=[
            html.H3("Effect Size Heatmap (ε²)", className="card-title"),
            html.P("Colour intensity = ε². Annotations = significance stars. "
                   "Dotted line = Batch B boundary.",
                   className="card-subtitle"),
            dcc.Graph(id="ss-heatmap", config={"displayModeBar": "hover"}),
        ]),

        html.Div(className="card", children=[
            html.H3("Champion & Peak Table", className="card-title"),
            html.Div(className="filter-row", children=[
                html.Label("Trait:", className="filter-label"),
                dcc.Dropdown(
                    id="ss-trait",
                    options=[{"label": TRAIT_LABELS[t], "value": t} for t in TRAIT_COLS],
                    value="n_stolon_primary", clearable=False, style={"width": "300px"},
                ),
            ]),
            html.Div(id="ss-champ"),
        ]),
    ]),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(Output("ss-heatmap", "figure"), Input("url", "pathname"))
def render_heatmap(_):
    return _heatmap(cache.stats_cache, cache.df_clean)


@callback(Output("ss-champ", "children"), Input("ss-trait", "value"))
def upd_champ(trait):
    return _champ_table(cache.season_metrics, trait or TRAIT_COLS[0])
