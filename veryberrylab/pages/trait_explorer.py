"""
pages/trait_explorer.py
========================
Page 2 — Trait Explorer

Two views:
  A) Time-series:  mean ± SE lines per cultivar, raw replicate dots (jittered),
                   batch gap indicated by a vertical separator.
  B) Date strip:   dot plots for each measurement date (small multiples),
                   showing individual reps + mean marker.

No connecting lines across batch gaps (lines break at batch boundaries).
"""

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html
from plotly.subplots import make_subplots

import src.data_cache as cache
from src.etl import BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_LABELS

dash.register_page(__name__, path="/trait-explorer", name="Trait Explorer", order=1)

# Okabe-Ito palette
PALETTE = [
    "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2",
    "#D55E00", "#CC79A7", "#000000", "#AA4499", "#44BB99", "#BBCC33",
]
ALL_CULTIVARS = sorted(BATCH_A | BATCH_B)
CV_COLOR = {cv: PALETTE[i] for i, cv in enumerate(ALL_CULTIVARS)}


# ---------------------------------------------------------------------------
# Figure builders
# ---------------------------------------------------------------------------

def _time_series_fig(df, trait, selected_cvs, show_raw):
    """Multi-cultivar mean ± SE time series, raw points optional."""
    fig = go.Figure()

    batch_a_dates = sorted(df[df["batch"] == "A"]["date"].unique())
    batch_b_dates = sorted(df[df["batch"] == "B"]["date"].unique())

    # Vertical separator between last batch-A date and first batch-B date
    if batch_a_dates and batch_b_dates:
        sep_x = batch_a_dates[-1] + (batch_b_dates[0] - batch_a_dates[-1]) / 2
        fig.add_vline(x=sep_x.timestamp() * 1000, line_dash="dot",
                      line_color="#cccccc", line_width=1)
        fig.add_annotation(
            x=sep_x, y=1, yref="paper",
            text="← A | B →", showarrow=False,
            font=dict(size=10, color="#aaaaaa"),
        )

    for cv in selected_cvs:
        color = CV_COLOR.get(cv, "#888888")
        cv_df = df[df["cultivar"] == cv][["date", "batch", trait]].copy()
        cv_df = cv_df.dropna(subset=[trait])
        if cv_df.empty:
            continue

        # Aggregate per date
        agg = cv_df.groupby(["date", "batch"])[trait].agg(
            mean="mean", se=lambda x: x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0
        ).reset_index()
        agg = agg.sort_values("date")

        # Draw lines WITHIN each batch only (no cross-batch line)
        for batch in ["A", "B"]:
            batch_agg = agg[agg["batch"] == batch].sort_values("date")
            if batch_agg.empty:
                continue
            x_line = batch_agg["date"].tolist()
            y_line = batch_agg["mean"].tolist()
            y_up   = (batch_agg["mean"] + batch_agg["se"]).tolist()
            y_dn   = (batch_agg["mean"] - batch_agg["se"]).tolist()

            # SE ribbon
            fig.add_trace(go.Scatter(
                x=x_line + x_line[::-1],
                y=y_up + y_dn[::-1],
                fill="toself",
                fillcolor=color.replace(")", ", 0.12)").replace("rgb", "rgba")
                    if color.startswith("rgb") else color + "1f",
                line_color="rgba(0,0,0,0)",
                showlegend=False,
                hoverinfo="skip",
            ))
            # Mean line
            fig.add_trace(go.Scatter(
                x=x_line, y=y_line,
                mode="lines+markers",
                name=cv,
                legendgroup=cv,
                showlegend=(batch == "A" or (
                    "A" not in agg["batch"].values)),
                line=dict(color=color, width=2),
                marker=dict(size=8, color=color),
                hovertemplate=f"<b>{cv}</b> ({batch})<br>%{{x|%d %b}}<br>"
                              f"Mean: %{{y:.2f}}<extra></extra>",
            ))

        # Raw rep dots (jittered slightly in x)
        if show_raw:
            raw = cv_df.sort_values("date")
            # Jitter: spread 3 reps ±0.4 day
            jitter_offsets = np.linspace(-0.4, 0.4, 3) * 86400 * 1000  # ms
            rep_counts = raw.groupby("date").cumcount()
            x_jitter = [
                (d.value // 10**6 + jitter_offsets[min(r, 2)])
                for d, r in zip(raw["date"], rep_counts)
            ]
            fig.add_trace(go.Scatter(
                x=pd.to_datetime(x_jitter, unit="ms"),
                y=raw[trait].tolist(),
                mode="markers",
                name=cv,
                legendgroup=cv,
                showlegend=False,
                marker=dict(size=5, color=color, opacity=0.6,
                            line=dict(width=0.5, color="white")),
                hovertemplate=f"<b>{cv}</b> — rep point<br>%{{x|%d %b}}<br>"
                              f"%{{y:.2f}}<extra></extra>",
            ))

    fig.update_layout(
        height=420,
        margin=dict(l=60, r=20, t=20, b=50),
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(title=None, showgrid=True, gridcolor="#f0f0f0",
                   tickformat="%d %b"),
        yaxis=dict(title=TRAIT_LABELS.get(trait, trait),
                   showgrid=True, gridcolor="#f0f0f0"),
        legend=dict(orientation="v", x=1.01, y=1, xanchor="left"),
        font=dict(family="Inter, sans-serif", size=12),
        hovermode="closest",
    )
    return fig


def _date_strip_fig(df, trait, selected_cvs):
    """Small-multiple dot plots, one per measurement date."""
    all_dates = sorted(df[df["cultivar"].isin(selected_cvs)]["date"].unique())
    if not all_dates:
        return go.Figure()

    n_dates = len(all_dates)
    cols = min(6, n_dates)
    rows = (n_dates + cols - 1) // cols

    subplot_titles = [pd.Timestamp(d).strftime("%d %b") for d in all_dates]
    fig = make_subplots(
        rows=rows, cols=cols,
        subplot_titles=subplot_titles,
        shared_yaxes=True,
        horizontal_spacing=0.04,
        vertical_spacing=0.14,
    )

    for i, date in enumerate(all_dates):
        row = i // cols + 1
        col = i % cols + 1

        date_df = df[(df["date"] == date) & (df["cultivar"].isin(selected_cvs))][
            ["cultivar", trait]
        ].dropna(subset=[trait])

        for j, cv in enumerate(selected_cvs):
            cv_vals = date_df[date_df["cultivar"] == cv][trait].tolist()
            if not cv_vals:
                continue
            color = CV_COLOR.get(cv, "#888")
            n = len(cv_vals)
            # Spread reps at fixed y offsets
            y_offsets = np.linspace(-0.25, 0.25, n) if n > 1 else [0.0]
            fig.add_trace(
                go.Scatter(
                    x=cv_vals,
                    y=[j + ofs for ofs in y_offsets],
                    mode="markers",
                    marker=dict(size=8, color=color,
                                line=dict(width=1, color="white")),
                    name=cv,
                    legendgroup=cv,
                    showlegend=(i == 0),
                    hovertemplate=f"<b>{cv}</b><br>%{{x:.2f}}<extra></extra>",
                ),
                row=row, col=col,
            )
            # Mean marker
            mean_val = np.mean(cv_vals)
            fig.add_trace(
                go.Scatter(
                    x=[mean_val], y=[j],
                    mode="markers",
                    marker=dict(size=11, color=color, symbol="diamond",
                                line=dict(width=1.5, color="white")),
                    showlegend=False,
                    hovertemplate=f"<b>{cv}</b> mean: %{{x:.2f}}<extra></extra>",
                ),
                row=row, col=col,
            )

        # Update y-axis ticks for this subplot
        fig.update_yaxes(
            tickvals=list(range(len(selected_cvs))),
            ticktext=selected_cvs,
            row=row, col=col,
        )

    fig.update_layout(
        height=max(280, rows * 200),
        margin=dict(l=100, r=20, t=40, b=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, sans-serif", size=11),
        showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
    fig.update_yaxes(showgrid=False)
    return fig


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Trait Explorer", className="page-title"),
        html.P("Time-series and date-level distributions for any trait across cultivars.",
               className="page-subtitle"),
    ]),
    html.Div(className="content-area", children=[

        # Filters
        html.Div(className="card filter-card", children=[
            html.Div(className="filter-row", children=[
                html.Div([
                    html.Label("Trait", className="filter-label"),
                    dcc.Dropdown(
                        id="te-trait",
                        options=[{"label": TRAIT_LABELS[t], "value": t} for t in TRAIT_COLS],
                        value="n_stolon_primary",
                        clearable=False,
                        style={"width": "280px"},
                    ),
                ]),
                html.Div([
                    html.Label("Cultivars", className="filter-label"),
                    dcc.Dropdown(
                        id="te-cultivars",
                        options=[{"label": cv, "value": cv} for cv in ALL_CULTIVARS],
                        value=ALL_CULTIVARS,
                        multi=True,
                        style={"width": "420px"},
                    ),
                ]),
                html.Div([
                    html.Label("Show raw replicates", className="filter-label"),
                    dcc.Checklist(
                        id="te-show-raw",
                        options=[{"label": "", "value": "show"}],
                        value=["show"],
                        className="toggle-check",
                    ),
                ]),
            ]),
        ]),

        # Time series
        html.Div(className="card", children=[
            html.H3("Time Series (mean ± SE)", className="card-title"),
            dcc.Graph(id="te-timeseries", config={"displayModeBar": "hover"}),
        ]),

        # Date strip
        html.Div(className="card", children=[
            html.H3("Distribution by Date", className="card-title"),
            html.P("Each point = one replicate plant. Diamond = cultivar mean.",
                   className="card-subtitle"),
            dcc.Graph(id="te-strip", config={"displayModeBar": "hover"}),
        ]),
    ]),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("te-timeseries", "figure"),
    Input("te-trait",      "value"),
    Input("te-cultivars",  "value"),
    Input("te-show-raw",   "value"),
)
def update_timeseries(trait, cultivars, show_raw_flag):
    df = cache.df_clean
    cvs = cultivars or ALL_CULTIVARS
    show_raw = bool(show_raw_flag)
    return _time_series_fig(df, trait or TRAIT_COLS[0], cvs, show_raw)


@callback(
    Output("te-strip", "figure"),
    Input("te-trait",     "value"),
    Input("te-cultivars", "value"),
)
def update_strip(trait, cultivars):
    df = cache.df_clean
    cvs = cultivars or ALL_CULTIVARS
    return _date_strip_fig(df, trait or TRAIT_COLS[0], cvs)
