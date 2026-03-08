"""
viz/prototype.py
================
Build Plotly visualization prototypes from pheno4_aggregated.csv.

Viz A — Multi-cultivar time-series line chart (all cultivars, one trait)
Viz B — Small multiples facet grid (per cultivar, Level-1 stolon traits)

Run from the veryberrylab/ directory:
    python viz/prototype.py

Outputs (self-contained HTML files, no server required):
    viz/chart_A.html  — Viz A
    viz/chart_B.html  — Viz B
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT    = Path(__file__).resolve().parent.parent
AGG_CSV = ROOT / "data" / "processed" / "pheno4_aggregated.csv"
VIZ_DIR = ROOT / "viz"

# ---------------------------------------------------------------------------
# Colorblind-safe 11-color palette (Okabe-Ito + extras)
# ---------------------------------------------------------------------------
PALETTE = [
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#009E73",  # bluish green
    "#F0E442",  # yellow
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
    "#000000",  # black
    "#AA4499",  # purple
    "#44BB99",  # mint
    "#BBCC33",  # lime
]

# Trait display labels
TRAIT_LABELS = {
    "n_stolon_primary":       "Primary Stolons",
    "n_stolon_secondary":     "Secondary Stolons",
    "n_stolon_tertiary":      "Tertiary Stolons",
    "n_stolon_quaternary":    "Quaternary Stolons",
    "n_dp_alt_primary":       "Daughter Plants (Alt) on Primary",
    "n_dp_alt_secondary":     "Daughter Plants (Alt) on Secondary",
    "n_dp_alt_tertiary":      "Daughter Plants (Alt) on Tertiary",
    "n_dp_alt_quaternary":    "Daughter Plants (Alt) on Quaternary",
    "n_dp_mid_primary":       "Daughter Plants (Mid) on Primary",
    "n_dp_mid_secondary":     "Daughter Plants (Mid) on Secondary",
    "n_dp_total_alt":         "Total Daughter Plants (Alternate Nodes)",
    "n_dp_total_mid":         "Total Daughter Plants (Mid Nodes)",
    "n_flowers_total":        "Total Flowers",
    "n_flowers_mp":           "Flowers on Mother Plant",
    "n_flowers_dp":           "Flowers on Daughter Plants",
    "stolon_length_primary_cm": "Primary Stolon Length (cm)",
    "crown_diameter_mm":       "Crown Diameter (mm)",
}

# Stolon line styles for Viz B
STOLON_STYLES = {
    "n_stolon_primary":    ("solid",   "#0072B2"),
    "n_stolon_secondary":  ("dash",    "#D55E00"),
    "n_stolon_tertiary":   ("dot",     "#009E73"),
    "n_stolon_quaternary": ("dashdot", "#CC79A7"),
}


# ---------------------------------------------------------------------------
# Viz A — Multi-cultivar time-series (interactive, with dropdowns)
# ---------------------------------------------------------------------------

def make_viz_a(df: pd.DataFrame, out_path: Path) -> None:
    """
    One chart per trait, all cultivars as lines.  A dropdown lets users switch
    between traits.  Only the active trait's traces are visible.
    """
    cultivars = sorted(df["cultivar"].unique())
    color_map = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(cultivars)}

    # Determine which trait columns are available
    all_traits = [t for t in TRAIT_LABELS if f"{t}_mean" in df.columns]

    fig = go.Figure()

    # Build one set of traces per trait (hidden by default except first)
    for t_idx, trait in enumerate(all_traits):
        mean_col = f"{trait}_mean"
        se_col   = f"{trait}_se"
        visible  = (t_idx == 0)  # only first trait shown by default

        for c_idx, cultivar in enumerate(cultivars):
            sub = df[df["cultivar"] == cultivar].sort_values("date")
            if mean_col not in sub.columns:
                continue

            means = sub[mean_col].tolist()
            ses   = sub[se_col].tolist() if se_col in sub.columns else [None] * len(means)
            dates = sub["date"].tolist()

            # SE shading band (upper + lower merged into one filled trace)
            upper = [m + s if (m == m and s == s) else None for m, s in zip(means, ses)]
            lower = [m - s if (m == m and s == s) else None for m, s in zip(means, ses)]

            # Shaded SE band
            fig.add_trace(go.Scatter(
                x=dates + dates[::-1],
                y=upper + lower[::-1],
                fill="toself",
                fillcolor=color_map[cultivar],
                opacity=0.15,
                line=dict(width=0),
                showlegend=False,
                hoverinfo="skip",
                visible=visible,
                name=f"{cultivar}_{trait}_band",
            ))

            # Mean line
            fig.add_trace(go.Scatter(
                x=dates,
                y=means,
                mode="lines+markers",
                name=cultivar,
                line=dict(color=color_map[cultivar], width=2),
                marker=dict(size=7),
                legendgroup=cultivar,
                showlegend=(t_idx == 0),
                visible=visible,
                customdata=list(zip(ses, sub.get(f"{trait}_n", [None]*len(means)))),
                hovertemplate=(
                    "<b>%{x|%b %d, %Y}</b><br>"
                    f"<b>{cultivar}</b><br>"
                    "Mean: %{y:.2f}<br>"
                    "SE: ±%{customdata[0]:.2f}<br>"
                    "n = %{customdata[1]}<extra></extra>"
                ),
            ))

    # ---- Dropdown buttons to switch between traits ----
    # Each button sets visibility for its 2 traces per cultivar (band + line)
    # per-trait block size = 2 traces × n_cultivars
    traces_per_trait = 2 * len(cultivars)
    total_traces = len(all_traits) * traces_per_trait

    buttons = []
    for t_idx, trait in enumerate(all_traits):
        vis = [False] * total_traces
        start = t_idx * traces_per_trait
        for j in range(traces_per_trait):
            vis[start + j] = True

        buttons.append(dict(
            label=TRAIT_LABELS.get(trait, trait),
            method="update",
            args=[
                {"visible": vis},
                {"yaxis.title.text": f"Mean {TRAIT_LABELS.get(trait, trait)} per Plant"},
            ],
        ))

    fig.update_layout(
        title=dict(
            text="Strawberry Cultivar Phenotyping 4 — Stolon & Daughter Dynamics",
            font=dict(size=18),
        ),
        xaxis=dict(
            title="Measurement Date",
            tickformat="%b %d",
            tickmode="array",
            tickvals=sorted(df["date"].unique()),
        ),
        yaxis=dict(title=f"Mean {TRAIT_LABELS.get(all_traits[0], all_traits[0])} per Plant"),
        legend=dict(
            title="Cultivar",
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="#cccccc",
            borderwidth=1,
        ),
        updatemenus=[dict(
            buttons=buttons,
            direction="down",
            pad={"r": 10, "t": 10},
            showactive=True,
            x=0.01,
            xanchor="left",
            y=1.12,
            yanchor="top",
            bgcolor="#f5f5f5",
            bordercolor="#cccccc",
        )],
        annotations=[dict(
            text="Trait:",
            showarrow=False,
            x=0.01, xref="paper",
            y=1.15, yref="paper",
            align="left",
            font=dict(size=13),
        )],
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="closest",
        height=600,
        margin=dict(t=120, b=60, l=70, r=30),
    )

    fig.write_html(str(out_path), include_plotlyjs="cdn", full_html=True)
    print(f"Saved → {out_path}")


# ---------------------------------------------------------------------------
# Viz B — Small multiples (one panel per cultivar, Level-1 stolon traits)
# ---------------------------------------------------------------------------

def make_viz_b(df: pd.DataFrame, out_path: Path) -> None:
    """
    3×4 grid (last panel empty): one panel per cultivar, lines for each stolon order.
    """
    cultivars = sorted(df["cultivar"].unique())
    n         = len(cultivars)
    ncols     = 4
    nrows     = -(-n // ncols)  # ceiling division

    fig = make_subplots(
        rows=nrows, cols=ncols,
        subplot_titles=cultivars + [""] * (nrows * ncols - n),
        shared_xaxes=True,
        shared_yaxes=False,
        vertical_spacing=0.10,
        horizontal_spacing=0.06,
    )

    stolon_traits = [t for t in STOLON_STYLES if f"{t}_mean" in df.columns]

    for i, cultivar in enumerate(cultivars):
        row = i // ncols + 1
        col = i % ncols  + 1
        sub = df[df["cultivar"] == cultivar].sort_values("date")

        for trait in stolon_traits:
            mean_col = f"{trait}_mean"
            se_col   = f"{trait}_se"
            if mean_col not in sub.columns:
                continue

            dash, color = STOLON_STYLES[trait]
            label = TRAIT_LABELS.get(trait, trait)
            show_legend = (i == 0)

            fig.add_trace(
                go.Scatter(
                    x=sub["date"],
                    y=sub[mean_col],
                    mode="lines+markers",
                    name=label,
                    legendgroup=trait,
                    showlegend=show_legend,
                    line=dict(dash=dash, color=color, width=2),
                    marker=dict(size=5, color=color),
                    hovertemplate=(
                        "<b>%{x|%b %d}</b><br>"
                        f"{label}: %{{y:.1f}}<extra>{cultivar}</extra>"
                    ),
                ),
                row=row, col=col,
            )

    fig.update_layout(
        title=dict(
            text="Stolon Counts per Cultivar — Phenotyping 4",
            font=dict(size=16),
        ),
        height=200 * nrows + 100,
        showlegend=True,
        legend=dict(
            title="Stolon Order",
            orientation="h",
            yanchor="bottom",
            y=-0.12,
            xanchor="center",
            x=0.5,
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )

    # Format x-axes on bottom row
    for col in range(1, ncols + 1):
        fig.update_xaxes(tickformat="%b %d", row=nrows, col=col)

    fig.write_html(str(out_path), include_plotlyjs="cdn", full_html=True)
    print(f"Saved → {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not AGG_CSV.exists():
        print(f"ERROR: {AGG_CSV} not found. Run src/etl.py and src/aggregate.py first.")
        raise SystemExit(1)

    print(f"Loading: {AGG_CSV}")
    df = pd.read_csv(str(AGG_CSV), parse_dates=["date"])
    print(f"  {df.shape[0]} rows, {df.shape[1]} columns")
    print(f"  Cultivars: {sorted(df['cultivar'].unique())}")

    make_viz_a(df, VIZ_DIR / "chart_A.html")
    make_viz_b(df, VIZ_DIR / "chart_B.html")

    print("\nDone. Open viz/chart_A.html and viz/chart_B.html in a browser.")
