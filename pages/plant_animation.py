"""
pages/plant_animation.py — Page 5: Plant Animation

Stylised plant figure driven by measured trait values.
Cultivar selector + date slider + cross-cultivar mean toggle.
Exact numeric values shown beside the graphic.
"""

import math

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

import src.data_cache as cache
from src.etl import BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_LABELS

dash.register_page(__name__, path="/plant-animation", name="Plant Animation", order=4)

PALETTE  = ["#E69F00","#56B4E9","#009E73","#F0E442","#0072B2",
            "#D55E00","#CC79A7","#000000","#AA4499","#44BB99","#BBCC33"]
ALL_CVS  = sorted(BATCH_A | BATCH_B)
CV_COLOR = {cv: PALETTE[i] for i, cv in enumerate(ALL_CVS)}


# ---------------------------------------------------------------------------
# Plant figure
# ---------------------------------------------------------------------------

def _plant(cultivar: str, date_str: str, df: pd.DataFrame, mean_mode: bool) -> go.Figure:
    date_ts = pd.Timestamp(date_str)

    if mean_mode:
        sub = df[df["date"] == date_ts][TRAIT_COLS]
        row = sub.mean()
        title   = f"Cross-cultivar mean — {date_ts.strftime('%d %b %Y')}"
        c_color = "#888888"
    else:
        sub = df[(df["cultivar"] == cultivar) & (df["date"] == date_ts)][TRAIT_COLS]
        if sub.empty:
            return _empty(f"No data for {cultivar} on {date_ts.strftime('%d %b %Y')}")
        row     = sub.mean()
        title   = f"{cultivar} — {date_ts.strftime('%d %b %Y')}"
        c_color = CV_COLOR.get(cultivar, "#888")

    def safe(col, default=0.0):
        v = row.get(col, default)
        return default if pd.isna(v) else float(v)

    crown_diam  = safe("crown_diameter_mm",    20.0)
    n_prim      = max(0, round(safe("n_stolon_primary")))
    stolon_len  = max(0.5, safe("stolon_length_primary_cm", 10.0))
    n_sec       = max(0, round(safe("n_stolon_secondary")))
    n_dp_alt    = max(0, round(safe("n_dp_total_alt")))
    n_dp_mid    = max(0, round(safe("n_dp_total_mid")))
    n_flowers   = max(0, round(safe("n_flowers_total")))

    crown_r    = max(0.15, crown_diam / 200.0)
    stolon_u   = min(2.6,  stolon_len / 20.0)

    fig = go.Figure()

    # Ground strip
    fig.add_shape(type="rect", x0=-3.5, x1=3.5, y0=-0.28, y1=-0.50,
                  fillcolor="#c8a96e", line_color="#a08050", line_width=1)

    # Primary stolons
    spread = math.pi * 0.75
    angles = ([0.0] if n_prim == 1
              else list(np.linspace(-spread / 2, spread / 2, n_prim)) if n_prim > 1
              else [])

    dp_alt_done = 0
    dp_mid_done = 0

    for pi, ang in enumerate(angles):
        xt = math.cos(ang) * stolon_u
        yt = math.sin(ang) * stolon_u

        fig.add_trace(go.Scatter(
            x=[0, xt], y=[0, yt], mode="lines",
            line=dict(color="#5a8a3a", width=3),
            showlegend=False, hoverinfo="skip",
        ))

        # Alternate-node daughter at tip
        if dp_alt_done < n_dp_alt:
            fig.add_trace(go.Scatter(
                x=[xt], y=[yt], mode="markers",
                marker=dict(size=14, color="#2d7a45", symbol="circle",
                            line=dict(width=1.5, color="white")),
                showlegend=False,
                hovertemplate="Daughter plant (alt node)<extra></extra>",
            ))
            dp_alt_done += 1

        # Secondary stolons
        n_sec_this = n_sec // max(n_prim, 1) + (1 if pi < (n_sec % max(n_prim, 1)) else 0)
        for si in range(n_sec_this):
            frac = 0.45 + 0.12 * si
            bx   = math.cos(ang) * stolon_u * frac
            by   = math.sin(ang) * stolon_u * frac
            bang = ang + math.pi / 2 * (1 if si % 2 == 0 else -1)
            sl   = stolon_u * 0.45
            stx  = bx + math.cos(bang) * sl
            sty  = by + math.sin(bang) * sl

            fig.add_trace(go.Scatter(
                x=[bx, stx], y=[by, sty], mode="lines",
                line=dict(color="#7cb87c", width=2),
                showlegend=False, hoverinfo="skip",
            ))

            if dp_mid_done < n_dp_mid:
                fig.add_trace(go.Scatter(
                    x=[stx], y=[sty], mode="markers",
                    marker=dict(size=11, color="#56B4E9", symbol="circle",
                                line=dict(width=1.5, color="white")),
                    showlegend=False,
                    hovertemplate="Daughter plant (mid node)<extra></extra>",
                ))
                dp_mid_done += 1

    # Crown
    fig.add_shape(type="circle",
        x0=-crown_r, y0=-crown_r, x1=crown_r, y1=crown_r,
        fillcolor=c_color, line_color="white", line_width=2, opacity=0.9)

    # Flowers
    if n_flowers > 0:
        fc   = min(n_flowers, 24)
        fang = np.linspace(0, 2 * math.pi, fc, endpoint=False)
        fr   = crown_r * 1.4
        fx   = [fr * math.cos(a) * (0.8 + 0.4 * (i % 3 == 0)) for i, a in enumerate(fang)]
        fy   = [fr * math.sin(a) * (0.8 + 0.4 * (i % 3 == 0)) for i, a in enumerate(fang)]
        fig.add_trace(go.Scatter(
            x=fx, y=fy, mode="markers",
            marker=dict(size=9, color="#FFD700", symbol="star",
                        line=dict(width=1, color="#FFA000")),
            showlegend=False,
            hovertemplate="Flower<extra></extra>",
        ))

    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b><br><sup>Visual summary — exact values in table</sup>",
            x=0.5, xanchor="center", font=dict(size=14),
        ),
        height=440, margin=dict(l=20, r=20, t=70, b=20),
        plot_bgcolor="#f0f7ee", paper_bgcolor="white",
        xaxis=dict(range=[-3.5, 3.5], visible=False, scaleanchor="y"),
        yaxis=dict(range=[-3.5, 3.5], visible=False),
        font=dict(family="Inter, sans-serif", size=12),
        hovermode="closest",
    )
    return fig


def _empty(msg="No data"):
    fig = go.Figure()
    fig.update_layout(
        height=360, plot_bgcolor="#f0f7ee", paper_bgcolor="white",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        annotations=[dict(text=msg, x=0.5, y=0.5, xref="paper", yref="paper",
                          showarrow=False, font=dict(size=14, color="#888"))],
    )
    return fig


def _values_table(cultivar, date_str, df, mean_mode):
    date_ts = pd.Timestamp(date_str)
    if mean_mode:
        row = df[df["date"] == date_ts][TRAIT_COLS].mean()
    else:
        sub = df[(df["cultivar"] == cultivar) & (df["date"] == date_ts)][TRAIT_COLS]
        if sub.empty:
            return html.Div("No data.")
        row = sub.mean()

    shown = ["crown_diameter_mm", "n_stolon_primary", "stolon_length_primary_cm",
             "n_stolon_secondary", "n_stolon_tertiary",
             "n_dp_total_alt", "n_dp_total_mid",
             "n_flowers_total", "n_flowers_mp", "n_flowers_dp"]

    return html.Table(className="vals-table", children=[
        html.Thead(html.Tr([html.Th("Trait"), html.Th("Mean")])),
        html.Tbody([
            html.Tr([
                html.Td(TRAIT_LABELS.get(t, t), className="vals-lbl"),
                html.Td(f"{row.get(t, float('nan')):.1f}"
                        if pd.notna(row.get(t)) else "—",
                        className="vals-val"),
            ]) for t in shown
        ]),
    ])


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Plant Animation", className="page-title"),
        html.P("Schematic plant architecture scaled to measured trait values. "
               "Exact measurements shown in the table.",
               className="page-subtitle"),
    ]),
    html.Div(className="content-area", children=[

        html.Div(className="card filter-card", children=[
            html.Div(className="filter-row", children=[
                html.Div([
                    html.Label("Cultivar", className="filter-label"),
                    dcc.Dropdown(
                        id="pa-cv", options=[{"label": cv, "value": cv} for cv in ALL_CVS],
                        value=ALL_CVS[0], clearable=False, style={"width": "200px"},
                    ),
                ]),
                html.Div([
                    html.Label("Cross-cultivar mean", className="filter-label"),
                    dcc.Checklist(id="pa-mean",
                                  options=[{"label": "", "value": "y"}],
                                  value=[], className="toggle-check"),
                ]),
            ]),
            html.Div(style={"marginTop": "14px"}, children=[
                html.Label("Date:", className="filter-label"),
                html.Div(id="pa-slider-wrap"),
            ]),
        ]),

        html.Div(className="pa-row", children=[
            html.Div(className="pa-fig card", children=[
                dcc.Graph(id="pa-fig", config={"displayModeBar": False}),
                html.P("⚠ Schematic only — stolon positions evenly spaced for clarity.",
                       className="disclaimer"),
            ]),
            html.Div(className="pa-vals card", children=[
                html.H3("Measured Values", className="card-title"),
                html.P("Cultivar mean across replicates on this date.",
                       className="card-subtitle"),
                html.Div(id="pa-vals"),
            ]),
        ]),
    ]),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(Output("pa-slider-wrap", "children"),
          Input("pa-cv", "value"), Input("pa-mean", "value"))
def build_slider(cv, mean_flag):
    df = cache.df_clean
    dates = (sorted(df["date"].unique()) if "y" in (mean_flag or [])
             else sorted(df[df["cultivar"] == cv]["date"].unique()))
    if not dates:
        return html.P("No dates available.")
    marks = {i: pd.Timestamp(d).strftime("%d %b") for i, d in enumerate(dates)}
    return dcc.Slider(id="pa-slider", min=0, max=len(dates) - 1, step=1,
                      value=len(dates) - 1, marks=marks, included=False)


@callback(Output("pa-fig", "figure"), Output("pa-vals", "children"),
          Input("pa-cv", "value"), Input("pa-slider", "value"),
          Input("pa-mean", "value"))
def upd_plant(cv, idx, mean_flag):
    df   = cache.df_clean
    mean_mode = "y" in (mean_flag or [])
    dates = (sorted(df["date"].unique()) if mean_mode
             else sorted(df[df["cultivar"] == cv]["date"].unique()))
    if not dates or idx is None:
        return _empty(), html.Div()
    idx      = min(idx, len(dates) - 1)
    date_str = str(dates[idx])[:10]
    return _plant(cv, date_str, df, mean_mode), _values_table(cv, date_str, df, mean_mode)
