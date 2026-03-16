"""
pages/season_summary.py
========================
Page 4 — Season Summary

Two views:
  A) Effect-size heatmap: traits (rows) × dates (columns), coloured by ε²,
     annotated with significance stars.  Batch A and B shown as separate blocks.
  B) Champion & peak table: for the selected trait, champion win %, peak value,
     peak date, and trend arrow per cultivar.
     Links to Date Compare for drill-down.
"""

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html
from plotly.subplots import make_subplots

import src.data_cache as cache
from src.etl import BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_LABELS
from src.stats import sig_label

dash.register_page(__name__, path="/season-summary", name="Season Summary", order=3)


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

def _epsilon2_heatmap(stats_cache, df):
    all_dates  = sorted(df["date"].unique())
    date_strs  = [str(d)[:10] for d in all_dates]
    date_labels = [pd.Timestamp(d).strftime("%d %b") for d in all_dates]
    traits = TRAIT_COLS
    n_traits = len(traits)
    n_dates  = len(all_dates)

    z_vals   = np.zeros((n_traits, n_dates))
    text_vals = [[""] * n_dates for _ in range(n_traits)]
    hover_vals = [[""] * n_dates for _ in range(n_traits)]

    for ti, trait in enumerate(traits):
        for di, date_str in enumerate(date_strs):
            res = stats_cache.get((trait, date_str))
            if res is None:
                z_vals[ti, di] = np.nan
                text_vals[ti][di] = ""
                hover_vals[ti][di] = "No data"
            else:
                z_vals[ti, di] = res.epsilon2
                label = sig_label(res.kw_p)
                text_vals[ti][di] = label if label != "ns" else ""
                hover_vals[ti][di] = (
                    f"<b>{TRAIT_LABELS.get(trait, trait)}</b><br>"
                    f"{pd.Timestamp(date_str).strftime('%d %b %Y')}<br>"
                    f"ε² = {res.epsilon2:.3f}<br>"
                    f"KW p = {res.kw_p:.4f} ({label})<br>"
                    f"Cultivars: {len(res.cultivars)}"
                )

    # Batch separator
    batch_a_dates = sorted(df[df["batch"] == "A"]["date"].unique())
    batch_b_dates = sorted(df[df["batch"] == "B"]["date"].unique())
    sep_idx = None
    if batch_b_dates:
        first_b = min(batch_b_dates)
        if first_b in all_dates:
            sep_idx = all_dates.index(first_b) - 0.5

    fig = go.Figure(go.Heatmap(
        z=z_vals.tolist(),
        x=date_labels,
        y=[TRAIT_LABELS.get(t, t) for t in traits],
        text=text_vals,
        texttemplate="%{text}",
        textfont=dict(size=10, color="black"),
        colorscale=[
            [0.0,  "#f5f9f6"],
            [0.1,  "#c8e6c9"],
            [0.3,  "#81c784"],
            [0.6,  "#388e3c"],
            [1.0,  "#1b5e20"],
        ],
        zmin=0, zmax=0.8,
        colorbar=dict(
            title=dict(text="ε²", side="right"),
            thickness=14, len=0.6,
        ),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover_vals,
        xgap=2, ygap=1,
    ))

    # Batch separator
    if sep_idx is not None:
        fig.add_shape(
            type="line",
            x0=sep_idx, x1=sep_idx, y0=-0.5, y1=n_traits - 0.5,
            line=dict(color="#E69F00", width=2, dash="dot"),
        )
        fig.add_annotation(
            x=sep_idx, y=n_traits - 0.3,
            text="B →", showarrow=False,
            font=dict(size=10, color="#E69F00"),
        )

    # Legend for significance
    for label, x_pos in [("* p<0.05", 0.72), ("** p<0.01", 0.81), ("*** p<0.001", 0.91)]:
        fig.add_annotation(
            x=x_pos, y=1.04, xref="paper", yref="paper",
            text=label, showarrow=False,
            font=dict(size=10, color="#444"),
        )

    fig.update_layout(
        height=max(400, n_traits * 28 + 80),
        margin=dict(l=240, r=100, t=40, b=70),
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(title=None, tickangle=-45, side="bottom"),
        yaxis=dict(title=None, autorange="reversed"),
        font=dict(family="Inter, sans-serif", size=11),
    )
    return fig


# ---------------------------------------------------------------------------
# Champion table
# ---------------------------------------------------------------------------

def _champion_table(season_metrics, trait):
    if season_metrics.empty:
        return html.Div("No season metrics available.", className="stats-empty")

    df_t = season_metrics[season_metrics["trait"] == trait].copy()
    if df_t.empty:
        return html.Div("No data for selected trait.", className="stats-empty")

    df_t = df_t.sort_values("champion_pct", ascending=False, na_position="last")

    trend_icon = {"up": "↑", "down": "↓", "flat": "→"}
    trend_color = {"up": "#2d7a45", "down": "#c62828", "flat": "#666"}

    rows = []
    for _, row in df_t.iterrows():
        peak_str = (
            f"{row['peak_value']:.2f} ({pd.Timestamp(row['peak_date']).strftime('%d %b')})"
            if pd.notna(row["peak_value"]) and row["peak_date"] is not None
            else "—"
        )
        champ_str = (
            f"{row['champion_pct']:.0f}% ({int(row['champion_wins'])}/{int(row['total_sig_dates'])})"
            if pd.notna(row["champion_pct"])
            else "—"
        )
        t_icon  = trend_icon.get(row["trend"], "→")
        t_color = trend_color.get(row["trend"], "#666")
        rows.append(html.Tr([
            html.Td(row["cultivar"], className="champ-cv"),
            html.Td(html.Span(t_icon, style={"color": t_color, "fontSize": "18px",
                                             "fontWeight": "700"})),
            html.Td(peak_str, className="champ-peak"),
            html.Td(champ_str, className="champ-pct"),
        ]))

    return html.Div([
        html.P(f"Champion = CLD letter 'a' on a date with significant KW (α = 0.05). "
               f"Trend = linear slope over observed dates.",
               className="card-subtitle"),
        html.Table(className="champion-table", children=[
            html.Thead(html.Tr([
                html.Th("Cultivar"),
                html.Th("Trend"),
                html.Th("Peak (date)"),
                html.Th("Champion wins"),
            ])),
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

        # Heatmap
        html.Div(className="card", children=[
            html.H3("Effect Size Heatmap (ε²)", className="card-title"),
            html.P("Colour intensity = effect size ε². Annotations: significance stars. "
                   "Only dates with ≥2 cultivars measured are shown.",
                   className="card-subtitle"),
            dcc.Graph(id="ss-heatmap", config={"displayModeBar": "hover"}),
        ]),

        # Champion / peak table
        html.Div(className="card", children=[
            html.H3("Champion & Peak Table", className="card-title"),
            html.Div(className="filter-row", children=[
                html.Label("Trait:", className="filter-label"),
                dcc.Dropdown(
                    id="ss-trait",
                    options=[{"label": TRAIT_LABELS[t], "value": t} for t in TRAIT_COLS],
                    value="n_stolon_primary",
                    clearable=False,
                    style={"width": "300px"},
                ),
            ]),
            html.Div(id="ss-champion"),
        ]),
    ]),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("ss-heatmap", "figure"),
    Input("url", "pathname"),
)
def render_heatmap(_pathname):
    return _epsilon2_heatmap(cache.stats_cache, cache.df_clean)


@callback(
    Output("ss-champion", "children"),
    Input("ss-trait", "value"),
)
def update_champion(trait):
    return _champion_table(cache.season_metrics, trait or TRAIT_COLS[0])
