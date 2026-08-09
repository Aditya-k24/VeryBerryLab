"""
pages/date_compare.py — Page 3: Date Compare

Sorted dot plot + CLD letters + KW stats panel + pairwise p-value table.
"""

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

import src.data_cache as cache
from src.ui import GRAPH_CONFIG
from src.etl import BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_LABELS
from src.stats import sig_label

dash.register_page(__name__, path="/date-compare", name="Day Compare", order=2)

PALETTE  = ["#E69F00","#56B4E9","#009E73","#F0E442","#0072B2",
            "#D55E00","#CC79A7","#000000","#AA4499","#44BB99","#BBCC33"]
ALL_CVS  = sorted(BATCH_A | BATCH_B)
CV_COLOR = {cv: PALETTE[i] for i, cv in enumerate(ALL_CVS)}
REP_OFF  = [-0.22, 0.0, 0.22]


# ---------------------------------------------------------------------------
# Dot-plot figure
# ---------------------------------------------------------------------------

def _dotplot(result):
    if result is None:
        fig = go.Figure()
        fig.update_layout(height=300, plot_bgcolor="white", paper_bgcolor="white",
                          annotations=[dict(text="No data for this selection.",
                                            x=0.5, y=0.5, xref="paper", yref="paper",
                                            showarrow=False, font=dict(size=14, color="#888"))])
        return fig

    sorted_cvs = sorted(result.cultivars, key=lambda cv: result.means.get(cv, 0))
    n = len(sorted_cvs)
    fig = go.Figure()

    # ── Alternating row bands ─────────────────────────────────────────────────
    for rank in range(n):
        if rank % 2 == 1:
            fig.add_shape(type="rect", layer="below",
                x0=0, x1=1, xref="paper",
                y0=rank - 0.5, y1=rank + 0.5, yref="y",
                fillcolor="rgba(0,0,0,0.025)", line_width=0)

    # ── Data traces ───────────────────────────────────────────────────────────
    for rank, cv in enumerate(sorted_cvs):
        color  = CV_COLOR.get(cv, "#888")
        vals   = result.raw_values.get(cv, [])
        mean_v = result.means.get(cv, np.nan)
        se_v   = result.se.get(cv, 0.0)

        fig.add_trace(go.Scatter(           # SE bar
            x=[mean_v - se_v, mean_v + se_v], y=[rank, rank],
            mode="lines", line=dict(color=color, width=3),
            showlegend=False, hoverinfo="skip"))

        for k, v in enumerate(vals):        # rep dots
            off = REP_OFF[k] if k < len(REP_OFF) else 0.0
            fig.add_trace(go.Scatter(
                x=[v], y=[rank + off], mode="markers",
                marker=dict(size=9, color=color, opacity=0.7,
                            line=dict(width=1, color="white")),
                showlegend=False,
                hovertemplate=f"<b>{cv}</b> rep {k+1}: %{{x:.2f}}<extra></extra>"))

        fig.add_trace(go.Scatter(           # mean diamond
            x=[mean_v], y=[rank], mode="markers", name=cv, showlegend=False,
            marker=dict(size=15, color=color, symbol="diamond",
                        line=dict(width=1.5, color="white")),
            hovertemplate=f"<b>{cv}</b><br>Mean: %{{x:.2f}}<br>±SE: {se_v:.2f}<extra></extra>"))

    # ── CLD letter baked into the tick label: "Portola · a" ──────────────────
    # This is the only approach that cannot overlap with plot content at any
    # figure width, since the tick label lives entirely in the left margin.
    tick_labels = [
        f"{cv} · {result.cld.get(cv, '')}" for cv in sorted_cvs
    ]

    # ── Best-group star — right margin only, safe at any width ───────────────
    if result.significant:
        for rank, cv in enumerate(sorted_cvs):
            if "a" in result.cld.get(cv, ""):
                fig.add_annotation(
                    x=1.02, y=rank, xref="paper", yref="y",
                    text="★", showarrow=False, xanchor="left",
                    font=dict(size=14, color="#E69F00"))

    fig.update_layout(
        height=max(280, n * 54 + 60),
        margin=dict(l=175, r=50, t=30, b=50),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(title=TRAIT_LABELS.get(result.trait, result.trait),
                   showgrid=True, gridcolor="#f0f0f0", zeroline=False),
        yaxis=dict(tickvals=list(range(n)), ticktext=tick_labels,
                   showgrid=False, tickfont=dict(size=12)),
        font=dict(family="Work Sans, Helvetica, Arial, sans-serif", size=12),
        hovermode="closest",
    )
    return fig


# ---------------------------------------------------------------------------
# Stats panel
# ---------------------------------------------------------------------------

def _stats_panel(result):
    if result is None:
        return html.Div("No result.", className="stats-empty")
    sig   = result.significant
    label = sig_label(result.kw_p)
    color = "#2d7a45" if sig else "#888"
    return html.Div(className="stats-panel", children=[
        html.Div(className="stats-header", children=[
            html.Span(label, className=f"sig-badge sig-{'yes' if sig else 'no'}"),
            html.Span("Kruskal–Wallis", className="stats-method"),
        ]),
        html.Table(className="stats-table", children=[
            html.Tr([html.Td("H statistic"), html.Td(f"{result.kw_H:.3f}")]),
            html.Tr([html.Td("p-value"),     html.Td(f"{result.kw_p:.4f}")]),
            html.Tr([html.Td("Effect ε²"),   html.Td(html.Span(
                f"{result.epsilon2:.3f}", style={"color": color, "fontWeight": "700"}
            ))]),
            html.Tr([html.Td("Groups (k)"),  html.Td(str(len(result.cultivars)))]),
            html.Tr([html.Td("Total n"),     html.Td(str(sum(result.n_per_cv.values())))]),
            html.Tr([html.Td("Post-hoc"),    html.Td("Conover–Iman")]),
            html.Tr([html.Td("Correction"),  html.Td(result.correction.capitalize())]),
            html.Tr([html.Td("α"),           html.Td(str(result.alpha))]),
        ]),
        html.Div(className="cld-note", children=[
            html.P(f"Cultivars sharing a letter are not significantly different (α={result.alpha}).",
                   className="cld-info"),
            html.P("★ = best group (letter 'a').", className="cld-info"),
        ]),
        html.Div(
            "KW not significant, post-hoc shown for exploration only.",
            className="exploratory-notice",
            style={"display": "none" if sig else "block"},
        ),
    ])


def _pairwise_table(result):
    if result is None or result.posthoc is None:
        return html.Div("Post-hoc not available.", className="stats-empty")
    ph  = result.posthoc
    cvs = sorted(ph.index.tolist())
    header = html.Tr([html.Th("")] + [html.Th(cv) for cv in cvs])
    rows = []
    for ci in cvs:
        cells = [html.Td(ci, className="ph-row")]
        for cj in cvs:
            if ci == cj:
                cells.append(html.Td("-", className="ph-cell ph-diag"))
            else:
                try:
                    p = float(ph.loc[ci, cj])
                    sig = p < result.alpha
                    cells.append(html.Td(f"{p:.3f}",
                                         className=f"ph-cell {'ph-sig' if sig else ''}"))
                except Exception:
                    cells.append(html.Td("-", className="ph-cell"))
        rows.append(html.Tr(cells))
    return html.Div(className="pw-wrap", children=[
        html.P(f"Holm-adjusted Conover–Iman p-values. Highlighted = significant at α={result.alpha}.",
               className="card-subtitle"),
        html.Table(className="pw-table", children=[html.Thead(header), html.Tbody(rows)]),
    ])


def _day_key_table():
    """Reference only: which "Day N" (Batch A / Batch B) is which actual
    calendar date, so the elapsed-day convention used everywhere on the
    site can still be checked against the source workbook."""
    df = cache.df_clean
    if df.empty:
        return html.Div("No data available.", className="stats-empty")
    batch_start = {b: df[df["batch"] == b]["date"].min() for b in ("A", "B")}
    seen, rows_raw = set(), []
    for _, r in df.sort_values("date").iterrows():
        key = (r["batch"], r["date"])
        if key in seen:
            continue
        seen.add(key)
        day = (pd.Timestamp(r["date"]) - batch_start[r["batch"]]).days
        rows_raw.append((r["batch"], day, pd.Timestamp(r["date"])))
    rows_raw.sort(key=lambda t: (t[0], t[1]))

    header = html.Tr([html.Th("Batch"), html.Th("Day"), html.Th("Actual date"),
                       html.Th("Cultivars")])
    rows = []
    for batch, day, date in rows_raw:
        cvs = sorted(df[(df["batch"] == batch) & (df["date"] == date)]["cultivar"].unique())
        rows.append(html.Tr([
            html.Td(batch),
            html.Td(f"Day {day}", style={"fontFamily": "var(--mono)", "fontWeight": "600"}),
            html.Td(date.strftime("%d %b %Y")),
            html.Td(", ".join(cvs), style={"color": "var(--muted)", "fontSize": "12px"}),
        ]))
    return html.Table(className="champ-table",
                       children=[html.Thead(header), html.Tbody(rows)])


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Day Compare", className="page-title"),
        html.P("Compare cultivars on a chosen day: KW test, effect size ε², "
               "CLD grouping letters, and pairwise post-hoc.",
               className="page-subtitle"),
    ]),
    html.Div(className="content-area", children=[

        html.Div(className="card filter-card", children=[
            html.Div(className="filter-row", children=[
                html.Div([html.Label("Trait", className="filter-label"),
                          dcc.Dropdown(id="dc-trait",
                                       options=[{"label": TRAIT_LABELS[t], "value": t}
                                                for t in TRAIT_COLS],
                                       value="n_stolon_primary", clearable=False,
                                       style={"width": "280px"})]),
                html.Div([html.Label("Day", className="filter-label"),
                          dcc.Dropdown(id="dc-date", clearable=False,
                                       style={"width": "200px"})]),
                html.Div([html.Label("α level", className="filter-label"),
                          dcc.Dropdown(id="dc-alpha",
                                       options=[{"label": "α = 0.05", "value": 0.05},
                                                {"label": "α = 0.01", "value": 0.01},
                                                {"label": "α = 0.10", "value": 0.10}],
                                       value=0.05, clearable=False,
                                       style={"width": "140px"})]),
            ]),
        ]),

        html.Div(className="dc-row", children=[
            html.Div(className="dc-chart card", children=[
                html.H3("Cultivar Comparison", className="card-title"),
                html.P("Diamond = mean · Bar = ±SE · Dots = replicates · Letter = CLD group",
                       className="card-subtitle"),
                dcc.Graph(id="dc-plot", config=GRAPH_CONFIG),
            ]),
            html.Div(className="dc-stats card", children=[
                html.H3("Statistics", className="card-title"),
                html.Div(id="dc-stats"),
            ]),
        ]),

        html.Div(className="card", children=[
            html.Details([
                html.Summary("Pairwise adjusted p-values",
                             style={"cursor": "pointer", "fontWeight": "600"}),
                html.Div(id="dc-pw"),
            ]),
        ]),

        html.Div(className="card", children=[
            html.Details([
                html.Summary("Day Index",
                             style={"cursor": "pointer", "fontWeight": "600"}),
                html.Div(style={"marginTop": "12px"}, children=[_day_key_table()]),
            ]),
        ]),
    ]),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(Output("dc-date", "options"), Output("dc-date", "value"),
          Input("dc-trait", "value"))
def upd_dates(trait):
    if not trait:
        return [], None
    df = cache.df_clean
    dates = sorted(df[df[trait].notna()]["date"].unique())
    # "Day N since its own batch's first measurement" instead of a calendar
    # date — batch-prefixed since both batches share this one dropdown.
    batch_start = {b: df[df["batch"] == b]["date"].min() for b in ("A", "B")}
    date_batch  = {d: df[df["date"] == d]["batch"].iloc[0] for d in dates}
    opts = [{"label": f"{date_batch[d]} · Day {(pd.Timestamp(d) - batch_start[date_batch[d]]).days}",
             "value": str(d)[:10]} for d in dates]
    return opts, (opts[-1]["value"] if opts else None)


@callback(Output("dc-plot", "figure"), Output("dc-stats", "children"),
          Output("dc-pw", "children"),
          Input("dc-trait", "value"), Input("dc-date", "value"),
          Input("dc-alpha", "value"))
def upd_charts(trait, date, alpha):
    if not trait or not date:
        empty = go.Figure()
        empty.update_layout(height=280, plot_bgcolor="white", paper_bgcolor="white",
                            annotations=[dict(text="Select a trait and date.", x=0.5, y=0.5,
                                              xref="paper", yref="paper", showarrow=False,
                                              font=dict(size=14, color="#888"))])
        return empty, html.Div(), html.Div()

    result = cache.stats_cache.get((trait, date))
    if result is None or result.alpha != alpha:
        from src.stats import compute_stats_for
        result = compute_stats_for(cache.df_clean, trait, date, alpha=alpha)

    return _dotplot(result), _stats_panel(result), _pairwise_table(result)
