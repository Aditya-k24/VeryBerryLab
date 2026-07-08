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


# ── Figure 1: extended timeline ───────────────────────────────────────────────

def _timeline(
    df_ws2: pd.DataFrame,
    df_merged: pd.DataFrame,
    trait: str,
    cvs: list[str],
    show_ws2: bool,
    show_merged: bool,
    batch_stats_cache: dict,
) -> go.Figure:

    fig = go.Figure()

    # WS2 season shaded band
    if not df_ws2.empty and trait in df_ws2.columns:
        ws2_dates = sorted(df_ws2["date"].unique())
        if len(ws2_dates) >= 2:
            fig.add_vrect(
                x0=ws2_dates[0], x1=ws2_dates[-1],
                fillcolor="rgba(126,200,164,0.08)",
                layer="below", line_width=0,
            )
            fig.add_annotation(
                x=ws2_dates[0] + (ws2_dates[-1] - ws2_dates[0]) / 2,
                y=1.05, yref="paper",
                text="◀ Pheno 4 season — WS2 detail ▶",
                showarrow=False, font=dict(size=10, color="#4a9e7c"),
                xanchor="center",
            )

    # Batch date verticals
    if not df_merged.empty:
        bdf = (
            df_merged.groupby("pheno_batch")["date"]
            .first().reset_index().sort_values("date")
        )
        for _, row in bdf.iterrows():
            if row["pheno_batch"] == "Pheno 4":
                continue
            fig.add_vline(
                x=row["date"].timestamp() * 1000,
                line_dash="dot", line_color="#cccccc", line_width=1.2,
            )
            fig.add_annotation(
                x=row["date"], y=1.05, yref="paper",
                text=row["pheno_batch"], showarrow=False,
                font=dict(size=9, color="#999"), xanchor="center",
            )

    added: set[str] = set()

    for cv in cvs:
        color = CV_COLOR.get(cv, "#888")

        # WS2 lines + SE ribbon
        if show_ws2 and not df_ws2.empty and trait in df_ws2.columns:
            cv_ws2 = df_ws2[df_ws2["cultivar"] == cv][["date", trait]].dropna(subset=[trait])
            if not cv_ws2.empty:
                agg = (
                    cv_ws2.groupby("date")[trait]
                    .agg(
                        mean="mean",
                        se=lambda x: x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0,
                    )
                    .reset_index().sort_values("date")
                )
                xs = agg["date"].tolist()
                ys = agg["mean"].tolist()
                yu = (agg["mean"] + agg["se"]).tolist()
                yd = (agg["mean"] - agg["se"]).tolist()

                fig.add_trace(go.Scatter(
                    x=xs + xs[::-1], y=yu + yd[::-1],
                    fill="toself", fillcolor=_hex_rgba(color, 0.12),
                    line_color="rgba(0,0,0,0)", showlegend=False,
                    hoverinfo="skip", legendgroup=cv,
                ))
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="lines+markers",
                    name=cv, legendgroup=cv, showlegend=(cv not in added),
                    line=dict(color=color, width=2),
                    marker=dict(size=6, color=color, line=dict(width=1, color="white")),
                    hovertemplate=(
                        f"<b>{cv}</b> · WS2<br>%{{x|%d %b %Y}}<br>"
                        f"{_ALL_TRAIT_LABELS.get(trait, trait)}: %{{y:.2f}}<extra></extra>"
                    ),
                ))
                added.add(cv)

        # Merged batch markers with ±1 SE + CLD letter
        if show_merged and not df_merged.empty and trait in df_merged.columns:
            cv_m = df_merged[df_merged["cultivar"] == cv]
            for batch in _BATCH_ORDER:
                bsub = cv_m[cv_m["pheno_batch"] == batch][trait].dropna()
                if bsub.empty:
                    continue
                bdate  = cv_m[cv_m["pheno_batch"] == batch]["date"].iloc[0]
                mean_v = bsub.mean()
                se_v   = bsub.std(ddof=1) / np.sqrt(len(bsub)) if len(bsub) > 1 else 0.0
                n_reps = len(bsub)

                # CLD letter for this cultivar at this batch
                sr = batch_stats_cache.get((trait, batch))
                cld_letter = sr.cld.get(cv, "") if sr else ""
                sig_txt    = f" · {sig_label(sr.kw_p)}" if sr else ""

                fig.add_trace(go.Scatter(
                    x=[bdate], y=[mean_v], mode="markers+text",
                    name=cv, legendgroup=cv, showlegend=(cv not in added),
                    marker=dict(
                        symbol=_BATCH_SYMBOL.get(batch, "circle"),
                        size=12, color="white",
                        line=dict(width=2.5, color=color),
                    ),
                    error_y=dict(
                        type="data", array=[se_v],
                        color=color, thickness=1.8, width=5,
                    ),
                    text=[cld_letter],
                    textposition="top center",
                    textfont=dict(size=9, color=color),
                    customdata=[[batch, n_reps, cld_letter, sig_txt]],
                    hovertemplate=(
                        f"<b>{cv}</b> · %{{customdata[0]}}<br>"
                        "%{x|%d %b %Y}<br>"
                        f"{_ALL_TRAIT_LABELS.get(trait, trait)}: %{{y:.2f}} ± SE<br>"
                        "n = %{customdata[1]}<br>"
                        "CLD = %{customdata[2]}%{customdata[3]}"
                        "<extra></extra>"
                    ),
                ))
                added.add(cv)

    # Symbol legend annotation
    sym_lines = [
        "── WS2 line (mean ± SE ribbon)",
        "◇  Pheno 1", "◆  Pheno 2", "⬠  Pheno 3", "★  Pheno 4", "▲  Pheno 5",
        "Letter = CLD group (shared = not sig. different)",
    ]
    fig.add_annotation(
        x=1.0, y=0.0, xref="paper", yref="paper",
        xanchor="right", yanchor="bottom",
        text="<br>".join(f"<span style='color:#888;font-size:9px'>{l}</span>" for l in sym_lines),
        showarrow=False, align="right",
        bgcolor="rgba(255,255,255,0.88)",
        bordercolor="#e8e8e8", borderwidth=1, borderpad=6,
    )

    fig.update_layout(
        height=500,
        margin=dict(l=60, r=230, t=55, b=55),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(
            title="Date", tickformat="%b %Y",
            showgrid=True, gridcolor="#f0f0f0", zeroline=False,
        ),
        yaxis=dict(
            title=_ALL_TRAIT_LABELS.get(trait, trait),
            showgrid=True, gridcolor="#f0f0f0", rangemode="tozero",
        ),
        legend=dict(x=1.01, y=1, xanchor="left", font=dict(size=11), tracegroupgap=2),
        hovermode="closest",
        font=dict(family="IBM Plex Sans, Helvetica, Arial, sans-serif", size=12),
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
            "Pheno batches 1–5 (2024–2026+) on one time axis. "
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
                    html.Label("Layers", className="filter-label"),
                    dcc.Checklist(
                        id="cb-layers",
                        options=[
                            {"label": "  WS2 season detail", "value": "ws2"},
                            {"label": "  Batch snapshots",   "value": "merged"},
                        ],
                        value=["ws2", "merged"],
                        inline=True,
                        inputStyle={"marginLeft": "10px"},
                        style={"fontSize": "13px"},
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
            html.H3("Extended Time Axis — 2024 → 2026+", className="card-title"),
            html.P(
                "Green band = Pheno 4 growing season (WS2 detail, mean ± SE ribbon). "
                "Hollow symbols = batch snapshot (mean ± 1 SE). "
                "Letter above marker = CLD group for that batch comparison.",
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
    Input("cb-layers", "value"),
    Input("cb-alpha",  "value"),
    Input("cb-batch",  "value"),
)
def update(trait, cvs, layers, alpha, batch):
    trait  = trait  or _DEFAULT_TRAIT
    cvs    = cvs    or _ALL_CVS
    layers = layers or []
    alpha  = alpha  or 0.05
    batch  = batch  or "Pheno 4"

    df_ws2    = cache.df_clean
    df_merged = cache.merged_df

    show_ws2    = "ws2"    in layers
    show_merged = "merged" in layers

    # Precompute all batch × trait stats (used by both heatmap and timeline CLD annotations)
    bstats = _all_batch_stats(df_merged, alpha=alpha)

    # Timeline
    fig_tl = _timeline(df_ws2, df_merged, trait, cvs, show_ws2, show_merged, bstats)

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
