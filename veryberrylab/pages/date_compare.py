"""
pages/date_compare.py
=====================
Page 3 — Date Compare

For a selected (trait, date):
  - Sorted dot plot: cultivars on Y sorted by mean, raw rep points at fixed offsets,
    mean marker, SE bar
  - CLD letters displayed beside each cultivar label
  - Stats panel: KW H, p, ε², n, correction method, significance
  - Pairwise adjusted p-value table (expandable)
  - Post-hoc greyed out when KW is not significant (with override toggle)
"""

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

import src.data_cache as cache
from src.etl import BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_LABELS
from src.stats import sig_label

dash.register_page(__name__, path="/date-compare", name="Date Compare", order=2)

PALETTE = [
    "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2",
    "#D55E00", "#CC79A7", "#000000", "#AA4499", "#44BB99", "#BBCC33",
]
ALL_CULTIVARS = sorted(BATCH_A | BATCH_B)
CV_COLOR = {cv: PALETTE[i] for i, cv in enumerate(ALL_CULTIVARS)}

REP_OFFSETS = [-0.22, 0.0, 0.22]


# ---------------------------------------------------------------------------
# Dot-plot figure
# ---------------------------------------------------------------------------

def _dot_plot(result, show_cld):
    if result is None:
        fig = go.Figure()
        fig.update_layout(
            height=350,
            annotations=[dict(text="No data for this selection",
                              x=0.5, y=0.5, xref="paper", yref="paper",
                              showarrow=False, font=dict(size=14, color="#888"))],
            plot_bgcolor="white", paper_bgcolor="white",
        )
        return fig

    # Sort cultivars by mean (ascending → top of chart = highest)
    sorted_cvs = sorted(result.cultivars, key=lambda cv: result.means.get(cv, 0))
    n_cvs = len(sorted_cvs)

    fig = go.Figure()

    for rank, cv in enumerate(sorted_cvs):
        color = CV_COLOR.get(cv, "#888")
        vals = result.raw_values.get(cv, [])
        mean_v = result.means.get(cv, np.nan)
        se_v   = result.se.get(cv, 0.0)

        # SE bar
        fig.add_trace(go.Scatter(
            x=[mean_v - se_v, mean_v + se_v],
            y=[rank, rank],
            mode="lines",
            line=dict(color=color, width=3),
            showlegend=False,
            hoverinfo="skip",
        ))

        # Raw rep dots
        for k, v in enumerate(vals):
            offset = REP_OFFSETS[k] if k < len(REP_OFFSETS) else 0.0
            fig.add_trace(go.Scatter(
                x=[v], y=[rank + offset],
                mode="markers",
                marker=dict(size=10, color=color, opacity=0.75,
                            line=dict(width=1, color="white")),
                showlegend=False,
                hovertemplate=f"<b>{cv}</b> rep {k+1}: %{{x:.2f}}<extra></extra>",
            ))

        # Mean diamond
        fig.add_trace(go.Scatter(
            x=[mean_v], y=[rank],
            mode="markers",
            marker=dict(size=14, color=color, symbol="diamond",
                        line=dict(width=1.5, color="white")),
            name=cv,
            showlegend=False,
            hovertemplate=f"<b>{cv}</b><br>Mean: %{{x:.2f}}<br>SE: ±{se_v:.2f}<extra></extra>",
        ))

    # CLD letters as y-axis annotations
    if show_cld and result.cld:
        for rank, cv in enumerate(sorted_cvs):
            letter = result.cld.get(cv, "")
            # Determine if cultivar is in best group
            is_best = result.significant and "a" in letter
            fig.add_annotation(
                x=-0.02, y=rank,
                xref="paper", yref="y",
                text=f"<b>{letter}</b>" if is_best else letter,
                showarrow=False,
                xanchor="right",
                font=dict(
                    size=13,
                    color="#2d7a45" if is_best else "#555555",
                ),
            )

    # Star for best-group cultivars
    if result.significant:
        for rank, cv in enumerate(sorted_cvs):
            if "a" in result.cld.get(cv, ""):
                fig.add_annotation(
                    x=1.01, y=rank,
                    xref="paper", yref="y",
                    text="★",
                    showarrow=False,
                    font=dict(size=14, color="#E69F00"),
                )

    fig.update_layout(
        height=max(300, n_cvs * 52 + 60),
        margin=dict(l=140, r=50, t=30, b=50),
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(
            title=TRAIT_LABELS.get(result.trait, result.trait),
            showgrid=True, gridcolor="#f0f0f0", zeroline=False,
        ),
        yaxis=dict(
            tickvals=list(range(n_cvs)),
            ticktext=sorted_cvs,
            showgrid=False,
        ),
        font=dict(family="Inter, sans-serif", size=12),
        hovermode="closest",
    )
    return fig


# ---------------------------------------------------------------------------
# Stats panel
# ---------------------------------------------------------------------------

def _stats_panel(result, show_exploratory):
    if result is None:
        return html.Div("No result.", className="stats-empty")

    sig = result.significant
    label = sig_label(result.kw_p)
    color = "#2d7a45" if sig else "#888"

    panel = html.Div(className="stats-panel", children=[
        html.Div(className="stats-header", children=[
            html.Span(label, className=f"sig-badge sig-{'yes' if sig else 'no'}"),
            html.Span("Kruskal–Wallis", className="stats-method"),
        ]),
        html.Table(className="stats-table", children=[
            html.Tr([html.Td("H statistic"), html.Td(f"{result.kw_H:.3f}")]),
            html.Tr([html.Td("p-value"),     html.Td(f"{result.kw_p:.4f}")]),
            html.Tr([html.Td("Effect ε²"),   html.Td(
                html.Span(f"{result.epsilon2:.3f}", style={"color": color, "fontWeight": "600"})
            )]),
            html.Tr([html.Td("Groups (k)"),  html.Td(str(len(result.cultivars)))]),
            html.Tr([html.Td("Total n"),     html.Td(str(sum(result.n_per_cv.values())))]),
            html.Tr([html.Td("Post-hoc"),    html.Td("Conover–Iman")]),
            html.Tr([html.Td("Correction"),  html.Td(result.correction.capitalize())]),
            html.Tr([html.Td("α"),           html.Td(str(result.alpha))]),
        ]),

        # CLD legend
        html.Div(className="cld-legend", children=[
            html.P("CLD: cultivars sharing a letter are not significantly different "
                   f"(α = {result.alpha}).",
                   className="cld-info"),
            html.P("★ = best group (letter 'a').", className="cld-info"),
        ]),

        # Non-significant notice
        html.Div(
            "KW not significant — pairwise results shown for exploration only.",
            className="exploratory-notice",
            style={"display": "block" if (not sig and show_exploratory) else
                              "none"   if sig else "block"},
        ) if not sig else html.Div(),
    ])
    return panel


def _pairwise_table(result):
    if result is None or result.posthoc is None:
        return html.Div("Post-hoc not available.", className="stats-empty")

    ph = result.posthoc
    cvs = sorted(ph.index.tolist())

    header = html.Tr([html.Th("")] + [html.Th(cv, className="ph-col-header") for cv in cvs])
    rows = []
    for cv_i in cvs:
        cells = [html.Td(cv_i, className="ph-row-header")]
        for cv_j in cvs:
            if cv_i == cv_j:
                cells.append(html.Td("—", className="ph-cell ph-diag"))
            else:
                try:
                    p = ph.loc[cv_i, cv_j]
                    sig = p < result.alpha
                    cells.append(html.Td(
                        f"{p:.3f}",
                        className=f"ph-cell {'ph-sig' if sig else ''}",
                        title=f"{cv_i} vs {cv_j}: p={p:.4f}",
                    ))
                except KeyError:
                    cells.append(html.Td("—", className="ph-cell"))
        rows.append(html.Tr(cells))

    return html.Div(className="pairwise-wrapper", children=[
        html.P(f"Adjusted p-values ({result.correction.capitalize()}-corrected Conover–Iman). "
               "Bold/highlighted = significant at the chosen α.",
               className="card-subtitle"),
        html.Table(className="pairwise-table", children=[html.Thead(header), html.Tbody(rows)]),
    ])


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def _date_options(df, trait):
    if not trait:
        return [], None
    dates = sorted(df[df[trait].notna()]["date"].unique())
    opts = [{"label": pd.Timestamp(d).strftime("%d %b %Y"), "value": str(d)[:10]}
            for d in dates]
    return opts, (opts[-1]["value"] if opts else None)


layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Date Compare", className="page-title"),
        html.P("Compare cultivars on a chosen date for a chosen trait — "
               "with Kruskal–Wallis, effect size ε², and compact letter display.",
               className="page-subtitle"),
    ]),
    html.Div(className="content-area", children=[

        # Filters
        html.Div(className="card filter-card", children=[
            html.Div(className="filter-row", children=[
                html.Div([
                    html.Label("Trait", className="filter-label"),
                    dcc.Dropdown(
                        id="dc-trait",
                        options=[{"label": TRAIT_LABELS[t], "value": t} for t in TRAIT_COLS],
                        value="n_stolon_primary",
                        clearable=False,
                        style={"width": "280px"},
                    ),
                ]),
                html.Div([
                    html.Label("Date", className="filter-label"),
                    dcc.Dropdown(
                        id="dc-date",
                        clearable=False,
                        style={"width": "200px"},
                    ),
                ]),
                html.Div([
                    html.Label("α (significance level)", className="filter-label"),
                    dcc.Dropdown(
                        id="dc-alpha",
                        options=[
                            {"label": "α = 0.05", "value": 0.05},
                            {"label": "α = 0.01", "value": 0.01},
                            {"label": "α = 0.10", "value": 0.10},
                        ],
                        value=0.05,
                        clearable=False,
                        style={"width": "140px"},
                    ),
                ]),
            ]),
        ]),

        # Main two-column: chart + stats
        html.Div(className="dc-main-row", children=[
            html.Div(className="dc-chart-col card", children=[
                html.H3("Cultivar Comparison", className="card-title"),
                html.P("Diamond = mean.  Bar = ±SE.  Dots = individual replicates.  "
                       "Letter 'a' = best group.",
                       className="card-subtitle"),
                dcc.Graph(id="dc-dotplot", config={"displayModeBar": "hover"}),
            ]),
            html.Div(className="dc-stats-col card", children=[
                html.H3("Statistics", className="card-title"),
                html.Div(id="dc-stats"),
            ]),
        ]),

        # Pairwise table (collapsible)
        html.Div(className="card", children=[
            html.Details([
                html.Summary("View pairwise adjusted p-values",
                             style={"cursor": "pointer", "fontWeight": "600"}),
                html.Div(id="dc-pairwise"),
            ]),
        ]),
    ]),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("dc-date", "options"),
    Output("dc-date", "value"),
    Input("dc-trait", "value"),
)
def update_date_options(trait):
    df = cache.df_clean
    opts, default = _date_options(df, trait)
    return opts, default


@callback(
    Output("dc-dotplot",  "figure"),
    Output("dc-stats",    "children"),
    Output("dc-pairwise", "children"),
    Input("dc-trait", "value"),
    Input("dc-date",  "value"),
    Input("dc-alpha", "value"),
)
def update_charts(trait, date, alpha):
    if not trait or not date:
        empty_fig = go.Figure()
        empty_fig.update_layout(
            height=300, plot_bgcolor="white", paper_bgcolor="white",
            annotations=[dict(text="Select a trait and date.", x=0.5, y=0.5,
                              xref="paper", yref="paper", showarrow=False,
                              font=dict(size=14, color="#888"))],
        )
        return empty_fig, html.Div(), html.Div()

    key = (trait, date)
    result = cache.stats_cache.get(key)

    # If not in cache (e.g. alpha changed), recompute
    if result is None or result.alpha != alpha:
        from src.stats import compute_stats_for
        result = compute_stats_for(cache.df_clean, trait, date, alpha=alpha)

    show_exp = True  # always show post-hoc (greyed/labelled if not sig)
    fig   = _dot_plot(result, show_cld=True)
    stats = _stats_panel(result, show_exploratory=show_exp)
    pw    = _pairwise_table(result)

    return fig, stats, pw
