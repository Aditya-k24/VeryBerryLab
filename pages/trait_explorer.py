"""
pages/trait_explorer.py — Page 2: Trait Explorer  (publication-grade rebuild)

Two figures for any trait:
  A) Time series — cultivar mean ± SE over the season. Batch A = solid,
     Batch B = dashed (the two cohorts are measured on interleaved weekly-offset
     schedules; there is NO sequential A→B split). Lines are continuous over
     each cultivar's own six measurement dates.
  B) Distribution by date — the three replicate plants per cultivar per date,
     with the cultivar mean ± SE, honest for n = 3.

Single-timepoint traits (e.g. crown diameter, recorded once at season end) are
rendered as an endpoint bar chart instead of a meaningless one-point line.

Every figure is styled for print and downloadable as hi-res PNG or vector SVG.
"""

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, clientside_callback, dcc, html
from plotly.subplots import make_subplots

import src.data_cache as cache
from src.etl import BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_LABELS

dash.register_page(__name__, path="/trait-explorer", name="Trait Explorer", order=1)

# ── Cultivar colours (colourblind-aware, legible on white) ────────────────────
# Batch A gets one set, Batch B another; combined with solid/dashed line style
# every cultivar is distinguishable to colour-vision-deficient readers too.
CV_COLOR = {
    # Batch A
    "Albion":   "#0072B2", "Cabrio": "#009E73", "Camarosa": "#D55E00",
    "Chandler": "#CC79A7", "Finn":   "#8C510A", "Sensation": "#7A7500",
    # Batch B
    "Brilliance": "#E69F00", "Moxie": "#E7298A", "Portola": "#111111",
    "Radiance":   "#7B3FA0", "Ruby June": "#56B4E9",
}
ALL_CVS = sorted(BATCH_A | BATCH_B)
# order: batch A first, then batch B (so the grouped legend reads A then B)
ORDERED_CVS = sorted(BATCH_A) + sorted(BATCH_B)

UNIT = {"stolon_length_primary_cm": "cm", "crown_diameter_mm": "mm"}

A_LABEL = "Batch A"
B_LABEL = "Batch B"

# Publication export config — vector SVG by default, high-res if PNG chosen.
_PUB_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "toImageButtonOptions": {"format": "svg", "filename": "trait_figure", "scale": 2},
}


def _batch(cv):
    return "A" if cv in BATCH_A else "B"


def _rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _y_title(trait):
    # TRAIT_LABELS already carry units where relevant (e.g. "… (cm)"), so just
    # use the label — appending UNIT again would double it.
    return TRAIT_LABELS.get(trait, trait)


def _pub_layout(fig, y_title, *, title=None, x_title="Measurement date",
                height=560, legend=True):
    fig.update_layout(
        template="simple_white",
        height=height,
        margin=dict(l=76, r=196 if legend else 34, t=54 if title else 26, b=58),
        font=dict(family="IBM Plex Sans, Helvetica, Arial, sans-serif", size=13, color="#222"),
        title=(dict(text=title, x=0.0, xanchor="left",
                    font=dict(size=16, color="#111")) if title else None),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(title=dict(text=x_title, font=dict(size=13)),
                   showgrid=False, ticks="outside", ticklen=5,
                   linecolor="#333", tickcolor="#333", tickfont=dict(size=12)),
        yaxis=dict(title=dict(text=y_title, font=dict(size=13)),
                   showgrid=True, gridcolor="#eef0f2", zeroline=False,
                   ticks="outside", ticklen=5, linecolor="#333",
                   tickcolor="#333", tickfont=dict(size=12)),
        hovermode="closest",
    )
    if legend:
        fig.update_layout(legend=dict(
            x=1.01, y=1, xanchor="left", yanchor="top",
            font=dict(size=12), groupclick="toggleitem",
            tracegroupgap=8, bordercolor="#e6e8ec", borderwidth=1,
        ))
    return fig


def _agg(df, cv, trait):
    """mean, SE, n per date for one cultivar (observed values only)."""
    sub = df[df["cultivar"] == cv][["date", trait]].dropna(subset=[trait])
    if sub.empty:
        return None
    g = sub.groupby("date")[trait].agg(
        mean="mean",
        se=lambda x: x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0,
        n="count",
    ).reset_index().sort_values("date")
    return g


def _n_timepoints(df, trait):
    s = df.dropna(subset=[trait])
    if s.empty:
        return 0
    return int(s.groupby("cultivar")["date"].nunique().max())


# ───────────────────────────────────────────────────────────────────────────
# A) Time series
# ───────────────────────────────────────────────────────────────────────────

def _timeseries(df, trait, cvs, err_style, show_raw, show_title):
    """Faceted growth curves — one panel per cohort (Batch A | Batch B), all
    solid lines on a shared y-axis. The two cohorts are measured on different
    (offset) dates, so separate panels are both cleaner and more honest than
    overlaying eleven solid/dashed lines on one axis."""
    a_cvs = [c for c in sorted(BATCH_A) if c in cvs]
    b_cvs = [c for c in sorted(BATCH_B) if c in cvs]
    panels = [p for p in [("A", A_LABEL, a_cvs), ("B", B_LABEL, b_cvs)] if p[2]]

    if not panels:
        fig = go.Figure()
        fig.add_annotation(text="No cultivars selected.", x=0.5, y=0.5,
                           xref="paper", yref="paper", showarrow=False,
                           font=dict(size=14, color="#888"))
        return _pub_layout(fig, _y_title(trait), legend=False, height=520)

    ncols = len(panels)
    fig = make_subplots(rows=1, cols=ncols, shared_yaxes=True,
                        horizontal_spacing=0.045,
                        subplot_titles=[p[1] for p in panels])

    for ci, (b, label, cvlist) in enumerate(panels, start=1):
        symbol = "circle" if b == "A" else "square"
        for cv in cvlist:
            g = _agg(df, cv, trait)
            if g is None:
                continue
            color = CV_COLOR.get(cv, "#666")
            xs, ys, se = g["date"].tolist(), g["mean"].tolist(), g["se"].tolist()

            if err_style == "band" and len(xs) > 1:
                yu = [m + s for m, s in zip(ys, se)]
                yd = [m - s for m, s in zip(ys, se)]
                fig.add_trace(go.Scatter(
                    x=xs + xs[::-1], y=yu + yd[::-1], fill="toself",
                    fillcolor=_rgba(color, 0.12), line=dict(color="rgba(0,0,0,0)"),
                    hoverinfo="skip", showlegend=False), row=1, col=ci)

            if show_raw:
                raw = df[df["cultivar"] == cv][["date", trait]].dropna(subset=[trait])
                jit = (np.random.default_rng(abs(hash(cv)) % 2**32)
                       .uniform(-0.16, 0.16, len(raw)) * 86400e3)
                fig.add_trace(go.Scatter(
                    x=(pd.to_datetime(raw["date"]).astype("int64") // 10**6 + jit),
                    y=raw[trait], mode="markers",
                    marker=dict(size=4, color=color, opacity=0.32, line=dict(width=0)),
                    hoverinfo="skip", showlegend=False), row=1, col=ci)

            err = (dict(type="data", array=se, thickness=1.2, width=3, color=color)
                   if err_style == "bars" else None)
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines+markers", name=cv,
                legendgroup=label, legendgrouptitle_text=label,
                line=dict(color=color, width=2.4),
                marker=dict(size=7, color=color, symbol=symbol,
                            line=dict(width=1, color="white")),
                error_y=err,
                customdata=np.stack([np.array(se), g["n"].to_numpy()], axis=-1),
                hovertemplate=(f"<b>{cv}</b> ({label})<br>%{{x|%d %b %Y}}<br>"
                               f"{TRAIT_LABELS.get(trait, trait)}: "
                               "%{y:.2f} ± %{customdata[0]:.2f}<br>"
                               "n = %{customdata[1]}<extra></extra>"),
                ), row=1, col=ci)

    # ── publication layout for the faceted figure ──
    fig.update_layout(
        template="simple_white",
        height=540,
        margin=dict(l=76, r=176, t=54, b=58),
        font=dict(family="IBM Plex Sans, Helvetica, Arial, sans-serif", size=13, color="#222"),
        title=(dict(text=_y_title(trait), x=0.0, xanchor="left",
                    font=dict(size=16, color="#111")) if show_title else None),
        plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(x=1.01, y=1, xanchor="left", yanchor="top",
                    font=dict(size=12), groupclick="toggleitem", tracegroupgap=8,
                    bordercolor="#e6e8ec", borderwidth=1),
        hovermode="closest",
    )
    fig.update_xaxes(title=dict(text="Measurement date", font=dict(size=12)),
                     tickformat="%d %b", dtick=14 * 86400e3, showgrid=False,
                     ticks="outside", ticklen=5, linecolor="#333",
                     tickcolor="#333", tickfont=dict(size=11))
    fig.update_yaxes(showgrid=True, gridcolor="#eef0f2", zeroline=False,
                     rangemode="tozero", ticks="outside", ticklen=5,
                     linecolor="#333", tickcolor="#333", tickfont=dict(size=12))
    fig.update_yaxes(title=dict(text=_y_title(trait), font=dict(size=13)),
                     row=1, col=1)
    for ann in fig.layout.annotations:      # panel titles
        ann.font = dict(size=13, color="#111")
    return fig


def _endpoint_bar(df, trait, cvs, show_title):
    """Single-timepoint traits → sorted mean ± SE bar (one bar per cultivar)."""
    cvs_ord = [c for c in ORDERED_CVS if c in cvs]
    rows = []
    for cv in cvs_ord:
        g = _agg(df, cv, trait)
        if g is None:
            continue
        r = g.iloc[-1]
        rows.append((cv, r["date"], r["mean"], r["se"], int(r["n"])))
    if not rows:
        fig = go.Figure()
        fig.add_annotation(text="No cultivars selected.", x=0.5, y=0.5,
                           xref="paper", yref="paper", showarrow=False,
                           font=dict(size=14, color="#888"))
        return _pub_layout(fig, _y_title(trait), legend=False, height=460)

    rows.sort(key=lambda rr: rr[2], reverse=True)
    fig = go.Figure(go.Bar(
        x=[r[0] for r in rows], y=[r[2] for r in rows],
        marker=dict(color=[CV_COLOR.get(r[0], "#666") for r in rows],
                    line=dict(width=0)),
        error_y=dict(type="data", array=[r[3] for r in rows],
                     thickness=1.3, width=5, color="#333"),
        customdata=[[r[3], r[4], pd.Timestamp(r[1]).strftime("%d %b %Y")]
                    for r in rows],
        hovertemplate=("<b>%{x}</b><br>%{y:.2f} ± %{customdata[0]:.2f} "
                       f"{UNIT.get(trait,'')}<br>n = %{{customdata[1]}} · "
                       "%{customdata[2]}<extra></extra>"),
    ))
    title = _y_title(trait) if show_title else None
    _pub_layout(fig, _y_title(trait), title=title, x_title="Cultivar",
                legend=False, height=460)
    fig.update_yaxes(rangemode="tozero")
    return fig


# ───────────────────────────────────────────────────────────────────────────
# B) Distribution by date (replicate spread)
# ───────────────────────────────────────────────────────────────────────────

def _distribution(df, trait, cvs):
    dates = sorted(df[df["cultivar"].isin(cvs)]["date"].unique())
    if not dates:
        return go.Figure()

    cols = min(6, len(dates))
    rows = (len(dates) + cols - 1) // cols
    titles = [pd.Timestamp(d).strftime("%d %b") for d in dates]
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=titles,
                        horizontal_spacing=0.05, vertical_spacing=0.14)

    for i, date in enumerate(dates):
        r, c = i // cols + 1, i % cols + 1
        day = df[(df["date"] == date) & (df["cultivar"].isin(cvs))]
        present = [cv for cv in ORDERED_CVS
                   if day[day["cultivar"] == cv][trait].notna().any()]
        for j, cv in enumerate(present):
            vals = day[day["cultivar"] == cv][trait].dropna().tolist()
            color = CV_COLOR.get(cv, "#666")
            oy = np.linspace(-0.22, 0.22, len(vals)) if len(vals) > 1 else [0.0]
            m = float(np.mean(vals))
            se = float(np.std(vals, ddof=1) / np.sqrt(len(vals))) if len(vals) > 1 else 0.0
            # SE whisker
            fig.add_trace(go.Scatter(
                x=[m - se, m + se], y=[j, j], mode="lines",
                line=dict(color=color, width=2), showlegend=False,
                hoverinfo="skip"), row=r, col=c)
            # replicate dots
            fig.add_trace(go.Scatter(
                x=vals, y=[j + o for o in oy], mode="markers",
                marker=dict(size=6, color=color, opacity=0.75,
                            line=dict(width=0.6, color="white")),
                showlegend=False,
                hovertemplate=f"<b>{cv}</b>: %{{x:.2f}}<extra></extra>",
                ), row=r, col=c)
            # mean diamond
            fig.add_trace(go.Scatter(
                x=[m], y=[j], mode="markers",
                marker=dict(size=11, color=color, symbol="diamond",
                            line=dict(width=1.2, color="white")),
                showlegend=False,
                hovertemplate=f"<b>{cv}</b> mean: %{{x:.2f}} (n={len(vals)})<extra></extra>",
                ), row=r, col=c)
        fig.update_yaxes(tickvals=list(range(len(present))), ticktext=present,
                         tickfont=dict(size=10), row=r, col=c,
                         showgrid=False, autorange="reversed")
        fig.update_xaxes(showgrid=True, gridcolor="#eef0f2", ticks="outside",
                         ticklen=4, tickfont=dict(size=10), row=r, col=c)

    fig.update_layout(
        template="simple_white",
        height=max(300, rows * 240),
        margin=dict(l=96, r=24, t=44, b=44),
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
        font=dict(family="IBM Plex Sans, Helvetica, Arial, sans-serif", size=11, color="#222"),
    )
    for ann in fig.layout.annotations:      # subplot titles
        ann.font = dict(size=12, color="#111")
    return fig


def _caption(df, trait):
    single = _n_timepoints(df, trait) <= 1
    if single:
        return ("Endpoint comparison — this trait was recorded once, at the end "
                "of each cohort's season. Bars are cultivar mean ± SE of n = 3 "
                "replicate plants; error bars = standard error.")
    return ("Mean ± standard error of n = 3 replicate plants per cultivar on each "
            "measurement date. Batch A (●) and Batch B (■) are separate cohorts "
            "measured on a one-week-offset schedule (A: Apr 16 – Jun 25; "
            "B: Apr 23 – Jul 2), so each is shown in its own panel on a shared "
            "y-axis.")


# ───────────────────────────────────────────────────────────────────────────
# Layout
# ───────────────────────────────────────────────────────────────────────────

def _dl_group(prefix):
    return html.Div(style={"display": "flex", "gap": "8px", "alignItems": "center"},
                    children=[
        html.Span("Download:", style={"fontSize": "11px", "color": "#889",
                                       "fontWeight": "600"}),
        html.Button("PNG", id=f"{prefix}-png", className="btn",
                    style={"padding": "3px 10px", "fontSize": "12px"}),
        html.Button("SVG", id=f"{prefix}-svg", className="btn",
                    style={"padding": "3px 10px", "fontSize": "12px"}),
    ])


layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Trait Explorer", className="page-title"),
        html.P("Season trajectories and replicate spread for any trait — "
               "publication-styled and exportable as PNG or SVG.",
               className="page-subtitle"),
    ]),
    html.Div(className="content-area", children=[

        html.Div(className="card filter-card", children=[
            html.Div(className="filter-row", style={"flexWrap": "wrap", "gap": "18px"},
                     children=[
                html.Div([
                    html.Label("Trait", className="filter-label"),
                    dcc.Dropdown(
                        id="te-trait",
                        options=[{"label": TRAIT_LABELS[t], "value": t} for t in TRAIT_COLS],
                        value="n_stolon_primary", clearable=False,
                        style={"width": "260px"}),
                ]),
                html.Div([
                    html.Label("Cultivars", className="filter-label"),
                    dcc.Dropdown(
                        id="te-cvs",
                        options=[{"label": cv, "value": cv} for cv in ALL_CVS],
                        value=ALL_CVS, multi=True, style={"width": "400px"}),
                ]),
                html.Div([
                    html.Label("Batch", className="filter-label"),
                    dcc.RadioItems(
                        id="te-batch",
                        options=[{"label": " Both", "value": "both"},
                                 {"label": " A", "value": "A"},
                                 {"label": " B", "value": "B"}],
                        value="both", inline=True,
                        inputStyle={"marginRight": "4px", "marginLeft": "10px"}),
                ]),
                html.Div([
                    html.Label("Error", className="filter-label"),
                    dcc.RadioItems(
                        id="te-err",
                        options=[{"label": " SE bars", "value": "bars"},
                                 {"label": " SE band", "value": "band"}],
                        value="bars", inline=True,
                        inputStyle={"marginRight": "4px", "marginLeft": "10px"}),
                ]),
                html.Div([
                    html.Label("Options", className="filter-label"),
                    dcc.Checklist(
                        id="te-opts",
                        options=[{"label": " Raw reps", "value": "raw"},
                                 {"label": " Title on figure", "value": "title"}],
                        value=[], inline=True,
                        inputStyle={"marginRight": "4px", "marginLeft": "10px"}),
                ]),
            ]),
        ]),

        html.Div(className="card", children=[
            html.Div(style={"display": "flex", "justifyContent": "space-between",
                            "alignItems": "center", "flexWrap": "wrap", "gap": "8px"},
                     children=[
                html.H3("Time Series — mean ± SE", className="card-title"),
                _dl_group("te-ts"),
            ]),
            dcc.Graph(id="te-ts", config=_PUB_CONFIG),
            html.P(id="te-ts-cap", className="card-subtitle",
                   style={"marginTop": "6px"}),
        ]),

        html.Div(className="card", children=[
            html.Div(style={"display": "flex", "justifyContent": "space-between",
                            "alignItems": "center", "flexWrap": "wrap", "gap": "8px"},
                     children=[
                html.H3("Distribution by Date", className="card-title"),
                _dl_group("te-dist"),
            ]),
            html.P("Each dot = one replicate plant · diamond = cultivar mean · "
                   "bar = ± SE. Panels are per measurement date (each date belongs "
                   "to a single batch).", className="card-subtitle"),
            dcc.Graph(id="te-dist", config=_PUB_CONFIG),
        ]),

        html.Div(id="te-dl-noop", style={"display": "none"}),
    ]),
])


# ───────────────────────────────────────────────────────────────────────────
# Callbacks
# ───────────────────────────────────────────────────────────────────────────

@callback(
    Output("te-cvs", "value"),
    Input("te-batch", "value"),
    prevent_initial_call=True,
)
def sync_batch(batch):
    if batch == "A":
        return sorted(BATCH_A)
    if batch == "B":
        return sorted(BATCH_B)
    return ALL_CVS


@callback(
    Output("te-ts", "figure"),
    Output("te-ts-cap", "children"),
    Input("te-trait", "value"), Input("te-cvs", "value"),
    Input("te-err", "value"), Input("te-opts", "value"),
)
def upd_ts(trait, cvs, err, opts):
    trait = trait or TRAIT_COLS[0]
    cvs = cvs or ALL_CVS
    show_raw = "raw" in (opts or [])
    show_title = "title" in (opts or [])
    df = cache.df_clean
    if _n_timepoints(df, trait) <= 1:
        fig = _endpoint_bar(df, trait, cvs, show_title)
    else:
        fig = _timeseries(df, trait, cvs, err, show_raw, show_title)
    return fig, _caption(df, trait)


@callback(
    Output("te-dist", "figure"),
    Input("te-trait", "value"), Input("te-cvs", "value"),
)
def upd_dist(trait, cvs):
    return _distribution(cache.df_clean, trait or TRAIT_COLS[0], cvs or ALL_CVS)


# ── Client-side hi-res image download (PNG 3×, or vector SVG) ─────────────────
def _dl_js(graph_id, fmt, name):
    return (
        "function(n){"
        "  if(!n) return '';"
        f"  var gd=document.querySelector('#{graph_id} .js-plotly-plot');"
        "  if(gd && window.Plotly){"
        f"    Plotly.downloadImage(gd,{{format:'{fmt}',"
        f"      filename:'{name}',width:1200,height:700,scale:3}});"
        "  }"
        "  return '';"
        "}"
    )


for _gid, _name in [("te-ts", "trait_timeseries"), ("te-dist", "trait_distribution")]:
    clientside_callback(_dl_js(_gid, "png", _name),
                        Output("te-dl-noop", "children", allow_duplicate=True),
                        Input(f"{_gid}-png", "n_clicks"), prevent_initial_call=True)
    clientside_callback(_dl_js(_gid, "svg", _name),
                        Output("te-dl-noop", "children", allow_duplicate=True),
                        Input(f"{_gid}-svg", "n_clicks"), prevent_initial_call=True)
