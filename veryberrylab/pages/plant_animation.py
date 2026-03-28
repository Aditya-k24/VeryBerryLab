"""
pages/plant_animation.py
========================
Page 5 — Plant Animation

A stylised SVG-like Plotly figure that summarises a cultivar's plant architecture
at a selected measurement date:

  Crown:           filled circle, size ∝ crown_diameter_mm
  Primary stolons: lines radiating from crown,
                   count = n_stolon_primary, length ∝ stolon_length_primary_cm
  Secondary stolons: short branches off each primary (count shared from n_stolon_secondary)
  Daughter plants: small circles at stolon tips and secondary nodes
  Flowers:         yellow stars scattered near crown

The figure is labelled as a VISUAL SUMMARY and shows exact numeric values
beside the graphic so the animation never becomes "handwavy".

Interaction:
  • Cultivar dropdown
  • Date slider (snaps to measurement dates for that cultivar)
  • Cross-cultivar mean toggle
"""

import math

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, ctx, dcc, html
from dash.exceptions import PreventUpdate

import src.data_cache as cache
from src.etl import BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_LABELS

dash.register_page(__name__, path="/plant-animation", name="Plant Animation", order=4)

PALETTE = [
    "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2",
    "#D55E00", "#CC79A7", "#000000", "#AA4499", "#44BB99", "#BBCC33",
]
ALL_CULTIVARS = sorted(BATCH_A | BATCH_B)
CV_COLOR = {cv: PALETTE[i] for i, cv in enumerate(ALL_CULTIVARS)}

# Animation canvas dimensions
XRANGE = (-3.5, 3.5)
YRANGE = (-3.5, 3.5)


# ---------------------------------------------------------------------------
# Plant figure builder
# ---------------------------------------------------------------------------

def _plant_fig(cultivar: str, date_str: str, df: pd.DataFrame, show_mean: bool) -> go.Figure:
    date_ts = pd.Timestamp(date_str)

    if show_mean:
        # Use cross-cultivar mean (all cultivars scheduled on this date)
        sub = df[df["date"] == date_ts][TRAIT_COLS]
        row = sub.mean()
        title_label = f"Cross-cultivar mean — {date_ts.strftime('%d %b %Y')}"
        crown_color = "#888888"
    else:
        sub = df[(df["cultivar"] == cultivar) & (df["date"] == date_ts)][TRAIT_COLS]
        if sub.empty:
            return _empty_fig(f"No data for {cultivar} on {date_ts.strftime('%d %b %Y')}")
        row = sub.mean()
        title_label = f"{cultivar} — {date_ts.strftime('%d %b %Y')}"
        crown_color = CV_COLOR.get(cultivar, "#888")

    # Extract values (with safe defaults)
    def safe(col, default=0.0):
        v = row.get(col, default)
        return default if pd.isna(v) else float(v)

    crown_diam   = safe("crown_diameter_mm", 20.0)
    n_prim       = max(0, round(safe("n_stolon_primary")))
    stolon_len   = max(0.5, safe("stolon_length_primary_cm", 10.0))
    n_sec        = max(0, round(safe("n_stolon_secondary")))
    n_dp_alt     = max(0, round(safe("n_dp_total_alt")))
    n_dp_mid     = max(0, round(safe("n_dp_total_mid")))
    n_flowers    = max(0, round(safe("n_flowers_total")))

    # Normalise
    crown_r     = max(0.15, crown_diam / 200.0)   # mm → plot units
    stolon_len_u = min(2.5, stolon_len / 20.0)     # cm → plot units

    fig = go.Figure()

    # ── Primary stolons ───────────────────────────────────────────────────
    angle_spread = math.pi * 0.75  # stolons spread across 135° on each side
    angles = []
    if n_prim > 0:
        if n_prim == 1:
            angles = [0.0]
        else:
            half = angle_spread / 2
            angles = list(np.linspace(-half, half, n_prim))

    dp_alt_placed = 0
    dp_mid_placed = 0

    for prim_idx, angle in enumerate(angles):
        x_tip = math.cos(angle) * stolon_len_u
        y_tip = math.sin(angle) * stolon_len_u

        # Primary stolon line
        fig.add_trace(go.Scatter(
            x=[0, x_tip], y=[0, y_tip],
            mode="lines",
            line=dict(color="#5a8a3a", width=3),
            showlegend=False,
            hoverinfo="skip",
        ))

        # Alternate-node daughter plant at tip
        if dp_alt_placed < n_dp_alt:
            fig.add_trace(go.Scatter(
                x=[x_tip], y=[y_tip],
                mode="markers",
                marker=dict(size=14, color="#2d7a45", symbol="circle",
                            line=dict(width=1.5, color="white")),
                showlegend=False,
                hovertemplate="Daughter plant (alt node)<extra></extra>",
            ))
            dp_alt_placed += 1

        # Secondary stolons branching off this primary
        n_sec_this = n_sec // max(n_prim, 1)
        remainder  = n_sec % max(n_prim, 1)
        if prim_idx < remainder:
            n_sec_this += 1

        for sec_i in range(n_sec_this):
            # Branch at midpoint of primary stolon
            frac = 0.45 + 0.12 * sec_i
            bx = math.cos(angle) * stolon_len_u * frac
            by = math.sin(angle) * stolon_len_u * frac
            # Branch angle: perpendicular to primary
            branch_angle = angle + math.pi / 2 * (1 if sec_i % 2 == 0 else -1)
            sec_len = stolon_len_u * 0.45
            sec_tx = bx + math.cos(branch_angle) * sec_len
            sec_ty = by + math.sin(branch_angle) * sec_len

            fig.add_trace(go.Scatter(
                x=[bx, sec_tx], y=[by, sec_ty],
                mode="lines",
                line=dict(color="#7cb87c", width=2),
                showlegend=False,
                hoverinfo="skip",
            ))

            # Mid-node daughter plant at secondary tip
            if dp_mid_placed < n_dp_mid:
                fig.add_trace(go.Scatter(
                    x=[sec_tx], y=[sec_ty],
                    mode="markers",
                    marker=dict(size=11, color="#56B4E9", symbol="circle",
                                line=dict(width=1.5, color="white")),
                    showlegend=False,
                    hovertemplate="Daughter plant (mid node)<extra></extra>",
                ))
                dp_mid_placed += 1

    # ── Crown ─────────────────────────────────────────────────────────────
    fig.add_shape(type="circle",
        x0=-crown_r, y0=-crown_r, x1=crown_r, y1=crown_r,
        fillcolor=crown_color,
        line_color="white",
        line_width=2,
        opacity=0.9)

    # ── Flowers ───────────────────────────────────────────────────────────
    if n_flowers > 0:
        flower_r = crown_r * 1.4
        f_count  = min(n_flowers, 24)
        f_angles = np.linspace(0, 2 * math.pi, f_count, endpoint=False)
        fx = [flower_r * math.cos(a) * (0.8 + 0.4 * (i % 3 == 0)) for i, a in enumerate(f_angles)]
        fy = [flower_r * math.sin(a) * (0.8 + 0.4 * (i % 3 == 0)) for i, a in enumerate(f_angles)]
        fig.add_trace(go.Scatter(
            x=fx, y=fy,
            mode="markers",
            marker=dict(size=9, color="#FFD700", symbol="star",
                        line=dict(width=1, color="#FFA000")),
            showlegend=False,
            hovertemplate="Flower<extra></extra>",
        ))

    # ── Layout ────────────────────────────────────────────────────────────
    fig.update_layout(
        title=dict(text=f"<b>{title_label}</b><br>"
                        f"<sup>Visual summary — values below are exact</sup>",
                   x=0.5, xanchor="center",
                   font=dict(size=14)),
        height=440,
        margin=dict(l=20, r=20, t=70, b=20),
        plot_bgcolor="#f0f7ee",
        paper_bgcolor="white",
        xaxis=dict(range=XRANGE, showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y"),
        yaxis=dict(range=YRANGE, showgrid=False, zeroline=False, visible=False),
        font=dict(family="Inter, sans-serif", size=12),
        hovermode="closest",
    )
    return fig


def _empty_fig(msg="No data"):
    fig = go.Figure()
    fig.update_layout(
        height=360,
        plot_bgcolor="#f0f7ee", paper_bgcolor="white",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        annotations=[dict(text=msg, x=0.5, y=0.5, xref="paper", yref="paper",
                          showarrow=False, font=dict(size=14, color="#888"))],
    )
    return fig


def _values_table(cultivar, date_str, df, show_mean):
    date_ts = pd.Timestamp(date_str)
    if show_mean:
        sub = df[df["date"] == date_ts][TRAIT_COLS]
        row = sub.mean()
    else:
        sub = df[(df["cultivar"] == cultivar) & (df["date"] == date_ts)][TRAIT_COLS]
        if sub.empty:
            return html.Div("No data.")
        row = sub.mean()

    display_traits = [
        "crown_diameter_mm", "n_stolon_primary", "stolon_length_primary_cm",
        "n_stolon_secondary", "n_stolon_tertiary",
        "n_dp_total_alt", "n_dp_total_mid",
        "n_flowers_total", "n_flowers_mp", "n_flowers_dp",
    ]

    table_rows = []
    for t in display_traits:
        v = row.get(t, np.nan)
        v_str = f"{v:.1f}" if pd.notna(v) else "—"
        table_rows.append(html.Tr([
            html.Td(TRAIT_LABELS.get(t, t), className="vals-label"),
            html.Td(v_str, className="vals-value"),
        ]))

    return html.Table(className="values-table", children=[
        html.Thead(html.Tr([html.Th("Trait"), html.Th("Mean")])),
        html.Tbody(table_rows),
    ])


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Plant Animation", className="page-title"),
        html.P("Stylised plant architecture driven by measured trait values. "
               "Exact measurements are shown in the table beside the figure.",
               className="page-subtitle"),
    ]),
    html.Div(className="content-area", children=[

        # Controls
        html.Div(className="card filter-card", children=[
            html.Div(className="filter-row", children=[
                html.Div([
                    html.Label("Cultivar", className="filter-label"),
                    dcc.Dropdown(
                        id="pa-cultivar",
                        options=[{"label": cv, "value": cv} for cv in ALL_CULTIVARS],
                        value=ALL_CULTIVARS[0],
                        clearable=False,
                        style={"width": "200px"},
                    ),
                ]),
                html.Div([
                    html.Label("Show cross-cultivar mean instead", className="filter-label"),
                    dcc.Checklist(
                        id="pa-show-mean",
                        options=[{"label": "", "value": "mean"}],
                        value=[],
                        className="toggle-check",
                    ),
                ]),
            ]),
            html.Div(style={"marginTop": "16px"}, children=[
                html.Div(style={"display": "flex", "alignItems": "center", "gap": "10px", "marginBottom": "8px"}, children=[
                    html.Label("Date:", className="filter-label", style={"margin": "0"}),
                    html.Button("▶ Play", id="pa-play-btn", n_clicks=0,
                                className="btn btn-primary",
                                style={"padding": "5px 14px", "fontSize": "12px"}),
                ]),
                html.Div(id="pa-slider-container"),
            ]),
        ]),

        # Main layout: figure + values table
        html.Div(className="pa-main-row", children=[
            html.Div(className="pa-fig-col card", children=[
                dcc.Graph(id="pa-figure", config={"displayModeBar": False}),
                html.P(
                    "⚠ This is a schematic diagram. "
                    "Stolon positions are evenly spaced for clarity, not anatomically exact.",
                    className="disclaimer",
                ),
            ]),
            html.Div(className="pa-vals-col card", children=[
                html.H3("Measured Values", className="card-title"),
                html.P("Cultivar mean across 3 replicates on this date.",
                       className="card-subtitle"),
                html.Div(id="pa-values"),
            ]),
        ]),
    ]),
    dcc.Interval(id="pa-interval", interval=1500, disabled=True, n_intervals=0),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("pa-slider-container", "children"),
    Input("pa-cultivar", "value"),
    Input("pa-show-mean", "value"),
)
def build_slider(cultivar, show_mean_flag):
    df = cache.df_clean
    show_mean = "mean" in (show_mean_flag or [])

    if show_mean:
        dates = sorted(df["date"].unique())
    else:
        dates = sorted(df[df["cultivar"] == cultivar]["date"].unique())

    if not dates:
        return html.P("No dates available.")

    marks = {i: pd.Timestamp(d).strftime("%d %b") for i, d in enumerate(dates)}
    return dcc.Slider(
        id="pa-date-slider",
        min=0, max=len(dates) - 1, step=1,
        value=0,
        marks=marks,
        included=False,
    )


@callback(
    Output("pa-interval", "disabled"),
    Output("pa-play-btn", "children"),
    Input("pa-play-btn", "n_clicks"),
    State("pa-interval", "disabled"),
    prevent_initial_call=True,
)
def toggle_play(_, is_disabled):
    playing = is_disabled  # was disabled → now playing
    return not playing, ("⏸ Pause" if playing else "▶ Play")


@callback(
    Output("pa-date-slider", "value", allow_duplicate=True),
    Input("pa-interval", "n_intervals"),
    State("pa-date-slider", "value"),
    State("pa-date-slider", "max"),
    prevent_initial_call=True,
)
def advance_slide(_, current, max_val):
    cur = current or 0
    nxt = cur + 1
    return 0 if nxt > (max_val or 0) else nxt


@callback(
    Output("pa-figure", "figure"),
    Output("pa-values", "children"),
    Input("pa-cultivar",    "value"),
    Input("pa-date-slider", "value"),
    Input("pa-show-mean",   "value"),
)
def update_plant(cultivar, date_idx, show_mean_flag):
    df = cache.df_clean
    show_mean = "mean" in (show_mean_flag or [])

    if show_mean:
        dates = sorted(df["date"].unique())
    else:
        dates = sorted(df[df["cultivar"] == cultivar]["date"].unique())

    if not dates or date_idx is None:
        return _empty_fig("No dates available."), html.Div()

    date_idx = min(date_idx, len(dates) - 1)
    date_str = str(dates[date_idx])[:10]

    fig    = _plant_fig(cultivar, date_str, df, show_mean)
    values = _values_table(cultivar, date_str, df, show_mean)
    return fig, values
