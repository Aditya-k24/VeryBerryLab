"""
pages/data_health.py
====================
Page 1 — Upload & Data Health

Shows:
  • Summary stats (cultivars, dates, traits, observations)
  • Batch timeline (which dates belong to which batch)
  • Completeness matrix (cultivar × date, coloured by observation status)
  • Ingestion warnings panel
"""

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

import src.data_cache as cache
from src.etl import BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_LABELS

dash.register_page(__name__, path="/", name="Data Health", order=0)


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def _summary_cards(df):
    n_cvs   = df["cultivar"].nunique()
    n_dates = df["date"].nunique()
    n_obs   = len(df)
    n_traits = len(TRAIT_COLS)
    missing_pct = df[TRAIT_COLS].isna().mean().mean() * 100

    cards = [
        ("Cultivars",    str(n_cvs),              "card-blue"),
        ("Dates",        str(n_dates),             "card-green"),
        ("Traits",       str(n_traits),            "card-purple"),
        ("Observations", f"{n_obs}",               "card-orange"),
        ("Missing",      f"{missing_pct:.1f}%",    "card-red"),
    ]
    return html.Div(
        className="summary-row",
        children=[
            html.Div(className=f"summary-card {cls}", children=[
                html.Div(val, className="summary-val"),
                html.Div(label, className="summary-label"),
            ])
            for label, val, cls in cards
        ],
    )


def _batch_timeline_fig(df):
    import pandas as pd

    batch_dates = {}
    for batch, cvs in [("A", BATCH_A), ("B", BATCH_B)]:
        cvs_present = [cv for cv in cvs if cv in df["cultivar"].values]
        dates = sorted(
            df[df["cultivar"].isin(cvs_present)]["date"].unique()
        )
        batch_dates[batch] = dates

    fig = go.Figure()
    colors = {"A": "#56B4E9", "B": "#E69F00"}

    for batch, dates in batch_dates.items():
        cvs = sorted(BATCH_A if batch == "A" else BATCH_B)
        for cv in cvs:
            cv_dates = sorted(
                df[df["cultivar"] == cv]["date"].unique()
            )
            if not cv_dates:
                continue
            fig.add_trace(go.Scatter(
                x=cv_dates,
                y=[cv] * len(cv_dates),
                mode="markers",
                marker=dict(size=12, color=colors[batch], symbol="diamond",
                            line=dict(width=1, color="white")),
                name=f"Batch {batch}",
                legendgroup=f"Batch {batch}",
                showlegend=(cv == sorted(BATCH_A if batch == "A" else BATCH_B)[0]),
                hovertemplate=f"<b>{cv}</b><br>%{{x|%d %b %Y}}<extra>Batch {batch}</extra>",
            ))

    fig.update_layout(
        height=320,
        margin=dict(l=120, r=20, t=10, b=40),
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(title=None, showgrid=True, gridcolor="#f0f0f0",
                   tickformat="%d %b"),
        yaxis=dict(title=None, autorange="reversed"),
        legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.2),
        font=dict(family="Inter, sans-serif", size=12),
    )
    return fig


def _completeness_fig(df, selected_trait="all"):
    import pandas as pd
    from src.aggregate import build_completeness_matrix

    comp = cache.completeness
    if comp.empty:
        comp = build_completeness_matrix(df)

    # If a specific trait is selected, filter
    if selected_trait != "all":
        comp = comp[comp["trait"] == selected_trait]

    # For "all" traits: summarise per (cultivar, date) as % observed
    if selected_trait == "all":
        pivot = comp.pivot_table(
            index="cultivar", columns="date",
            values="status",
            aggfunc=lambda x: (x == "observed").mean()
        )
        z_label = "% traits observed"
        colorscale = [[0, "#f5f5f5"], [0.001, "#fff3cd"], [0.5, "#a8d5a2"], [1.0, "#2d7a45"]]
        zmin, zmax = 0, 1
        text_fn = lambda v: f"{v*100:.0f}%" if v > 0 else ""
        hover = "%{x|%d %b}<br>%{y}<br>Observed: %{z:.0%}<extra></extra>"
    else:
        # For one trait: 1 = observed, 0.5 = not_measured, 0 = not_scheduled
        status_num = {"observed": 1.0, "not_measured": 0.4, "not_scheduled": 0.0}
        pivot = comp.pivot_table(
            index="cultivar", columns="date",
            values="status",
            aggfunc=lambda x: status_num.get(x.iloc[0], 0)
        )
        colorscale = [
            [0.0, "#e8e8e8"],
            [0.4, "#ffe082"],
            [0.4001, "#ffe082"],
            [1.0, "#2d7a45"],
        ]
        zmin, zmax = 0, 1
        hover = "%{x|%d %b}<br>%{y}<extra></extra>"

    cultivar_order = sorted(df["cultivar"].unique())
    date_order = sorted(df["date"].unique())
    pivot = pivot.reindex(index=cultivar_order, columns=date_order)

    z_vals = pivot.values.tolist()
    x_vals = [str(d)[:10] for d in date_order]
    x_display = [pd.Timestamp(d).strftime("%d %b") for d in date_order]
    y_vals = cultivar_order

    fig = go.Figure(go.Heatmap(
        z=z_vals,
        x=x_display,
        y=y_vals,
        colorscale=colorscale,
        zmin=zmin,
        zmax=zmax,
        showscale=True,
        hovertemplate=hover,
        xgap=2,
        ygap=2,
    ))

    # Batch separator line
    batch_a_dates = sorted(df[df["batch"] == "A"]["date"].unique())
    batch_b_dates = sorted(df[df["batch"] == "B"]["date"].unique())
    if batch_a_dates and batch_b_dates:
        # Find position of first Batch-B date
        all_sorted = sorted(date_order)
        first_b = min(batch_b_dates)
        pos = all_sorted.index(first_b) - 0.5
        fig.add_shape(type="line",
            x0=pos, x1=pos, y0=-0.5, y1=len(y_vals) - 0.5,
            line=dict(color="#E69F00", width=2, dash="dot"))
        fig.add_annotation(x=pos, y=-0.8, text="Batch B →",
            showarrow=False, font=dict(size=10, color="#E69F00"),
            xref="x", yref="y")

    fig.update_layout(
        height=350,
        margin=dict(l=120, r=20, t=10, b=60),
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(title=None, tickangle=-45),
        yaxis=dict(title=None, autorange="reversed"),
        font=dict(family="Inter, sans-serif", size=12),
    )
    return fig


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Data Health", className="page-title"),
        html.P("Verify cultivars, dates, and measurement completeness before analysis.",
               className="page-subtitle"),
    ]),
    html.Div(className="content-area", children=[

        # Summary cards
        html.Div(id="dh-summary"),

        # Batch timeline
        html.Div(className="card", children=[
            html.H3("Measurement Timeline", className="card-title"),
            html.P("Each diamond = one measurement date for that cultivar.",
                   className="card-subtitle"),
            dcc.Graph(id="dh-timeline", config={"displayModeBar": False}),
        ]),

        # Completeness matrix
        html.Div(className="card", children=[
            html.H3("Completeness Matrix", className="card-title"),
            html.Div(className="filter-row", children=[
                html.Label("View by trait:", className="filter-label"),
                dcc.Dropdown(
                    id="dh-trait-select",
                    options=[{"label": "All traits (% observed)", "value": "all"}]
                            + [{"label": TRAIT_LABELS[t], "value": t} for t in TRAIT_COLS],
                    value="all",
                    clearable=False,
                    style={"width": "320px"},
                ),
            ]),
            html.Div(className="legend-row", children=[
                html.Span(className="legend-dot", style={"background": "#2d7a45"}),
                html.Span("Observed", className="legend-label"),
                html.Span(className="legend-dot", style={"background": "#ffe082"}),
                html.Span("Not measured", className="legend-label"),
                html.Span(className="legend-dot", style={"background": "#e8e8e8"}),
                html.Span("Not scheduled", className="legend-label"),
            ]),
            dcc.Graph(id="dh-completeness", config={"displayModeBar": False}),
        ]),

        # Ingestion warnings
        html.Div(className="card", id="dh-warnings-card", children=[
            html.H3("Ingestion Warnings", className="card-title"),
            html.Details([
                html.Summary(id="dh-warnings-summary", style={"cursor": "pointer"}),
                html.Ul(id="dh-warnings-list", className="warnings-list"),
            ], open=False),
        ]),

    ]),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("dh-summary", "children"),
    Output("dh-timeline", "figure"),
    Input("url", "pathname"),
)
def render_static(_pathname):
    df = cache.df_clean
    return _summary_cards(df), _batch_timeline_fig(df)


@callback(
    Output("dh-completeness", "figure"),
    Input("dh-trait-select", "value"),
)
def update_completeness(trait):
    return _completeness_fig(cache.df_clean, trait or "all")


@callback(
    Output("dh-warnings-summary", "children"),
    Output("dh-warnings-list",    "children"),
    Input("url", "pathname"),
)
def render_warnings(_pathname):
    warnings = cache.ingestion_warnings
    summary = f"{len(warnings)} notice{'s' if len(warnings) != 1 else ''}"
    items = [html.Li(w, className="warning-item") for w in warnings]
    return summary, items
