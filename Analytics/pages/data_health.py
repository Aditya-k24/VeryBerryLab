"""
pages/data_health.py — Page 1: Data Health

• Summary stat cards
• Batch measurement timeline
• Completeness matrix (cultivar × date, coloured by observation status)
• Ingestion warnings panel
"""

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

import src.data_cache as cache
from src.ui import GRAPH_CONFIG
from src.etl import BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_LABELS

dash.register_page(__name__, path="/", name="Data Health", order=0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _timeline_fig(df):
    colors = {"A": "#56B4E9", "B": "#E69F00"}
    fig = go.Figure()
    for batch, cvs in [("A", BATCH_A), ("B", BATCH_B)]:
        cvs_present = sorted(c for c in cvs if c in df["cultivar"].values)
        for i, cv in enumerate(cvs_present):
            cv_dates = sorted(df[df["cultivar"] == cv]["date"].unique())
            fig.add_trace(go.Scatter(
                x=cv_dates, y=[cv] * len(cv_dates),
                mode="markers",
                marker=dict(size=13, color=colors[batch], symbol="diamond",
                            line=dict(width=1, color="white")),
                name=f"Batch {batch}",
                legendgroup=f"Batch {batch}",
                showlegend=(i == 0),
                hovertemplate=f"<b>{cv}</b><br>%{{x|%d %b %Y}}<extra>Batch {batch}</extra>",
            ))
    fig.update_layout(
        height=300, margin=dict(l=120, r=20, t=10, b=40),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(tickformat="%d %b", showgrid=True, gridcolor="#f0f0f0"),
        yaxis=dict(autorange="reversed"),
        legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.22),
        font=dict(family="IBM Plex Sans, Helvetica, Arial, sans-serif", size=12),
    )
    return fig


def _completeness_fig(df, selected_trait):
    comp = cache.completeness
    all_dates = sorted(df["date"].unique())
    cv_order  = sorted(df["cultivar"].unique())
    x_labels  = [pd.Timestamp(d).strftime("%d %b") for d in all_dates]

    if selected_trait == "all":
        # % of traits observed per (cultivar, date)
        pivot = comp.pivot_table(
            index="cultivar", columns="date", values="status",
            aggfunc=lambda x: (x == "observed").mean()
        ).reindex(index=cv_order, columns=all_dates)
        colorscale = [[0, "#f0f0f0"], [0.001, "#fff9c4"], [0.5, "#81c784"], [1, "#2d7a45"]]
        hover = "%{y}<br>%{x}<br>Observed: %{z:.0%}<extra></extra>"
    else:
        smap = {"observed": 1.0, "not_measured": 0.4, "not_scheduled": 0.0}
        pivot = comp[comp["trait"] == selected_trait].pivot_table(
            index="cultivar", columns="date", values="status",
            aggfunc=lambda x: smap.get(x.iloc[0], 0.0)
        ).reindex(index=cv_order, columns=all_dates)
        colorscale = [[0, "#e8e8e8"], [0.39, "#e8e8e8"], [0.4, "#ffe082"],
                      [0.41, "#ffe082"], [1, "#2d7a45"]]
        hover = "%{y}<br>%{x}<extra></extra>"

    fig = go.Figure(go.Heatmap(
        z=pivot.values.tolist(), x=x_labels, y=cv_order,
        colorscale=colorscale, zmin=0, zmax=1,
        hovertemplate=hover, xgap=2, ygap=2,
        colorbar=dict(thickness=12, len=0.5),
    ))

    # Batch boundary
    batch_b_start = min(sorted(df[df["batch"] == "B"]["date"].unique()), default=None)
    if batch_b_start and batch_b_start in all_dates:
        pos = list(all_dates).index(batch_b_start) - 0.5
        fig.add_shape(type="line", x0=pos, x1=pos, y0=-0.5, y1=len(cv_order) - 0.5,
                      line=dict(color="#E69F00", width=2, dash="dot"))

    fig.update_layout(
        height=320, margin=dict(l=120, r=80, t=10, b=60),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(tickangle=-40),
        yaxis=dict(autorange="reversed"),
        font=dict(family="IBM Plex Sans, Helvetica, Arial, sans-serif", size=12),
    )
    return fig


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def _hero():
    df = cache.df_clean
    n_cv = df["cultivar"].nunique() if not df.empty else 0
    n_dt = df["date"].nunique() if not df.empty else 0
    n_ob = len(df)
    n_tr = len(TRAIT_COLS)
    span = (f"{df['date'].min():%b} – {df['date'].max():%b %Y}" if not df.empty else "")
    complete = (100 - df[TRAIT_COLS].isna().mean().mean() * 100) if not df.empty else 0
    chip = lambda v, l: html.Div(className="hero-chip", children=[html.B(str(v)), html.Span(l)])
    return html.Div(className="hero", children=[
        html.Div(className="hero-glow"),
        html.Div(className="hero-glow two"),
        html.Div("VeryBerryLab · Phenotyping Batch 4", className="hero-eyebrow"),
        html.H1(className="hero-title", children=[
            "Strawberry ", html.Span("phenotyping", className="accent"), " analytics"]),
        html.P("Vegetative and reproductive architecture of eleven strawberry "
               "cultivars across a full growing season — ingestion, statistics, "
               "and publication-ready figures in one place.",
               className="hero-sub"),
        html.Div(className="hero-stats", children=[
            chip(n_cv, "Cultivars"), chip(n_dt, "Dates"),
            chip(n_tr, "Traits"), chip(n_ob, "Observations"),
            chip(f"{complete:.0f}%", "Complete"), chip(span, "Season"),
        ]),
        html.Div(className="hero-cta", children=[
            dcc.Link("Explore traits →", href="/trait-explorer",
                     className="hero-btn hero-btn-primary"),
            dcc.Link("Compare cultivars", href="/date-compare",
                     className="hero-btn hero-btn-ghost"),
            dcc.Link("Methods & export", href="/export",
                     className="hero-btn hero-btn-ghost"),
        ]),
    ])


layout = html.Div([
    html.Div(className="content-area", children=[

        _hero(),

        html.Div(className="card", children=[
            html.H3("Measurement Timeline", className="card-title"),
            html.P("Each diamond = one measurement date.", className="card-subtitle"),
            dcc.Graph(id="dh-timeline", config=GRAPH_CONFIG),
        ]),

        html.Div(className="card", children=[
            html.H3("Completeness Matrix", className="card-title"),
            html.Div(className="filter-row", children=[
                html.Label("View:", className="filter-label"),
                dcc.Dropdown(
                    id="dh-trait",
                    options=[{"label": "All traits (% observed)", "value": "all"}]
                            + [{"label": TRAIT_LABELS[t], "value": t} for t in TRAIT_COLS],
                    value="all", clearable=False, style={"width": "300px"},
                ),
            ]),
            html.Div(className="legend-row", children=[
                html.Span(className="leg-dot", style={"background": "#2d7a45"}),
                html.Span("Observed",      className="leg-label"),
                html.Span(className="leg-dot", style={"background": "#ffe082"}),
                html.Span("Not measured",  className="leg-label"),
                html.Span(className="leg-dot", style={"background": "#e8e8e8"}),
                html.Span("Not scheduled", className="leg-label"),
            ]),
            dcc.Graph(id="dh-completeness", config=GRAPH_CONFIG),
        ]),

        html.Div(className="card", children=[
            html.H3("Ingestion Notices", className="card-title"),
            html.Details([
                html.Summary(id="dh-warn-summary", style={"cursor": "pointer"}),
                html.Ul(id="dh-warn-list", className="warn-list"),
            ]),
        ]),
    ]),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(Output("dh-timeline", "figure"), Input("url", "pathname"))
def render_static(_):
    return _timeline_fig(cache.df_clean)


@callback(Output("dh-completeness", "figure"), Input("dh-trait", "value"))
def update_completeness(trait):
    return _completeness_fig(cache.df_clean, trait or "all")


@callback(Output("dh-warn-summary", "children"), Output("dh-warn-list", "children"),
          Input("url", "pathname"))
def render_warnings(_):
    ws = cache.ingestion_warnings
    return (f"{len(ws)} notice{'s' if len(ws) != 1 else ''}",
            [html.Li(w, className="warn-item") for w in ws])
