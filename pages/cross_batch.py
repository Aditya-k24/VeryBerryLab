"""
pages/cross_batch.py — Page 7: Cross-Batch Longitudinal View

Same statistical engine as all other pages:
  • KW omnibus · ε² effect size · Conover–Iman post-hoc · Holm correction · CLD
  • Dot-plot style identical to Date Compare
  • ε² heatmap identical in style to Season Summary

Three sections:
  1. Extended time axis  — WS2 lines + SE ribbon, batch snapshot markers ±1 SE, CLD annotations
  2. Batch Compare       — sorted dot plot + KW stats panel + pairwise table for a chosen batch
  3. ε² Heatmap          — batch × trait effect-size overview
"""

from __future__ import annotations

import math
import warnings

import dash
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

import src.data_cache as cache
from src.ui import GRAPH_CONFIG
from src.etl import BATCH_A, BATCH_B, TRAIT_COLS, TRAIT_LABELS
from src.merged_etl import MERGED_TRAIT_COLS, MERGED_TRAIT_LABELS
from src.stats import StatsResult, compute_stats_for, sig_label, _cld

dash.register_page(__name__, path="/cross-batch", name="Cross-Batch", order=6)

# ── Palette & cultivar map ────────────────────────────────────────────────────

_PALETTE = [
    "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2",
    "#D55E00", "#CC79A7", "#000000", "#AA4499", "#44BB99",
    "#BBCC33", "#4477AA", "#EE6677",
]
_WS2_CVS = sorted(BATCH_A | BATCH_B)
_NEW_CVS = ["Monterey", "Fronteras"]
_ALL_CVS = _WS2_CVS + _NEW_CVS
CV_COLOR = {cv: _PALETTE[i % len(_PALETTE)] for i, cv in enumerate(_ALL_CVS)}

_BATCH_ORDER  = ["Pheno 1", "Pheno 2", "Pheno 3", "Pheno 4", "Pheno 5"]
_BATCH_SYMBOL = {
    "Pheno 1": "square",
    "Pheno 2": "diamond",
    "Pheno 3": "pentagon",
    "Pheno 4": "star",
    "Pheno 5": "triangle-up",
}
REP_OFF = [-0.22, 0.0, 0.22]

# All traits available in merged data (superset of WS2)
_ALL_TRAIT_LABELS = {**TRAIT_LABELS, **MERGED_TRAIT_LABELS}
_TRAIT_OPTS = [
    {"label": _ALL_TRAIT_LABELS.get(t, t), "value": t}
    for t in MERGED_TRAIT_COLS
    if t in _ALL_TRAIT_LABELS
]
_DEFAULT_TRAIT = "n_stolon_primary"


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Stats engine — batch edition ──────────────────────────────────────────────

_SYNTH_DATE = pd.Timestamp("2000-01-01")  # synthetic date so compute_stats_for can filter


def _batch_stats(
    df_merged: pd.DataFrame,
    trait: str,
    batch: str,
    alpha: float = 0.05,
) -> StatsResult | None:
    """Run KW + Conover–Iman + CLD on merged data for one Pheno batch."""
    if df_merged.empty or trait not in df_merged.columns:
        return None
    sub = df_merged[df_merged["pheno_batch"] == batch][["cultivar", trait]].dropna(subset=[trait]).copy()
    if sub.empty:
        return None
    sub["date"] = _SYNTH_DATE
    return compute_stats_for(sub, trait, _SYNTH_DATE, alpha=alpha)


def _all_batch_stats(
    df_merged: pd.DataFrame,
    alpha: float = 0.05,
) -> dict[tuple[str, str], StatsResult]:
    """Precompute KW stats for all (trait, batch) combinations."""
    out: dict[tuple[str, str], StatsResult] = {}
    for trait in MERGED_TRAIT_COLS:
        for batch in _BATCH_ORDER:
            r = _batch_stats(df_merged, trait, batch, alpha=alpha)
            if r is not None:
                out[(trait, batch)] = r
    return out


# ── Figure 1: cross-batch trajectory ──────────────────────────────────────────

def _timeline(df_merged: pd.DataFrame, trait: str, cvs: list[str]) -> go.Figure:
    """Cross-batch trajectory. Pheno batches are discrete measurement campaigns,
    so they sit on an evenly-spaced categorical axis (not a squished calendar).
    One line per cultivar = mean +/- SE across the batches where it was measured.
    """
    fig = go.Figure()
    if df_merged.empty or trait not in df_merged.columns:
        fig.add_annotation(text="No cross-batch data for this trait.",
                           x=0.5, y=0.5, xref="paper", yref="paper",
                           showarrow=False, font=dict(size=14, color="#888"))
    else:
        batches = [b for b in _BATCH_ORDER if b in df_merged["pheno_batch"].unique()]
        for cv in cvs:
            cvd = df_merged[df_merged["cultivar"] == cv]
            xs, ys, es, meta = [], [], [], []
            for b in batches:
                vals = cvd[cvd["pheno_batch"] == b][trait].dropna()
                if vals.empty:
                    continue
                n = len(vals)
                se = float(vals.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
                dcol = cvd[cvd["pheno_batch"] == b]["date"]
                when = dcol.iloc[0].strftime("%b %Y") if len(dcol) else ""
                xs.append(b); ys.append(float(vals.mean())); es.append(se)
                meta.append([round(se, 2), n, when])
            if not xs:
                continue
            color = CV_COLOR.get(cv, "#888")
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines+markers", name=cv,
                line=dict(color=color, width=2.2),
                marker=dict(size=8, color=color, line=dict(width=1, color="white")),
                error_y=dict(type="data", array=es, color=color, thickness=1.2, width=4),
                customdata=meta,
                hovertemplate=(f"<b>{cv}</b> &middot; %{{x}}<br>%{{customdata[2]}}<br>"
                               f"{_ALL_TRAIT_LABELS.get(trait, trait)}: "
                               "%{y:.2f} &plusmn; %{customdata[0]:.2f}<br>"
                               "n = %{customdata[1]}<extra></extra>"),
            ))
        fig.update_xaxes(type="category", categoryorder="array", categoryarray=batches)

    fig.update_layout(
        template="simple_white", height=470,
        margin=dict(l=72, r=178, t=28, b=52),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(title=dict(text="Phenotyping batch", font=dict(size=13)),
                   showgrid=False, ticks="outside", ticklen=5,
                   linecolor="#333", tickcolor="#333", tickfont=dict(size=12)),
        yaxis=dict(title=dict(text=_ALL_TRAIT_LABELS.get(trait, trait), font=dict(size=13)),
                   showgrid=True, gridcolor="#eef0f2", zeroline=False, rangemode="tozero",
                   ticks="outside", ticklen=5, linecolor="#333", tickcolor="#333",
                   tickfont=dict(size=12)),
        legend=dict(x=1.01, y=1, xanchor="left", yanchor="top", font=dict(size=11),
                    tracegroupgap=2, bordercolor="#e6e8ec", borderwidth=1),
        hovermode="closest",
        font=dict(family="IBM Plex Sans, Helvetica, Arial, sans-serif", size=12, color="#222"),
    )
    return fig


# ── Figure 2: batch dot-plot (identical style to Date Compare) ────────────────

def _dotplot(result: StatsResult | None, trait: str) -> go.Figure:
    if result is None:
        fig = go.Figure()
        fig.update_layout(
            height=300, plot_bgcolor="white", paper_bgcolor="white",
            annotations=[dict(
                text="No data for this batch / trait combination.",
                x=0.5, y=0.5, xref="paper", yref="paper",
                showarrow=False, font=dict(size=14, color="#888"),
            )],
        )
        return fig

    sorted_cvs = sorted(result.cultivars, key=lambda cv: result.means.get(cv, 0))
    n = len(sorted_cvs)
    fig = go.Figure()

    # Alternating row bands
    for rank in range(n):
        if rank % 2 == 1:
            fig.add_shape(
                type="rect", layer="below", x0=0, x1=1, xref="paper",
                y0=rank - 0.5, y1=rank + 0.5, yref="y",
                fillcolor="rgba(0,0,0,0.025)", line_width=0,
            )

    for rank, cv in enumerate(sorted_cvs):
        color  = CV_COLOR.get(cv, "#888")
        vals   = result.raw_values.get(cv, [])
        mean_v = result.means.get(cv, np.nan)
        se_v   = result.se.get(cv, 0.0)

        # SE bar
        fig.add_trace(go.Scatter(
            x=[mean_v - se_v, mean_v + se_v], y=[rank, rank],
            mode="lines", line=dict(color=color, width=3),
            showlegend=False, hoverinfo="skip",
        ))
        # Rep dots
        for k, v in enumerate(vals):
            off = REP_OFF[k] if k < len(REP_OFF) else 0.0
            fig.add_trace(go.Scatter(
                x=[v], y=[rank + off], mode="markers",
                marker=dict(size=9, color=color, opacity=0.7,
                            line=dict(width=1, color="white")),
                showlegend=False,
                hovertemplate=f"<b>{cv}</b> rep {k+1}: %{{x:.2f}}<extra></extra>",
            ))
        # Mean diamond
        fig.add_trace(go.Scatter(
            x=[mean_v], y=[rank], mode="markers",
            marker=dict(size=15, color=color, symbol="diamond",
                        line=dict(width=1.5, color="white")),
            showlegend=False,
            hovertemplate=f"<b>{cv}</b><br>Mean: %{{x:.2f}}<br>±SE: {se_v:.2f}<extra></extra>",
        ))

    # Best-group star
    if result.significant:
        for rank, cv in enumerate(sorted_cvs):
            if "a" in result.cld.get(cv, ""):
                fig.add_annotation(
                    x=1.02, y=rank, xref="paper", yref="y",
                    text="★", showarrow=False, xanchor="left",
                    font=dict(size=14, color="#E69F00"),
                )

    tick_labels = [f"{cv} · {result.cld.get(cv, '')}" for cv in sorted_cvs]

    fig.update_layout(
        height=max(300, n * 54 + 60),
        margin=dict(l=175, r=50, t=30, b=50),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(
            title=_ALL_TRAIT_LABELS.get(trait, trait),
            showgrid=True, gridcolor="#f0f0f0", zeroline=False,
        ),
        yaxis=dict(
            tickvals=list(range(n)), ticktext=tick_labels,
            showgrid=False, tickfont=dict(size=12),
        ),
        font=dict(family="IBM Plex Sans, Helvetica, Arial, sans-serif", size=12),
        hovermode="closest",
    )
    return fig


# ── Stats panel (identical to Date Compare) ───────────────────────────────────

def _stats_panel(result: StatsResult | None) -> html.Div:
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
                f"{result.epsilon2:.3f}", style={"color": color, "fontWeight": "700"},
            ))]),
            html.Tr([html.Td("Groups (k)"),  html.Td(str(len(result.cultivars)))]),
            html.Tr([html.Td("Total n"),     html.Td(str(sum(result.n_per_cv.values())))]),
            html.Tr([html.Td("Post-hoc"),    html.Td("Conover–Iman")]),
            html.Tr([html.Td("Correction"),  html.Td(result.correction.capitalize())]),
            html.Tr([html.Td("α"),           html.Td(str(result.alpha))]),
        ]),
        html.Div(className="cld-note", children=[
            html.P(
                f"Cultivars sharing a letter are not significantly different (α={result.alpha}).",
                className="cld-info",
            ),
            html.P("★ = best group (letter 'a').", className="cld-info"),
        ]),
        html.Div(
            "KW not significant — post-hoc shown for exploration only.",
            className="exploratory-notice",
            style={"display": "none" if sig else "block"},
        ),
    ])


# ── Pairwise table (identical to Date Compare) ────────────────────────────────

def _pairwise_table(result: StatsResult | None) -> html.Div:
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
                cells.append(html.Td("—", className="ph-cell ph-diag"))
            else:
                try:
                    p   = float(ph.loc[ci, cj])
                    sig = p < result.alpha
                    cells.append(html.Td(
                        f"{p:.3f}",
                        className=f"ph-cell {'ph-sig' if sig else ''}",
                    ))
                except Exception:
                    cells.append(html.Td("—", className="ph-cell"))
        rows.append(html.Tr(cells))
    return html.Div(className="pw-wrap", children=[
        html.P(
            f"Holm-adjusted Conover–Iman p-values. Highlighted = significant at α={result.alpha}.",
            className="card-subtitle",
        ),
        html.Table(className="pw-table", children=[html.Thead(header), html.Tbody(rows)]),
    ])


# ── Figure 3: ε² heatmap (batch × trait, same style as Season Summary) ────────

def _eps2_heatmap(batch_stats_cache: dict, df_merged: pd.DataFrame) -> go.Figure:
    if df_merged.empty:
        return go.Figure()

    batches = [b for b in _BATCH_ORDER if b in df_merged["pheno_batch"].unique()]
    traits  = [t for t in MERGED_TRAIT_COLS
               if any((t, b) in batch_stats_cache for b in batches)
               and t in _ALL_TRAIT_LABELS]

    if not batches or not traits:
        return go.Figure()

    z     = np.full((len(traits), len(batches)), np.nan)
    annot = [[""] * len(batches) for _ in traits]
    hover = [["No data"] * len(batches) for _ in traits]

    for ti, trait in enumerate(traits):
        for bi, batch in enumerate(batches):
            r = batch_stats_cache.get((trait, batch))
            if r is None:
                continue
            z[ti, bi]     = r.epsilon2
            lbl           = sig_label(r.kw_p)
            annot[ti][bi] = lbl if lbl != "ns" else ""
            hover[ti][bi] = (
                f"<b>{_ALL_TRAIT_LABELS.get(trait, trait)}</b><br>"
                f"{batch}<br>"
                f"ε² = {r.epsilon2:.3f}<br>"
                f"p = {r.kw_p:.4f} ({lbl})<br>"
                f"k = {len(r.cultivars)}, n = {sum(r.n_per_cv.values())}"
            )

    ylabels = [_ALL_TRAIT_LABELS.get(t, t) for t in traits]

    fig = go.Figure(go.Heatmap(
        z=z.tolist(), x=batches, y=ylabels,
        text=annot, texttemplate="%{text}", textfont=dict(size=11),
        colorscale=[
            [0,    "#f5faf6"], [0.1,  "#c8e6c9"],
            [0.35, "#66bb6a"], [0.65, "#2e7d32"],
            [1,    "#1b5e20"],
        ],
        zmin=0, zmax=0.8,
        colorbar=dict(
            title=dict(text="ε²", side="right"),
            thickness=14, len=0.6,
        ),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover, xgap=3, ygap=1,
    ))

    fig.update_layout(
        height=max(380, len(traits) * 28 + 90),
        margin=dict(l=250, r=90, t=40, b=60),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(title="Phenotyping Batch", side="bottom"),
        yaxis=dict(autorange="reversed"),
        font=dict(family="IBM Plex Sans, Helvetica, Arial, sans-serif", size=11),
    )
    return fig


# ── Layout ────────────────────────────────────────────────────────────────────

layout = html.Div([
    html.Div(className="page-header", children=[
        html.H1("Cross-Batch Longitudinal View", className="page-title"),
        html.P(
            "Cultivar trajectories across phenotyping batches 1–5 (2024–2026+). "
            "Same statistical engine as all other pages: "
            "KW · ε² · Conover–Iman · Holm · CLD. "
            "New cultivars Monterey & Fronteras appear as batch snapshots only.",
            className="page-subtitle",
        ),
    ]),

    html.Div(className="content-area", children=[

        # ── Filter card ──────────────────────────────────────────────────
        html.Div(className="card filter-card", children=[
            html.Div(className="filter-row", children=[
                html.Div([
                    html.Label("Trait", className="filter-label"),
                    dcc.Dropdown(
                        id="cb-trait",
                        options=_TRAIT_OPTS,
                        value=_DEFAULT_TRAIT,
                        clearable=False,
                        style={"width": "300px"},
                    ),
                ]),
                html.Div([
                    html.Label("Cultivars", className="filter-label"),
                    dcc.Dropdown(
                        id="cb-cvs",
                        options=[{"label": cv, "value": cv} for cv in _ALL_CVS],
                        value=_ALL_CVS,
                        multi=True,
                        style={"width": "460px"},
                    ),
                ]),
                html.Div([
                    html.Label("α level", className="filter-label"),
                    dcc.Dropdown(
                        id="cb-alpha",
                        options=[
                            {"label": "α = 0.05", "value": 0.05},
                            {"label": "α = 0.01", "value": 0.01},
                            {"label": "α = 0.10", "value": 0.10},
                        ],
                        value=0.05, clearable=False,
                        style={"width": "130px"},
                    ),
                ]),
            ]),
        ]),

        # ── Section 1: Extended timeline ─────────────────────────────────
        html.Div(className="card", children=[
            html.H3("Cross-Batch Trajectory (Pheno 1 → 5)", className="card-title"),
            html.P(
                "Each cultivar's mean ± SE across phenotyping batches. Batches are "
                "discrete measurement campaigns (2024–2026), shown evenly spaced — "
                "a line spanning a gap means that cultivar was not measured in the "
                "skipped batch. Per-batch cultivar statistics are below.",
                className="card-subtitle",
            ),
            dcc.Graph(id="cb-timeline", config=GRAPH_CONFIG),
        ]),

        # ── Section 2: Batch Compare (Date Compare style) ─────────────────
        html.Div(className="card filter-card", children=[
            html.Div(className="filter-row", children=[
                html.Div([
                    html.Label("Compare cultivars at batch", className="filter-label"),
                    dcc.Dropdown(
                        id="cb-batch",
                        options=[{"label": b, "value": b} for b in _BATCH_ORDER],
                        value="Pheno 4",
                        clearable=False,
                        style={"width": "180px"},
                    ),
                ]),
                html.Div(id="cb-batch-meta",
                         style={"fontSize": "12px", "color": "#666", "alignSelf": "center"}),
            ]),
        ]),

        html.Div(className="dc-row", children=[
            html.Div(className="dc-chart card", children=[
                html.H3("Cultivar Comparison by Batch", className="card-title"),
                html.P(
                    "Diamond = mean · Bar = ±SE · Dots = replicates · Letter = CLD group",
                    className="card-subtitle",
                ),
                dcc.Graph(id="cb-dotplot", config=GRAPH_CONFIG),
            ]),
            html.Div(className="dc-stats card", children=[
                html.H3("Statistics", className="card-title"),
                html.Div(id="cb-stats"),
            ]),
        ]),

        html.Div(className="card", children=[
            html.Details([
                html.Summary("Pairwise adjusted p-values (Holm–Conover–Iman)",
                             style={"cursor": "pointer", "fontWeight": "600"}),
                html.Div(id="cb-pairwise"),
            ]),
        ]),

        # ── Section 3: ε² heatmap ────────────────────────────────────────
        html.Div(className="card", children=[
            html.H3("Effect Size Heatmap (ε²) — Batch × Trait", className="card-title"),
            html.P(
                "Colour = ε² (cultivar differentiation strength per batch × trait). "
                "Annotations = significance stars (* p<0.05 · ** p<0.01 · *** p<0.001). "
                "KW, Conover–Iman post-hoc, Holm correction — same engine as Season Summary.",
                className="card-subtitle",
            ),
            dcc.Graph(id="cb-heatmap", config=GRAPH_CONFIG),
        ]),

    ]),
])


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("cb-timeline", "figure"),
    Output("cb-dotplot",  "figure"),
    Output("cb-stats",    "children"),
    Output("cb-pairwise", "children"),
    Output("cb-heatmap",  "figure"),
    Output("cb-batch-meta", "children"),
    Input("cb-trait",  "value"),
    Input("cb-cvs",    "value"),
    Input("cb-alpha",  "value"),
    Input("cb-batch",  "value"),
)
def update(trait, cvs, alpha, batch):
    trait  = trait  or _DEFAULT_TRAIT
    cvs    = cvs    or _ALL_CVS
    alpha  = alpha  or 0.05
    batch  = batch  or "Pheno 4"

    df_merged = cache.merged_df

    # Precompute all batch × trait stats (used by the ε² heatmap)
    bstats = _all_batch_stats(df_merged, alpha=alpha)

    # Cross-batch trajectory
    fig_tl = _timeline(df_merged, trait, cvs)

    # Batch compare
    result = _batch_stats(df_merged, trait, batch, alpha=alpha)
    fig_dp = _dotplot(result, trait)
    panel  = _stats_panel(result)
    pw     = _pairwise_table(result)

    # Batch meta
    if result:
        b_date = df_merged[df_merged["pheno_batch"] == batch]["date"].iloc[0] if not df_merged.empty else None
        date_str = b_date.strftime("%d %b %Y") if b_date is not None else "—"
        meta = f"{batch} · {date_str} · {len(result.cultivars)} cultivars · n = {sum(result.n_per_cv.values())} obs"
    else:
        meta = f"{batch} — no data for this trait"

    # ε² heatmap
    fig_hm = _eps2_heatmap(bstats, df_merged)

    return fig_tl, fig_dp, panel, pw, fig_hm, meta
