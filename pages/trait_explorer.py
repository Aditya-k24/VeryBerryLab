"""
pages/trait_explorer.py — Page 2: Trait Explorer

A) Time series: mean ± SE per cultivar, raw rep dots, lines broken at batch gap.
B) Date strip:  dot plots per date (small multiples), one per measurement date.
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

PALETTE = ["#E69F00","#56B4E9","#009E73","#F0E442","#0072B2",
           "#D55E00","#CC79A7","#000000","#AA4499","#44BB99","#BBCC33"]
ALL_CVS   = sorted(BATCH_A | BATCH_B)
CV_COLOR  = {cv: PALETTE[i] for i, cv in enumerate(ALL_CVS)}


def _hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """Convert #RRGGBB to rgba(r,g,b,alpha)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# Figure builders
# ---------------------------------------------------------------------------

def _timeseries(df, trait, cvs, show_raw):
    fig = go.Figure()
    a_dates = sorted(df[df["batch"] == "A"]["date"].unique())
    b_dates = sorted(df[df["batch"] == "B"]["date"].unique())

    if a_dates and b_dates:
        sep = a_dates[-1] + (b_dates[0] - a_dates[-1]) / 2
        fig.add_vline(x=sep.timestamp() * 1000, line_dash="dot",
                      line_color="#cccccc", line_width=1)
        fig.add_annotation(x=sep, y=1.02, yref="paper", text="← A | B →",
                           showarrow=False, font=dict(size=10, color="#aaa"))

    for cv in cvs:
        color = CV_COLOR.get(cv, "#888")
        cv_df = df[df["cultivar"] == cv][["date", "batch", trait]].dropna(subset=[trait])
        if cv_df.empty:
            continue

        agg = cv_df.groupby(["date", "batch"])[trait].agg(
            mean="mean",
            se=lambda x: x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0,
        ).reset_index()

        for batch in ["A", "B"]:
            ba = agg[agg["batch"] == batch].sort_values("date")
            if ba.empty:
                continue
            xs, ys = ba["date"].tolist(), ba["mean"].tolist()
            yu = (ba["mean"] + ba["se"]).tolist()
            yd = (ba["mean"] - ba["se"]).tolist()
            first_in_legend = batch == "A" or "A" not in agg["batch"].values

            # SE ribbon
            fig.add_trace(go.Scatter(
                x=xs + xs[::-1], y=yu + yd[::-1],
                fill="toself", fillcolor=_hex_to_rgba(color, 0.15),
                line_color="rgba(0,0,0,0)", showlegend=False, hoverinfo="skip",
            ))
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines+markers", name=cv,
                legendgroup=cv, showlegend=first_in_legend,
                line=dict(color=color, width=2),
                marker=dict(size=7, color=color),
                hovertemplate=f"<b>{cv}</b> ({batch})<br>%{{x|%d %b}}<br>Mean: %{{y:.2f}}<extra></extra>",
            ))

        if show_raw:
            raw = cv_df.sort_values("date")
            rn  = raw.groupby("date").cumcount()
            offsets = np.linspace(-0.4, 0.4, 3) * 86400 * 1000
            xj = pd.to_datetime(
                [d.value // 10**6 + offsets[min(r, 2)] for d, r in zip(raw["date"], rn)],
                unit="ms"
            )
            fig.add_trace(go.Scatter(
                x=xj, y=raw[trait].tolist(), mode="markers",
                name=cv, legendgroup=cv, showlegend=False,
                marker=dict(size=5, color=color, opacity=0.55,
                            line=dict(width=0.5, color="white")),
                hovertemplate=f"<b>{cv}</b> rep<br>%{{x|%d %b}}: %{{y:.2f}}<extra></extra>",
            ))

    fig.update_layout(
        height=420, margin=dict(l=60, r=20, t=24, b=50),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(tickformat="%d %b", showgrid=True, gridcolor="#f0f0f0"),
        yaxis=dict(title=TRAIT_LABELS.get(trait, trait), showgrid=True, gridcolor="#f0f0f0"),
        legend=dict(x=1.01, y=1, xanchor="left"),
        font=dict(family="Inter, sans-serif", size=12),
        hovermode="closest",
    )
    return fig


def _strip(df, trait, cvs):
    dates = sorted(df[df["cultivar"].isin(cvs)]["date"].unique())
    if not dates:
        return go.Figure()

    cols = min(6, len(dates))
    rows = (len(dates) + cols - 1) // cols
    titles = [pd.Timestamp(d).strftime("%d %b") for d in dates]

    fig = make_subplots(rows=rows, cols=cols, subplot_titles=titles,
                        shared_yaxes=True, horizontal_spacing=0.04, vertical_spacing=0.16)

    for i, date in enumerate(dates):
        r, c = i // cols + 1, i % cols + 1
        day_df = df[(df["date"] == date) & (df["cultivar"].isin(cvs))][["cultivar", trait]].dropna(subset=[trait])

        for j, cv in enumerate(cvs):
            vals = day_df[day_df["cultivar"] == cv][trait].tolist()
            if not vals:
                continue
            color = CV_COLOR.get(cv, "#888")
            n = len(vals)
            oy = np.linspace(-0.25, 0.25, n) if n > 1 else [0.0]
            fig.add_trace(go.Scatter(
                x=vals, y=[j + o for o in oy], mode="markers",
                marker=dict(size=8, color=color, line=dict(width=1, color="white")),
                name=cv, legendgroup=cv, showlegend=(i == 0),
                hovertemplate=f"<b>{cv}</b>: %{{x:.2f}}<extra></extra>",
            ), row=r, col=c)
            fig.add_trace(go.Scatter(
                x=[float(np.mean(vals))], y=[j], mode="markers",
                marker=dict(size=12, color=color, symbol="diamond",
                            line=dict(width=1.5, color="white")),
                showlegend=False,
                hovertemplate=f"<b>{cv}</b> mean: %{{x:.2f}}<extra></extra>",
            ), row=r, col=c)

        fig.update_yaxes(tickvals=list(range(len(cvs))), ticktext=cvs, row=r, col=c)

    fig.update_layout(
        height=max(260, rows * 190), margin=dict(l=100, r=20, t=40, b=20),
        plot_bgcolor="white", paper_bgcolor="white",
        showlegend=False, font=dict(family="Inter, sans-serif", size=11),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
    return fig


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Trait Explorer", className="page-title"),
        html.P("Time-series and per-date dot plots for any trait across cultivars.",
               className="page-subtitle"),
    ]),
    html.Div(className="content-area", children=[

        html.Div(className="card filter-card", children=[
            html.Div(className="filter-row", children=[
                html.Div([
                    html.Label("Trait", className="filter-label"),
                    dcc.Dropdown(
                        id="te-trait",
                        options=[{"label": TRAIT_LABELS[t], "value": t} for t in TRAIT_COLS],
                        value="n_stolon_primary", clearable=False, style={"width": "280px"},
                    ),
                ]),
                html.Div([
                    html.Label("Cultivars", className="filter-label"),
                    dcc.Dropdown(
                        id="te-cvs",
                        options=[{"label": cv, "value": cv} for cv in ALL_CVS],
                        value=ALL_CVS, multi=True, style={"width": "420px"},
                    ),
                ]),
                html.Div([
                    html.Label("Show raw reps", className="filter-label"),
                    dcc.Checklist(id="te-raw",
                                  options=[{"label": "", "value": "y"}],
                                  value=["y"], className="toggle-check"),
                ]),
            ]),
        ]),

        html.Div(className="card", children=[
            html.H3("Time Series — mean ± SE", className="card-title"),
            dcc.Graph(id="te-ts", config={"displayModeBar": "hover"}),
        ]),

        html.Div(className="card", children=[
            html.H3("Distribution by Date", className="card-title"),
            html.P("Diamond = cultivar mean. Each dot = one replicate plant.",
                   className="card-subtitle"),
            dcc.Graph(id="te-strip", config={"displayModeBar": "hover"}),
        ]),
    ]),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(Output("te-ts", "figure"),
          Input("te-trait", "value"), Input("te-cvs", "value"), Input("te-raw", "value"))
def upd_ts(trait, cvs, raw):
    return _timeseries(cache.df_clean, trait or TRAIT_COLS[0], cvs or ALL_CVS, bool(raw))


@callback(Output("te-strip", "figure"),
          Input("te-trait", "value"), Input("te-cvs", "value"))
def upd_strip(trait, cvs):
    return _strip(cache.df_clean, trait or TRAIT_COLS[0], cvs or ALL_CVS)
